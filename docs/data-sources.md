# Data sources

All sources indexed in the `polish_finance` Qdrant collection. See `data/sources_manifest.json` for machine-readable version with current chunk counts and scrape timestamps.

---

## Blogger sources

These are the primary opinionated sources — practical, Polish-context, real-world tested advice. They complement official sources by explaining *how* things work in practice, not just what the law says.

### inwestomat.eu

| Field | Value |
|---|---|
| Author | Mateusz Samołyk |
| Language | Polish |
| Content types | Blog articles (HTML), occasional Excel tools |
| Topics | ETFs on GPW, IKE/IKZE strategy, portfolio construction, Belka tax, obligacje skarbowe, passive investing |
| Scrape frequency | Weekly |
| Loader | `scrape_blogs.py` → `WebBaseLoader` + BeautifulSoup |
| Chunk strategy | RecursiveChar 512/64, split on `\n\n` first |
| robots.txt | Respected |
| Notes | Strong on data-driven ETF analysis and tax optimisation. Articles are long (3000–8000 words) and produce 20–60 chunks each. Excel tools downloaded separately and processed row-by-row. |

### marciniwuc.com

| Field | Value |
|---|---|
| Author | Marcin Iwuć |
|---|---|
| Language | Polish |
| Content types | Blog articles (HTML), YouTube video transcripts, occasional PDFs |
| Topics | Personal finance planning, mortgages, insurance, retirement planning, budgeting, investment psychology |
| Scrape frequency | Weekly (articles), manual (videos) |
| Loader | `scrape_blogs.py` (articles), `transcribe_videos.py` (YouTube) |
| Chunk strategy | Articles: RecursiveChar 512/64. Videos: 30s windows, 5s overlap |
| robots.txt | Respected |
| Notes | More holistic and planning-focused than Inwestomat. Video transcripts indexed with timestamp metadata. High value for mortgage and insurance topics. |

---

## Government and regulatory sources

Authoritative but dense. These ground the RAG in legal fact rather than opinion.

### KNF — Komisja Nadzoru Finansowego

| Field | Value |
|---|---|
| URL | `knf.gov.pl`, `inwestoredukacja.pl` |
| Language | Polish |
| Content types | HTML articles, PDFs |
| Topics | IKE/IKZE rules and limits, PPK, ETF regulation, TFI funds, investor protection |
| Scrape frequency | Monthly |
| Loader | `download_pdfs.py` + `scrape_blogs.py` |
| Notes | `inwestoredukacja.pl` is KNF's consumer-facing education portal — plainer language than main site. Both are indexed. IKE/IKZE contribution limits change in January each year — manual check triggered then. |

### Ministerstwo Finansów / podatki.gov.pl

| Field | Value |
|---|---|
| URL | `podatki.gov.pl` |
| Language | Polish |
| Content types | PDF guides, HTML |
| Topics | PIT filing, capital gains (PIT-38), Belka tax (19%), tax deductions, ulga mieszkaniowa, tax brackets |
| Scrape frequency | Yearly + on law change |
| Loader | `download_pdfs.py` |
| Notes | PIT-38 guide is the most important document for ETF investors — covers exactly how Belka tax applies to fund distributions and sale gains. Updated each tax year. |

### ISAP — Internetowy System Aktów Prawnych

| Field | Value |
|---|---|
| URL | `isap.sejm.gov.pl` |
| Language | Polish |
| Content types | Legal text (HTML + PDF) |
| Topics | Ustawa o PIT, Ustawa o IKE i IKZE, Ustawa o obligacjach, Ustawa o kredycie hipotecznym |
| Scrape frequency | On law change (manual trigger) |
| Chunk strategy | 1024/128 — legal articles are self-contained units |
| Loader | `download_pdfs.py` |
| Notes | Primary legal source. The RAG uses these for "what does the law actually say" queries. Chunk size increased to 1024 to avoid splitting individual legal articles. |

### NBP — Narodowy Bank Polski

| Field | Value |
|---|---|
| URL | `nbp.pl`, `api.nbp.pl` |
| Language | Polish / JSON |
| Content types | HTML reports (indexed), REST API (live tool) |
| Topics | WIBOR, WIRON, NBP reference rate, inflation reports, exchange rates |
| Indexed content | NBP monetary policy reports, inflation projections (quarterly) |
| Live tool | `tools/nbp_rates.py` — called at query time for current rates |
| Notes | **Current rates are never indexed** — always fetched live via `api.nbp.pl`. Reports are indexed for context (e.g. "why is WIRON replacing WIBOR?"). WIBOR→WIRON transition documents are specifically indexed as this is a common source of confusion. |

