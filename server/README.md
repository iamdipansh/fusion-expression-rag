# Fusion Expression RAG — server

FastAPI server for the hybrid retrieval pipeline described in the repo-root `CLAUDE.md`. Read
that file first — it's the spec.

## Setup

Requires Python 3.12 (installed via `brew install python@3.12` — the system Python was 3.9,
too old for this ML stack).

```bash
python3.12 -m venv .venv
./.venv/bin/pip install -e ".[hybrid,dev]"
```

`[hybrid]` pulls torch, transformers and FlagEmbedding for the dense+rerank path. Omit it for the
lean, model-free stack that actually gets deployed — that's what `pip install .` installs, and
what keeps the deployed image in the hundreds of MB rather than several GB.

Copy `.env.example` to `.env` if you need to override any setting in `config.py`.

## Layout

- `config.py` — every setting lives here, nothing scattered
- `ingestion/` — milestone 1: PDF -> pages (`parse.py`) -> chunks (`chunk.py`), CLI in `ingest.py`
- `retrieval/` — both paths are built. Lexical: `store.py`'s
  `lexical_search`/`write_chunks_lexical_only` (LanceDB native FTS, no embedding model) and
  `hybrid.py`'s `lexical_baseline_retrieve`/`lexical_expanded_retrieve`. Hybrid: `embed.py`,
  `rerank.py`, `store.py`'s `dense_search`/`sparse_search`/`write_chunks` (bge-m3 learned sparse —
  a different mechanism from the lexical/FTS baseline, see the module docstring), and `hybrid.py`'s
  dense+RRF+rerank. `retrieve()` dispatches between them on `config.retrieval_mode`; the
  hybrid-only imports are lazy so the lean install never touches torch.
- `generation/` — `local_llm.py` (Qwen2.5-0.5B query rewrite, the glossary, the local sufficiency
  gate) and `synthesize.py` (BYOK Claude, Gemini fallback, tier prompts, the remote gate)
- `app/` — FastAPI app, request/response schemas, routers
- `eval/` — milestone 2 (done): `build_gold_set.py` generates `gold_set.jsonl` (72 Q/A pairs,
  grounded against real chunk_ids — regenerate after any ingestion change); `run_eval.py` has the
  `GoldExample` schema, recall@k/precision@k, and a real CLI that logs results to `eval/results/`
- `data/` — `raw/` holds the manual PDF and `parsed/` the JSONL output of ingestion; both stay
  untracked, being the most directly reproducible form of Blackmagic's copyrighted work.
  `index/fusion_manual.lancedb` **is** tracked, decided deliberately: Render's filesystem is
  ephemeral and deploys from git, so the service can't answer anything without it. See CLAUDE.md's
  copyright note. `index/sparse_weights.json` stays untracked — 17MB only the hybrid path reads.

## Status

**Milestones 1-7 are done and the service is deployed** (https://fusion-rag-api.onrender.com).
Milestone 8, the Resolve-API validation loop, was always optional and isn't started. Current
retrieval numbers and known issues live in the repo-root README; this section covers how to
regenerate each artifact.
- Milestone 1 (ingest + chunk): `ingestion/parse.py` and `ingestion/chunk.py` are real. Run
  `./.venv/bin/python -m ingestion.ingest` against `data/raw/DaVinci Resolve Manual.pdf`
  (Resolve 21, 4,444 pages) to regenerate `data/parsed/pages.jsonl` and
  `data/parsed/chunks.jsonl` — currently ~5,800 chunks.
- Milestone 2 (gold eval set): `./.venv/bin/python -m eval.build_gold_set` regenerates
  `eval/gold_set.jsonl` from real chunk_ids (72 examples).
- Milestones 3-4 (retrieval): `./.venv/bin/python -m retrieval.build_index` builds the LanceDB
  index, then `./.venv/bin/python -m eval.run_eval --run-name <name> --retriever <r>` measures it.
  Retrievers: `lexical-baseline`, `lexical-expanded`, `hybrid-candidates`, `hybrid-reranked`.
  Results land in `eval/results/`; the comparison table is in the repo-root README.

  Note the eval numbers in `*-v1.json` predate a gold-set fix and are **not** comparable to later
  runs — `build_gold_set.py` used to collapse every source chunk into one `[min_page, max_page]`
  span, so a question grounded in two distant sections scored a hit anywhere in a ~1,300-page
  window. Compare v2 and later only.

`app/main.py` and the `/health`, `/query` routes are runnable locally:

```bash
./.venv/bin/uvicorn app.main:app --reload --port 8000
```

### Ingestion design notes (read before touching parse.py/chunk.py)

Breadcrumbs come from the PDF's embedded bookmark tree, which goes down to level-3 subsections
with per-page precision — treat it as ground truth over any font-size heuristic. About 1 in 8
bookmarks has no PDF destination (mostly chapter-title entries whose first subsection has one but
the title itself doesn't); `extract_heading_checkpoints` resolves those via a bounded,
whitespace-insensitive text search between the bookmark's nearest resolved neighbors, requiring
the match to start its own line (`find_heading_start`) so it can't be fooled by a heading's name
recurring in the very next sentence, or by a "Contents" mini-TOC listing the same title.

Several regex-based cleanup passes in `_clean_text` strip PDF layout furniture with no content
value: running page footers, the redundant "Chapter N" stub before a chapter's real title,
dot-leader glyphs (decode as U+FFFD) and a broken discretionary-hyphen glyph (U+FFFE) in words
like "right-click", and per-chapter/part "Contents" mini-TOC blocks (both the per-chapter
`Contents` and all-caps part-level `CONTENTS` variants) — the latter matters beyond cosmetics
since an unstripped listing can fool the bookmark resolver above.

`_classify_content_type` treats "Term: description" runs (Resolve's dominant style for
documenting UI controls and node parameters — prose, not PDF tables) as `parameter_reference`;
missing this on the first pass was why that category had ~9 chunks instead of ~1,800.

**Known limitations, found via the required 50-chunk hand-inspection (do not skip it after
changing this code):**
- The "Menu Descriptions" appendix (last ~15 pages) has all 14 menu-category bookmarks (File,
  Edit, Trim, ...) pointing at the *same* PDF destination, so those chunks all inherit the last
  one's breadcrumb ("...Help"). Bookmark-tree breadcrumbing can't recover finer granularity there
  without a bespoke text-scanning heuristic just for this low-relevance corner (menu shortcuts,
  not Fusion expression content) — not built, on purpose.
- Figure captions are not extracted (`PageRecord.figure_captions` is always `[]`).
- A residual few chunks are pure navigation-index noise (e.g. a "Step N–Title ... pageNum" summary
  block) that didn't match the Contents-block stripper's exact shape. Rare enough (~1 in 50 in the
  hand sample) that further regex-chasing has diminishing returns — let the milestone 2-4 eval
  loop tell you if it actually costs recall/precision before spending more time here.

## Before touching ingestion code further

Consult the `pdf` skill for extraction strategy / table / figure extraction if extending
`parse.py` further. Always re-run the 50-random-chunk hand inspection after any change to
`parse.py` or `chunk.py` — every fix above was found that way, not by reasoning about the code.
