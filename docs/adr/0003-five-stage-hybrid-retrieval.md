# ADR-0003: Five-stage hybrid retrieval — BM25 + dense (e5) + cross-encoder + LLM listwise rerank + citation engine

## Status

Accepted (2026-05-22)

## Context

The retrieval surface of the knowledge base feeds two downstream consumers: the Assistant dialogue (needs `[1]/[2]`-style citation-grounded answers) and the 5-axis similar-cases ranker (needs domain-similarity ordering on top of text similarity — see [ADR-0004](0004-five-axis-weighted-similarity.md)). Both consumers require:

1. **High recall on the first stage** — the casebook is small (synthetic PoC corpus, hundreds of cases) but the production target is thousands. A miss in the first stage cannot be recovered downstream.
2. **High precision after rerank** — the Assistant dialogue surfaces at most 5 cases; the cross-encoder must filter aggressively enough that the top 5 are domain-correct candidates.
3. **Citation link-back** — every retrieved chunk must carry a stable identifier back to its source artefact (PMI case ID, paper chunk ID), so the Assistant's `[1]/[2]` markers are reproducible.
4. **Japanese + English bilingual** — engagement notes are predominantly Japanese; reference papers are predominantly English. The encoder and tokenizer must work bilingually without per-language pipelines.
5. **Run in the default $0 / no-credit-card path** — see [Selected under](../../README.md#selected-under). No paid embedding API in the default code path.

## Decision

A five-stage retrieval pipeline, composed of permissively-licensed components, where each stage's role is fixed and downstream consumers see a uniform `RetrievalResult` schema:

| Stage | Component | License | Role |
| --- | --- | --- | --- |
| 1 — lexical recall | `rank-bm25` | Apache-2.0 | Tokenized BM25 over case text + paper chunks. Recovers exact-term matches that dense retrieval drops. |
| 2 — dense recall | `multilingual-e5-large` via `sentence-transformers`, served from `faiss-cpu` index | MIT (model) + MIT (faiss) | Semantic recall; handles JP↔EN paraphrase. |
| 3 — cross-encoder rerank | `cross-encoder/ms-marco-MiniLM-L-12-v2` | Apache-2.0 | Pairwise (query, candidate) scoring; reorders the union of stages 1+2 by domain-textual relevance. |
| 4 — LLM listwise CoT rerank | `LLMProvider` Protocol (3-tier swap: mock / Ollama / paid API) | MIT (Anthropic SDK), MIT (Ollama) | Listwise chain-of-thought rerank over top-K candidates from stage 3, producing a calibrated final order. |
| 5 — citation-grounded retrieval | `LlamaIndex CitationQueryEngine` | MIT | Wraps the final ranking into a citation-array response shape, with `[1]/[2]` markers tied to source artefact IDs. |

The pipeline is invoked from [src/orchestrator/build_state_graph.py](../../src/orchestrator/build_state_graph.py) as a sequence of LangGraph nodes; intermediate `RetrievalResult` objects pass through Pydantic v2 boundary validation.

## Why this composition (not a single stage)

### Stage 1 + 2 together (not either alone)

BM25 alone misses paraphrase ("post-merger integration" vs "PMI"); dense alone misses exact-term anchors (deal codenames, ISIN codes, financial band labels). Their union recovers both. The union step is unweighted set-merge (RRF-style ordering at this stage; final ordering is decided by stages 3–4).

### Stage 3 cross-encoder before stage 4 LLM rerank

Cross-encoder rerank is ~100× cheaper per (query, candidate) pair than an LLM call and is enough to drop most stage-1+2 noise. Reserving the LLM for the listwise pass over the cross-encoder top-K is the cost / quality balance — listwise LLM rerank without a cross-encoder filter would either blow the token budget or force a much smaller K.

### Stage 5 last (not earlier)

LlamaIndex CitationQueryEngine bundles answer-synthesis with citation-array construction. Running it earlier would re-do the retrieval ranking and lose the cross-encoder + LLM rerank signal. Running it last preserves the rerank order and lets the synthesis step focus on the answer construction surface.

## Alternatives considered

### BM25 only (rejected)

- **Pros**: simplest, deterministic, no model load, no GPU.
- **Cons**: misses paraphrase, misses JP↔EN cross-language matching, no semantic similarity for the 5-axis case ranker's text-similarity input.
- **Why rejected**: insufficient recall on the bilingual corpus.

### Dense only (multilingual-e5 + faiss) (rejected)

- **Pros**: handles paraphrase + cross-language, simpler pipeline.
- **Cons**: misses exact-term anchors (deal codenames, financial-band labels), and dense-only recall has known weaknesses on rare entities — exactly the case for PMI domain artefacts.
- **Why rejected**: stage 1 lexical anchor is load-bearing for entity-level retrieval.

### Reciprocal Rank Fusion (RRF) without cross-encoder rerank (rejected)

- **Pros**: lighter than the chosen stack; RRF is a well-known fusion baseline.
- **Cons**: RRF only reorders the union of stages 1+2; it has no per-(query, candidate) semantic signal. Empirically, RRF top-5 on this corpus included off-domain candidates that cross-encoder rerank filtered out.
- **Why rejected**: precision at K=5 is the dialogue surface — a noisier top-5 directly degrades the Assistant's citation array.

### Cohere Rerank / paid managed rerank API (rejected)

- **Pros**: high-quality reranking with no model-hosting cost on the consumer laptop.
- **Cons**: paid managed service requires a credit card and an account; violates the [Selected under](../../README.md#selected-under) zero-credit-card constraint for the default path.
- **Why rejected**: incompatible with the portfolio's $0 / no-CC default. The 3-tier swap path in [README "Configuration (env)"](../../README.md#configuration-env) allows the customer to enable a paid reranker via `T5_LLM_PROVIDER=claude` for stage 4, but the default code path uses Ollama-local or mock.

### LLM-only retrieval (let the LLM read the whole casebook) (rejected)

- **Pros**: simplest from a code-structure perspective.
- **Cons**: blows the context window once the corpus exceeds a few hundred cases; no citation link-back to specific chunks; cost scales linearly with corpus size on every query.
- **Why rejected**: does not scale beyond PoC; defeats the citation-link-back requirement.

## Consequences

### Positive

- Each stage is independently swappable behind a Pydantic schema boundary; replacing `multilingual-e5-large` with a newer dense encoder is a single import change.
- The pipeline degrades gracefully — when the Ollama-local LLM is offline, stages 1–3 + 5 still produce a usable citation-grounded retrieval (with the listwise rerank step skipped). This is what makes the [Selected under](../../README.md#selected-under) "local LLM (default)" constraint hold without the system going dark.
- Citation chunk IDs flow through the schema and arrive intact at the Assistant's response — see [src/citation/citation_engine.py](../../src/citation/citation_engine.py).

### Negative

- Latency stack-up: cold start loads three model sets (e5 large + MS-MARCO cross-encoder + Ollama backend). The long-running uvicorn process amortizes this; one-shot CLI invocations pay the cold cost on every call.
- Stage 4 LLM rerank quality is bounded by the chosen provider in the 3-tier swap. The Ollama `gemma3:4b` default is good enough for the PoC corpus; paid-tier Claude Sonnet meaningfully improves listwise ranking at the customer-deployment swap point.

### Reversibility

Each stage is behind an interface in [src/retrieval/](../../src/retrieval/). The five-stage shape itself is the design contract; component swaps inside a stage are local edits. Dropping a stage (e.g., removing stage 4 in low-budget deployments) requires only that the orchestrator skip the corresponding LangGraph node; downstream consumers continue to operate.

## References

- [Robertson & Zaragoza, "The Probabilistic Relevance Framework: BM25 and Beyond"](https://www.staff.city.ac.uk/~sbrp622/papers/foundations_bm25_review.pdf)
- [Wang et al., "Multilingual E5 Text Embeddings: A Technical Report"](https://arxiv.org/abs/2402.05672)
- [Reimers & Gurevych, "Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks"](https://arxiv.org/abs/1908.10084)
- [MS MARCO Cross-Encoders documentation](https://www.sbert.net/docs/cross_encoder/pretrained_models.html)
- [LlamaIndex CitationQueryEngine](https://docs.llamaindex.ai/en/stable/examples/query_engine/citation_query_engine/)
- [`rank-bm25` project](https://github.com/dorianbrown/rank_bm25)
- [`faiss` project](https://github.com/facebookresearch/faiss)
- [Cormack et al., "Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods"](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf) — RRF baseline alternative considered
- Code: [src/retrieval/](../../src/retrieval/), [src/orchestrator/build_state_graph.py](../../src/orchestrator/build_state_graph.py), [src/citation/citation_engine.py](../../src/citation/citation_engine.py)
