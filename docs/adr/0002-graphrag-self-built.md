# ADR-0002: GraphRAG core — self-built on NetworkX Louvain, not vendored Microsoft GraphRAG

## Status

Accepted (2026-05-21)

## Context

The knowledge base needs a graph layer over PMI domain entities (PMICase / Decision / Outcome / Pattern / ReferencePaper) with three operations: entity extraction from unstructured engagement notes + paper text, relation extraction, and community detection (so similar engagements / decisions cluster and propagate at retrieval time). The retrieval surface promised in the README is "5 most-similar past cases, ranked by 5 axes, with citation link-back."

Microsoft's GraphRAG (Apache-2.0) is the canonical reference implementation of this pattern. The question is whether to vendor it whole, vendor parts, or build from first principles. Three constraints frame the answer:

1. **License hygiene** — the portfolio's [Selected under](../../README.md#selected-under) constraint set forbids GPL-family transitive dependencies. Several Leiden-family community-detection implementations are GPL-3, which would taint the whole dependency graph.
2. **Infrastructure budget** — Microsoft GraphRAG's reference pipeline assumes a managed graph store (Cosmos DB / Neo4j Aura) and a managed LLM (Azure OpenAI). Both require credit cards, which the [4-constraint baseline](../../README.md#selected-under) explicitly forbids in the default path.
3. **Audit-grade replayability** — the Assistant dialogue must produce a citation array that points back to specific source artefacts (ADR file, paper chunk ID). That requires the graph build pipeline to be deterministic and inspectable, not a black-box pipeline behind a managed-service call.

## Decision

Build the GraphRAG core from first principles inside [src/retrieval/graphrag_native.py](../../src/retrieval/graphrag_native.py), using a three-layer boundary discipline:

1. **OS-primitives layer** — `networkx` (BSD-3) for the graph data structure and `networkx.algorithms.community.louvain_communities` for community detection. Anthropic / Ollama SDK for LLM-driven entity + relation extraction via the `LLMProvider` Protocol.
2. **Business-logic layer (in-house)** — three prompt templates (entity extraction / relation extraction / community summarization), the PMI-domain Ontology gate (80% coverage threshold), and the PII boundary check.
3. **Framework-as-a-whole layer (rejected)** — Microsoft GraphRAG is **not** vendored whole. It is referenced as decomposed prior art for prompt-template structure only (per [D-PRIOR-ART-FIRST]).

The intent is captured in the module header of [src/retrieval/graphrag_native.py](../../src/retrieval/graphrag_native.py) — "decomposed prior art per doctrine: prior-art-first."

## Why NetworkX Louvain specifically (not Leiden)

A prior iteration of the code path used `networkx.algorithms.community.leiden_communities`. NetworkX 3.6 ships `leiden_communities` as an API dispatcher only — the actual algorithm lives in a backend package that is not in the default install path. Calling it without a backend raises `NotImplementedError` at runtime. This was caught on 2026-05-14 and the code path was migrated to `louvain_communities`, which is implemented natively in NetworkX (BSD-3) and requires no backend.

The supersession history is recorded in the module docstring at [src/retrieval/graphrag_native.py:14-19](../../src/retrieval/graphrag_native.py).

## Alternatives considered

### Vendor Microsoft GraphRAG whole (rejected)

