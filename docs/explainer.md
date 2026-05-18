# FinFortress — Complete Technical Explainer

For a software engineer with no prior ML/NLP background.
After reading this you should be able to explain every component to anyone.

---

## 1. The core problem

GPT-4o knows a lot about finance in general. It does not know:
- The exact IKE contribution limit for 2025 (changes yearly)
- The current COI bond rate (changes monthly)
- The exact text of the Polish ustawa o IKE/IKZE
- What Mateusz Samołyk wrote last week on inwestomat.eu

If you ask GPT-4o "what's the 2025 IKE limit?", it will answer confidently
with a number. That number might be from 2022. There's no way to tell.

This is the **hallucination problem**: LLMs generate plausible-sounding text
based on training data, not live facts. For financial advice, wrong facts
cause real harm.

**Solution: RAG (Retrieval-Augmented Generation)**

Instead of asking the model to recall facts from training, we:
1. Retrieve relevant text from a database of authoritative Polish sources
2. Hand that text to the model as context
3. Tell the model to answer ONLY from what it was given

The model's job becomes synthesis and explanation, not recall.

---

## 2. What is an embedding?

An embedding converts text into a list of numbers (a vector). Similar meaning
= similar numbers = nearby points in space.

Example (simplified to 2D):
```
"IKE"                     → [0.2, 0.8]
"konto emerytalne"        → [0.21, 0.79]   ← similar to IKE
"kredyt hipoteczny"       → [0.9, 0.1]    ← different topic
"mortgage"                → [0.88, 0.11]  ← similar to kredyt hipoteczny
```

In reality we use 1024 dimensions, not 2. The model is
`intfloat/multilingual-e5-large` — trained on multilingual text including
Polish. It knows that "konto emerytalne" and "IKE" are semantically related
even though they share no words.

**Why not OpenAI embeddings?** OpenAI's ada-002 was trained mostly on English.
Polish financial terms like "WIBOR", "ulga mieszkaniowa", "kredyt hipoteczny"
degrade — the model places them in wrong regions of the space. e5-large handles
Polish correctly because it was trained on multilingual data.

**The critical gotcha:** e5-large was trained with prefixes. You MUST add them:
```python
# When indexing documents:
text = f"passage: {chunk_text}"

# When searching:
text = f"query: {user_question}"
```
Without these prefixes, retrieval quality drops 15-20%. LangChain doesn't add
them automatically — we wrote a custom `E5Embeddings` wrapper.

---

## 3. What is a vector database?

A normal database answers: "find rows where content LIKE '%IKE%'"
A vector database answers: "find the 6 nearest vectors to this query vector"

**Qdrant** is our vector database. It stores each text chunk as:
```json
{
  "id": "uuid",
  "vector": [0.12, -0.34, ...],   // 1024 numbers
  "payload": {                     // metadata
    "page_content": "Limit wpłat na IKE...",
    "source": "inwestomat.eu",
    "author": "Mateusz Samołyk",
    "date": "2025-01-10",
    "content_type": "blog_article",
    "content_hash": "sha256..."
  }
}
```

At query time:
1. Embed the user's question → query vector
2. Ask Qdrant: "find 6 vectors closest to this" (cosine similarity)
3. Get back 6 chunks with their payloads

**Why Qdrant over alternatives?**
- Chroma: simple but weak metadata filtering
- FAISS: no metadata filtering at all
- Pinecone: cloud-only
- Qdrant: rich payload filters (filter by `year > 2023`, `content_type = pdf_gov`),
  Docker-native, production-ready

---

## 4. Chunking — why we cut articles into pieces

A blog article about IKE is 5000 words. One vector for 5000 words is too
diffuse — it represents "everything about IKE" not "the specific paragraph
about the contribution limit."

We cut each article into overlapping windows:
```
chunk_size = 512 tokens (~400 words)
chunk_overlap = 64 tokens (~50 words)
```

The overlap ensures a sentence split across chunk boundaries still appears
fully in at least one chunk.

