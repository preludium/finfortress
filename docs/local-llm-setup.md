# Local LLM setup — oMLX

finfortress uses [oMLX](https://github.com/jundot/omlx) to run all LLMs locally on Apple Silicon.
oMLX exposes an OpenAI-compatible API at `localhost` — no code changes needed, just point the base URL there.

## Requirements

- macOS 15.0+
- Apple Silicon (M1–M4)
- 48 GB unified memory recommended (32 GB minimum — see model tiers below)

## Install oMLX

```bash
brew tap jundot/omlx https://github.com/jundot/omlx
brew install omlx
```

## Models

| Role | Model | RAM (4-bit) | Notes |
|---|---|---|---|
| Generator | `gemma-4-26B-A4B` (MoE) | ~15 GB | 26B total params, only 4B active during inference — fast + low RAM. Native JSON output. |
| Grader | `gemma-4-E4B` | ~6 GB | Native structured JSON output — no regex fence-stripping needed. Fires 6× per query. Fast edge model sufficient for binary relevance scoring. |
| Embeddings | `multilingual-e5-large` | ~3 GB | Runs via sentence-transformers, not oMLX |

**Total: ~25 GB** — comfortable on 48 GB M4 Pro.

### Smaller machines (16–32 GB)

| RAM | Generator | Grader |
|---|---|---|
| 16 GB | `gemma-4-E4B` (~7 GB) | `gemma-4-E2B` (~3 GB) |
| 32 GB | `gemma-4-26B-A4B` (~15 GB) | `gemma-4-E4B` (~7 GB) |

## Download models and start server

Start the server pointing at a local model directory:

```bash
mkdir -p ~/models
omlx serve --model-dir ~/models
```

Open the admin dashboard at `http://localhost:8000/admin` and download models from there.
Search for and download:

- `gemma-4-26B-A4B-it-OptiQ-4bit`
- `gemma-4-12B-it-OptiQ-4bit`

oMLX auto-discovers models in `--model-dir` and keeps loaded models in memory concurrently.
Default port: `8000`. Dashboard: `http://localhost:8000/admin`.

## Environment variables

Copy `.env.example` to `.env` and fill in:

```bash
OPENAI_BASE_URL=http://localhost:8000/v1
OPENAI_API_KEY=omlx-<your-key>     # find this in http://localhost:8000/admin → API Keys
LLM_MODEL=gemma-4-26B-A4B-it-OptiQ-4bit
GRADER_MODEL=gemma-4-12B-it-OptiQ-4bit
```

> **Note:** oMLX generates its own API key — find it in the admin dashboard under API Keys.
> The key format is `omlx-XXXXXXXXXXXX`.

The agent uses `ChatOpenAI` from `langchain-openai` pointed at `OPENAI_BASE_URL`.
No changes needed in agent code — the OpenAI-compatible API is a drop-in.

## Why these models

**gemma-4-26B-A4B for generation:** Mixture-of-Experts — 26B total parameters but only ~4B active during
inference. Faster than a 32B dense model at similar quality. Trained on 140+ languages including Polish.
Native structured output eliminates fence-stripping hacks in the generate node.

**gemma-4-E4B for grading:** The grader fires on every retrieved chunk — up to 6× per query across
retry loops. Native JSON output (no markdown fences) is the primary requirement — E4B (~4B params)
is fast enough for binary relevance scoring where speed matters more than deep reasoning.

**multilingual-e5-large for embeddings:** Purpose-built for multilingual dense retrieval.
Keeps Polish financial vocabulary (kredyt hipoteczny, obligacje skarbowe) semantically coherent.
oMLX has a `/v1/embeddings` endpoint (BGE-M3) but e5-large is already installed and benchmarked
for this corpus — no reason to swap.

## Verify setup

With oMLX running:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma-4-26B-A4B-it-OptiQ-4bit",
    "messages": [{"role": "user", "content": "Czym jest IKE?"}]
  }'
```

Should return a short Polish answer about Individual Retirement Accounts.
