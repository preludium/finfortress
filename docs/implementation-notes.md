# Implementation notes

Practical knowledge accumulated during design. Read this before starting each
major component — it captures the "why didn't anyone tell me this" moments.

---

## Ingestion pipeline

### HTML cleaning is the most important step — don't skip it

Raw HTML from Inwestomat and Marcin Iwuć contains nav menus, cookie banners,
sidebar widgets, footer links, and comment sections. If you chunk without
cleaning, these end up as vectors in Qdrant. A retrieval for "IKE limit 2025"
will return "© 2024 Inwestomat. Wszelkie prawa zastrzeżone." as a top chunk.

Target only the article body. For both blogs, the content lives in:
- `article` tag
- `.entry-content`
- `.post-content`

Strip everything else before passing to the chunker. Verify by printing the
first 200 characters of each cleaned document — you should see article text,
not nav links.

### Implement hash-based deduplication before you write a single line of embedding code

The temptation is to get embedding working first, then "add deduplication later."
Don't. Once you've run the embedder once without dedup, you'll have duplicates in
Qdrant that silently degrade retrieval. Adding dedup after means either wiping
the collection and re-running, or writing a cleanup script.

Hash: `SHA-256(url + str(chunk_index) + page_content[:100])`
Store the hash in Qdrant payload as `"content_hash"`.
Before embedding, check `qdrant_client.scroll(filter={"content_hash": hash})`.
If it exists, skip.

### PDF extraction has a fallback chain — implement all three levels

Level 1: `PyMuPDF` (fitz) — fast, handles most PDFs well
Level 2: `pdfplumber` — better on tables and PDFs with complex layouts
Level 3: `pytesseract` OCR — for scanned government documents

Some older KNF and MF PDFs are scanned images, not text. PyMuPDF returns empty
strings for these. Always check `len(text.strip()) < 100` after extraction and
fall back automatically. Log which fallback was used — useful for debugging.

### Whisper transcription tip for Polish

Default Whisper (base model) works for Polish but makes errors on financial
terms: "WIBOR" becomes "Wibor" or "Vibor", "IKE" becomes "ike", "Belki"
becomes "belki". These lowercase/mangled versions still embed reasonably well
for semantic search but hurt sparse keyword matching — simplemma lemmatizes
correctly but can't fix a misspelled root.

Fix: post-process transcripts with a Polish financial term glossary. Simple
string replacement: `{"wibor": "WIBOR", "ike": "IKE", " belki": " Belki"}`.
Keep the glossary in `ingest/utils/pl_finance_glossary.py`.

### Excel rows need column context prepended

A row like `["COI0325", "6.55%", "2027-03-01"]` is useless without headers.
The embedder has no idea what these numbers mean.

Prepend headers: `"Seria: COI0325, Oprocentowanie: 6.55%, Data wykupu: 2027-03-01"`

This makes individual rows retrievable by semantic search AND BM25. Without it,
obligacje rate data is nearly unretrievable.

### robots.txt — check both blogs before scraping

Both inwestomat.eu and marciniwuc.com allow crawling as of the time of writing.
Always check `https://inwestomat.eu/robots.txt` before your first scrape and
add a polite delay (1.5s between requests). Use a descriptive User-Agent:
`"finfortress-bot/1.0 (personal RAG project, non-commercial)"`

---

## Embedding

### Use `intfloat/multilingual-e5-large` — not the base variant, not OpenAI

`multilingual-e5-base` (768 dims) is meaningfully worse on Polish financial
vocabulary in testing. The large model (1024 dims) is worth the extra compute.

On CPU-only (no GPU): large is slow (~2 chunks/second). Use base for development
iteration, switch to large for final ingestion run. Results differ noticeably.

### e5 models require a query prefix

This is the most common gotcha with multilingual-e5. The model was trained with
prefixes and performs significantly worse without them:

```python
# For documents being indexed:
text = f"passage: {chunk_text}"

# For queries at search time:
text = f"query: {user_question}"
```

LangChain's `HuggingFaceEmbeddings` does NOT add these prefixes automatically.
You need a custom wrapper:

```python
class E5Embeddings(HuggingFaceEmbeddings):
    def embed_documents(self, texts):
        return super().embed_documents([f"passage: {t}" for t in texts])

    def embed_query(self, text):
        return super().embed_query(f"query: {text}")
```

Skipping this tanks retrieval quality by 15–20% on Polish text. Easy to miss
because the pipeline still works — just worse.

### First embedding run will download ~2GB

`multilingual-e5-large` is ~2.2GB. It downloads to `~/.cache/huggingface/` on
first use. On a slow connection, plan for this. It's cached after the first
download — subsequent runs start immediately.

---

## Qdrant

