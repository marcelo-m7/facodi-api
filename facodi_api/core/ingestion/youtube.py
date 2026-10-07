"""Acquire real transcript timing; never invent timing for manual text."""
from __future__ import annotations
import re
import urllib.parse
import uuid
import time
import requests
from ..contracts.dtos import ContentDocument, SourceType, TranscriptSegment, utc_now_iso

class YouTubeAcquisitionError(ValueError):
    def __init__(self, code="YOUTUBE_UNAVAILABLE"):
        self.code = code
        super().__init__(code)


class BoundedTranscriptSession(requests.Session):
    """No retries; bound each request and the adapter's overall acquisition budget."""
    def __init__(self, budget_seconds=45):
        super().__init__()
        self.deadline = time.monotonic() + budget_seconds

    def request(self, method, url, **kwargs):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise YouTubeAcquisitionError("YOUTUBE_TIMEOUT")
        kwargs["timeout"] = (min(5, remaining), min(10, remaining))
        kwargs["stream"] = True
        response = super().request(method, url, **kwargs)
        content = bytearray()
        try:
            for chunk in response.iter_content(65536):
                if time.monotonic() > self.deadline:
                    raise YouTubeAcquisitionError("YOUTUBE_TIMEOUT")
                content.extend(chunk)
                if len(content) > 4 * 1024 * 1024:
                    raise YouTubeAcquisitionError("YOUTUBE_RESPONSE_TOO_LARGE")
            response._content = bytes(content)
            response._content_consumed = True
        except Exception:
            response.close()
            raise
        if time.monotonic() > self.deadline:
            response.close()
            raise YouTubeAcquisitionError("YOUTUBE_TIMEOUT")
        return response


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
            try:
                from youtube_transcript_api import YouTubeTranscriptApi
                with BoundedTranscriptSession() as session:
                    available = YouTubeTranscriptApi(http_client=session).list(video_id)
                    transcript = available.find_transcript([language, 'en', 'es'])
                    language = transcript.language_code
                    metadata['is_generated'] = transcript.is_generated
                    size = 0
                    for item in transcript.fetch():
                        get = item.get if isinstance(item, dict) else lambda key, default=None: getattr(item, key, default)
                        value = str(get('text', '')).strip()
                        size += len(value.encode('utf-8'))
                        if len(segments) >= self.MAX_SEGMENTS or size > self.MAX_TRANSCRIPT_BYTES:
                            raise YouTubeAcquisitionError("YOUTUBE_TRANSCRIPT_TOO_LARGE")
                        segments.append(TranscriptSegment(float(get('start', 0)), float(get('duration', 0)), value))
            except YouTubeAcquisitionError:
                raise
            except requests.Timeout:
                raise YouTubeAcquisitionError("YOUTUBE_TIMEOUT") from None
            except Exception as exc:
                code = {
                    "IpBlocked": "YOUTUBE_IP_BLOCKED", "RequestBlocked": "YOUTUBE_IP_BLOCKED",
                    "TranscriptsDisabled": "YOUTUBE_TRANSCRIPTS_DISABLED",
                    "NoTranscriptFound": "YOUTUBE_LANGUAGE_UNAVAILABLE",
                    "VideoUnavailable": "YOUTUBE_VIDEO_UNAVAILABLE",
                }.get(type(exc).__name__, "YOUTUBE_UNAVAILABLE")
                raise YouTubeAcquisitionError(code) from None
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
