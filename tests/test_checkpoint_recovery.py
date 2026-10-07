import pytest

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


def test_retry_reuses_completed_document_checkpoint(tmp_path):
    runner = PipelineRunner(InterruptedProvider(), str(tmp_path))
    source = ContentSource(SourceType.MANUAL, raw_content='Learning workflow preserves original content and native review.')
    with pytest.raises(RuntimeError):
        runner.run_pipeline(source, idempotency_key='checkpoint')
    saved = next(tmp_path.glob('*.json'))
    import json
    checkpoint = json.loads(saved.read_text())
    assert checkpoint['metadata'].get('document_data'), 'Completed ingestion must survive a later provider error'
    original_document_id = checkpoint['metadata']['document_data']['id']
    output = runner.run_pipeline(source, idempotency_key='checkpoint')
    assert output.metadata['document_data']['id'] == original_document_id
    assert output.metadata['enriched_data']['document_id'] == original_document_id
    assert output.metadata['chunks_data']


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