**Separator hierarchy** (RecursiveCharacterTextSplitter):
Split on `\n\n` first (paragraph), then `\n` (line), then `. ` (sentence),
then ` ` (word). This preserves semantic units — a paragraph about IKE limits
stays in one chunk rather than being split mid-sentence.

**Legal text exception:** `chunk_size=1024` for ISAP legal documents. Each
legal article (artykuł) is a self-contained unit that should not be split.

---

## 5. The ingestion pipeline

```
Source → Loader → Cleaner → Chunker → Hasher → Embedder → Qdrant
```

### Loader (scrape_blogs.py, download_pdfs.py)

Each source type has a dedicated loader:
- **Blog HTML** (inwestomat, marciniwuc): requests + BeautifulSoup, targets
  `article/.entry-content/.post-content`, strips nav/footer/cookies/comments
- **PDFs** (KNF, ISAP, MF): PyMuPDF → pdfplumber → pytesseract OCR fallback chain
- **Excel** (obligacje rates): pandas, column headers prepended to each row

### Cleaner (cleaner.py)

Strips HTML boilerplate. The most important step — without it, "© 2024
Inwestomat. Wszelkie prawa zastrzeżone." ends up as a retrievable chunk.

### Chunker (chunker.py)

RecursiveCharacterTextSplitter. Adds `chunk_index` and `chunk_total` to
metadata so citations can say "chunk 3 of 12."

### Hasher (hasher.py)

```python
SHA-256(url + str(chunk_index) + page_content[:100])
```

Stored in Qdrant payload as `content_hash`. Before embedding, check if hash
exists → skip if yes. Makes the pipeline safe to re-run without duplicates.

### Embedder (embed_and_store.py)

Loads e5-large, adds `passage:` prefix, encodes in batches of 32, upserts to
Qdrant. Collection created with `Distance.COSINE` (correct for e5 — dot
product gives wrong results with this model).

---

## 6. The query pipeline — LangGraph

Every user question flows through a directed graph of nodes. Each node reads
from and writes to a shared `AgentState` TypedDict.

```
START
  ↓
classify       → sets query_type, needs_live_data
  ↓
fetch_live     → if needs_live_data: fetch NBP rates / obligacje rates
  ↓
retrieve       → hybrid search: dense (Qdrant) + BM25, merged with RRF
  ↓
grade          → score each chunk 0-1 for relevance, detect stale data
  ↓
[needs_rewrite?]
  ├─ NO  → generate → END
  ├─ YES, rewrite_count < 2 → rewrite → retrieve (loop)
  └─ YES, rewrite_count >= 2 → fallback → END
```

### Why LangGraph?

LangGraph manages the conditional retry loop. Without it you'd write:
```python
while rewrite_count < 2:
    context = retrieve(query)
    grade = grade_context(context)
    if grade.avg >= 0.6:
        break
    query = rewrite(query)
answer = generate(context)
```

That's brittle — no state management, no streaming, no observability.
LangGraph handles state passing between nodes, allows conditional edges,
and provides `astream()` for SSE streaming.

---

## 7. Hybrid retrieval

Two retrievers run in parallel, results merged with Reciprocal Rank Fusion:

**Dense retrieval (Qdrant):**
- Embed query with `query:` prefix
- Find top-6 nearest vectors by cosine similarity
- Finds semantically similar chunks even with different keywords
- "konto emerytalne" finds "IKE" chunks

**BM25 (keyword search):**
- Classic keyword ranking algorithm (TF-IDF variant)
- Built in-memory at startup from all Qdrant payloads (~3s for 20k chunks)
- Finds exact term matches: "WIRON 3M 2025-01" won't appear in dense results
  if it's a rare term, but BM25 finds it directly

**Reciprocal Rank Fusion (RRF):**
```
score(doc) = 0.6 × 1/(60 + rank_dense) + 0.4 × 1/(60 + rank_bm25)
```
Documents appearing in both ranked lists get boosted. Dense weighted 60%,
BM25 40% — financial queries benefit more from semantic than keyword matching.

