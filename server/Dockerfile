# Runs on Oracle Cloud's Always Free Ampere A1 (arm64) — python:3.12-slim ships multi-arch
# manifests, so a native `docker build` on that host pulls the arm64 base automatically.
FROM python:3.12-slim

WORKDIR /app

# Most dependencies ship prebuilt wheels (including linux/arm64) — a compiler is cheap insurance
# against a wheel gap in any one transitive dependency, not a requirement we've hit.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Only what's needed to serve a query: app (API), config, ingestion (Chunk model + its own
# imports), retrieval, generation. eval/ and tests/ are dev-only, left out of the runtime image.
COPY pyproject.toml config.py ./
COPY app app
COPY ingestion ingestion
COPY retrieval retrieval
COPY generation generation

# Lean by default: this installs neither torch nor transformers nor FlagEmbedding (they live in
# the `hybrid` extra), which is what keeps the image in the hundreds of MB rather than several GB
# and lets it run on a 512MB free tier. The container therefore must run in lexical retrieval
# mode — FUSION_RAG_RETRIEVAL_MODE=lexical, set in deploy/docker-compose.yml.
#
# For a full hybrid image instead (needs ~5.5GB RAM at runtime, so a bigger host):
#   RUN pip install --no-cache-dir '.[hybrid]'
RUN pip install --no-cache-dir .

# bge-m3, bge-reranker-v2-m3, and Qwen2.5-0.5B-Instruct download from the Hugging Face Hub on
# first request and cache under HF_HOME — see deploy/docker-compose.yml, which mounts this as a
# named volume so weights persist across container restarts instead of re-downloading every time.
ENV HF_HOME=/root/.cache/huggingface

# data/ (the prebuilt LanceDB index) is not baked into the image — it's a local artifact
# transferred to the host separately (see deploy/README.md) and mounted as a volume, since the
# manual it's derived from is copyrighted and never committed to git.

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
