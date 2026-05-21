# MAIS — PMI Knowledge Base

> **GraphRAG-based knowledge layer** that structures past PMI engagements + public research into queryable form. Junior consultants ask in natural language; the system returns the **5 most-similar past cases** (across 5 axes) with citations and a ranked recommendation.

[![tests](https://img.shields.io/badge/tests-245%20passing%20%2F%20248-brightgreen)]()
[![pip-audit](https://github.com/leagames0221-sys/mais-pmi-knowledge-base/actions/workflows/pip-audit.yml/badge.svg)](https://github.com/leagames0221-sys/mais-pmi-knowledge-base/actions/workflows/pip-audit.yml)
[![python](https://img.shields.io/badge/python-3.12-blue)]()
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

---

## 30-second pitch

A senior PMI consultant carries 100+ deals of pattern memory. A junior has none. Six months of onboarding closes part of the gap, but most of that knowledge is in unstructured emails, PowerPoints, and tribal lore.

**MAIS PMI Knowledge Base** structures that knowledge:
- Past PMI engagements stored as Architecture Decision Records (decision → outcome → pattern)
- Public PMI research papers ingested via Docling + chunked + embedded + linked back
- 5-axis weighted similarity (industry / scale / culture / financial / integration type) surfaces the closest 2-3 historical cases
- AI Assistant dialogue: junior consultant asks → retrieves cases + papers → returns ranked recommendation with `[1]` / `[2]` citations + audit log

GraphRAG core (entity / relation / community detection via NetworkX Louvain) implemented from scratch — Microsoft GraphRAG used as decomposed prior art only, not vendored.

---

## Architecture

```
┌──────────────────────────────────────────────┐
│  Sibling tool inputs (T1-T4 outputs)         │
│  • Profile/Company match                     │
│  • Citation array + Q-A pairs                │
│  • IntegrationPlan + RiskScore               │
│  • CockpitProject + KpiSnapshot              │
└──────────────────┬───────────────────────────┘
                   │
                   ▼
       ┌───────────────────────────┐
       │  PMICase lifecycle root   │
       │  (PMI-XXXXXXXXX)          │
       │  • DD stage               │
       │  • Day-1                  │
       │  • Day-100                │
       │  • outcome                │
       └───────────────┬───────────┘
                       │
   ┌───────────────────┼───────────────────────┐
   │                   │                       │
   ▼                   ▼                       ▼
┌──────────┐   ┌────────────────┐   ┌──────────────────┐
│ Decision │   │ Outcome        │   │ Pattern          │
│ (ADR)    │   │ (success /     │   │ (cross-case      │
│          │   │  failure /     │   │  abstraction +   │
│          │   │  partial)      │   │  5-axis weight)  │
└────┬─────┘   └────────┬───────┘   └────────┬─────────┘
     │                  │                    │
     └──────────────────┴────────────────────┘
                        │
                        ▼
       ┌─────────────────────────────────┐
       │  GraphRAG (self-built)          │
       │  • Entity extraction (LLM)      │
       │  • Relation extraction (LLM)    │
       │  • Community detection          │
       │    (NetworkX Louvain BSD-3)     │
       └────────────────┬────────────────┘
                        │
                        ▼
       ┌─────────────────────────────────┐
       │  5-axis weighted similarity     │
       │  • industry                     │
       │  • scale                        │
       │  • culture                      │
       │  • financial                    │
       │  • integration type             │
       └────────────────┬────────────────┘
                        │
                        ▼
       ┌─────────────────────────────────┐
       │  AI Assistant dialogue          │
       │  (LangGraph 9-node DAG)         │
       │                                 │
       │  query → context retrieval →    │
       │  citation array → ranked        │
       │  recommendation + audit log     │
       └─────────────────────────────────┘
```

---

## What's inside

| Capability | Implementation |
|---|---|
| **ADR-format PMI structuring** | Past engagements recorded as Architecture Decision Records (decision → rationale → outcome → measurable KPI delta) |
| **GraphRAG (self-built)** | NetworkX `louvain_communities` (BSD-3) + LLM-driven entity / relation extraction. Microsoft GraphRAG (Apache-2.0) referenced as decomposed prior art only |
| **5-axis weighted similarity** | Industry / scale / culture / financial / integration type — weights tunable per engagement type |
| **AI Assistant dialogue** | LangGraph 9-node state graph: query → 5-stage hybrid retrieval → 5-axis similar cases → citation array → ranked recommendation + audit log |
| **Paper RAG integration** | Docling parses PDF/Word/Excel/PPT → chunked + embedded + indexed; joins with engagement records on retrieval |
| **Hardened controls (PoC-scoped)** | env-var-gated portable config: HTTPBasic auth, CSRF token, in-process per-IP rate-limit, persistent audit dir, PII redaction layer with block / warn modes |
| **Vault Pattern** | PII (consultant identifiers, paper signatories) Fernet-encrypted at rest |

---

## Tech stack

| Layer | Choice |
|---|---|
| GraphRAG | NetworkX `louvain_communities` (BSD-3) — self-built; Microsoft GraphRAG referenced |
| Orchestrator | LangGraph 1.2.0+ (MIT) — stateful DAG with checkpoint replay |
| Retrieval | rank-bm25 + multilingual-e5-large + cross-encoder/ms-marco-MiniLM-L-12-v2 + LLM listwise CoT rerank |
| RAG | LlamaIndex CitationQueryEngine + Docling (Excel/Word/PPT/PDF + OCR + vision) |
| ANN | faiss-cpu (MIT) |
| Japanese NLP | fugashi + PMI domain dictionary (32 canonical terms) |
| LLM | Anthropic SDK (MIT) — Claude Sonnet 4.6, Ollama (gemma3:4b) — env-var swap |
| Web | FastAPI + uvicorn + Jinja2 (MIT) |
| Schema | Pydantic v2 (MIT) |
| Crypto | cryptography Fernet (Apache-2.0) |
| Tests | pytest (248 collected) |

---

## ID conventions

| Prefix | Entity |
|---|---|
| `PMI-` | PMICase (one engagement lifecycle root, DD + Day-1 + Day-100 + outcome) |
| `DEC-` | Decision (ADR-formatted) |
| `OUT-` | Outcome (success / failure / partial) |
| `PAT-` | Pattern (cross-case abstraction with 5-axis weights) |
| `REF-` | ReferencePaper (synthetic in PoC; real with per-paper license confirmation in production) |
| `AIQ-` | AssistantQuery (dialogue audit trail) |

---

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-week0.txt

# generate synthetic PMI cases + papers
python -m src.data_gen.generate_synthetic_pmi
python -m src.ingestion.generate_synthetic_papers

# launch UI
uvicorn src.api.app:app --reload --port 8000
```

---

## Configuration (env)

The knowledge base ships with a **3-tier LLM swap path** for the AI Assistant dialogue + entity extraction. Pick the tier that matches your environment — `T5_LLM_PROVIDER=mock` is the test/dev default; production hardening adds auth + rate-limit + audit on top.

### Tier 1 — PoC default (zero cost, zero credit card, runs offline)

```bash
# T5_LLM_PROVIDER=mock is the implicit default; AI Assistant dialogue +
# GraphRAG retrieval + 5-axis similarity all work on deterministic templated
# outputs without any external API call.
VAULT_KEY=<fernet key>                  # always required
SESSION_SECRET=<token_urlsafe>          # always required
SYNTHETIC_SEED=20260514
DATA_DIR=./data
```

### Tier 2 — Local LLM swap (still zero cost, zero credit card; uses your own GPU/CPU)

For developers / customers who want real LLM Assistant dialogue without paid APIs. Requires [Ollama](https://ollama.com/) running locally with a model pulled.

```bash
T5_LLM_PROVIDER=ollama                  # switches default_provider() to Ollama
T5_OLLAMA_MODEL=gemma3:4b               # default (other supported: qwen2.5:7b, llama3.x, etc.)
# ... plus the always-required vars from tier 1
```

### Tier 3 — Customer / production swap (paid API; the only tier that touches credit-card-backed services)

For customer deployments where higher Assistant quality or hosted-model SLA is required. **This is the only place credit-card-backed services enter the system** — paste the customer's key here.

```bash
T5_LLM_PROVIDER=claude                  # or "gemini" / future provider
ANTHROPIC_API_KEY=sk-ant-...            # paste customer's key here (tier 1 + tier 2 never read this var)
# ... plus the always-required vars from tier 1
```

### Production hardening overrides (orthogonal to LLM tier — apply on tier 2 or tier 3)

```bash
T5_AUTH_REQUIRED=1           # HTTPBasic auth
T5_BASIC_USER=<username>
T5_BASIC_PASS=<password>
T5_CSRF_REQUIRED=1
T5_RATE_LIMIT_PER_MIN=60
T5_AUDIT_DIR=data/audit/assistant
T5_BLOCK_PII=1               # PII redaction enforce
```

GraphRAG retrieval + NetworkX Louvain community detection + 5-axis weighted similarity all run on tier 1 alone. The LLM tier is only consulted by the AI Assistant dialogue node and the entity-extraction step at ingestion — every preceding stage ships even when the LLM tier is offline.

---

## Production deployment notes

- Real PMI engagement data → sandbox (Docker / WSL2 / Codespaces)
- Real research papers → per-paper license confirmation (public papers have redistribution licenses individually)
- Customer sandbox dry-run + 1-week stability before cutover
- Sweep 2026 advisories for LangGraph, LlamaIndex, HuggingFace Transformers, Docling
- External penetration test recommended for large engagements

---

## Sibling tools (M&A Intelligence Suite)

- [mais-deal-matching](https://github.com/leagames0221-sys/mais-deal-matching) — sourcing
- [mais-dd-workbench](https://github.com/leagames0221-sys/mais-dd-workbench) — DD
- [mais-day1-cockpit](https://github.com/leagames0221-sys/mais-day1-cockpit) — Day-1 readiness
- [mais-pmi-cockpit](https://github.com/leagames0221-sys/mais-pmi-cockpit) — 100-day PMI dashboard
- **[mais-pmi-knowledge-base](https://github.com/leagames0221-sys/mais-pmi-knowledge-base)** ← this repo (knowledge layer)
- [mais-portfolio](https://github.com/leagames0221-sys/mais-portfolio) — overview

---

## License

MIT. See [LICENSE](LICENSE).