**Why hybrid?**
Dense alone misses exact product codes (COI0325, WIRON 3M).
BM25 alone misses synonyms (kredyt = mortgage, konto = account).
Together they cover both. RRF consistently outperforms either alone.

---

## 8. The grading loop — why it exists

RAG without grading answers from whatever it retrieved, relevant or not.
Example: user asks "what's the 2025 IKE limit?" — retriever returns 6 chunks
about passive investing portfolios. Without grading, GPT-4o answers anyway,
possibly hallucinating a number.

The grader (Qwen2.5-7B via oMLX) receives each chunk + the question and
returns:
```json
{"score": 0.0-1.0, "temporal_mismatch": false, "reason": "..."}
```

**Threshold: 0.6.** Below this, the chunk is treated as noise.
**Temporal mismatch:** True when the document date is >18 months old AND the
question implies current data (keywords: teraz, aktualny, ile wynosi, WIBOR...).
A 2022 document answering "what's the current WIBOR?" is dangerous.

If `avg_grade < 0.6` OR any chunk has `temporal_mismatch=True`:
→ rewrite the query and try again (max 2 times)
→ after 2 failures: graceful fallback with source suggestions

**Why GPT-4o-mini / Qwen2.5-7B for grading, not the main model?**
The grader does a simple binary task (is this relevant?) not complex reasoning.
A 7B model is 5-10x cheaper and faster. Grading fires 6 times per query —
using the 32B model for this would be expensive and slow.

---

## 9. Query rewriting

When grading fails, the rewriter produces a more specific query:

**Low relevance:** adds Polish financial context terms
```
"IKE" → "limit rocznych wpłat na IKE 2025 Polska indywidualne konto emerytalne"
```

**Stale data:** adds year constraint
```
"WIBOR" → "aktualna stawka WIBOR 3M 2025 Polska stopa referencyjna GPW Benchmark"
```

Maximum 2 rewrites. This prevents infinite loops while giving the retriever
two chances to find relevant content.

---

## 10. Live data tools

Some data changes daily (exchange rates) or monthly (bond rates). Indexing
it would make it stale within hours. We never index it — always fetch fresh.

**nbp_rates.py:** calls `api.nbp.pl` REST API for EUR/USD/CHF/GBP exchange
rates. Returns JSON, parses to formatted string injected into the generate
prompt as `live_data`.

**obligacje_rates.py:** scrapes `obligacjeskarbowe.pl` product pages for all
8 bond series (COI, EDO, OTS, ROR, DOR, TOS, ROS, ROD). No official API
exists — fresh HTML parse on each call.

Both tools are triggered in `fetch_live` node when `needs_live_data=True` AND
the question contains matching keywords.

