"""Pipeline runner executing steps idempotently with persistence."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from ..contracts.dtos import (
    CatalogSnapshot,
    ContentDocument,
    ContentSource,
    EnrichedDocument,
    MappingResult,
    PipelineRun,
    PipelineStep,
    RunStatus,
    SourceType,
    StepStatus,
    utc_now_iso,
)
from ..enrichment.provider import BaseEnrichmentProvider, BaselineDeterministicProvider
from ..ingestion import IngestionService
from ..mapping.mapper import CurriculumMapper
from ..normalization.normalizer import ContentNormalizer

logger = logging.getLogger("facodi_api.pipeline")


class PipelineRunner:
    """Executes ingestion -> normalization -> enrichment -> mapping."""

    def __init__(
        self,
        enrichment_provider: Optional[BaseEnrichmentProvider] = None,
        storage_dir: Optional[str] = None,
    ):
        self.ingestion_service = IngestionService()
        self.normalizer = ContentNormalizer()
        self.enrichment_provider = enrichment_provider or BaselineDeterministicProvider()
        self.mapper = CurriculumMapper()
        if storage_dir:
            self.storage_dir = storage_dir
        elif os.getenv("FACODI_PIPELINE_RUNS_DIR"):
            self.storage_dir = os.environ["FACODI_PIPELINE_RUNS_DIR"]
        else:
            # Fallback safely to /tmp or user cache rather than root /
            base_dir = os.getenv("XDG_CACHE_HOME") or "/tmp"
            self.storage_dir = os.path.join(base_dir, "facodi_pipeline_runs")
        os.makedirs(self.storage_dir, exist_ok=True)

    def _get_run_path(self, run_id: str) -> str:
        return os.path.join(self.storage_dir, f"{run_id}.json")

    def save_run(self, run: PipelineRun) -> None:
        """Persist pipeline run state to JSON artifact storage."""
        path = self._get_run_path(run.run_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(run.to_dict(), f, indent=2, ensure_ascii=False)

    def load_run(self, run_id: str) -> Optional[PipelineRun]:
        """Load pipeline run from disk."""
        path = self._get_run_path(run_id)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return PipelineRun.from_dict(data)

    def run_pipeline(
        self,
        source: ContentSource,
        catalog: Optional[CatalogSnapshot] = None,
        idempotency_key: Optional[str] = None,
    ) -> PipelineRun:
        """Execute all steps idempotently."""
        run_id = idempotency_key or str(uuid.uuid4())
        
        # Check if already completed under this idempotency_key
        existing = self.load_run(run_id)
        if existing and existing.status == RunStatus.SUCCEEDED:
            logger.info("Run %s already completed (idempotency hit)", run_id)
            return existing

        now = utc_now_iso()
        steps = [
            PipelineStep(step_key="ingest", name="Ingestão de Conteúdo", status=StepStatus.PENDING),
            PipelineStep(step_key="normalize", name="Normalização e Segmentação", status=StepStatus.PENDING),
            PipelineStep(step_key="enrich", name="Enriquecimento e Conceitos", status=StepStatus.PENDING),
            PipelineStep(step_key="map", name="Mapeamento Curricular", status=StepStatus.PENDING),
        ]
        run = PipelineRun(
            run_id=run_id,
            idempotency_key=idempotency_key or run_id,
            source_type=source.source_type,
            source_url=source.url,
            status=RunStatus.RUNNING,
            created_at=now,
            updated_at=now,
            steps=steps,
        )
        self.save_run(run)

        try:
            # 1. Ingestion
            t0 = time.time()
            content_doc = self.ingestion_service.ingest(source)
            dur = round(time.time() - t0, 3)
            steps[0] = PipelineStep(
                step_key="ingest",
                name="Ingestão de Conteúdo",
                status=StepStatus.COMPLETED,
                started_at=now,
                completed_at=utc_now_iso(),
                execution_time_seconds=dur,
                artifact_id=content_doc.id,
            )
            run = PipelineRun(
                run_id=run.run_id,
                idempotency_key=run.idempotency_key,
                source_type=run.source_type,
                source_url=run.source_url,
                status=RunStatus.RUNNING,
                created_at=run.created_at,
                updated_at=utc_now_iso(),
                steps=list(steps),
                artifacts={**run.artifacts, "document": content_doc.id},
                metadata={**run.metadata, "document_title": content_doc.title},
            )
            self.save_run(run)

            # 2. Normalization & Chunking
            t0 = time.time()
            chunks = self.normalizer.chunk_document(content_doc)
            dur = round(time.time() - t0, 3)
            steps[1] = PipelineStep(
                step_key="normalize",
                name="Normalização e Segmentação",
                status=StepStatus.COMPLETED,
                started_at=utc_now_iso(),
                completed_at=utc_now_iso(),
                execution_time_seconds=dur,
            )
            run = PipelineRun(
                run_id=run.run_id,
                idempotency_key=run.idempotency_key,
                source_type=run.source_type,
                source_url=run.source_url,
                status=RunStatus.RUNNING,
                created_at=run.created_at,
                updated_at=utc_now_iso(),
                steps=list(steps),
                artifacts=run.artifacts,
                metadata={**run.metadata, "chunks_count": len(chunks)},
            )
            self.save_run(run)

            # 3. Enrichment
            t0 = time.time()
            enriched_doc = self.enrichment_provider.enrich(content_doc, chunks)
            dur = round(time.time() - t0, 3)
            steps[2] = PipelineStep(
                step_key="enrich",
                name="Enriquecimento e Conceitos",
                status=StepStatus.COMPLETED,
                started_at=utc_now_iso(),
                completed_at=utc_now_iso(),
                execution_time_seconds=dur,
                artifact_id=enriched_doc.id,
            )
            run = PipelineRun(
                run_id=run.run_id,
                idempotency_key=run.idempotency_key,
                source_type=run.source_type,
                source_url=run.source_url,
                status=RunStatus.RUNNING,
                created_at=run.created_at,
                updated_at=utc_now_iso(),
                steps=list(steps),
                artifacts={**run.artifacts, "enriched": enriched_doc.id},
                metadata={
                    **run.metadata,
                    "concepts_count": len(enriched_doc.concepts),
                    "topics_count": len(enriched_doc.topics),
                },
            )
            self.save_run(run)

            # 4. Mapping
            t0 = time.time()
            effective_catalog = catalog or CatalogSnapshot(
                snapshot_id="empty-catalog",
                created_at=utc_now_iso(),
                targets=[],
            )
            mapping_result = self.mapper.map_document(enriched_doc, effective_catalog)
            dur = round(time.time() - t0, 3)
            steps[3] = PipelineStep(
                step_key="map",
                name="Mapeamento Curricular",
                status=StepStatus.COMPLETED,
                started_at=utc_now_iso(),
                completed_at=utc_now_iso(),
                execution_time_seconds=dur,
                artifact_id=mapping_result.id,
            )

            # Finalize run
            run = PipelineRun(
                run_id=run.run_id,
                idempotency_key=run.idempotency_key,
                source_type=run.source_type,
                source_url=run.source_url,
                status=RunStatus.SUCCEEDED,
                created_at=run.created_at,
                updated_at=utc_now_iso(),
                steps=list(steps),
                artifacts={
                    **run.artifacts,
                    "document": content_doc.id,
                    "enriched": enriched_doc.id,
                    "mapping": mapping_result.id,
                },
                metadata={
                    **run.metadata,
                    "candidates_count": len(mapping_result.candidates),
                    "document_data": content_doc.to_dict(),
                    "enriched_data": enriched_doc.to_dict(),
                    "mapping_data": mapping_result.to_dict(),
                },
            )
            self.save_run(run)
            return run

        except Exception as exc:
            logger.exception("Pipeline run %s failed", run_id)
            err_dict = {"code": "pipeline_execution_error", "message": str(exc)}
            failed_steps = []
            for s in steps:
                if s.status == StepStatus.RUNNING or s.status == StepStatus.PENDING:
                    failed_steps.append(
                        PipelineStep(
                            step_key=s.step_key,
                            name=s.name,
                            status=StepStatus.FAILED,
                            error_message=str(exc),
                            completed_at=utc_now_iso(),
                        )
                    )
                else:
                    failed_steps.append(s)

            run = PipelineRun(
                run_id=run.run_id,
                idempotency_key=run.idempotency_key,
                source_type=run.source_type,
                source_url=run.source_url,
                status=RunStatus.FAILED,
                created_at=run.created_at,
                updated_at=utc_now_iso(),
                steps=failed_steps,
                artifacts=run.artifacts,
                error=err_dict,
                metadata=run.metadata,
            )
            self.save_run(run)
            raise
