# CLAUDE.md — Fusion Expression RAG

Project context for Claude. Read this before writing any code in this repo.

---

## What we're building

A retrieval system over the **DaVinci Resolve reference manual** (~4,000 pages, born-digital PDF), used to author **Fusion expressions** — spring, bounce, squash-and-stretch, and similar procedural animation.

**The real problem:** web search returns wrong or hallucinated Fusion syntax. The manual is the only reliable source for node names, input names, and expression grammar. Retrieval exists to *ground the syntax*, not to find finished answers.

**Important:** the manual does **not** contain recipes for "spring animation" or "squash and stretch." It documents primitives — the `time` variable, SimpleExpressions, Custom Tool, the Lua/Python scripting surface, and per-node parameter tables. The model composes the animation math on top of verified primitives. Design every component around that split.

**Scale:** ~1.5–2M tokens, roughly 3,000–5,000 chunks. Runs on a laptop. No Pinecone, no Kubernetes, no LangChain — at this size they cost more than they give.

---

## Constraints

1. **Zero recurring cost.** Free-tier or self-hosted only. No paid API dependency in the serving path.
2. **No compromise on retrieval quality.** Constraint 1 must not degrade recall or precision — see "Why free is not a compromise" below.
3. **Personal use, publicly hosted.** A single-user tool with a public URL, not a product.

## Open decisions (ask before assuming)

1. ~~**Manual version**~~ — **Resolved: Resolve 21.** PDF lives at
   `server/data/raw/DaVinci Resolve Manual.pdf` (4,444 pages, confirmed via PDF metadata + cover
   page). `config.py`'s `manual_version` and `manual_pdf_path` are set accordingly.
2. **Copyright posture.** The manual is Blackmagic's copyrighted work; a public site serving its text back is redistribution. Public-safe design: Claude-composed answers, citations as *page-number pointers* into the official PDF rather than reproduced text, quotes held to a sentence or two. Settle before milestone 5.
3. **Host.** See Hosting below — free-tier terms need verifying against the actual account.

---

## Why free is not a compromise

The open models here are not budget substitutes:

- `bge-m3` is competitive with paid embedding APIs on a corpus this size, and emits **dense + sparse lexical weights in one pass** — exactly what exact-token Fusion syntax (`Transform1.Center`, `nTime`, `Fusion.GetPrevKeyFrame`) needs.
- `bge-reranker-v2-m3` is a strong cross-encoder, competitive with commercial rerank endpoints.

**Tuning heuristic:** in a hybrid pipeline the reranker carries more quality than the embedder. The bi-encoder only has to land the right chunk in the top 30; the cross-encoder picks the top 6. If RAM gets tight, **shrink the embedder, never the reranker.**

---

## Architecture

**Ingestion (local, one-time).** `pypdfium2` or `pdfplumber` for text + layout; pdfplumber for tables. Pull the embedded bookmark tree — it gives the chapter/section hierarchy for free and is the highest-value artifact in the pipeline. No OCR needed. Output JSONL, one record per page: raw text, heading spans, tables, figure captions, page number. **Parse once, never re-parse.**

> Do **not** use PyMuPDF. It is AGPL; this project is publicly hosted. `pypdfium2` is permissively licensed. Swapping the parser later means re-running ingestion from scratch, so get this right the first time.

**Chunking.** Structure-aware, not fixed-window. Split on the heading hierarchy, then break oversized sections at paragraph boundaries with ~15% overlap. Target 400–800 tokens. Tables flatten to markdown and never split mid-row.

Chunk metadata:

- `breadcrumb` — e.g. `Part 9 → Fusion Page → Animating in Fusion → Expressions`
- `page_start`, `page_end`
- `content_type` — `prose` | `table` | `parameter_reference` | `code_example` | `ui_description`
- `has_expression_syntax` — regex flag for `:GetValue()`, `Point(`, `time`, `sin(`, `iif(`

**Retrieval — hybrid, non-negotiable.** Dense + sparse, fused with Reciprocal Rank Fusion (k=60), then rerank top ~30 → top 6–8 with the cross-encoder. `bge-m3` supplies both dense and sparse; keep SQLite FTS5 as a cheap cross-check during evaluation and drop it if it adds nothing.

**Query expansion.** Rewrite "how do I make something bounce" into Fusion vocabulary before retrieval. Large win — user phrasing and manual phrasing barely overlap.

**Parent-document retrieval.** Embed small chunks for precision, return the full parent section for context.

**Answer tiering.** Three tiers, always rendered visibly:

1. `GROUNDED` — strong retrieval, cites page numbers
2. `SYNTHESIZED` — manual supplies primitives, model composes the expression, marked as derived from cited syntax
3. `UNVERIFIED` — nothing relevant retrieved, general knowledge, explicit warning

Gate with a cheap sufficiency check (`sufficient | partial | insufficient`) over retrieved chunks — more reliable than thresholding cosine similarity. An answer that admits it's unverified beats a confident wrong one; that's the entire point of the project.

**Validation loop (milestone 7).** Resolve ships a Python/Lua scripting API. Create a comp programmatically, set the expression on a node input, check for errors → generate/test/repair. Optional for v1; keep interfaces clean enough to bolt on.