- **Pros**: canonical reference implementation, well-documented, actively maintained by Microsoft Research.
- **Cons**: brings in a heavy managed-service assumption (Cosmos DB / Neo4j Aura + Azure OpenAI), pulls Apache-2.0 + several transitive dependencies into the runtime, and obscures the prompt templates behind a framework layer (defeating the audit-grade replayability requirement).
- **Why rejected**: framework-as-a-whole inject violates the [Selected under](../../README.md#selected-under) zero-credit-card + audit-grade constraint pair simultaneously. Decomposed prior art (prompt structure only) gives the same design benefit without the integration cost.

### `leidenalg` (Python Leiden, by Traag et al.) (rejected)

- **Pros**: published in [Nature Scientific Reports 9, 5233 (2019)](https://www.nature.com/articles/s41598-019-41695-z) as a strict improvement over Louvain (no disconnected communities). Well-tested, fast.
- **Cons**: GPL-3 licensed (viral copyleft). Including it as a runtime dependency would impose GPL-3 on the whole repo, conflicting with the [Selected under](../../README.md#selected-under) "free / OSS only" constraint which targets permissive licenses (MIT / Apache-2.0 / BSD).
- **Why rejected**: license incompatibility. Acceptable in private deployments where licensee terms allow GPL-3 in the dependency graph, but not in a permissively-licensed public portfolio.

### `networkx.algorithms.community.leiden_communities` (rejected)

- **Pros**: NetworkX-native API surface, no external dependency, would match the Leiden quality claim.
- **Cons**: NetworkX 3.6 ships only the dispatcher; the actual implementation must be supplied by a backend (`nx-cugraph` or similar). Backend install drags in CUDA dependencies or GPL-family runtime libraries depending on the chosen backend, defeating both the consumer-laptop and license-hygiene constraints.
- **Why rejected**: empty dispatcher in the default install path. Raises `NotImplementedError` on the consumer laptop deployment target.

### `graspologic` (Microsoft / Apache-2.0) (rejected)

- **Pros**: provides graph statistical methods including community detection, Apache-2.0 licensed.
- **Cons**: project has been on maintenance-only status since 2024 with sparse releases; not a confident long-term dependency for a portfolio piece intended to remain runnable.
- **Why rejected**: maintenance signal is weak; risk of being stranded on an unmaintained dependency.

### Neo4j + Aura managed Cypher (rejected)

- **Pros**: industrial-strength graph backend, query language with strong tooling.
- **Cons**: managed service requires a credit card; self-hosted Neo4j Community edition is GPL-3 (viral on the JVM linkage path); operating an external graph store contradicts the "PoC runs end-to-end on a single laptop" baseline.
- **Why rejected**: violates [Selected under](../../README.md#selected-under) constraints 1 (zero credit card) and 3 (free / OSS only — GPL-3 transitive).

## Consequences

### Positive

- Permissive-license-only dependency graph (BSD-3 from NetworkX, MIT from Pydantic, Apache-2.0 from cryptography) — matches the [Selected under](../../README.md#selected-under) constraint set with no friction.
- Prompt templates are inspectable in-repo, which is necessary for the citation-grounded Assistant dialogue to remain auditable.
- The full pipeline runs on a consumer laptop with no managed service. The 3-tier LLM swap (mock / Ollama / paid API per [README "Configuration (env)"](../../README.md#configuration-env)) gives a customer-paid path without changing the default.
- The boundary-discipline comment block at [src/retrieval/graphrag_native.py:8-12](../../src/retrieval/graphrag_native.py) makes the "decomposed prior art" claim machine-readable for future audits.

### Negative

- Self-built community detection is bounded to PoC-scale (entity count < ~100 per case). On the PoC corpus, Louvain's disconnected-community pathology is not observed empirically — but at production scale (real PMI casebooks with thousands of entities), the disconnected-community case would become non-negligible and the code path would need to switch to a NetworkX Leiden backend or to `leidenalg` under a private-deployment license.
- The "swap to Leiden when production scale demands it" path is documented but not implemented; this is the explicit follow-up wedge for the deployment-tier ★★★★ step (see [README "Production deployment notes"](../../README.md#production-deployment-notes)).

### Reversibility

The graph backend is isolated to [src/retrieval/graphrag_native.py](../../src/retrieval/graphrag_native.py). Replacing `louvain_communities` with `leidenalg.find_partition` is a ~10-line change at a single import boundary, contingent on accepting the GPL-3 in the customer environment. The boundary contract (`PMICase` / `Decision` / `Outcome` / `Pattern` Pydantic schemas) does not change.

## References

- [Microsoft GraphRAG (Apache-2.0)](https://github.com/microsoft/graphrag) — decomposed prior art reference (prompt structure only)
- [NetworkX `louvain_communities` documentation](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.community.louvain.louvain_communities.html)
- [Blondel et al., "Fast unfolding of communities in large networks" (Louvain algorithm)](https://doi.org/10.1088/1742-5468/2008/10/P10008)
- [Traag et al., "From Louvain to Leiden: guaranteeing well-connected communities" (Nature Scientific Reports, 2019)](https://www.nature.com/articles/s41598-019-41695-z)
- [`leidenalg` project (GPL-3)](https://github.com/vtraag/leidenalg) — license-incompatible alternative considered
- [`graspologic` project (Apache-2.0)](https://github.com/microsoft/graspologic) — maintenance-status alternative considered
- [Code path: `src/retrieval/graphrag_native.py`](../../src/retrieval/graphrag_native.py)
