# Deploying Fusion Expression RAG

## Which retrieval mode you're deploying

The backend ships in **lexical** mode (`FUSION_RAG_RETRIEVAL_MODE=lexical`): BM25 over LanceDB's
FTS index plus a string-matching glossary for query expansion, loading no models at all. That's a
measured choice — on the 67-example gold set, lexical scored recall@10 0.955 / precision@5 0.334
against the full hybrid stack's 0.970 / 0.358, tying exactly on the hardest category
(composed_animation, 0.846 both). One question's difference, for ~5.5GB of resident models.

What it buys: the image drops torch entirely and runs in roughly 200-400MB instead of ~6GB, so it
fits free tiers that don't ask for a credit card (Render, Koyeb) rather than needing a 24GB VM.

What it costs: the sufficiency gate and keyless generation both go to Gemini's free tier, so every
query depends on an external API — a deliberate departure from CLAUDE.md's constraint #1 ("no paid
API dependency in the serving path"), and bounded by that tier's ~1,000 requests/day.

To deploy the hybrid stack instead: build with `pip install '.[hybrid]'` (see server/Dockerfile),
set `FUSION_RAG_RETRIEVAL_MODE=hybrid`, and give it ~6GB RAM — which is what the Oracle
instructions below are sized for.

---

Two services, two hosts, zero recurring cost:

- **Backend** (`server/`) → Oracle Cloud's Always Free Ampere A1 VM if running hybrid; in lexical
  mode any ~512MB free tier works, which sidesteps Oracle's credit-card verification entirely.
- **Frontend** (`client/`) → Vercel's free tier — zero-config for Next.js, trivial for a mostly
  client-side app like this one.