**Routing bypass:** if `live_data` is present, the agent skips the grade
threshold check and proceeds to generate. The live data IS the answer — poor
retrieved context is expected (the corpus doesn't index rates).

---

## 11. External tools reference

| Tool | What it is | Why we use it |
|---|---|---|
| **LangGraph** | Python library for stateful agent graphs | Manages the classify→retrieve→grade→rewrite loop cleanly with conditional edges and streaming |
| **Qdrant** | Vector database (Docker) | Persistent, rich metadata filtering, efficient cosine search |
| **multilingual-e5-large** | HuggingFace embedding model (local) | Handles Polish financial vocabulary correctly; free; data stays local |
| **rank-bm25** | Python BM25 implementation | Keyword search alongside dense vectors for exact term matching |
| **oMLX** | Local LLM inference server (Apple Silicon) | Runs Qwen2.5 models locally via OpenAI-compatible API; no API costs |
| **Qwen2.5-32B-Instruct** | Main generator LLM | Best locally-runnable model for Polish reasoning and citation |
| **Qwen2.5-7B-Instruct** | Grader LLM | Fast, reliable JSON output for relevance scoring |
| **sentence-transformers** | Python library for e5-large | Loads and runs the embedding model |
| **FastAPI** | Python web framework | REST API with async streaming SSE support |
| **Streamlit** | Python UI library | Fast browser demo without writing JavaScript |
| **BeautifulSoup** | HTML parser | Extracts article body from blog HTML |
| **PyMuPDF (fitz)** | PDF extractor | Fast, handles most PDFs |
| **pdfplumber** | PDF extractor | Better on complex layouts and tables |
| **pytesseract** | OCR | Scanned government PDFs |
| **python-dateutil** | Date parser | Parses various date formats from HTML/PDFs |
| **RAGAS** | Evaluation framework | Measures faithfulness, answer relevance, context recall |
| **LangSmith** | Observability platform | Traces every LLM call and retrieved chunk in production |
| **uv** | Python package manager | Faster than pip, proper dependency locking |

---

## 12. The AgentState — the spine of the system

Every node reads from and writes partial updates to this shared dict:

```python
class AgentState(TypedDict):
    question:      str            # original question, never changes
    current_query: Optional[str]  # rewritten query (None = use question)
    query_type:    str            # factual / calculation / comparison / advice
    needs_live_data: bool         # should we call NBP/obligacje APIs?
    context:       List[Document] # retrieved chunks from Qdrant+BM25
    avg_grade:     float          # mean relevance score (0-1)
    needs_rewrite: bool           # true if avg_grade < 0.6 or stale
    stale_data:    bool           # true if any chunk has temporal mismatch
    rewrite_count: int            # how many rewrites so far (max 2)
    live_data:     Optional[str]  # formatted live rates string
    answer:        Optional[str]  # final answer text
    citations:     Optional[List[Citation]]
    confidence:    Optional[str]  # high / medium / low
    disclaimer:    Optional[str]  # non-None for advice queries
    give_up:       bool           # true after 2 failed rewrites
```

`question` is immutable after classify. `current_query` is what the retriever
actually uses — set by the rewrite node on retry. This preserves the original
question for the generator to answer correctly.

---

## 13. Confidence levels

The final answer includes a confidence level derived from `avg_grade`:

| avg_grade | confidence | Meaning |
|---|---|---|
| ≥ 0.8 | high | Retrieved chunks directly answer the question |
| 0.6–0.8 | medium | Chunks are related but not a perfect match |
| < 0.6 | low | Weak retrieval — answer may be incomplete |

For live data queries (rates), confidence is always low because the retrieved
corpus chunks score low (they don't contain current rates). The answer quality
is still high — the accurate information comes from live_data, not context.
This is a known limitation to explain to users.

---

## 14. What "advice" queries get a disclaimer

When `query_type == "advice"` (user asks "should I invest in X?"), the
generator appends:

> WAŻNE: Poniższa odpowiedź ma charakter wyłącznie informacyjny i edukacyjny.
> Nie stanowi rekomendacji inwestycyjnej ani porady finansowej.

This is both a legal necessity (unlicensed investment advice is regulated in
Poland) and a user trust signal. The classify node detects advice queries by
phrases like "czy powinienem", "co wybrać dla mnie", "czy warto".

---

## 15. Source trust hierarchy

When retrieved chunks from different sources conflict, the generator uses:

1. **ISAP legal text** — what the law says (highest authority)
2. **KNF / Ministerstwo Finansów** — official regulatory interpretation
3. **NBP** — monetary policy facts
4. **UOKiK / BGK** — consumer guidance
5. **inwestomat.eu / marciniwuc.com** — practitioner interpretation (may be opinionated)
6. **CFPB** — general concepts only (English, supplementary)

The generator prompt instructs the model to note when sources conflict and
prefer higher-trust sources for factual claims.

---

## 16. How to explain this to someone in 2 minutes

> "It's a Q&A assistant that only answers from authoritative Polish financial
> sources — not from the model's training data.
>
> When you ask a question, it searches a database of 5000+ text chunks from
> KNF, NBP, tax office PDFs, and top Polish finance blogs. It grades the
> results for relevance and freshness. If the results are bad, it rephrases
> the question and tries again. Only after finding good sources does it
> generate an answer — and every claim is cited.
>
> For live data like exchange rates or bond rates, it fetches directly from
> official APIs instead of searching the database. This prevents stale data.
>
> The whole pipeline runs locally on your Mac — no data leaves your machine."
