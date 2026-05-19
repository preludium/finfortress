# FinFortress

A self-correcting RAG assistant for Polish personal finance — grounded in indexed Polish sources, not generic LLM knowledge.

---

## The problem

Generic LLMs handle Polish financial questions poorly. They have no reliable knowledge of current IKE/IKZE contribution limits, WIBOR/WIRON rates, Belka tax rules, or BGK housing programmes — and they hallucinate specifics confidently. The problem is structural: this information is Poland-specific, changes yearly, and is underrepresented in LLM training data.

FinFortress solves it by retrieval: answers are built from indexed authoritative Polish sources (KNF, NBP, podatki.gov.pl, inwestomat.eu, marciniwuc.com) and verified for relevance before generation. A grader LLM scores each retrieved chunk and triggers a query rewrite if quality is low. Current rates are never indexed — they're fetched live at query time.

---

## How it works

```
Question
   │
   ▼
┌──────────┐
│ Classify │  → query_type (factual | calculation | comparison | advice)
└──────────┘    needs_live_data flag
   │
   ▼
┌────────────┐
│ Fetch live │  → calls NBP API or obligacje scraper when needed
└────────────┘
   │
   ▼
┌──────────┐
│ Retrieve │  → dense (e5-large / Qdrant) + sparse (BM25), merged with RRF
└──────────┘    returns top-6 chunks
   │
   ▼
┌──────────┐
│  Grade   │  → scores each chunk 0–1 for relevance, detects stale docs
└──────────┘
   │
   ├── avg_grade ≥ 0.6 ─────────────────────────────────┐
   │                                                     ▼
   ├── needs_rewrite, rewrite_count < 2 ──► Rewrite ──► Retrieve (loop)
   │
   └── give_up (max rewrites exhausted, grade still low)
          │                                              │
          ▼                                              ▼
      ┌──────────┐                                ┌──────────┐
      │ Fallback │                                │ Generate │
      └──────────┘                                └──────────┘
      transparent no-answer +                     answer + citations +
      source suggestions                          confidence + disclaimer
```

The graph is implemented with LangGraph. See [`docs/architecture.md`](docs/architecture.md) for full design rationale.

---

## Stack

| Layer | Default (local) | Alternative (cloud) |
|---|---|---|
| Generator LLM | `Qwen2.5-32B-Instruct-4bit` via oMLX | OpenAI GPT-4o |
| Grader LLM | `Qwen2.5-7B-Instruct-4bit` via oMLX | OpenAI GPT-4o-mini |
| Embeddings | `intfloat/multilingual-e5-large` (local) | — |
| Vector store | Qdrant (Docker) | Qdrant Cloud |
| Keyword search | BM25 (rank-bm25, in-memory) | — |
| Retrieval fusion | Reciprocal Rank Fusion | — |
| Agent orchestration | LangGraph | — |
| API | FastAPI + SSE streaming | — |
| Demo UI | Streamlit | Streamlit Cloud |

The default setup runs entirely locally on Apple Silicon (48 GB unified memory recommended). See [`docs/local-llm-setup.md`](docs/local-llm-setup.md) for oMLX setup and model tiers by RAM.

---

## Personalised answers

By default FinFortress answers general questions about Polish finance. Add a personal profile and it answers in the context of your specific situation — income, tax bracket, mortgage, IKE/IKZE contributions, investment horizon — without you repeating it in every message.

```bash
cp data/user_profile.example.md data/user_profile.md
# opisz swoją sytuację finansową, zrestartuj aplikację
```

See the [**Personal profile**](docs/getting-started.md#set-up-your-personal-profile) section in the getting-started guide.

---

## Data sources

| Source | Type | Topics |
|---|---|---|
| inwestomat.eu | Blog HTML | ETFs, IKE/IKZE, Belka tax, passive investing |
| marciniwuc.com | Blog HTML | Mortgages, retirement planning, budgeting |
| KNF / inwestoredukacja.pl | Gov HTML + PDF | IKE/IKZE rules, PPK, fund regulation |
| podatki.gov.pl | PDF | PIT filing, capital gains (PIT-38), Belka tax |
| isap.sejm.gov.pl | Legal text | Ustawa o PIT, IKE/IKZE, obligacjach |
| obligacjeskarbowe.pl | HTML | Bond product descriptions, purchase guide |
| uokik.gov.pl | Gov HTML | Mortgage consumer rights, RRSO |
| bgk.pl | PDF | Government housing programmes |
| nbp.pl | HTML reports | WIBOR/WIRON transition, inflation reports |

Current WIBOR/WIRON, NBP reference rate, and bond rates are always fetched live at query time — never indexed. See [`docs/data-sources.md`](docs/data-sources.md) for full source detail.

---

## Quick start

```bash
git clone https://github.com/your-username/finfortress && cd finfortress
uv sync
cp .env.example .env          # fill in OPENAI_API_KEY or oMLX config
docker compose up -d          # start Qdrant
bash scripts/ingest_all.sh    # index all sources (~30–90 min)
streamlit run app/streamlit_app.py
```

Full setup instructions, including oMLX local LLM configuration and smoke testing: [`docs/getting-started.md`](docs/getting-started.md)

---

## Documentation

| Doc | What it covers |
|---|---|
| [`docs/getting-started.md`](docs/getting-started.md) | Installation, configuration, personal profile setup, ingestion, smoke testing |
| [`docs/architecture.md`](docs/architecture.md) | Design decisions with rationale: retrieval, grading, embedding, vector store |
| [`docs/api.md`](docs/api.md) | API reference: POST /query, POST /query/stream (SSE), GET /health |
| [`docs/configuration.md`](docs/configuration.md) | All environment variables with defaults |
| [`docs/data-sources.md`](docs/data-sources.md) | Every source: type, topics, trust hierarchy, what is excluded |
| [`docs/local-llm-setup.md`](docs/local-llm-setup.md) | oMLX setup and model recommendations by RAM |
| [`docs/implementation-notes.md`](docs/implementation-notes.md) | Practical gotchas: e5 prefixes, Qdrant volume, grader JSON parsing |
| [`docs/evaluation.md`](docs/evaluation.md) | RAGAS methodology and golden test set |

---

## License

MIT