### Always mount a volume — never run without `-v`

```bash
# WRONG — data lost on container stop
docker run -d -p 6333:6333 qdrant/qdrant

# RIGHT — data persists in ./qdrant_data/
docker run -d -p 6333:6333 \
  -v $(pwd)/qdrant_data:/qdrant/storage \
  qdrant/qdrant
```

If you forget the volume flag during development and run the embedder, you lose
everything and must re-embed. Add this to your startup checklist.

### Create the collection explicitly with the right distance metric and sparse config

Don't let LangChain create the collection implicitly — it uses defaults that
may not match. Create it explicitly:

```python
from qdrant_client.models import Distance, VectorParams, SparseVectorParams, Modifier

client.create_collection(
    collection_name="polish_finance",
    vectors_config=VectorParams(
        size=1024,                 # multilingual-e5-large output dim
        distance=Distance.COSINE,  # cosine, not dot product
    ),
    sparse_vectors_config={
        "bm25": SparseVectorParams(modifier=Modifier.IDF),
    },
)
```

Cosine similarity is correct for e5 embeddings. Dot product gives different
(worse) results for this model. The `sparse_vectors_config` is required for
hybrid retrieval — without it, only dense search runs.

### Sparse vectors are stored in Qdrant — no in-memory index at startup

The keyword (BM25-style) index lives in Qdrant as native sparse vectors. The collection must be created with `sparse_vectors_config`:

```python
from qdrant_client.models import SparseVectorParams, Modifier

client.create_collection(
    collection_name="polish_finance",
    vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
    sparse_vectors_config={"bm25": SparseVectorParams(modifier=Modifier.IDF)},
)
```

At ingest time each chunk gets a TF sparse vector (token → normalized frequency) alongside its dense vector. At query time Qdrant applies IDF server-side — no vocabulary file or corpus statistics to maintain locally.

**Migrating an existing collection** (no sparse config): the Qdrant server cannot add a new vector type to an existing collection. Run the one-time migration script:

```bash
just backfill-sparse   # scrolls all points, recreates collection, re-upserts with sparse
```

Safe to re-run — exits immediately if the collection already has sparse vectors.

**After a tokenizer change** (e.g. after upgrading lemmatization): existing sparse vectors use the old token IDs and must be recomputed. Use `--force` to bypass the idempotency check:

```bash
just reindex-sparse   # same as backfill-sparse --force — always rebuilds sparse vectors
```

---

## LangGraph agent

### AgentState rewrite_count must be initialised to 0 at invocation

```python
# WRONG — KeyError on first grade node
result = app.invoke({"question": "..."})

# RIGHT
result = app.invoke({"question": "...", "rewrite_count": 0, "give_up": False})
```

LangGraph doesn't initialise TypedDict defaults for you. Missing keys cause
cryptic KeyErrors inside nodes, not at invocation time.

### The grader prompt needs explicit JSON-only instruction

GPT-4o-mini will sometimes wrap JSON in markdown fences (```json ... ```) even
when instructed not to. Add to the grader system prompt:

`"Respond with raw JSON only. No markdown, no explanation, no code fences."`

And always use a try/except when parsing:

```python
import json, re

raw = grader_llm.invoke(prompt).content
# Strip fences just in case
raw = re.sub(r"```json?\n?|```", "", raw).strip()
grade = json.loads(raw)
```

### Temporal mismatch detection — tune the keywords list

The grader prompt asks the model to detect when a question implies current data.
The keywords that reliably trigger this in Polish:

```python
TEMPORAL_KEYWORDS = [
    "teraz", "aktualny", "aktualne", "aktualnie",
    "obecny", "obecne", "obecnie",
    "2025", "dziś", "dzisiaj",
    "ile wynosi", "jaka jest",
    "czy nadal", "czy wciąż",
]
```

Also trigger on rate-related nouns without a date: "WIBOR", "WIRON",
"oprocentowanie", "stopa procentowa", "rata" — these almost always imply
current data.

### The fallback response is as important as the answer

When `give_up=True`, don't return an empty string or a generic "I don't know."
Return something actionable:

```python
FALLBACK_TEMPLATE = """
I could not find reliable enough information to answer this question.

Check these authoritative sources directly:
- KNF / inwestoredukacja.pl — IKE, IKZE, investment funds
- podatki.gov.pl — tax questions (PIT, Belka tax)
- nbp.pl — current interest rates (WIBOR, WIRON, reference rate)
- obligacjeskarbowe.pl — current government bond rates

Your question: {question}
"""
```

This is what separates a trustworthy assistant from one that halluccinates when
it doesn't know. The fallback message is a feature, not a failure.

---

## FastAPI + streaming

### SSE streaming requires specific response headers