Steps marked **(you)** need your own action — account creation, cloud console clicks, or
anything involving payment/identity details — and can't be done from here. Steps without that
marker are commands to run yourself in a terminal (copy-pasted, not run automatically, since
they touch infrastructure that doesn't exist until you provision it).

---

## Part 1 — Backend on Render (recommended)

Render's free tier needs no credit card, which is why it's the default here. 512MB RAM, 0.1 CPU,
sleeps after 15 idle minutes with a ~1 minute cold start, 750 instance-hours/month per workspace.
The measured footprint is 186MB peak, so the RAM is not the constraint — the 0.1 CPU is what makes
cold starts slow.

`render.yaml` at the repo root already declares the service, so there's no dashboard
configuration to get wrong.

1. **(you)** Sign up at [render.com](https://render.com) and connect your GitHub account.
2. **(you)** **New → Blueprint**, pick `iamdipansh/fusion-expression-rag`. Render reads
   `render.yaml` and configures the service itself.
3. **(you)** It will prompt for `FUSION_RAG_GEMINI_API_KEY` — the one value marked `sync: false`,
   so it lives in the dashboard rather than the repo. Paste the same key from `server/.env`. In
   lexical mode this powers both the sufficiency gate and keyless generation, so the service
   can't answer without it.
4. **(you)** Deploy. First build takes a few minutes.
5. Verify: `curl https://<your-service>.onrender.com/health` → `{"status":"ok","index_loaded":true}`

`index_loaded: true` confirms the committed LanceDB index shipped with the repo — that's the whole
reason it's tracked (see CLAUDE.md's copyright note).

Then skip to **Part 2** for the frontend, and **Part 3** to point CORS at it.

---

## Part 1 (alternative) — Backend on Oracle Cloud

### 1. Create an Oracle Cloud account **(you)**

Go to [oracle.com/cloud/free](https://www.oracle.com/cloud/free/) and sign up for the **Always
Free** tier. It asks for a card for identity verification but the Always Free resources
(including the ARM VM below) never expire and never charge — just don't provision anything
outside the "Always Free eligible" labeled options.

### 2. Provision the Always Free ARM VM **(you)**

In the OCI Console:

1. **Compute → Instances → Create Instance**
2. **Image and shape**: change shape to `VM.Standard.A1.Flex` (Ampere ARM) — this is the Always
   Free one. Give it the full allotment: 4 OCPUs, 24GB RAM.
3. **Image**: Canonical Ubuntu 22.04 (aarch64/ARM build).
4. **Networking**: use the default VCN, and check **"Assign a public IPv4 address."**
5. **SSH keys**: let OCI generate a key pair, or paste your own public key (`~/.ssh/id_ed25519.pub`
   if you have one). Save the private key — you'll need it to SSH in.
6. Create the instance. Note its **public IP** once it's running — you'll need it repeatedly
   below.
7. **Open the firewall**: go to the instance's subnet → **Security Lists** → the default list →
   **Add Ingress Rules**. Add two rules, source CIDR `0.0.0.0/0`, destination ports **80** and
   **443** (TCP). Without this, Caddy can't get a certificate or serve traffic — the VM's own
   firewall (`iptables`/`ufw`) usually allows these by default on a fresh Ubuntu image, but the
   OCI security list blocks them until you open it explicitly.

### 3. SSH in and install Docker

```bash
ssh -i /path/to/your/private/key ubuntu@<VM_PUBLIC_IP>

# On the VM:
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker
docker --version
docker compose version
```

### 4. Clone this repo onto the VM

The repo is private, so the VM needs its own read-only deploy key rather than your personal
GitHub credentials.

```bash
# On the VM:
ssh-keygen -t ed25519 -C "oracle-vm-deploy-key" -f ~/.ssh/deploy_key -N ""
cat ~/.ssh/deploy_key.pub
```

Copy that output. **(you)** In GitHub: `github.com/iamdipansh/fusion-expression-rag` → **Settings
→ Deploy keys → Add deploy key** → paste it, leave "Allow write access" unchecked, save.

```bash
# Back on the VM:
cat >> ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile ~/.ssh/deploy_key
EOF
git clone git@github.com:iamdipansh/fusion-expression-rag.git
cd fusion-expression-rag
```

### 5. Transfer the prebuilt index

The manual PDF, parsed pages, and vector index are gitignored (copyrighted, derived content —
see `server/.gitignore`), so they need a direct transfer from your Mac, not a git pull.

```bash
# On your Mac, not the VM:
rsync -avz --progress \
  "/Users/dipansh/Desktop/Davinci RAG/server/data/" \
  ubuntu@<VM_PUBLIC_IP>:~/fusion-expression-rag/server/data/
```

This sends ~250MB (the PDF, parsed JSONL, and LanceDB index) — only needs to happen once, and
again any time you rebuild the index locally.

### 6. Configure and launch

```bash
# On the VM:
cd ~/fusion-expression-rag/deploy
cp .env.example .env
nano .env   # fill in BACKEND_DOMAIN using the VM's public IP, e.g. 140-238-12-34.sslip.io
docker compose up -d --build
```

First build takes a few minutes (installing torch, transformers, etc.). Watch it come up:

```bash
docker compose logs -f backend
```

The first request after that will trigger downloading bge-m3, the reranker, and Qwen2.5-0.5B
from Hugging Face (a few GB total) — expect the first real query to take a minute or two; after
that they're cached in the `hf-cache` volume and stay warm indefinitely (this VM never sleeps).

### 7. Verify

```bash
curl https://<BACKEND_DOMAIN>/health
# {"status":"ok","index_loaded":true}
```

If this hangs or errors, check `docker compose logs caddy` (usually a firewall/port issue — see
step 2.7) or `docker compose logs backend`.

---

## Part 2 — Frontend on Vercel

### 1. Import the project **(you)**

Go to [vercel.com/new](https://vercel.com/new), sign in with GitHub, and import
`iamdipansh/fusion-expression-rag`.

### 2. Configure the monorepo root **(you)**

Vercel will ask for a **Root Directory** — set it to `client`. It auto-detects Next.js from
there; leave build/output settings on their defaults.

### 3. Set the API URL **(you)**

Under **Environment Variables**, add:

```
NEXT_PUBLIC_API_BASE_URL = https://<BACKEND_DOMAIN>
```

using the same `BACKEND_DOMAIN` from Part 1.

### 4. Deploy **(you)**

Click Deploy. Vercel gives you a URL like `https://fusion-expression-rag.vercel.app` when it's
done.

---

## Part 3 — Close the loop (CORS)

The backend only accepts requests from origins listed in `CORS_ORIGINS`. Update it now that you
have the real Vercel URL:

**On Render:** dashboard → your service → **Environment** → set
`FUSION_RAG_CORS_ORIGINS` to `["https://your-app.vercel.app"]` (a JSON array, not
comma-separated — pydantic-settings parses list fields as JSON). Saving triggers a redeploy.

**On an Oracle VM instead:**

```bash
cd ~/fusion-expression-rag/deploy
nano .env   # set CORS_ORIGINS=["https://fusion-expression-rag.vercel.app"]
docker compose up -d
```

Open the Vercel URL and ask a question — this is the first real end-to-end test of the deployed
app.

---

## Updating after a code change

```bash
# Frontend: Vercel redeploys automatically on every push to main. Nothing to do.

# Backend, on the VM:
cd ~/fusion-expression-rag
git pull
cd deploy
docker compose up -d --build
```
