"""Unit tests for normalization, chunking, enrichment, mapping and pipeline runner."""

import os
import shutil
import pytest
from facodi_api.core.contracts.dtos import (
    CatalogSnapshot,
    ContentDocument,
    ContentSource,
    SourceType,
    TargetEntity,
    TranscriptSegment,
)
from facodi_api.core.enrichment.provider import BaselineDeterministicProvider
from facodi_api.core.mapping.mapper import CurriculumMapper
from facodi_api.core.normalization.normalizer import ContentNormalizer
from facodi_api.core.pipeline.runner import PipelineRunner


def test_chunking_by_paragraphs():
    normalizer = ContentNormalizer()
    text = (
        "Primeiro parágrafo longo com informações sobre inteligência artificial e aprendizado de máquina.\n\n"
        "Segundo parágrafo detalhando técnicas de processamento de linguagem natural.\n\n"
        "Terceiro parágrafo abordando sistemas de recomendação e grafos de conhecimento."
    )
    doc = ContentDocument(
        id="doc-1",
        source_type=SourceType.DOCUMENT,
        title="IA e NLP",
        text_content=text,
        markdown_content=text,
        language="pt",
    )
    chunks = normalizer.chunk_document(doc)
    assert len(chunks) >= 1
    assert "aprendizado" in chunks[0].text


def test_chunking_by_transcript_segments():
    normalizer = ContentNormalizer()
    segments = [
        TranscriptSegment(start=0.0, duration=5.0, text="Olá mundo este é o início do curso."),
        TranscriptSegment(start=5.0, duration=5.0, text="Vamos falar sobre arquitetura moderna de software."),
    ]
    doc = ContentDocument(
        id="doc-2",
        source_type=SourceType.YOUTUBE,
        title="Curso de Arquitetura",
        text_content="Olá mundo este é o início do curso. Vamos falar sobre arquitetura moderna de software.",
        markdown_content="...",
        language="pt",
        segments=segments,
    )
    chunks = normalizer.chunk_document(doc)
    assert len(chunks) == 1
    assert chunks[0].start_time == 0.0
    assert chunks[0].end_time == 10.0


def test_enrichment_provider():
    provider = BaselineDeterministicProvider()
    doc = ContentDocument(
        id="doc-enrich",
        source_type=SourceType.DOCUMENT,
        title="Segurança em APIs REST",
        text_content="Autenticação e autorização são pilares fundamentais. Tokens JWT garantem integridade e segurança. APIs REST devem proteger endpoints contra acessos não autorizados. Tokens devem expirar adequadamente.",
        markdown_content="...",
        language="pt",
    )
    normalizer = ContentNormalizer()
    chunks = normalizer.chunk_document(doc)
    enriched = provider.enrich(doc, chunks)

    assert enriched.summary is not None
    assert len(enriched.concepts) > 0
    assert any("Tokens" in c.name or "Segurança" in c.name or "Apis" in c.name for c in enriched.concepts)
    assert len(enriched.topics) > 0


def test_curriculum_mapper():
    mapper = CurriculumMapper()
    provider = BaselineDeterministicProvider()
    doc = ContentDocument(
        id="doc-map",
        source_type=SourceType.DOCUMENT,
        title="Odoo 19 ORM e Modelos",
        text_content="O ORM do Odoo 19 permite criar modelos com campos relacionais, constraints SQL e mixins como mail.thread. A integração com controllers HTTP expõe rotas seguras.",
        markdown_content="...",
        language="pt",
    )
    chunks = ContentNormalizer().chunk_document(doc)
    enriched = provider.enrich(doc, chunks)

    catalog = CatalogSnapshot(
        snapshot_id="snap-test",
        created_at="2026-10-06T12:00:00Z",
        targets=[
            TargetEntity(id="mod-odoo", type="course", name="Módulo Odoo 19 Avançado", tags=["odoo", "orm", "python"]),
            TargetEntity(id="mod-react", type="course", name="Frontend React", tags=["react", "typescript", "frontend"]),
        ],
    )
    result = mapper.map_document(enriched, catalog)
    assert len(result.candidates) > 0
    top = result.candidates[0]
    assert top.target_id == "mod-odoo"
    assert top.score > 0.3


def test_pipeline_runner_end_to_end(tmp_path):
    storage = str(tmp_path / "runs")
    runner = PipelineRunner(storage_dir=storage)

    source = ContentSource(
        source_type=SourceType.MARKDOWN,
        title="Engenharia de Prompt",
        raw_content="# Engenharia de Prompt\n\nTécnicas de few-shot, zero-shot e chain-of-thought para modelos de linguagem.",
        language="pt",
    )

    run = runner.run_pipeline(source=source, idempotency_key="idemp-test-01")
    assert run.status.value == "succeeded"
    assert len(run.steps) == 4
    for step in run.steps:
        assert step.status.value == "completed"

    # Test idempotency
    run2 = runner.run_pipeline(source=source, idempotency_key="idemp-test-01")
    assert run2.run_id == run.run_id
    assert run2.updated_at == run.updated_at
