import json
import pytest

from facodi_api.core.contracts.dtos import ContentDocument, ContentChunk, SourceType
from facodi_api.core.enrichment import provider
from facodi_api.core.enrichment import gemini_transport


def source():
    return ContentDocument('document', SourceType.MANUAL, 'Evidence',
                           'Learning evidence is original.', 'Learning evidence is original.', 'en')


def payload():
    return {'summary': 'Original learning evidence.', 'topics': ['Learning'], 'keywords': ['Evidence'],
            'concepts': [{'name': 'Learning', 'relevance': 0.8, 'category': 'Concept',
                          'evidence_snippet': 'Learning evidence', 'chunk_indices': [0]}]}


def build():
    cls = getattr(provider, 'GeminiStructuredProvider', None)
    assert cls is not None, 'Independent structured provider must exist'
    return cls(model='gemini-test-fixture', max_output_tokens=2048)


def test_structured_output_uses_real_chunk_evidence(monkeypatch):
    instance = build()
    monkeypatch.setattr(instance, '_generate', lambda chunks: payload())
    result = instance.enrich(source(), [ContentChunk(0, 'Original', source().text_content)])
    assert result.provider_name == 'gemini-structured'
    assert result.concepts[0].evidence_snippet in source().text_content
    assert result.concepts[0].chunk_indices == [0]
    assert result.prerequisites == []


@pytest.mark.parametrize('mutation', [
    lambda value: value.update(extra_credentials='secret'),
    lambda value: value['concepts'][0].update(chunk_indices=[999]),
    lambda value: value['concepts'][0].update(evidence_snippet='Invented evidence'),
    lambda value: value['concepts'][0].update(relevance=float('nan')),
    lambda value: value['concepts'][0].update(relevance=True),
    lambda value: value.update(summary=''),
])
def test_invalid_or_invented_provider_output_is_rejected(monkeypatch, mutation):
    instance = build()
    value = payload()
    mutation(value)
    monkeypatch.setattr(instance, '_generate', lambda chunks: value)
    with pytest.raises(ValueError, match='PROVIDER_INVALID_OUTPUT'):
        instance.enrich(source(), [ContentChunk(0, 'Original', source().text_content)])


def test_provider_cache_identity_contains_budget_and_model_but_no_secret(monkeypatch):
    monkeypatch.setenv('FACODI_ENRICHMENT_API_KEY', 'secret-fixture')
    instance = build()
    identity = json.dumps(instance.cache_identity())
    assert 'secret-fixture' not in identity
    assert 'gemini-test-fixture' in identity
    assert '2048' in identity
    assert instance.cache_identity() != provider.GeminiStructuredProvider(model='gemini-other', max_output_tokens=2048).cache_identity()


@pytest.mark.parametrize('model,budget', [('https://evil.invalid', 2048), ('gemini-test', True), ('gemini-test', 999999)])
def test_provider_endpoint_and_budget_are_bounded(model, budget):
    build()
    with pytest.raises(ValueError):
        provider.GeminiStructuredProvider(model=model, max_output_tokens=budget)


def test_transport_classifies_connection_failure_as_unavailable(monkeypatch):
    monkeypatch.setenv('FACODI_ENRICHMENT_API_KEY', 'secret-fixture')
    monkeypatch.setattr(
        gemini_transport.requests.Session,
        'post',
        lambda *args, **kwargs: (_ for _ in ()).throw(
            gemini_transport.requests.ConnectionError('offline')
        ),
    )
    with pytest.raises(gemini_transport.TransportError, match='PROVIDER_UNAVAILABLE'):
        gemini_transport.generate({
            'model': 'gemini-test-fixture',
            'max_output_tokens': 2048,
            'chunks': [{'index': 0, 'text': 'Original evidence.'}],
        })
