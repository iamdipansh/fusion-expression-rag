"""Build the LanceDB index from data/parsed/chunks.jsonl.

Milestone 3: --lexical-only builds just the FTS index (fast, no embedding model).
Milestone 4: the default builds dense + bge-m3-sparse too — embeds all chunks, which is the
slow step (CPU-only on this machine; expect real wall-clock time for ~5,800 chunks).

Usage:
    python -m retrieval.build_index                # dense + sparse + lexical (milestone 4)
    python -m retrieval.build_index --lexical-only  # lexical/FTS only (milestone 3)
"""

import argparse
import time

from config import settings
from ingestion.chunk import read_chunks_jsonl
from retrieval.embed import embed_chunks
from retrieval.store import write_chunks, write_chunks_lexical_only


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lexical-only", action="store_true")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="embedding batch size (only used without --lexical-only)",
    )
    args = parser.parse_args()

    chunks = read_chunks_jsonl(settings.chunks_path)

    if args.lexical_only:
        write_chunks_lexical_only(chunks)
        print(f"indexed {len(chunks)} chunks (lexical/FTS only) into {settings.lancedb_uri}")
        return

    start = time.monotonic()
    embedded = embed_chunks(chunks, batch_size=args.batch_size)
    elapsed = time.monotonic() - start
    print(
        f"embedded {len(embedded)} chunks in {elapsed:.1f}s ({elapsed / len(embedded):.3f}s/chunk)"
    )

    write_chunks(embedded)
    print(f"indexed {len(embedded)} chunks (dense + sparse + lexical) into {settings.lancedb_uri}")


if __name__ == "__main__":
    main()
