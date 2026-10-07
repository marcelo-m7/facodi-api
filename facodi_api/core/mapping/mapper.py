"""Curriculum mapping engine with deterministic scoring and justifications."""

from __future__ import annotations

import re
import uuid
from typing import List

from ..contracts.dtos import (
    CatalogSnapshot,
    EnrichedDocument,
    MappingCandidate,
    MappingResult,
    TargetEntity,
    utc_now_iso,
)


class CurriculumMapper:
    """Matches an EnrichedDocument to TargetEntities in a CatalogSnapshot."""

    CONFIDENCE_THRESHOLD = 0.25

    def map_document(
        self, document: EnrichedDocument, catalog: CatalogSnapshot
    ) -> MappingResult:
        """Score entities in catalog against document concepts and keywords."""
        candidates: List[MappingCandidate] = []
        matched_concept_names = set()

        doc_concept_map = {c.name.lower(): c.name for c in document.concepts}
        topic_words = set(w.lower() for w in document.topics)
        summary_words = set(re.findall(r"\b\w{3,}\b", document.summary.lower()))

        for entity in catalog.targets:
            entity_name_words = set(re.findall(r"\b\w{3,}\b", entity.name.lower()))
            entity_tag_words = set(t.lower() for t in entity.tags)
            entity_topic_words = set(t.lower() for t in entity.topics)

            matched_terms: List[str] = []
            entity_matched_concepts: List[str] = []
            score = 0.0

            # Match concepts directly
            for c_lower, c_orig in doc_concept_map.items():
                if c_lower in entity_name_words or c_lower in entity_tag_words or c_lower in entity_topic_words:
                    entity_matched_concepts.append(c_orig)
                    matched_concept_names.add(c_lower)
                    score += 0.30

            # Match tags (high value)
            for tag in entity_tag_words:
                if tag in doc_concept_map or tag in topic_words or tag in summary_words:
                    matched_terms.append(f"tag:{tag}")
                    score += 0.25

            # Match title words
            for w in entity_name_words:
                if w in doc_concept_map:
                    matched_terms.append(f"termo:{w}")
                    score += 0.20
                elif w in summary_words:
                    matched_terms.append(f"sumário:{w}")
                    score += 0.10

            score = min(round(score, 2), 1.0)
            if score >= self.CONFIDENCE_THRESHOLD or not catalog.targets:
                justification = (
                    f"Correspondência encontrada com base em: {', '.join(matched_terms + entity_matched_concepts)}"
                    if (matched_terms or entity_matched_concepts)
                    else "Compatibilidade genérica de catálogo."
                )
                candidates.append(
                    MappingCandidate(
                        target_id=entity.id,
                        target_name=entity.name,
                        target_type=entity.type,
                        relation="matches_course" if entity.type == "course" else "matches_curricular_unit",
                        score=score,
                        confidence=score,
                        justification=justification,
                        evidence=matched_terms,
                        matched_concepts=entity_matched_concepts,
                    )
                )

        # Sort candidates descending by score
        candidates.sort(key=lambda c: c.score, reverse=True)

        unmatched = [
            c.name
            for c in document.concepts
            if c.name.lower() not in matched_concept_names
        ]

        return MappingResult(
            id=str(uuid.uuid4()),
            enriched_document_id=document.id,
            snapshot_id=catalog.snapshot_id,
            snapshot_hash=catalog.compute_hash(),
            candidates=candidates[:5],
            unmatched_concepts=unmatched,
            ranking_algorithm_version="deterministic-v2",
            created_at=utc_now_iso(),
        )

