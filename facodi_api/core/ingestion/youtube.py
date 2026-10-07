"""YouTube ingestion adapter with timestamped transcript and metadata preservation."""

from __future__ import annotations

import re
import urllib.parse
import uuid
from typing import Any, Dict, List, Optional

from ..contracts.dtos import (
    ContentDocument,
    ContentSource,
    SourceType,
    TranscriptSegment,
    utc_now_iso,
)


class YouTubeIngestionAdapter:
    """Ingests YouTube video transcript and builds timestamped ContentDocument."""

    YOUTUBE_URL_PATTERNS = [
        re.compile(r"(?:https?:\/\/)?(?:www\.)?youtube\.com\/watch\?v=([a-zA-Z0-9_-]{11})"),
        re.compile(r"(?:https?:\/\/)?(?:www\.)?youtu\.be\/([a-zA-Z0-9_-]{11})"),
        re.compile(r"(?:https?:\/\/)?(?:www\.)?youtube\.com\/embed\/([a-zA-Z0-9_-]{11})"),
    ]

    @classmethod
    def extract_video_id(cls, url: str) -> Optional[str]:
        """Extract 11-char video id from diverse YouTube URL formats."""
        if not url:
            return None
        for pattern in cls.YOUTUBE_URL_PATTERNS:
            match = pattern.search(url)
            if match:
                return match.group(1)
        parsed = urllib.parse.urlparse(url)
        if "youtube.com" in parsed.netloc:
            query = urllib.parse.parse_qs(parsed.query)
            if "v" in query and query["v"]:
                return query["v"][0]
        return None

    def ingest(self, source: ContentSource) -> ContentDocument:
        """Fetch transcript and produce ContentDocument."""
        doc_id = str(uuid.uuid4())
        warnings: List[str] = []
        video_id = self.extract_video_id(source.url or "")
        title = source.title or f"Vídeo {video_id or 'YouTube'}"

        segments: List[TranscriptSegment] = []
        duration_seconds = 0.0

        # Check if manual transcript was provided in source metadata or raw_content
        if source.raw_content and (source.metadata.get("is_manual_transcript") or not video_id):
            # Parse lines of manual transcript: e.g. [00:12] text or just plain text
            lines = source.raw_content.splitlines()
            current_time = 0.0
            for line in lines:
                line_str = line.strip()
                if not line_str:
                    continue
                # Time regex: [00:15] or 00:15
                time_match = re.match(r"^\[?(\d{1,2}):(\d{2})\]?\s*(.*)$", line_str)
                if time_match:
                    mins = int(time_match.group(1))
                    secs = int(time_match.group(2))
                    current_time = float(mins * 60 + secs)
                    text = time_match.group(3)
                else:
                    text = line_str
                segments.append(TranscriptSegment(start=current_time, duration=4.0, text=text))
                current_time += 4.0
            duration_seconds = current_time
            warnings.append("Used manual transcript supplied directly in source.")
        elif video_id:
            try:
                from youtube_transcript_api import YouTubeTranscriptApi
                from youtube_transcript_api._errors import (
                    NoTranscriptFound,
                    TranscriptsDisabled,
                    VideoUnavailable,
                )

                languages = [source.language or "pt", "en", "es"]
                try:
                    # Preferred: specific languages
                    api = YouTubeTranscriptApi()
                    transcript_list = api.list(video_id)
                    # Find transcript matching language or generated
                    transcript_data = None
                    try:
                        transcript = transcript_list.find_transcript(languages)
                        transcript_data = transcript.fetch()
                        if transcript.is_generated:
                            warnings.append("Using auto-generated YouTube subtitles.")
                    except Exception:
                        # Fallback to any transcript available
                        for t in transcript_list:
                            transcript_data = t.fetch()
                            warnings.append(f"Fell back to transcript in language: {t.language_code}")
                            break
                    
                    if not transcript_data:
                        transcript_data = api.get_transcript(video_id, languages=languages)

                    for item in transcript_data:
                        seg = TranscriptSegment(
                            start=float(item.get("start", 0.0)),
                            duration=float(item.get("duration", 0.0)),
                            text=str(item.get("text", "")).strip(),
                        )
                        segments.append(seg)
                        duration_seconds = max(duration_seconds, seg.start + seg.duration)

                except TranscriptsDisabled:
                    warnings.append("Transcripts are disabled for this YouTube video.")
                except NoTranscriptFound:
                    warnings.append(f"No transcript found for video in languages: {languages}")
                except VideoUnavailable:
                    warnings.append(f"YouTube video {video_id} is unavailable or private.")
                except Exception as e:
                    err_name = type(e).__name__
                    if "IpBlocked" in err_name or "TooManyRequests" in err_name:
                        warnings.append("YouTube IP rate limit or block detected during transcript fetch.")
                    else:
                        warnings.append(f"YouTube transcript acquisition failed ({err_name}): {str(e)}")

            except ImportError:
                warnings.append("youtube-transcript-api library not available in environment.")
        else:
            warnings.append(f"Invalid or missing YouTube URL: {source.url}")

        # Build markdown representation with timestamps
        md_lines = [f"# {title}\n"]
        if video_id:
            md_lines.append(f"**YouTube Video ID:** `{video_id}`  ")
            md_lines.append(f"**URL:** {source.url}\n")

        if segments:
            md_lines.append("## Transcrição com Marcadores Temporais\n")
            for seg in segments:
                mins = int(seg.start // 60)
                secs = int(seg.start % 60)
                time_str = f"{mins:02d}:{secs:02d}"
                md_lines.append(f"- **[{time_str}]** {seg.text}")
        else:
            md_lines.append("*Nenhuma transcrição ou legenda disponível para este vídeo.*")

        markdown_content = "\n".join(md_lines)
        text_content = " ".join(seg.text for seg in segments)

        return ContentDocument(
            id=doc_id,
            source_type=SourceType.YOUTUBE,
            title=title,
            text_content=text_content,
            markdown_content=markdown_content,
            language=source.language or "pt",
            source_url=source.url,
            duration_seconds=round(duration_seconds, 2) if duration_seconds > 0 else None,
            segments=segments,
            metadata={
                **source.metadata,
                "video_id": video_id,
                "segments_count": len(segments),
            },
            warnings=warnings,
            input_hash=source.compute_hash(),
            acquired_at=utc_now_iso(),
        )
