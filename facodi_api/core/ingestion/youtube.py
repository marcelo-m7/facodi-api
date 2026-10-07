"""Acquire real transcript timing; never invent timing for manual text."""
from __future__ import annotations
import re
import urllib.parse
import uuid
from ..contracts.dtos import ContentDocument, SourceType, TranscriptSegment, utc_now_iso

class YouTubeIngestionAdapter:
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
        segments, warnings = [], []
        language = source.language or 'pt'
        duration = None
        metadata = dict(source.metadata)
        if source.raw_content and (metadata.get('is_manual_transcript') or not video_id):
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
            try:
                from youtube_transcript_api import YouTubeTranscriptApi
                available = YouTubeTranscriptApi().list(video_id)
                transcript = available.find_transcript([language, 'en', 'es'])
                language = transcript.language_code
                metadata['is_generated'] = transcript.is_generated
                for item in transcript.fetch():
                    get = item.get if isinstance(item, dict) else lambda key, default=None: getattr(item, key, default)
                    segments.append(TranscriptSegment(float(get('start', 0)), float(get('duration', 0)), str(get('text', '')).strip()))
            except Exception as exc:
                raise ValueError('YouTube transcript unavailable') from exc
            if not segments or not any(segment.text for segment in segments):
                raise ValueError('YouTube transcript unavailable')
            text = ' '.join(segment.text for segment in segments)
            duration = max(segment.start + segment.duration for segment in segments)
            metadata['timing_provenance'] = 'provider'
        if not text:
            raise ValueError('Empty transcript')
        title = source.title or f'Vídeo {video_id or "YouTube"}'
        markdown = f'# {title}\n\n' + text
        return ContentDocument(id=str(uuid.uuid4()), source_type=SourceType.YOUTUBE,
            title=title, text_content=text, markdown_content=markdown, language=language,
            source_url=source.url, duration_seconds=duration, segments=segments,
            metadata={**metadata, 'video_id': video_id, 'segments_count': len(segments)},
            warnings=warnings, input_hash=source.compute_hash(), acquired_at=utc_now_iso())