```python
from fastapi.responses import StreamingResponse

@app.post("/query")
async def query(request: QueryRequest):
    async def generate():
        async for chunk in agent.astream({"question": request.question, ...}):
            yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # critical for nginx proxying
        }
    )
```

Without `X-Accel-Buffering: no`, nginx buffers the entire response and the
user sees nothing until the answer is complete — defeating the purpose of
streaming.

### Test with curl before building any frontend

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"question": "Jaki jest limit IKE w 2025?"}' \
  --no-buffer
```

If streaming works in curl, it'll work in any frontend. If it doesn't work in
curl, no frontend will fix it.

---

## Streamlit

### Use `st.session_state` for chat history

Streamlit re-runs the entire script on every interaction. Without session_state,
chat history disappears on each message.

```python
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if question := st.chat_input("Zadaj pytanie..."):
    st.session_state.messages.append({"role": "user", "content": question})
    # ... run agent, append response
```

### Render citations as expandable sections, not inline text

Inline citations clutter the answer. Use `st.expander`:

```python
with st.expander(f"Sources ({len(result['citations'])})"):
    for cite in result["citations"]:
        st.caption(f"**{cite['source']}** — {cite['author']} ({cite['date']})")
        st.markdown(f"[Open ↗]({cite['url']})")
```

---

## Evaluation

### Run smoke_test.py before running full RAGAS

RAGAS costs API tokens (it uses an LLM to evaluate). The smoke test is free —
it just prints retrieved chunks for 5 known questions. If the smoke test shows
footer text or irrelevant chunks, fix the retriever before spending on RAGAS.

### Golden test set — write questions before you build

Write `data/eval/test_questions.json` before you build the agent, not after.
Writing questions after you've built it leads to unconsciously writing questions
your system happens to answer well. Write them from your own actual needs:
"what would I actually want to ask this thing?"

Good test questions for this project:
- "Jaki jest limit wpłat na IKE w 2025 roku?" (factual, specific year)
- "Czym różni się WIRON od WIBOR?" (temporal, transition topic)
- "Czy ETF w IKE płaci podatek Belki?" (factual, tax)
- "Jak obliczyć ratę kredytu hipotecznego przy WIRON 3M?" (calculation)
- "IKE czy IKZE — co wybrać dla osoby w 35% progu podatkowym?" (comparison)
- "Czy powinienem teraz kupić ETF?" (advice — must trigger disclaimer)
- "Jaka jest najlepsza kryptowaluta?" (fallback — not in corpus)

---

## Common errors and fixes

| Error | Cause | Fix |
|---|---|---|
| `KeyError: 'rewrite_count'` | AgentState not initialised | Pass `rewrite_count=0` at invocation |
| Empty retrieval results | e5 prefix missing | Add `query:` / `passage:` prefixes |
| `sparse index unavailable` warning | Collection has no sparse vectors | Run `just backfill-sparse` |
| Grader JSON parse error | LLM added markdown fences | Strip fences before `json.loads()` |
| Qdrant data lost on restart | No volume mount | Always use `-v $(pwd)/qdrant_data:/qdrant/storage` |
| Streamlit history reset | No `session_state` | Use `st.session_state.messages` |
| SSE not streaming | Missing nginx header | Add `X-Accel-Buffering: no` |
| Polish inflected forms not matching | Whitespace tokenizer (old) | Fixed: `sparse_vectorizer.tokenize()` uses `simplemma` Polish lemmatization + regex split. After changing, run `just backfill-sparse` to re-index. |
| Slow first embedding run | Model download | ~2.2GB download on first use, cached after |
| Wrong cosine similarity | Wrong distance metric | Use `Distance.COSINE` not `Distance.DOT` |

---

## Development order recommendation

Build in this order — each step is independently testable:

```
1. agent/state.py          — AgentState TypedDict, no dependencies
2. ingest/utils/chunker.py — pure function, easy to unit test
3. ingest/utils/cleaner.py — pure function, test on real HTML
4. ingest/utils/hasher.py  — pure function
5. ingest/scrape_blogs.py  — test on single article first
6. ingest/embed_and_store.py — test with 10 chunks before full run
7. agent/nodes/retrieve.py — test retrieval quality with smoke_test.py
8. agent/nodes/grade.py    — test grader on known good/bad chunks
9. agent/nodes/generate.py — test generation with known context
10. agent/graph.py         — wire nodes together
11. scripts/smoke_test.py  — verify end-to-end
12. app/streamlit_app.py   — first interactive interface
13. api/main.py            — FastAPI wrapper
14. eval/run_ragas.py      — formal evaluation
```

Don't jump to step 12 before step 11 is working. The temptation to build the
UI early is strong — resist it. A bad agent with a pretty UI is still a bad agent.
```
