"""Milestone 2: the gold eval set itself (this file's `GoldExample` schema + `gold_set.jsonl`).
Milestones 3-4: recall@10 / precision@5 against it, sparse-only baseline vs. dense+RRF+rerank.
Every retrieval experiment gets logged with its numbers — no undocumented tuning (see
Conventions in CLAUDE.md). Build the eval set before tuning the retriever — this file exists so
that isn't optional.

Gold set format (eval/gold_set.jsonl), one JSON object per line — see GoldExample below.
`expected_pages` is a list of `[min_page, max_page]` ranges, one per unique source breadcrumb —
composed_animation questions ground against multiple, disjoint manual sections (e.g. the
SimpleExpression primitives page plus a separate node's parameter page), so collapsing them into
one enclosing range would make a hit against either individually-irrelevant page span count as
correct. A retrieved chunk is scored as a hit if it overlaps *any* one of these ranges, not the
envelope across all of them. Derived from real chunk_ids while authoring the set (see
eval/build_gold_set.py), not hand-typed.

Usage:
    python -m eval.run_eval --run-name sparse-baseline
"""

import argparse
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from config import AnswerTier

GOLD_SET_PATH = Path(__file__).parent / "gold_set.jsonl"
RESULTS_DIR = Path(__file__).parent / "results"

GoldCategory = Literal[
    "parameter_lookup", "node_lookup", "expression_syntax", "composed_animation", "out_of_scope"
]


class GoldExample(BaseModel):
    id: int
    category: GoldCategory
    question: str
    expected_tier: AnswerTier
    expected_breadcrumbs: list[str]
    expected_pages: list[list[int]]  # one [min_page, max_page] range per expected_breadcrumbs entry
    answer: str


def load_gold_set(gold_set_path: Path = GOLD_SET_PATH) -> list[GoldExample]:
    examples = []
    with gold_set_path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(GoldExample.model_validate_json(line))
    return examples


def _pages_overlap(a: list[int], b: list[int]) -> bool:
    """Both are [min_page, max_page] ranges."""
    return a[0] <= b[1] and b[0] <= a[1]


def _overlaps_any(retrieved_range: list[int], expected_ranges: list[list[int]]) -> bool:
    """A hit against any one of the gold answer's (possibly disjoint) expected ranges counts —
    see the expected_pages note at the top of this file for why they aren't collapsed into one."""
    return any(_pages_overlap(retrieved_range, er) for er in expected_ranges)


def recall_at_k(
    retrieved_page_ranges: list[list[int]], expected_pages: list[list[int]], k: int
) -> float:
    """Single-question recall: 1.0 if any of the top-k retrieved chunks' page range overlaps any
    of the gold answer's expected ranges, else 0.0. Average across the gold set for the
    corpus-level metric."""
    top_k = retrieved_page_ranges[:k]
    return 1.0 if any(_overlaps_any(r, expected_pages) for r in top_k) else 0.0


def precision_at_k(
    retrieved_page_ranges: list[list[int]], expected_pages: list[list[int]], k: int
) -> float:
    top_k = retrieved_page_ranges[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for r in top_k if _overlaps_any(r, expected_pages))
    return hits / len(top_k)


