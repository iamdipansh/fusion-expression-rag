"""CLI entrypoint for milestone 1: parse -> chunk -> write JSONL. Deterministic — re-running
against the same PDF must produce the same output. Run once per manual version.

Embedding + LanceDB (milestones 3-4) are a separate step once the retriever is being built —
this command stops at chunks.jsonl so milestone 1's hand-inspection step has something to read
without requiring the embedding model to be downloaded first.

Usage:
    python -m ingestion.ingest
"""

from config import settings
from ingestion.chunk import chunk_pages, write_chunks_jsonl
from ingestion.parse import parse_pdf, write_pages_jsonl


def main() -> None:
    pages = parse_pdf(settings.manual_pdf_path)
    write_pages_jsonl(pages, settings.parsed_pages_path)

    pages_for_chunking = parse_pdf(settings.manual_pdf_path)
    chunks = chunk_pages(pages_for_chunking)
    write_chunks_jsonl(chunks, settings.chunks_path)


if __name__ == "__main__":
    main()