### Obligacjeskarbowe.pl — Ministerstwo Finansów

| Field | Value |
|---|---|
| URL | `obligacjeskarbowe.pl` |
| Language | Polish |
| Content types | HTML, Excel rate sheets |
| Topics | COI (inflation-linked), EDO (10-year), ROS/ROD (family bonds), current rates, purchase process |
| Indexed content | Product descriptions, FAQ, purchase guide |
| Live tool | `tools/obligacje_rates.py` — current rates fetched at query time |
| Notes | Rates reset on the 1st of each month. **Current rates fetched live**, not indexed. Product descriptions and eligibility rules are indexed. |

### UOKiK — Urząd Ochrony Konkurencji i Konsumentów

| Field | Value |
|---|---|
| URL | `uokik.gov.pl` |
| Language | Polish |
| Content types | HTML guides |
| Topics | Kredyt hipoteczny consumer rights, RRSO, early repayment, mortgage refinancing, complaints |
| Scrape frequency | Quarterly |
| Loader | `scrape_blogs.py` |
| Notes | Written for consumers, not lawyers. Most useful for mortgage-related queries about borrower rights. |

### BGK — Bank Gospodarstwa Krajowego

| Field | Value |
|---|---|
| URL | `bgk.pl` |
| Language | Polish |
| Content types | PDF program documentation |
| Topics | Government housing programs (Bezpieczny Kredyt 2%, Mieszkanie na Start), first-home buyer support |
| Scrape frequency | On program change (manual) |
| Loader | `download_pdfs.py` |
| Notes | Program eligibility rules, application process. Programs change or end — documents are date-tagged and grader detects when a program referenced in a document is no longer active. |

### CFPB — Consumer Financial Protection Bureau

| Field | Value |
|---|---|
| URL | `consumerfinance.gov` |
| Language | English |
| Content types | HTML guides |
| Topics | General personal finance concepts (mortgage mechanics, credit scores, compound interest) |
| Scrape frequency | Yearly |
| Notes | Supplementary source for general financial concepts not well covered in Polish sources. English only — filtered out for purely Polish regulatory queries. Useful for foundational "how does X work" questions. |

---

## Live API tools (not indexed)

These data sources are **never stored in Qdrant**. They are called fresh at query time as LangGraph tools.

### NBP API — api.nbp.pl

```
Endpoint: https://api.nbp.pl/api/
Format: JSON
Data: WIBOR 1M/3M/6M, WIRON O/N/1W/1M, NBP reference rate, EUR/USD/CHF/GBP rates
Called when: query_type == "calculation" OR temporal_mismatch detected on rate query
Rate limit: No official limit — add 0.5s delay between calls to be polite
```

### Obligacje rates scraper

```
Source: https://obligacjeskarbowe.pl/oferta-obligacji/
Format: HTML table (no official API)
Data: Current monthly rates for COI, EDO, OTS, ROS, ROD series
Called when: question mentions "obligacje", "COI", "EDO", "oprocentowanie obligacji"
Scrape: Fresh HTML parse at query time — no caching
```

---

## Source trust hierarchy

When retrieved chunks from different sources conflict, the agent uses this hierarchy to resolve:

1. **ISAP legal text** — what the law says (highest authority)
2. **KNF / Ministerstwo Finansów** — official regulatory interpretation
3. **NBP** — monetary policy facts
4. **UOKiK / BGK** — consumer guidance
5. **inwestomat.eu / marciniwuc.com** — practitioner interpretation (may be opinionated)
6. **CFPB** — general concepts only

The generator prompt instructs the model to note when sources conflict and to prefer higher-trust sources for factual claims while still surfacing blogger perspective for practical advice.

---

## What is not indexed

| Source | Reason |
|---|---|
| Social media (Twitter, Reddit r/Polska_Finansowa) | Too noisy, unverifiable, changes too fast |
| Bank product pages (mBank, PKO, Pekao) | Promotional content, not educational |
| News articles | Too transient — grader would flag most as stale within weeks |
| Forum discussions (Bankier.pl forum) | Anecdotal, not authoritative |
| Any source without clear authorship or date | Cannot perform temporal mismatch detection |
