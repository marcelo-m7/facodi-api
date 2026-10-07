"""Acquire real transcript timing; never invent timing for manual text."""
from __future__ import annotations
import re
import urllib.parse
import uuid
from ..contracts.dtos import ContentDocument, SourceType, TranscriptSegment, utc_now_iso

from pathlib import Path
import json
import subprocess
import sys
from .youtube_transport import YouTubeAcquisitionError

_WORKER_SCRIPT = Path(__file__).with_name('youtube_transport.py')


def acquire_transcript(video_id, language, *, budget_seconds=45):
    """OS-enforced deadline: terminate the child even on redirect/trickle stalls."""
    try:
        result = subprocess.run(
            [sys.executable, str(_WORKER_SCRIPT)],
            input=json.dumps({'video_id': video_id, 'language': language}),
            capture_output=True, text=True, timeout=budget_seconds, check=False,
        )
    except subprocess.TimeoutExpired:
        raise YouTubeAcquisitionError('YOUTUBE_TIMEOUT') from None
    except OSError:
        raise YouTubeAcquisitionError('YOUTUBE_TRANSPORT_UNAVAILABLE') from None
    if result.returncode or len(result.stdout.encode('utf-8')) > 2 * 1024 * 1024:
        raise YouTubeAcquisitionError()
    try:
        payload = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise YouTubeAcquisitionError() from None
    if payload.get('error'):
        raise YouTubeAcquisitionError(payload['error'])
    return payload


class YouTubeIngestionAdapter:
    MAX_SEGMENTS = 10000
    MAX_TRANSCRIPT_BYTES = 262144

    @classmethod
    def extract_video_id(cls, url):
        try:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
                return None
            host = parsed.hostname
            if host in ('youtu.be', 'www.youtu.be'):
                candidate = parsed.path.strip('/')
            elif host in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
                if parsed.path == '/watch':
                    candidate = urllib.parse.parse_qs(parsed.query).get('v', [''])[0]
                elif parsed.path.startswith(('/embed/', '/shorts/')):
                    candidate = parsed.path.split('/')[-1]
                else:
                    return None
            else:
                return None
            return candidate if re.fullmatch(r'[A-Za-z0-9_-]{11}', candidate) else None
        except (ValueError, TypeError):
            return None

    def ingest(self, source):
        video_id = self.extract_video_id(source.url or '')
        if not video_id:
            raise ValueError('Invalid YouTube URL')
        segments, warnings = [], []
        language = source.language or 'pt'
        duration = None
        metadata = dict(source.metadata)
        if source.raw_content and metadata.get('is_manual_transcript'):
            text = source.raw_content.strip()
            timed = []
            for line in text.splitlines():
                match = re.fullmatch(r'\[?(\d{1,2}):(\d{2})\]?\s+(.+)', line.strip())
                if match and int(match[2]) < 60:
                    timed.append((int(match[1]) * 60 + int(match[2]), match[3]))
                elif line.strip():
                    timed = []
                    break
            for index, (start, value) in enumerate(timed):
                next_start = timed[index+1][0] if index+1 < len(timed) else start
                segments.append(TranscriptSegment(float(start), float(next_start-start), value))
            warnings.append('Manual transcript; video duration is unknown.')
            metadata['timing_provenance'] = 'manual_markers' if timed else 'unavailable'
        else:
            if not video_id:
                raise ValueError('Invalid YouTube URL')
            payload = acquire_transcript(video_id, language)
            language = payload['language']
            metadata['is_generated'] = payload['is_generated']
            for item in payload['segments']:
                segments.append(TranscriptSegment(item['start'], item['duration'], item['text']))
            if not segments or not any(segment.text for segment in segments):
                raise YouTubeAcquisitionError()
            text = ' '.join(segment.text for segment in segments)
            duration = max(segment.start + segment.duration for segment in segments)
            metadata['timing_provenance'] = 'provider'
        if len(text.encode('utf-8')) > self.MAX_TRANSCRIPT_BYTES or len(segments) > self.MAX_SEGMENTS:
            raise YouTubeAcquisitionError('YOUTUBE_TRANSCRIPT_TOO_LARGE')
        if not text:
            raise ValueError('Empty transcript')
        title = source.title or f'Vídeo {video_id or "YouTube"}'
        markdown = f'# {title}\n\n' + text
        return ContentDocument(id=str(uuid.uuid4()), source_type=SourceType.YOUTUBE,
            title=title, text_content=text, markdown_content=markdown, language=language,
            source_url=source.url, duration_seconds=duration, segments=segments,
            metadata={**metadata, 'video_id': video_id, 'segments_count': len(segments)},
            warnings=warnings, input_hash=source.compute_hash(), acquired_at=utc_now_iso())
