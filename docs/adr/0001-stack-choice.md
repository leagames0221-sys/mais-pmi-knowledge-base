# ADR-0001: Stack choice — Python 3.12 + FastAPI + LangGraph + Pydantic v2

## Status

Accepted (2026-05-21)

## Context

`mais-pmi-knowledge-base` is the knowledge-layer member of the MAIS suite — a GraphRAG-backed retrieval surface for past PMI engagements + public research, with citation-grounded AI Assistant dialogue and a 5-axis weighted similarity ranker over historical cases. The implementation stack drives every downstream choice (graph library, retrieval libraries, RAG framework, web layer, schema validation, test harness, LLM provider abstraction).

Five constraints frame the decision:

1. **ML / NLP ecosystem fit** — GraphRAG, dense retrieval, cross-encoder reranking, Docling document parsing, and BM25 are all Python-native; the canonical reference implementations and the model checkpoints (multilingual-e5, MS-MARCO MiniLM) ship as Python libraries first.
2. **Citation-grounded RAG** — `LlamaIndex CitationQueryEngine` is the closest off-the-shelf primitive for answer-with-`[1]/[2]`-citation, and is Python-only.
3. **Stateful orchestrator** — the AI Assistant dialogue is a 9-node DAG (query → 5-stage retrieval → 5-axis similar cases → citation array → ranked recommendation + audit log) with checkpoint replay; LangGraph is the most mature option and is Python-first.
4. **Free + no-credit-card constraint** — every runtime dependency must work on a consumer laptop with no paid API in the default path (see README "Selected under").
5. **Type-safe schema across module boundaries** — PMI domain entities (PMICase / Decision / Outcome / Pattern / ReferencePaper / AssistantQuery) flow across ingestion → graph → retrieval → similarity → assistant, and need runtime-validated boundary contracts.

## Decision

| Layer | Selection | Free + no-CC verified |
| --- | --- | --- |
| Language | Python 3.12 (strict typing where practical) | ✅ |
| Web framework | FastAPI 0.115+ (MIT) | ✅ |
| ASGI server | uvicorn (BSD-3) | ✅ |
| Templating | Jinja2 (BSD-3) | ✅ |
| Schema / runtime validation | Pydantic v2 (MIT) | ✅ |
| Orchestrator | LangGraph 1.2.0+ (MIT) | ✅ |
| RAG | LlamaIndex `CitationQueryEngine` (MIT) | ✅ |
| Document parsing | Docling (MIT) | ✅ |
| Graph | NetworkX (BSD-3) — see [ADR-0002](0002-graphrag-self-built.md) | ✅ |
| ANN | faiss-cpu (MIT) | ✅ |
| Lexical retrieval | rank-bm25 (Apache-2.0) — see [ADR-0003](0003-five-stage-hybrid-retrieval.md) | ✅ |
| Dense encoder | multilingual-e5-large (MIT) — see [ADR-0003](0003-five-stage-hybrid-retrieval.md) | ✅ |
| Reranker | cross-encoder ms-marco-MiniLM-L-12-v2 (Apache-2.0) — see [ADR-0003](0003-five-stage-hybrid-retrieval.md) | ✅ |
| Japanese tokenizer | fugashi + MeCab dict (GPL-2 / BSD compat for fugashi wrapper, dict licensed separately) | ✅ |
| LLM provider | Anthropic SDK (MIT) + Ollama local (MIT) — env-var-gated 3-tier swap (see README "Configuration (env)") | ✅ |
| Crypto | `cryptography` Fernet (Apache-2.0) — for PII-at-rest vault | ✅ |
| Test framework | pytest (MIT) — 248 collected, 245 passing | ✅ |
| CI | GitHub Actions free tier (`pip-audit` workflow active) | ✅ |

## Rationale

### Ecosystem fit dominates the language choice

Every retrieval primitive in [ADR-0003](0003-five-stage-hybrid-retrieval.md) — BM25, dense encoders, cross-encoder reranking, document parsing, citation engine — ships Python-first. A non-Python implementation would either rebind every primitive via FFI/subprocess (adding cost without buying anything) or reimplement them (multiplying scope without changing the outcome).

### Pydantic v2 + LangGraph give typed, replayable workflows

