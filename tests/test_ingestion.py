"""Unit tests for ingestion adapters."""

import pytest
from facodi_api.core.contracts.dtos import ContentSource, SourceType
from facodi_api.core.ingestion.document import DocumentIngestionAdapter
from facodi_api.core.ingestion.youtube import YouTubeIngestionAdapter


def test_markdown_and_manual_ingestion():
    adapter = DocumentIngestionAdapter()
    source = ContentSource(
        source_type=SourceType.MARKDOWN,
        title="Guia do Desenvolvedor",
        raw_content="# Introdução\n\nEste é um guia de arquitetura para a plataforma FACODI.",
    )
    doc = adapter.ingest(source)
    assert doc.title == "Guia do Desenvolvedor"
    assert "Introdução" in doc.text_content
    assert doc.source_type == SourceType.MARKDOWN
    assert len(doc.warnings) == 0


def test_text_file_ingestion():
    adapter = DocumentIngestionAdapter()
    text = "Conteúdo textual puro em bytes para simular arquivo txt."
    source = ContentSource(
        source_type=SourceType.DOCUMENT,
        raw_file_bytes=text.encode("utf-8"),
        raw_file_name="exemplo.txt",
    )
    doc = adapter.ingest(source)
    assert "Conteúdo textual puro" in doc.text_content
    assert doc.metadata["filename"] == "exemplo.txt"


def test_youtube_url_parsing():
    assert YouTubeIngestionAdapter.extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert YouTubeIngestionAdapter.extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert YouTubeIngestionAdapter.extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert YouTubeIngestionAdapter.extract_video_id("https://google.com") is None


def test_youtube_manual_transcript_fallback():
    adapter = YouTubeIngestionAdapter()
    source = ContentSource(
        source_type=SourceType.YOUTUBE,
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        title="Rickroll",
        raw_content="[00:00] Never gonna give you up\n[00:04] Never gonna let you down\n[00:08] Never gonna run around and desert you",
        metadata={"is_manual_transcript": True},
    )
    doc = adapter.ingest(source)
    assert len(doc.segments) == 3
    assert doc.segments[0].start == 0.0
    assert "Never gonna give you up" in doc.segments[0].text
    assert doc.duration_seconds is not None
    assert doc.duration_seconds >= 12.0
