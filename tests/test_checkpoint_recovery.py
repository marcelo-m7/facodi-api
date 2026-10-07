import pytest
from unittest.mock import Mock

from facodi_api.core.contracts.dtos import ContentSource, SourceType
from facodi_api.core.enrichment.provider import BaselineDeterministicProvider
from facodi_api.core.pipeline.runner import PipelineRunner


class InterruptedProvider(BaselineDeterministicProvider):
    def __init__(self):
        self.interrupted = False

    def enrich(self, document, chunks):
        if not self.interrupted:
            self.interrupted = True
            raise RuntimeError('Provider boundary interrupted')
        return super().enrich(document, chunks)


def test_retry_reuses_completed_document_checkpoint(tmp_path, monkeypatch):
    runner = PipelineRunner(InterruptedProvider(), str(tmp_path))
    source = ContentSource(SourceType.MANUAL, raw_content='Learning workflow preserves original content and native review.')
    with pytest.raises(RuntimeError):
        runner.run_pipeline(source, idempotency_key='checkpoint')
    saved = next(tmp_path.glob('*.json'))
    import json
    checkpoint = json.loads(saved.read_text())
    assert checkpoint['metadata'].get('document_data'), 'Completed ingestion must survive a later provider error'
    original_document_id = checkpoint['metadata']['document_data']['id']
    def repeated_step(*args, **kwargs):
        raise AssertionError('Completed ingestion and normalization must not repeat')
    monkeypatch.setattr(runner.ingestion_service, 'ingest', repeated_step)
    monkeypatch.setattr(runner.normalizer, 'chunk_document', repeated_step)
    output = runner.run_pipeline(source, idempotency_key='checkpoint')
    assert output.metadata['document_data']['id'] == original_document_id
    assert output.metadata['enriched_data']['document_id'] == original_document_id
    assert output.metadata['chunks_data']


def test_failure_before_ingestion_has_no_false_checkpoint(tmp_path, monkeypatch):
    runner = PipelineRunner(storage_dir=str(tmp_path))
    source = ContentSource(SourceType.MANUAL, raw_content='Original educational evidence.')
    original = runner.ingestion_service.ingest
    failed_ingest = Mock(side_effect=RuntimeError('Acquisition interrupted'))
    monkeypatch.setattr(runner.ingestion_service, 'ingest', failed_ingest)
    with pytest.raises(RuntimeError, match='Acquisition interrupted'):
        runner.run_pipeline(source, idempotency_key='before-ingestion')
    import json
    checkpoint = json.loads(next(tmp_path.glob('*.json')).read_text())
    assert 'document_data' not in checkpoint['metadata']
    monkeypatch.setattr(runner.ingestion_service, 'ingest', original)
    output = runner.run_pipeline(source, idempotency_key='before-ingestion')
    assert output.status.value == 'succeeded'
    assert failed_ingest.call_count == 1


def test_mapping_retry_reuses_all_completed_processing(tmp_path, monkeypatch):
    runner = PipelineRunner(storage_dir=str(tmp_path))
    source = ContentSource(SourceType.MANUAL, raw_content='Learning evidence preserves course review.')
    ingest = Mock(wraps=runner.ingestion_service.ingest)
    normalize = Mock(wraps=runner.normalizer.chunk_document)
    enrich = Mock(wraps=runner.enrichment_provider.enrich)
    mapping = runner.mapper.map_document
    monkeypatch.setattr(runner.ingestion_service, 'ingest', ingest)
    monkeypatch.setattr(runner.normalizer, 'chunk_document', normalize)
    monkeypatch.setattr(runner.enrichment_provider, 'enrich', enrich)
    monkeypatch.setattr(runner.mapper, 'map_document', Mock(side_effect=RuntimeError('Mapping interrupted')))
    with pytest.raises(RuntimeError, match='Mapping interrupted'):
        runner.run_pipeline(source, idempotency_key='mapping-retry')
    monkeypatch.setattr(runner.mapper, 'map_document', mapping)
    output = runner.run_pipeline(source, idempotency_key='mapping-retry')
    assert output.status.value == 'succeeded'
    assert (ingest.call_count, normalize.call_count, enrich.call_count) == (1, 1, 1)


def test_retry_initial_receipt_preserves_completed_checkpoints_on_interrupt(tmp_path):
    runner = PipelineRunner(InterruptedProvider(), str(tmp_path))
    source = ContentSource(SourceType.MANUAL, raw_content='Durable checkpoint evidence for retry.')
    with pytest.raises(RuntimeError):
        runner.run_pipeline(source, idempotency_key='retry-initial-save')

    original_save = runner.save_run
    calls = 0

    def interrupt_after_initial_save(run):
        nonlocal calls
        original_save(run)
        calls += 1
        if calls == 1:
            raise RuntimeError('worker stopped after retry receipt')

    runner.save_run = interrupt_after_initial_save
    with pytest.raises(RuntimeError, match='retry receipt'):
        runner.run_pipeline(source, idempotency_key='retry-initial-save')

    import json
    checkpoint = json.loads(next(tmp_path.glob('*.json')).read_text())
    assert checkpoint['metadata']['document_data']
    assert checkpoint['metadata']['chunks_data']


class VersionedProvider(BaselineDeterministicProvider):
    version = 'first'

    def cache_identity(self):
        return {'provider': 'versioned', 'version': self.version}


def test_changed_provider_version_cannot_reuse_a_completed_receipt(tmp_path):
    provider = VersionedProvider()
    runner = PipelineRunner(provider, str(tmp_path))
    source = ContentSource(SourceType.MANUAL, raw_content='Some original resource evidence.')
    runner.run_pipeline(source, idempotency_key='provider-version')
    provider.version = 'second'
    with pytest.raises(ValueError, match='Idempotency conflict'):
        runner.run_pipeline(source, idempotency_key='provider-version')


def test_baseline_concepts_reference_actual_input_chunks(tmp_path):
    result = PipelineRunner(storage_dir=str(tmp_path)).run_pipeline(
        ContentSource(SourceType.MANUAL, raw_content='Learning workflow preserves learning evidence and review history.'),
        idempotency_key='evidence',
    )
    chunks = {item['index']: item['text'] for item in result.metadata.get('chunks_data', [])}
    assert chunks
    for concept in result.metadata['enriched_data']['concepts']:
        assert concept['chunk_indices']
        assert any(concept['evidence_snippet'] in chunks[index] for index in concept['chunk_indices'])
    assert result.metadata['enriched_data']['warnings']
