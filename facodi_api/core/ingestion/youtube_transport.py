"""Standalone bounded YouTube transport; executed in a disposable child process."""
import json
import sys
import time
import requests

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
        kwargs["allow_redirects"] = False
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



def fetch_transcript(video_id, language):
    from youtube_transcript_api import YouTubeTranscriptApi
    with BoundedTranscriptSession() as session:
        available = YouTubeTranscriptApi(http_client=session).list(video_id)
        transcript = available.find_transcript([language, 'en', 'es'])
        segments, size = [], 0
        for item in transcript.fetch():
            get = item.get if isinstance(item, dict) else lambda key, default=None: getattr(item, key, default)
            text = str(get('text', '')).strip()
            size += len(text.encode('utf-8'))
            if len(segments) >= 10000 or size > 262144:
                raise YouTubeAcquisitionError('YOUTUBE_TRANSCRIPT_TOO_LARGE')
            segments.append({'start': float(get('start', 0)), 'duration': float(get('duration', 0)), 'text': text})
        return {'language': transcript.language_code, 'is_generated': transcript.is_generated, 'segments': segments}


def error_code(exc):
    if isinstance(exc, YouTubeAcquisitionError):
        return exc.code
    if isinstance(exc, requests.Timeout):
        return 'YOUTUBE_TIMEOUT'
    return {
        'IpBlocked': 'YOUTUBE_IP_BLOCKED', 'RequestBlocked': 'YOUTUBE_IP_BLOCKED',
        'TranscriptsDisabled': 'YOUTUBE_TRANSCRIPTS_DISABLED',
        'NoTranscriptFound': 'YOUTUBE_LANGUAGE_UNAVAILABLE',
        'VideoUnavailable': 'YOUTUBE_VIDEO_UNAVAILABLE',
    }.get(type(exc).__name__, 'YOUTUBE_UNAVAILABLE')


if __name__ == '__main__':
    try:
        payload = json.load(sys.stdin)
        result = fetch_transcript(payload['video_id'], payload['language'])
    except Exception as exc:
        result = {'error': error_code(exc)}
    print(json.dumps(result, ensure_ascii=False))
