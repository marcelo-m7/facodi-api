"""Command Line Interface for standalone execution of the FACODI Content Pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from ..core.contracts.dtos import (
    CatalogSnapshot,
    ContentSource,
    SourceType,
    TargetEntity,
)
from ..core.pipeline.runner import PipelineRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="facodi-pipeline",
        description="Standalone runner for FACODI Python Content Processing Pipeline",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run command
    run_parser = subparsers.add_parser("run", help="Run pipeline on a document or video")
    run_parser.add_argument(
        "--type",
        choices=["document", "youtube", "markdown", "manual"],
        default="document",
        help="Source type (default: document)",
    )
    run_parser.add_argument("--url", help="URL of YouTube video or remote file")
    run_parser.add_argument("--file", help="Local file path for document or markdown")
    run_parser.add_argument("--text", help="Direct text/markdown content string")
    run_parser.add_argument("--title", help="Title for the ingested content")
    run_parser.add_argument("--lang", default="pt", help="Content language (default: pt)")
    run_parser.add_argument("--idempotency-key", help="Idempotency key for deterministic re-runs")
    run_parser.add_argument("--catalog", help="Optional path to catalog JSON file")
    run_parser.add_argument("--output", help="Optional output path to save JSON run result")

    # get command
    get_parser = subparsers.add_parser("get", help="Get execution result of a previous run")
    get_parser.add_argument("run_id", help="Pipeline Run ID")

    return parser


def main(args: Optional[list[str]] = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(args)

    runner = PipelineRunner()

    if parsed.command == "get":
        run = runner.load_run(parsed.run_id)
        if not run:
            print(f"Error: Run {parsed.run_id} not found.", file=sys.stderr)
            return 1
        print(json.dumps(run.to_dict(), indent=2, ensure_ascii=False))
        return 0

    if parsed.command == "run":
        file_bytes = None
        file_name = None
        if parsed.file:
            with open(parsed.file, "rb") as f:
                file_bytes = f.read()
            file_name = parsed.file

        source = ContentSource(
            source_type=SourceType(parsed.type),
            url=parsed.url,
            title=parsed.title,
            raw_content=parsed.text,
            raw_file_bytes=file_bytes,
            raw_file_name=file_name,
            language=parsed.lang,
        )

        catalog = None
        if parsed.catalog:
            with open(parsed.catalog, "r", encoding="utf-8") as f:
                catalog = CatalogSnapshot.from_dict(json.load(f))

        try:
            run = runner.run_pipeline(
                source=source,
                catalog=catalog,
                idempotency_key=parsed.idempotency_key,
            )
            out_json = json.dumps(run.to_dict(), indent=2, ensure_ascii=False)
            if parsed.output:
                with open(parsed.output, "w", encoding="utf-8") as f:
                    f.write(out_json)
                print(f"Result written to {parsed.output}")
            else:
                print(out_json)
            return 0
        except Exception as e:
            print(f"Pipeline execution failed: {e}", file=sys.stderr)
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
