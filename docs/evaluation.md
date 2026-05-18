# Evaluation

## Why evaluation matters here

Financial Q&A has a higher correctness bar than most domains. A hallucinated IKE contribution limit or a wrong WIBOR rate is not a minor annoyance — it can lead to a real financial mistake. Evaluation is not optional for this project.

The evaluation pipeline runs automatically on every merge to main via GitHub Actions and blocks merges that regress key metrics below defined thresholds.

---

## RAGAS metrics

[RAGAS](https://docs.ragas.io) (Retrieval Augmented Generation Assessment) evaluates four dimensions independently:

### Faithfulness

**What it measures**: Are all claims in the generated answer supported by the retrieved context? A faithful answer never introduces facts that aren't in the retrieved chunks.

**Why it matters here**: The agent must not invent IKE limits, tax rates, or bond yields. If the retrieved context doesn't contain the answer, the agent should say so — not confabulate.

**Target**: ≥ 0.85. Below this threshold, the agent is hallucinating financial facts at an unacceptable rate.

### Answer relevance

**What it measures**: Does the answer actually address the question asked? An answer can be faithful (grounded in context) but still fail to answer the question.

**Why it matters here**: Polish financial questions are often precise. "Jaki jest limit IKE w 2025?" has a specific answer. An answer about IKE history that never states the limit is irrelevant regardless of how accurate it is.

**Target**: ≥ 0.80.

### Context recall

**What it measures**: Does the retrieved context contain the information needed to answer the question? Low context recall means the retriever is failing to find the relevant chunks.

**Why it matters here**: If the answer to "what is the current COI bond rate" is in our indexed documents but retrieval misses it, the agent either hallucinates or falls through to fallback. Both are bad.

**Target**: ≥ 0.80.

### Context precision

**What it measures**: Of the retrieved chunks, what fraction are actually relevant? Low precision means the retriever is returning noise alongside good chunks, which can confuse the generator.

**Why it matters here**: The grading step is specifically designed to improve context precision by filtering low-relevance chunks before generation. Low precision in evaluation indicates the grader threshold needs tuning.

**Target**: ≥ 0.75.

---

## Golden test set

Located at `data/eval/test_questions.json`. 30 questions covering all query types and all major source domains. **This file is committed to the repository** — it is the reproducibility anchor for all benchmark comparisons.

### Structure

```json
[
  {
    "id": "factual_ike_limit_2025",
    "question": "Jaki jest limit rocznych wpłat na IKE w 2025 roku?",
    "query_type": "factual",
    "expected_answer_contains": ["23 472", "IKE", "2025"],
    "expected_source_domains": ["knf.gov.pl", "inwestoredukacja.pl"],
    "should_not_contain": ["IKZE"],
    "notes": "Tests basic factual retrieval from KNF source"
  },
  {
    "id": "factual_wiron_vs_wibor",
    "question": "Czym różni się WIRON od WIBOR i który teraz obowiązuje?",
    "query_type": "factual",
    "expected_answer_contains": ["WIRON", "WIBOR", "reforma"],
    "expected_source_domains": ["nbp.pl"],
    "temporal_sensitive": true,
    "notes": "Tests temporal awareness — WIBOR being phased out. Old docs about WIBOR as current standard should trigger stale detection."
  }
]
```

### Question distribution

| Category | Count | Tests |
|---|---|---|
| Factual — IKE/IKZE | 5 | Limit retrieval, tax treatment, eligibility |
| Factual — mortgage | 4 | WIBOR/WIRON, RRSO, early repayment |
| Factual — bonds | 4 | COI/EDO rates, purchase process, inflation linking |
| Factual — taxes | 4 | PIT-38, Belka, ulga mieszkaniowa |
| Calculation | 4 | Mortgage payment, compound interest, inflation adjustment |
| Comparison | 4 | IKE vs IKZE, ETF vs obligacje, fixed vs variable rate |
| Advice | 3 | Open-ended investment questions — tests disclaimer generation |
| Temporal | 2 | Stale document detection, WIBOR→WIRON transition |
| Fallback | 2 | Unanswerable questions — tests graceful fallback quality |
| Cross-source | 2 | Questions requiring context from multiple sources |

---

## Running evaluation locally

```bash
# Run full RAGAS evaluation
python eval/run_ragas.py

# Run on a subset for quick iteration
python eval/run_ragas.py --subset factual

# Run on a single question
python eval/run_ragas.py --id factual_ike_limit_2025

# Output: eval/results/ragas_YYYY-MM-DD.json
```

The evaluation runner:
1. Loads each question from the golden test set
2. Runs the full agent pipeline (classify → retrieve → grade → generate)
3. Passes the question, retrieved context, and generated answer to RAGAS
4. Writes per-question scores and aggregate metrics to `eval/results/`

`eval/results/` is gitignored — only the test questions are committed, not the results. Results are posted as GitHub Actions PR comments instead.

---

## CI pipeline

```yaml
# .github/workflows/eval.yml — runs on every PR to main
- name: Run RAGAS evaluation
  run: python eval/run_ragas.py --output eval/results/ci.json

- name: Check thresholds
  run: python eval/check_thresholds.py --input eval/results/ci.json
  # Fails if:
  #   faithfulness     < 0.85
  #   answer_relevance < 0.80
  #   context_recall   < 0.80
  #   context_precision < 0.75

- name: Post results as PR comment
  uses: actions/github-script@v7
  # Posts a markdown table of metrics to the PR
```

---

## Manual spot-checking

Automated metrics catch regressions but don't catch everything. After each significant pipeline change, manually test these edge cases:

**Temporal sensitivity**
- Ask about current WIBOR/WIRON rate without specifying a date
- Expected: agent fetches live NBP data, not indexed documents
- Red flag: agent cites a 2022 WIBOR rate as current

**Advice disclaimer**
- Ask "Czy powinienem teraz kupić ETF czy obligacje?"
- Expected: answer includes a financial disclaimer, confidence marked "low"
- Red flag: agent gives a direct recommendation without disclaimer

**Graceful fallback**
- Ask about a very niche topic not in the corpus
- Expected: agent says it doesn't have enough information and suggests specific sources
- Red flag: agent hallucinates an answer or returns an empty response

**Cross-language**
- Ask the same question in English
- Expected: answer in English, citations still reference Polish sources
- Red flag: answer switches to Polish mid-sentence or cites English-only sources for Polish tax rules

**Source attribution**
- Ask about Inwestomat's recommendation on ETF selection
- Expected: citation explicitly names "inwestomat.eu — Mateusz Samołyk"
- Red flag: source attributed to KNF or left uncited

---

## Iterating on the pipeline

When a metric drops below threshold, follow this debugging order:

1. **Context recall drops** → retrieval problem. Check: embedding model, chunk size, BM25 weight in RRF, whether the relevant source is indexed and not stale.

2. **Context precision drops** → too much noise in retrieval. Check: grader threshold (raise from 0.6?), metadata filters, whether a source is producing poor-quality chunks (e.g. footer text not cleaned).

3. **Faithfulness drops** → generation problem. Check: system prompt constraints, whether the generator is ignoring low-confidence context, whether live tool data is being cited correctly.

4. **Answer relevance drops** → classification or generation problem. Check: classifier is correctly identifying query type, generator prompt is asking for a direct answer to the question asked.
