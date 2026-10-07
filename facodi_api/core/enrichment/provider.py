"""Enrichment provider interface and implementations."""

from __future__ import annotations

import abc
import os
import re
import uuid
from typing import List, Optional

from ..contracts.dtos import (
    ConceptExtraction,
    ContentCategory,
    ContentChunk,
    ContentDocument,
    EnrichedDocument,
    SourceType,
    utc_now_iso,
)


class BaseEnrichmentProvider(abc.ABC):
    """Abstract provider for concept extraction, summary and key takeaway generation."""

    def cache_identity(self):
        return {'implementation': type(self).__module__ + '.' + type(self).__name__}

    @abc.abstractmethod
    def enrich(
        self, document: ContentDocument, chunks: List[ContentChunk]
    ) -> EnrichedDocument:
        """Enrich content chunks into an EnrichedDocument with concepts, takeaways and summary."""
        pass


class BaselineDeterministicProvider(BaseEnrichmentProvider):
    """Deterministic, offline enrichment provider requiring no external LLM API."""

    def cache_identity(self):
        return {**super().cache_identity(), 'version': 'regex-frequency-v2-evidence'}

    STOP_WORDS = {
        "a", "o", "os", "as", "um", "uma", "uns", "umas", "de", "do", "da", "dos", "das",
        "em", "no", "na", "nos", "nas", "para", "por", "com", "sem", "sob", "sobre",
        "que", "se", "ou", "e", "mas", "como", "mais", "muito", "sua", "seu", "seus", "suas",
        "este", "esta", "estes", "estas", "isto", "esse", "essa", "esses", "essas", "isso",
        "aquele", "aquela", "aqueles", "aquelas", "aquilo", "ele", "ela", "eles", "elas",
        "nos", "vos", "me", "te", "lhe", "lhes", "minha", "meu", "nosso", "nossa",
        "the", "and", "or", "of", "to", "in", "for", "with", "on", "at", "by", "from",
        "up", "about", "into", "over", "after", "is", "are", "was", "were", "be", "been",
    }

    def enrich(
        self, document: ContentDocument, chunks: List[ContentChunk]
    ) -> EnrichedDocument:
        """Extract structured metadata and concepts deterministically."""
        full_text = document.text_content or document.markdown_content or ""
        words = re.findall(r"\b[A-Za-zÀ-ÖØ-öø-ÿ0-9_-]{3,}\b", full_text.lower())
        
        freq: dict[str, int] = {}
        for w in words:
            if w not in self.STOP_WORDS and not w.isdigit():
                freq[w] = freq.get(w, 0) + 1

        sorted_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        top_concepts: List[ConceptExtraction] = []
        for name, count in sorted_words[:12]:
            score = round(min(count / 10.0, 1.0), 2)
            references = [chunk for chunk in chunks if re.search(r'\b' + re.escape(name) + r'\b', chunk.text, re.I)]
            if not references:
                continue
            evidence_chunk = references[0]
            match = re.search(r'\b' + re.escape(name) + r'\b', evidence_chunk.text, re.I)
            snippet = evidence_chunk.text[max(0, match.start() - 80):match.end() + 80]
            top_concepts.append(
                ConceptExtraction(
                    name=name.capitalize(),
                    relevance=score,
                    category="Keyword",
                    evidence_snippet=snippet,
                    chunk_indices=[chunk.index for chunk in references],
                )
            )

        # Generate summary
        sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+", full_text)
            if len(s.strip()) > 25
        ]
        if sentences:
            summary_sentences = sentences[:3]
            summary = " ".join(summary_sentences)
        else:
            summary = (full_text[:300] + "...") if len(full_text) > 300 else full_text

        # Estimate reading time (approx 180 words per min)
        reading_time = max(1, round(len(words) / 180))

        # Determine category
        cat = ContentCategory.ARTICLE
        if document.source_type == SourceType.YOUTUBE:
            cat = ContentCategory.VIDEO
        elif document.source_type == SourceType.DOCUMENT:
            cat = ContentCategory.DOCUMENT

        topics = [c.name for c in top_concepts[:5]]
        keywords = [c.name for c in top_concepts]

        return EnrichedDocument(
            id=str(uuid.uuid4()),
            document_id=document.id,
            summary=summary,
            topics=topics,
            concepts=top_concepts,
            keywords=keywords,
            suggested_category=cat,
            target_audience_level="unspecified",
            prerequisites=[],
            provider_name="baseline-deterministic",
            model_name="regex-frequency-v2-evidence",
            warnings=['Deterministic lexical baseline; no LLM analysis or academic equivalence is inferred.'],
            created_at=utc_now_iso(),
        )
