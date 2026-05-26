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
| Generator | `Qwen2.5-32B-Instruct` | ~20 GB | Best reasoning + Polish quality at this size, reliable structured output |
| Grader | `Qwen2.5-7B-Instruct` | ~5 GB | Fast JSON scoring — grader fires 6× per query, smaller model keeps latency low |
| Embeddings | `multilingual-e5-large` | ~3 GB | Runs via sentence-transformers, not oMLX |

**Total: ~28 GB** — comfortable on 48 GB M4 Pro.

> If you want minimal setup, use `Qwen2.5-32B-Instruct` for both generator and grader.
> One model to manage, ~20 GB total — fully valid on 48 GB.

### Smaller machines (16–32 GB)

| RAM | Generator | Grader |
|---|---|---|
| 16 GB | `Qwen2.5-14B-Instruct` (~9 GB) | `Qwen2.5-7B-Instruct` (~5 GB) |
| 32 GB | `Qwen2.5-32B-Instruct` (~20 GB) | `Qwen2.5-7B-Instruct` (~5 GB) |

## Download models and start server

Start the server pointing at a local model directory:

```bash
mkdir -p ~/models
omlx serve --model-dir ~/models
```

Open the admin dashboard at `http://localhost:8000/admin` and download models from there.
Search for and download:

- `mlx-community/Qwen2.5-32B-Instruct-4bit`
- `mlx-community/Qwen2.5-7B-Instruct-4bit`

oMLX auto-discovers models in `--model-dir` and keeps loaded models in memory concurrently.
Default port: `8000`. Dashboard: `http://localhost:8000/admin`.

## Environment variables

Copy `.env.example` to `.env` and fill in:

```bash
OPENAI_BASE_URL=http://localhost:8000/v1
OPENAI_API_KEY=omlx-<your-key>     # find this in http://localhost:8000/admin → API Keys
LLM_MODEL=Qwen2.5-32B-Instruct-4bit
GRADER_MODEL=Qwen2.5-7B-Instruct-4bit
```

> **Note:** oMLX generates its own API key — find it in the admin dashboard under API Keys.
> The key format is `omlx-XXXXXXXXXXXX`.

The agent uses `ChatOpenAI` from `langchain-openai` pointed at `OPENAI_BASE_URL`.
No changes needed in agent code — the OpenAI-compatible API is a drop-in.

## Why these models

**Qwen2.5-32B for generation:** Best instruction-following and citation quality available locally at this
size. Strong Polish despite not being Polish-specific. Reliable structured output — important for the
`confidence` and `disclaimer` fields in the answer schema.

**Qwen2.5-7B for grading:** The grader fires on every retrieved chunk — up to 6× per query across
retry loops. A smaller, faster model keeps total latency acceptable. Qwen2.5-7B produces
reliable structured JSON output, which is the grader's primary requirement.

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
    "model": "Qwen2.5-32B-Instruct-4bit",
    "messages": [{"role": "user", "content": "Czym jest IKE?"}]
  }'
```

Should return a short Polish answer about Individual Retirement Accounts.
