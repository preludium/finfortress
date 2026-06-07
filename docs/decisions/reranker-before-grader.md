# Why reranker before grader, not instead of it?

## Context

The retrieval pipeline returns 12 candidates after RRF fusion. The grader scores each
chunk independently (up to 6 LLM calls) and decides whether retrieval was good enough —
if not, it triggers a rewrite. Question: wouldn't a reranker alone replace the grader's
LLM calls?

## This is not about model quality

The grader and reranker do fundamentally different jobs:

**Grader** asks: *"is this chunk good enough?"*
- Scores each chunk independently against a 0.6 threshold
- May pass 10 chunks or 2 — depends on the query
- Detects `temporal_mismatch` (a 2023 chunk answering a 2025 question)
- Triggers the rewrite loop when avg_grade < 0.6

**Reranker** asks: *"which chunk is the best among these 12?"*
- Always returns the best N, regardless of absolute scores
- Optimized for selection, not quality assessment
- Has no concept of staleness, triggers nothing

## Why both are needed

The reranker guarantees the grader receives the **best possible six** from 12 candidates,
not a random six that happened to pass a threshold. The grader still does its job —
assessing quality and freshness of that six, and deciding whether generation can proceed.

```
RRF (12) → reranker (12→6, selection) → grader (6→quality assessment) → generate / rewrite
```

## Impact

- Grader receives better chunks → higher avg_grade → fewer rewrite cycles
- Reranker runs locally (~100–200ms, no API cost), so the extra step is cheap
- Total LLM cost per query drops despite the additional node
