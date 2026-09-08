# Fusion Expression RAG

Retrieval over the DaVinci Resolve reference manual, built to write **Fusion expressions** —
springs, bounces, ease curves, squash-and-stretch — without inventing node names.

- **App:** https://davincirag.vercel.app
- **API:** https://fusion-rag-api.onrender.com

## Why it exists

Web search returns confidently wrong Fusion syntax. The manual is the only reliable source for
node names, input names, and expression grammar.

But the manual documents **primitives, not recipes**. There is no "how to make it bounce" page —
there's the `time` variable, `sin`/`cos`/`iif`, SimpleExpressions, and per-node parameter tables.
So retrieval's job is to *ground the syntax*, and the model composes the animation math on top.
That split is why answers carry a tier:

| Tier | Meaning |
|---|---|
| `GROUNDED` | The manual answers this directly. Cites page numbers. |
| `SYNTHESIZED` | The manual supplied verified primitives; the model composed the rest, marking which is which. |
| `UNVERIFIED` | Nothing relevant retrieved. General knowledge, explicitly flagged. |

An answer that admits it's unverified beats a confident wrong one. That's the whole point.

## How it works

```
question → query expansion → retrieval → sufficiency gate → tier → synthesis → answer + citations
```

**Retrieval has two modes** (`retrieval_mode` in `server/config.py`):

| | `lexical` (deployed) | `hybrid` |
|---|---|---|
| Retrieval | BM25 over LanceDB FTS | bge-m3 dense + sparse, RRF, cross-encoder rerank |
| Query expansion | string-matching glossary | glossary + Qwen2.5-0.5B rewrite |
| Models loaded | **none** | three (~5.5GB) |
| Memory | ~186MB | ~6GB |
| recall@10 / precision@5 | **0.955 / 0.334** | **0.970 / 0.358** |

The deployed service runs `lexical`. On the 67-example gold set that costs **one question**
(64/67 vs 65/67) and ties exactly on the hardest category — for 5.5GB less memory, which is what
made free hosting viable. The hybrid path is intact behind the config switch; its heavy
dependencies live in a `hybrid` extra, so `pip install .` never pulls torch.

**Generation is bring-your-own-key.** Paste an Anthropic key in the UI and Claude writes the
answer; the key is held in browser session state only — never written to disk, logged, or sent
anywhere but the request body. With no key, a shared free-tier Gemini fallback answers, clearly
labelled as reduced quality.

## Measured results

Every retrieval change is logged in `server/eval/results/` with its numbers, against a
hand-written gold set of 72 questions (67 scored; 5 `out_of_scope` test the UNVERIFIED gate).

| Run | recall@10 | precision@5 | Notes |
|---|---|---|---|
| `sparse-baseline-v2` | 0.910 | 0.313 | BM25 only |
| `hybrid-reranked-v2` | 0.925 | 0.331 | dense + RRF + rerank, no expansion |
| `hybrid-reranked-v3` | 0.627 | 0.299 | expansion applied to *everything* — a regression |
| `hybrid-reranked-v4` | **0.970** | **0.358** | expansion gated to procedural questions |
| `lexical-expanded-v1` | 0.955 | 0.334 | **deployed** — BM25 + glossary, no models |

The v3 row is kept deliberately. Expanding every query lifted `composed_animation` 0.615 → 0.923
but collapsed `node_lookup` and `parameter_lookup` from 1.000 to ~0.35, because lookup questions
already use the manual's vocabulary and paraphrasing corrupts them. Gating expansion to
*procedural* phrasing ("how do I make it bounce") kept the gain and restored the rest.

## Layout

```
server/     FastAPI backend — ingestion, retrieval, generation, eval
client/     Next.js frontend
deploy/     Deployment runbook, docker-compose + Caddy for a VM target
render.yaml Render blueprint (the deployed backend)
CLAUDE.md   The spec. Read it before changing anything.
```

## Local development

```bash
# Backend (full stack, both retrieval modes)
cd server
python3.12 -m venv .venv
./.venv/bin/pip install -e ".[hybrid,dev]"     # omit [hybrid] for the lean, model-free stack
./.venv/bin/uvicorn app.main:app --reload --port 8000

# Frontend
cd client && npm install && npm run dev
```

The prebuilt index is committed, so retrieval works immediately. Regenerating it from the PDF
(only needed if chunking changes) requires `data/raw/DaVinci Resolve Manual.pdf` locally:

```bash
./.venv/bin/python -m ingestion.ingest        # PDF → pages.jsonl → chunks.jsonl
./.venv/bin/python -m retrieval.build_index   # → LanceDB
./.venv/bin/python -m eval.run_eval --run-name <name> --retriever lexical-expanded
```

## Deployment

See `deploy/README.md`. Backend on Render's free tier (512MB, no credit card, sleeps after 15
idle minutes), frontend on Vercel. `render.yaml` configures the backend; the only value set by
hand is the Gemini key.

## Known issues

- **The sufficiency gate is non-deterministic.** Identical input has returned `partial` and
  `insufficient` across repeated runs, even at `temperature=0`, so an answer's tier — and whether
  its citations are shown — can vary between identical requests. Retrieval is unaffected. Two
  models (Qwen2.5-0.5B, Gemini Flash-Lite) proved unreliable at this three-way judgement, and a
  BM25 score floor was measured and rejected: out-of-scope questions score *higher* than in-scope
  ones (median 26.2 vs 23.6), because BM25 measures lexical match, not whether an answer exists.
  Untested lead: a stronger classifier via the BYOK Claude path.
- **Nothing measures tier accuracy.** `run_eval.py` scores retrieval only, so the three-tier
  system — arguably the project's core claim — has never been measured against the gold set's
  `expected_tier` labels.
- **The keyless Gemini quota is shared** across everyone using the site and is small. Supplying
  your own Anthropic key bypasses it entirely.
- **Cold starts are slow.** Render's free tier sleeps after 15 idle minutes and wakes on 0.1 CPU.

## A note on the corpus

The manual is Blackmagic's copyrighted work. The PDF and parsed text are **not** committed. The
LanceDB index is, deliberately — Render's filesystem is ephemeral and deploys from git, so the
service cannot answer anything without it. What the app serves publicly is unchanged: composed
answers with page-number pointers, not the manual's text. See CLAUDE.md's copyright note.