The state-graph nodes pass typed `PMICase` / `RetrievalResult` / `CitationArray` / `AssistantTurn` objects across boundaries. Pydantic v2's discriminated unions plus `model_config = ConfigDict(frozen=True)` on schema types ([src/schema/types.py](../../src/schema/types.py)) make boundary contracts machine-checkable, which is necessary for the citation-grounded dialogue to remain auditable.

### `LlamaIndex CitationQueryEngine` is the wedge primitive

The portfolio's value is "answer with `[1]/[2]` citation link-back to the source ADR or paper chunk." That primitive exists in LlamaIndex and would otherwise need to be re-implemented. Selecting LlamaIndex locks Python.

## Alternatives considered

### Node.js / TypeScript (rejected)

- **Pros**: shared stack with the security-tool sibling repos (mcp-guard / sbom-pilot / agentic-appsec-pilot); single language across the wider portfolio.
- **Cons**: no first-class binding for multilingual-e5 + MS-MARCO cross-encoder + Docling + LlamaIndex CitationQueryEngine + fugashi. Each would need FFI/subprocess wrapping or rewriting. Pydantic v2's runtime validation has no equally-mature TS analogue (`zod` is close but does not produce typed dataclasses).
- **Why rejected**: the cost of rebinding the entire ML/NLP stack exceeds the value of stack uniformity. The portfolio already accepts heterogeneity (security tools = TS, ML/RAG = Python).

### Go (rejected)

- **Pros**: single-binary distribution, strong concurrency story.
- **Cons**: nearly the entire RAG / dense-retrieval / reranking stack would need to be reimplemented. Citation engine, Docling, LlamaIndex have no Go equivalents at production maturity in 2026.
- **Why rejected**: same ecosystem-fit argument as TypeScript, more severe.

### Python without FastAPI (Flask / Django / Starlette) (rejected)

- **Pros**: Flask is simpler; Django adds an ORM the project would not use.
- **Cons**: FastAPI's Pydantic-native request/response model removes a serialization layer that Flask would otherwise need to add by hand; Starlette is FastAPI's underlying ASGI layer (FastAPI = Starlette + Pydantic + OpenAPI), so picking Starlette directly means re-implementing the Pydantic glue.
- **Why rejected**: FastAPI strictly dominates the alternatives given the Pydantic v2 boundary-contract decision.

## Consequences

### Positive

- Every retrieval / RAG / reranking primitive is used as-published, no FFI / subprocess overhead.
- Pydantic v2 + FastAPI + LangGraph + LlamaIndex all share a Python type system that flows from HTTP request body through the orchestrator nodes to the citation engine and back, removing several would-be glue layers.
- The 3-tier LLM swap path (mock / Ollama local / paid API) is a single `LLMProvider` Protocol with three implementations ([src/llm/provider.py](../../src/llm/provider.py)).

### Negative

- Distribution is not single-binary. Users install via `pip install -r requirements-weekN.txt` against a Python 3.12 environment. For customer deployment this is mitigated by containerizing (Docker / Podman / WSL2) — see [README "Production deployment notes"](../../README.md#production-deployment-notes).
- Python startup cost is non-trivial (~1s cold for the full retrieval stack with model loading). Mitigated by long-running uvicorn process; not a concern for a stateful service.

### Reversibility

The intermediate Pydantic schemas in [src/schema/types.py](../../src/schema/types.py) are language-agnostic in shape (they would round-trip through any sufficiently-strict type system). A language pivot is feasible, but would require either rebinding or replacing the retrieval / RAG / reranking stack — neither is cheap, which is the original argument for staying in Python.

## References

- [Python 3.12 release notes](https://docs.python.org/3/whatsnew/3.12.html)
- [FastAPI documentation](https://fastapi.tiangolo.com/)
- [Pydantic v2 documentation](https://docs.pydantic.dev/latest/)
- [LangGraph documentation](https://langchain-ai.github.io/langgraph/)
- [LlamaIndex `CitationQueryEngine`](https://docs.llamaindex.ai/en/stable/examples/query_engine/citation_query_engine/)
- [Docling project](https://github.com/docling-project/docling)
- [NetworkX project](https://networkx.org/)
- [README — Tech stack](../../README.md#tech-stack)
