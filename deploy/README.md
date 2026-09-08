# Deploying Fusion Expression RAG

Two services, two hosts, zero recurring cost:

- **Backend** (`server/`) → Oracle Cloud's Always Free Ampere A1 VM — the only free tier with
  enough RAM to hold bge-m3 + the reranker + Qwen2.5-0.5B in memory at once without sleeping or
  cold-starting on every idle return.
- **Frontend** (`client/`) → Vercel's free tier — zero-config for Next.js, trivial for a mostly
  client-side app like this one.

Steps marked **(you)** need your own action — account creation, cloud console clicks, or
anything involving payment/identity details — and can't be done from here. Steps without that
marker are commands to run yourself in a terminal (copy-pasted, not run automatically, since
they touch infrastructure that doesn't exist until you provision it).

---

## Part 1 — Backend on Oracle Cloud

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

```bash
# On the VM:
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
