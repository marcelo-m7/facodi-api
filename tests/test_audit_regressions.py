"""Regressions reproduced during the 2026-10-07 audit; no live services."""
import json
import math
import sys
import types
from pathlib import Path

import pytest

from facodi_api.core.contracts.dtos import (
    CatalogSnapshot, ContentSource, SourceType, TranscriptSegment,
)
from facodi_api.core.ingestion.document import DocumentIngestionAdapter
from facodi_api.core.ingestion.youtube import YouTubeIngestionAdapter
from facodi_api.core.pipeline.runner import PipelineRunner


def source(text="A document about mathematics.", **kwargs):
    return ContentSource(source_type=SourceType.MARKDOWN, raw_content=text, **kwargs)


@pytest.mark.parametrize("field,value", [("language", "en"), ("title", "Changed"),
                                           ("metadata", {"is_manual_transcript": True})])
def test_source_hash_covers_processing_input(field, value):
    assert source().compute_hash() != source(**{field: value}).compute_hash()


def test_storage_rejects_path_traversal(tmp_path):
    outside = tmp_path / "private.json"
    outside.write_text('{"private": true}')
    runner = PipelineRunner(storage_dir=str(tmp_path / "runs"))
    with pytest.raises(ValueError, match="identifier"):
        runner.load_run("../private")


def test_storage_idempotency_key_cannot_escape_directory(tmp_path):
    runner = PipelineRunner(storage_dir=str(tmp_path / "runs"))
    run = runner.run_pipeline(source(), idempotency_key="../escaped")
    assert not (tmp_path / "escaped.json").exists()
    assert runner.load_run(run.run_id).run_id == run.run_id


def test_replay_conflicts_with_different_content(tmp_path):
    runner = PipelineRunner(storage_dir=str(tmp_path))
    runner.run_pipeline(source(), idempotency_key="same-command")
    with pytest.raises(ValueError, match="Idempotency"):
        runner.run_pipeline(source("Changed content"), idempotency_key="same-command")


def test_replay_conflicts_with_different_catalog(tmp_path):
    runner = PipelineRunner(storage_dir=str(tmp_path))
    runner.run_pipeline(source(), idempotency_key="same-command")
    snapshot = CatalogSnapshot(snapshot_id="different", created_at="2026-10-07", targets=[])
    with pytest.raises(ValueError, match="Idempotency"):
        runner.run_pipeline(source(), catalog=snapshot, idempotency_key="same-command")


@pytest.mark.parametrize("url", [
    "https://evil-youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtube.com.evil.test/watch?v=dQw4w9WgXcQ",
    "https://evil.test/?next=https://youtube.com/watch?v=dQw4w9WgXcQ",
    "http://youtube.com/watch?v=dQw4w9WgXcQ",
    "https://user@youtube.com/watch?v=dQw4w9WgXcQ",
    "https://youtube.com:444/watch?v=dQw4w9WgXcQ",
])
def test_youtube_exact_https_host(url):
    assert YouTubeIngestionAdapter.extract_video_id(url) is None


def test_manual_plain_transcript_does_not_invent_timestamps():
    doc = YouTubeIngestionAdapter().ingest(ContentSource(
        source_type=SourceType.YOUTUBE, url="https://youtu.be/dQw4w9WgXcQ",
        raw_content="First sentence.\nSecond sentence.", metadata={"is_manual_transcript": True}))
    assert doc.segments == []
    assert doc.duration_seconds is None
    assert "First sentence" in doc.text_content


def test_current_transcript_api_attribute_snippets(monkeypatch):
    transcript = types.SimpleNamespace(language_code="en", is_generated=True,
        fetch=lambda: [types.SimpleNamespace(start=2.5, duration=1.25, text="Real evidence")])
    api = types.SimpleNamespace(list=lambda video_id: types.SimpleNamespace(find_transcript=lambda langs: transcript))
    module = types.ModuleType("youtube_transcript_api")
    module.YouTubeTranscriptApi = lambda: api
    errors = types.ModuleType("youtube_transcript_api._errors")
    for name in ("NoTranscriptFound", "TranscriptsDisabled", "VideoUnavailable"):
        setattr(errors, name, type(name, (Exception,), {}))
    monkeypatch.setitem(sys.modules, "youtube_transcript_api", module)
    monkeypatch.setitem(sys.modules, "youtube_transcript_api._errors", errors)
    doc = YouTubeIngestionAdapter().ingest(ContentSource(source_type=SourceType.YOUTUBE,
        url="https://youtu.be/dQw4w9WgXcQ", language="pt"))
    assert len(doc.segments) == 1
    assert doc.segments[0].text == "Real evidence"
    assert doc.segments[0].start == 2.5
    assert doc.language == "en"


def test_empty_document_is_not_success():
    with pytest.raises(ValueError):
        DocumentIngestionAdapter().ingest(ContentSource(source_type=SourceType.DOCUMENT))


def test_missing_transcript_is_not_success(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "youtube_transcript_api", None)
    runner = PipelineRunner(storage_dir=str(tmp_path))
    with pytest.raises(ValueError):
        runner.run_pipeline(ContentSource(source_type=SourceType.YOUTUBE,
                            url="https://youtu.be/dQw4w9WgXcQ"), idempotency_key="no-transcript")


@pytest.mark.parametrize("number", [float("nan"), float("inf"), -1.0])
def test_transcript_rejects_invalid_times(number):
    with pytest.raises(ValueError):
        TranscriptSegment(start=number, duration=1.0, text="Evidence")


def test_failed_provider_does_not_persist_secrets(tmp_path, caplog):
    class FailedProvider:
        def enrich(self, *args):
            raise RuntimeError("private-provider-secret")
    runner = PipelineRunner(storage_dir=str(tmp_path), enrichment_provider=FailedProvider())
    with pytest.raises(RuntimeError):
        runner.run_pipeline(source(), idempotency_key="safe-error")
    outputs = "".join(p.read_text() for p in tmp_path.glob("*.json"))
    assert "private-provider-secret" not in outputs
    assert "private-provider-secret" not in caplog.text

def test_odoo_entrypoints_compile():
    import ast
    from pathlib import Path
    for path in Path('facodi_api').rglob('*.py'):
        ast.parse(path.read_text(), filename=str(path))
