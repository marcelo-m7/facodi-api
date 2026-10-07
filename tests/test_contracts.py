"""Unit tests for DTO contracts, validation and serialization."""

import pytest
from facodi_api.core.contracts.dtos import (
    CatalogSnapshot,
    ConceptExtraction,
    ContentChunk,
    ContentDocument,
    ContentSource,
    EnrichedDocument,
    MappingCandidate,
    MappingResult,
    PipelineRun,
    PipelineStep,
    RunStatus,
    SourceType,
    StepStatus,
    TargetEntity,
)


def test_content_source_hash():
    s1 = ContentSource(source_type=SourceType.DOCUMENT, url="https://example.com/doc.pdf", title="Doc 1")
    s2 = ContentSource(source_type=SourceType.DOCUMENT, url="https://example.com/doc.pdf", title="Doc 1")
    s3 = ContentSource(source_type=SourceType.YOUTUBE, url="https://youtube.com/watch?v=123", title="Video")

    assert s1.compute_hash() == s2.compute_hash()
    assert s1.compute_hash() != s3.compute_hash()


def test_pipeline_run_serialization_roundtrip():
    step = PipelineStep(
        step_key="ingest",
        name="Ingestão",
        status=StepStatus.COMPLETED,
        execution_time_seconds=0.45,
    )
    run = PipelineRun(
        run_id="run-123",
        idempotency_key="idemp-123",
        status=RunStatus.SUCCEEDED,
        source_type=SourceType.MARKDOWN,
        source_url=None,
        created_at="2026-10-06T12:00:00Z",
        updated_at="2026-10-06T12:00:01Z",
        steps=[step],
        artifacts={"doc": "doc-123"},
    )

    data = run.to_dict()
    assert data["run_id"] == "run-123"
    assert data["source_type"] == "markdown"
    assert len(data["steps"]) == 1

    restored = PipelineRun.from_dict(data)
    assert restored.run_id == run.run_id
    assert restored.source_type == SourceType.MARKDOWN
    assert restored.steps[0].execution_time_seconds == 0.45
    assert restored.artifacts["doc"] == "doc-123"


def test_catalog_snapshot_roundtrip():
    entity = TargetEntity(
        id="e-1",
        name="Módulo 1",
        type="course",
        code="MOD-1",
        tags=["gestão", "liderança"],
    )
    catalog = CatalogSnapshot(
        snapshot_id="snap-1",
        created_at="2026-10-06T12:00:00Z",
        targets=[entity],
    )

    data = catalog.to_dict()
    restored = CatalogSnapshot.from_dict(data)

    assert len(restored.targets) == 1
    assert restored.targets[0].name == "Módulo 1"
    assert "gestão" in restored.targets[0].tags
    assert restored.compute_hash() is not None
