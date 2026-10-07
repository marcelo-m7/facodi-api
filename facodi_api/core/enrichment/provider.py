"""Enrichment provider interface and implementations."""

from __future__ import annotations

import abc
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
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


class EnrichmentError(ValueError):
    SAFE_CODES = {'PROVIDER_INVALID_OUTPUT', 'PROVIDER_NOT_CONFIGURED', 'PROVIDER_TIMEOUT',
                  'PROVIDER_UNAVAILABLE', 'PROVIDER_RATE_LIMITED', 'PROVIDER_REJECTED', 'PROVIDER_INPUT_TOO_LARGE'}

    def __init__(self, code):
        self.code = code if isinstance(code, str) and code in self.SAFE_CODES else 'PROVIDER_UNAVAILABLE'
        super().__init__(self.code)


class GeminiStructuredProvider(BaseEnrichmentProvider):
    """Independent bounded REST provider; it has no tools or domain write authority."""
    VERSION = 'gemini-chunk-evidence-v1'

    def __init__(self, *, model, max_output_tokens=4096):
        if (not isinstance(model, str) or not re.fullmatch(r'gemini-[A-Za-z0-9_.-]{1,70}', model)
                or type(max_output_tokens) is not int or not 256 <= max_output_tokens <= 8192):
            raise ValueError('Invalid server-owned provider configuration')
        self.model = model
        self.max_output_tokens = max_output_tokens

    def cache_identity(self):
        return {**super().cache_identity(), 'version': self.VERSION, 'model': self.model,
                'max_output_tokens': self.max_output_tokens, 'max_attempts': 2, 'deadline_seconds': 60}

    def _generate(self, chunks):
        if not (os.environ.get('FACODI_ENRICHMENT_API_KEY') or '').strip():
            raise EnrichmentError('PROVIDER_NOT_CONFIGURED')
        try:
            result = subprocess.run(
                [sys.executable, str(Path(__file__).with_name('gemini_transport.py'))],
                input=json.dumps({'model': self.model, 'max_output_tokens': self.max_output_tokens,
                                  'chunks': [chunk.to_dict() for chunk in chunks]}, allow_nan=False),
                capture_output=True, text=True, timeout=60, check=False,
            )
        except subprocess.TimeoutExpired:
            raise EnrichmentError('PROVIDER_TIMEOUT') from None
        except OSError:
            raise EnrichmentError('PROVIDER_UNAVAILABLE') from None
        if result.returncode or len(result.stdout.encode()) > 2 * 1024 * 1024:
            raise EnrichmentError('PROVIDER_INVALID_OUTPUT')
        try:
            response = json.loads(result.stdout, parse_constant=lambda value: (_ for _ in ()).throw(ValueError()))
            if not isinstance(response, dict):
                raise ValueError()
            if response.get('error'):
                raise EnrichmentError(response['error'])
            return response['output']
        except (KeyError, TypeError, json.JSONDecodeError):
            raise EnrichmentError('PROVIDER_INVALID_OUTPUT') from None

    def enrich(self, document, chunks):
        if not chunks or len(chunks) > 128 or sum(len(chunk.text.encode()) for chunk in chunks) > 262144:
            raise EnrichmentError('PROVIDER_INPUT_TOO_LARGE')
        payload = self._generate(chunks)
        try:
            if not isinstance(payload, dict) or set(payload) != {'summary', 'topics', 'keywords', 'concepts'}:
                raise ValueError()
            summary = payload['summary']
            if not isinstance(summary, str) or not summary.strip() or len(summary) > 8000:
                raise ValueError()
            for name in ('topics', 'keywords'):
                values = payload[name]
                if not isinstance(values, list) or len(values) > 32 or any(
                        not isinstance(value, str) or not value.strip() or len(value) > 100 for value in values):
                    raise ValueError()
            values = payload['concepts']
            if not isinstance(values, list) or len(values) > 32:
                raise ValueError()
            by_index = {chunk.index: chunk for chunk in chunks}
            concepts = []
            for value in values:
                if not isinstance(value, dict) or set(value) != {'name', 'category', 'relevance', 'evidence_snippet', 'chunk_indices'}:
                    raise ValueError()
                if any(not isinstance(value[key], str) or not value[key].strip() or len(value[key]) > 500
                       for key in ('name', 'category', 'evidence_snippet')):
                    raise ValueError()
                score, indices = value['relevance'], value['chunk_indices']
                if (type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1
                        or not isinstance(indices, list) or not indices or len(indices) > 128
                        or any(type(index) is not int or index not in by_index for index in indices)
                        or not any(value['evidence_snippet'] in by_index[index].text for index in indices)):
                    raise ValueError()
                concepts.append(ConceptExtraction(**value))
            return EnrichedDocument(
                id=str(uuid.uuid4()), document_id=document.id, summary=summary.strip(),
                topics=payload['topics'], keywords=payload['keywords'], concepts=concepts,
                suggested_category=(ContentCategory.VIDEO if document.source_type == SourceType.YOUTUBE else
                                    ContentCategory.DOCUMENT if document.source_type == SourceType.DOCUMENT else ContentCategory.ARTICLE),
                target_audience_level='unspecified', prerequisites=[], provider_name='gemini-structured',
                model_name=self.model, warnings=['Model relevance is not a calibrated probability; editorial review remains required.'],
                created_at=utc_now_iso(),
            )
        except (TypeError, KeyError, ValueError):
            raise EnrichmentError('PROVIDER_INVALID_OUTPUT') from None