---

## Stack

| Layer | Choice | Cost |
|---|---|---|
| Parsing | pypdfium2 + pdfplumber | free, permissive licence |
| Embeddings | `bge-m3`, local | free |
| Rerank | `bge-reranker-v2-m3`, local (ONNX-quantized for serving) | free |
| Store | LanceDB — vectors + metadata + FTS in one file | free |
| Orchestration | plain Python | free |
| API | FastAPI | free |
| UI | Gradio (fastest) or Next.js | free |
| Generation | BYOK — see below | free to host |
| Eval | Ragas + hand-written gold set | free |
| Resolve | free version includes the full Fusion page | free |

### Generation: bring your own key

Hosted, so no copy-paste hybrid. The UI accepts an API key held **in session state only — never written to disk, never logged, never echoed back.** The operator pastes their own Anthropic key.

Split the calls:

- **Query expansion + sufficiency check** → small local model, works with no key at all
- **Final answer synthesis** → BYOK Claude
- **No key present** → optional Gemini free-tier fallback, clearly labelled as reduced quality

Note for anyone assuming otherwise: a Claude Pro/Max subscription does **not** include API access. Separate products, separate billing.

---

## Hosting

**Ship the index as a static prebuilt artifact.** The manual never changes — ingestion, chunking and embedding are one-time local jobs. The server only embeds a query and reranks, which is why 2 CPU cores suffice.

Candidates, in order:

1. **Hugging Face Spaces** — 16GB RAM / 2 vCPU / 50GB non-persistent disk; free hardware sleeps after ~48h idle (fine here). ⚠️ HF docs currently state that creating a *compute* Space (Gradio or Docker) requires a paid plan, while Static Spaces stay free. Third-party sources disagree. **Verify against the actual account before building for this target.**
2. **Oracle Cloud Always Free ARM** — 4 cores / 24GB RAM, no expiry, no sleep. More setup, most headroom.
3. **Google Cloud Run** — scale-to-zero, but cold-starting a reranker is painful and it wants a card on file.

**Cold starts are the real tradeoff, not answer quality.** First request after sleep spends 30–60s loading models. Mitigate with ONNX-quantized weights (~4× smaller) and lazy-loading the reranker only on first query. Acceptable for a personal tool.

---

## Milestones

1. Ingest + chunk. **Hand-inspect 50 random chunks.** Fix chunking. Do not skip the inspection.
2. Gold eval set: 50–80 hand-written Q/A pairs — parameter lookups, "which node does X," expression syntax, composed-animation questions.
3. Sparse-only baseline. Measure recall@10, precision@5.
4. Add dense + RRF + rerank. Measure the delta against baseline.
5. Answer generation with the three-tier gate.
6. Thin UI + BYOK key handling.
7. Deploy.
8. Resolve-API validation loop.

Build the eval set **before** tuning the retriever. Without it you're tuning blind.

---

## Skills

### Already available — use these

- **`pdf-reading`** — consult before writing any ingestion code. Extraction strategy, page rasterization for visual inspection, table and embedded-image extraction. Directly relevant to milestone 1.
- **`frontend-design`** — milestone 6 if the UI goes beyond Gradio defaults.
- **`xlsx`** — if the gold eval set is maintained as a spreadsheet rather than JSON.
- **`skill-creator`** — for authoring the custom skills below.

### Worth authoring for this project

Use `skill-creator` for each. Keep `SKILL.md` under 500 lines, push detail into `references/`, and make descriptions slightly pushy — Claude under-triggers skills otherwise.

**1. `fusion-expressions`** — highest value. The verified syntax layer.
- `SKILL.md`: expression grammar, SimpleExpression vs. Custom Tool vs. scripting, common failure modes
- `references/node-inputs.md`: exact input names per commonly-used node
- `references/math-patterns.md`: spring, damped oscillator, ease curves, squash-and-stretch volume preservation — the compositions the manual *doesn't* have
- Trigger: any Fusion expression request, including phrasings like "make this bounce"

**2. `resolve-manual-ingest`** — the chunking contract as an executable spec.
- Metadata schema, heading-detection heuristics, table-flattening rules
- `scripts/ingest.py` so re-runs are deterministic
- Prevents chunking drift when ingestion is revisited months later

**3. `rag-eval`** — the measurement discipline.
- Gold-set format, metric definitions, how to report a before/after delta
- `scripts/run_eval.py`
- Trigger: any retrieval change, so no unmeasured tuning ships

Order: `fusion-expressions` first (it pays off before RAG even works), then `resolve-manual-ingest`, then `rag-eval`.

### Tooling

- Filesystem access for the corpus and index
- A Resolve scripting bridge for milestone 8 — likely a small local MCP server wrapping the Resolve Python API

---

## Conventions

- Type hints on all functions; `ruff` + `mypy`
- Config in one `config.py`, no scattered constants
- Every retrieval experiment logged with its eval numbers — no undocumented tuning
- API keys live in session state only. Never persisted, never logged, never rendered
- Never fabricate a node name, input name, or function signature. If it isn't in retrieved context, mark the answer `UNVERIFIED`
