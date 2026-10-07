"""Text normalization and deterministic chunking."""

from __future__ import annotations

import re
from typing import List, Optional

from ..contracts.dtos import (
    ContentChunk,
    ContentDocument,
    TranscriptSegment,
)


class ContentNormalizer:
    """Normalizes text and breaks ContentDocument into structured chunks."""

    TARGET_CHUNK_TOKENS = 350
    MAX_CHUNK_TOKENS = 600

    @classmethod
    def clean_text(cls, text: str) -> str:
        """Sanitize control chars and excessive whitespace."""
        if not text:
            return ""
        # Remove null bytes and non-printable control chars
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    def chunk_document(self, doc: ContentDocument) -> List[ContentChunk]:
        """Produce structured chunks from document (by transcript intervals or paragraphs)."""
        if doc.segments:
            return self._chunk_by_segments(doc.segments)
        else:
            return self._chunk_by_text(doc.text_content or doc.markdown_content)

    def _chunk_by_segments(self, segments: List[TranscriptSegment]) -> List[ContentChunk]:
        """Aggregate timestamped segments into coherent time-bounded chunks."""
        chunks: List[ContentChunk] = []
        if not segments:
            return chunks

        current_words: List[str] = []
        current_start: Optional[float] = None
        current_end: Optional[float] = None
        chunk_idx = 1

        for seg in segments:
            words = seg.text.split()
            if not words:
                continue

            if current_start is None:
                current_start = seg.start
            current_end = seg.start + seg.duration
            current_words.extend(words)

            if len(current_words) >= self.TARGET_CHUNK_TOKENS:
                chunk_text = " ".join(current_words)
                mins_start = int(current_start // 60)
                secs_start = int(current_start % 60)
                mins_end = int(current_end // 60)
                secs_end = int(current_end % 60)
                title = f"Secção {chunk_idx} ({mins_start:02d}:{secs_start:02d} - {mins_end:02d}:{secs_end:02d})"

                chunks.append(
                    ContentChunk(
                        index=chunk_idx,
                        title=title,
                        text=chunk_text,
                        start_time=round(current_start, 2),
                        end_time=round(current_end, 2),
                        token_count_estimate=len(current_words),
                    )
                )
                chunk_idx += 1
                current_words = []
                current_start = None
                current_end = None

        if current_words:
            chunk_text = " ".join(current_words)
            mins_start = int((current_start or 0.0) // 60)
            secs_start = int((current_start or 0.0) % 60)
            mins_end = int((current_end or 0.0) // 60)
            secs_end = int((current_end or 0.0) % 60)
            title = f"Secção {chunk_idx} ({mins_start:02d}:{secs_start:02d} - {mins_end:02d}:{secs_end:02d})"
            chunks.append(
                ContentChunk(
                    index=chunk_idx,
                    title=title,
                    text=chunk_text,
                    start_time=round(current_start or 0.0, 2),
                    end_time=round(current_end or 0.0, 2),
                    token_count_estimate=len(current_words),
                )
            )

        return chunks

    def _chunk_by_text(self, text: str) -> List[ContentChunk]:
        """Aggregate textual paragraphs into target token size chunks."""
        chunks: List[ContentChunk] = []
        cleaned = self.clean_text(text)
        if not cleaned:
            return chunks

        paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]
        current_paragraphs: List[str] = []
        current_word_count = 0
        chunk_idx = 1

        for para in paragraphs:
            para_words = para.split()
            if current_word_count + len(para_words) > self.MAX_CHUNK_TOKENS and current_paragraphs:
                chunk_text = "\n\n".join(current_paragraphs)
                title = f"Bloco {chunk_idx}"
                chunks.append(
                    ContentChunk(
                        index=chunk_idx,
                        title=title,
                        text=chunk_text,
                        token_count_estimate=current_word_count,
                    )
                )
                chunk_idx += 1
                current_paragraphs = [para]
                current_word_count = len(para_words)
            else:
                current_paragraphs.append(para)
                current_word_count += len(para_words)

        if current_paragraphs:
            chunk_text = "\n\n".join(current_paragraphs)
            chunks.append(
                ContentChunk(
                    index=chunk_idx,
                    title=f"Bloco {chunk_idx}",
                    text=chunk_text,
                    token_count_estimate=current_word_count,
                )
            )

        return chunks