def _make_retriever(name: str):  # type: ignore[no-untyped-def]
    """Returns a `question -> list[Chunk]` callable for the named retrieval path. Imported
    lazily inside here (not at module top-level) so `--retriever lexical-baseline` doesn't pull
    in bge-m3/the reranker at all — those are only needed for the hybrid-* paths."""
    if name == "lexical-baseline":
        from retrieval.hybrid import lexical_baseline_retrieve

        return lambda q: lexical_baseline_retrieve(q, limit=10)
    if name == "hybrid-candidates":
        # Pre-rerank: dense + bge-m3-sparse fused with RRF. Measures the embedder/fusion stage
        # on its own — CLAUDE.md's heuristic is this stage only needs the right chunk somewhere
        # in the top ~30, so this is the fairest recall@10 comparison against the milestone-3
        # baseline (same k, same "did we find it at all" question).
        from retrieval.hybrid import retrieve_candidates

        return lambda q: retrieve_candidates(q)[:10]
    if name == "hybrid-reranked":
        # Full production pipeline: dense + RRF + rerank, capped at rerank_top_k (8). This is
        # what answer synthesis would actually see — precision@5 here is the meaningful number,
        # recall@10 is really recall@8 since the list is shorter by design.
        from retrieval.hybrid import retrieve

        return retrieve
    raise ValueError(f"unknown retriever: {name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-name", required=True)
    parser.add_argument(
        "--retriever",
        choices=["lexical-baseline", "hybrid-candidates", "hybrid-reranked"],
        default="lexical-baseline",
        help="lexical-baseline = milestone 3 (BM25/FTS only). hybrid-candidates = milestone 4's "
        "dense+bge-m3-sparse+RRF, pre-rerank. hybrid-reranked = the full pipeline including the "
        "cross-encoder rerank.",
    )
    args = parser.parse_args()

    examples = load_gold_set()
    print(f"[{args.run_name}] loaded {len(examples)} gold examples")
    print("by category:", dict(Counter(e.category for e in examples)))
    print("by expected tier:", dict(Counter(e.expected_tier for e in examples)))

    # out_of_scope examples have no expected_pages by design (see build_gold_set.py) — they test
    # the UNVERIFIED gate downstream, not retrieval accuracy, so they're excluded here rather
    # than silently scored as failures against nothing.
    scored = [e for e in examples if e.expected_pages]
    skipped = len(examples) - len(scored)

    retrieve_fn = _make_retriever(args.retriever)

    # Checkpoint to disk after every example — this eval hits an 8GB-RAM ceiling loading bge-m3 +
    # the reranker together and has been OOM-killed mid-run before. Resuming from a checkpoint
    # means a kill near the end doesn't cost redoing the whole run.
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint_path = RESULTS_DIR / f"{args.run_name}.checkpoint.jsonl"
    per_example: list[dict] = []
    done_ids: set[int] = set()
    if checkpoint_path.exists():
        with checkpoint_path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    row = json.loads(line)
                    per_example.append(row)
                    done_ids.add(row["id"])
        if done_ids:
            print(f"[{args.run_name}] resuming: {len(done_ids)}/{len(scored)} already checkpointed")

    with checkpoint_path.open("a") as checkpoint_f:
        for i, ex in enumerate(scored, start=1):
            if ex.id in done_ids:
                continue
            print(f"[{args.run_name}] scoring {i}/{len(scored)}: {ex.id}", flush=True)
            retrieved = retrieve_fn(ex.question)
            retrieved_ranges = [[c.page_start, c.page_end] for c in retrieved]
            recall10 = recall_at_k(retrieved_ranges, ex.expected_pages, k=10)
            precision5 = precision_at_k(retrieved_ranges, ex.expected_pages, k=5)
            row = {
                "id": ex.id,
                "category": ex.category,
                "question": ex.question,
                "recall@10": recall10,
                "precision@5": precision5,
                "top1_breadcrumb": retrieved[0].breadcrumb if retrieved else None,
            }
            per_example.append(row)
            checkpoint_f.write(json.dumps(row) + "\n")
            checkpoint_f.flush()

    mean_recall10 = sum(r["recall@10"] for r in per_example) / len(per_example)
    mean_precision5 = sum(r["precision@5"] for r in per_example) / len(per_example)

    by_category: dict[str, list[dict]] = defaultdict(list)
    for r in per_example:
        by_category[r["category"]].append(r)
    category_breakdown = {
        cat: {
            "n": len(rows),
            "recall@10": sum(row["recall@10"] for row in rows) / len(rows),
            "precision@5": sum(row["precision@5"] for row in rows) / len(rows),
        }
        for cat, rows in by_category.items()
    }

    print(f"\nscored {len(scored)} examples ({skipped} out_of_scope examples excluded)")
    print(f"recall@10:    {mean_recall10:.3f}")
    print(f"precision@5:  {mean_precision5:.3f}")
    print("\nby category:")
    for cat, stats in sorted(category_breakdown.items()):
        print(
            f"  {cat:20s} n={stats['n']:3d}  recall@10={stats['recall@10']:.3f}  "
            f"precision@5={stats['precision@5']:.3f}"
        )

    result_path = RESULTS_DIR / f"{args.run_name}.json"
    result_path.write_text(
        json.dumps(
            {
                "run_name": args.run_name,
                "retriever": args.retriever,
                "timestamp": datetime.now(UTC).isoformat(),
                "n_gold_examples": len(examples),
                "n_scored": len(scored),
                "n_skipped_out_of_scope": skipped,
                "mean_recall@10": mean_recall10,
                "mean_precision@5": mean_precision5,
                "by_category": category_breakdown,
                "per_example": per_example,
            },
            indent=2,
        )
    )
    print(f"\nlogged to {result_path}")
    checkpoint_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
