# MAIS — PMI Knowledge Base

> **M&A Intelligence Suite (MAIS)** の 5 番目のツール。
> 過去 PMI (Post-Merger Integration) 案件と公開リサーチ paper を構造化し、
> 「過去のうち最も類似する案件」を 5 軸 (業種 / 規模 / 文化 / 財務 / 統合 type) で auto-surface、
> ジュニアコンサルタントの query に対し AI が citation 付きで recommendation を返す。

[![tests](https://img.shields.io/badge/tests-207%20passed-brightgreen)]()
[![pip-audit](https://img.shields.io/badge/pip--audit-0%20CVE-brightgreen)]()
[![python](https://img.shields.io/badge/python-3.12-blue)]()
[![license](https://img.shields.io/badge/license-PoC%20demo-lightgrey)]()

---

## 何ができるか

| 機能 | 内容 |
|---|---|
| **ADR 形式 PMI 構造化** | 過去案件の意思決定 / 失敗 / 修正 / 成果を Architecture Decision Record 形式で記録 |
| **GraphRAG ベース知識検索** | Microsoft GraphRAG (Apache-2.0) prompt 構造を decomposed prior art として参考、 自作実装。 Entity / Relation / Community を NetworkX で構築 |
| **5 軸類似 case auto-surface** | 業種 / 規模 / 文化 / 財務 / 統合 type の重み付き類似度で過去 case top-K 抽出 |
| **AI Assistant 対話** | query → 関連 case retrieval → citation array → ranked recommendation。 LLM listwise CoT + audit log |
| **paper RAG 統合** | 公開 PMI リサーチ paper を chunk + embed + index、 過去案件と join して回答に citation |
| **黒×金 brand UI** | FastAPI + Jinja2、 検索 / 対話 / 類似 case panel |

---

## 想定ユースケース

- **M&A advisory firm** ジュニアコンサルタントの過去案件 catch-up
- **PMI 担当者** が新規案件着手時に類似案件 + lesson learned を即時 surface
- **コーポレート M&A 部門** が internal knowledge base として deploy

---

## tech stack

| 層 | 採用 |
|---|---|
| Orchestrator | LangGraph 1.2.0+ (stateful DAG + checkpoint replay) |
| Retrieval | 5-stage hybrid pipeline + 5 dim weighted similarity detector (自作) |
| RAG | LlamaIndex CitationQueryEngine + docling (Excel/Word/PPT/PDF parser) |
| Embedding | sentence-transformers + faiss-cpu + rank-bm25 + cross-encoder |
| GraphRAG | NetworkX `louvain_communities` (BSD-3) + Microsoft GraphRAG prompt 構造参考 |
| LLM | MockProvider + ClaudeProvider + OllamaProvider (env-var swap) |
| 日本語処理 | fugashi + PMI domain dictionary (32 canonical terms) |
| Web UI | FastAPI + Jinja2 + 黒×金 brand identity |
| Security | python-ml-stack 5-layer 防御 (Standard Pin / pip-audit strict / Dependabot / Lock / Dependency Review) |

---

## verify evidence

- **207 test PASS** (pytest, 1.02s)
- **pip-audit: 0 CVE** (commercial-grade hardening 済)
- **Ollama gemma3:4b** end-to-end smoke ✅
- **8 gate AI 単独 PASS 8/8** (内部 verify rubric)

---

## 4-Week roadmap (PoC scope)

| Week | scope | deliverable |
|---|---|---|
| **Week 0** | Discovery → Requirements → Design → Tasks、 GitHub PRIVATE repo + drift CI install | scaffold + design doc |
| **Week 1** | 合成 PMI case data 生成 (PMI case 30 件 + Decision 200 件 + Outcome 200 件 + Pattern 20 件 + paper 50 件) + Object Type schema | T4 出力 → PMI case lifecycle inherit 動作 |
| **Week 2** | LangGraph state graph + 5 dim weighted similarity detector | similar case auto-surface + recommendation smoke |
| **Week 3** | AI Assistant 対話 full active (query → context + 引用 + 推奨) + paper ingestion | junior コンサル query → AI 推奨 動作 |
| **Week 4** | FastAPI/Jinja UI + Vault Pattern (PII Fernet 暗号化) + e2e smoke | 実機 demo (Cloudflare quick tunnel) + 静止 screenshot |

---

## 環境設定

```powershell
# venv 作成 + activate
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Week 0 (scaffold + audit) deps
pip install -r requirements-week0.txt

# .env 新規作成 (commit しない、 .gitignore で literal block 済)
# 必須 env var:
#   ANTHROPIC_API_KEY       # Week 3+ で active
#   VAULT_KEY               # Week 4 Fernet
#   SESSION_SECRET          # Week 4 FastAPI
#   SYNTHETIC_SEED=20260514
#   DATA_DIR=./data
```

production deploy 時の追加 env var:

```bash
T5_LLM_PROVIDER=ollama       # default mock (test) / production = ollama
T5_OLLAMA_MODEL=gemma3:4b    # default
T5_AUTH_REQUIRED=1           # HTTPBasic auth
T5_BASIC_USER=<username>
T5_BASIC_PASS=<password>
T5_CSRF_REQUIRED=1
T5_RATE_LIMIT_PER_MIN=60
T5_AUDIT_DIR=data/audit/assistant
T5_BLOCK_PII=1               # PII redaction enforce
```

---

## 制約 (PoC scope)

- **無料 + クレカ不要範囲** で完走 (pip OSS + GitHub PRIVATE + Cloudflare quick tunnel)
- **consumer laptop** で完走前提
- **合成 PMI case data + 合成 paper RAG corpus only** — 実 PMI 案件 / 実 paper download は一切扱わない
- **vendor lock-in ZERO** (Anthropic API + OSS only、 Gemini / Claude / Ollama 1 file swap path)

---

## 移植段階の追加要件

- 実 PMI 案件投入時 = sandbox (Docker / WSL2) + 顧客 sandbox dry-run + 1 週間 stability
- 実 paper ingestion 時 = paper license individual confirm (公開 paper でも redistribution license 個別)
- 大型案件 = external pentesting 推奨

---

## related tools (M&A Intelligence Suite)

- **mais-deal-matching** — sourcing stage
- **mais-dd-workbench** — Due Diligence automation
- **mais-day1-cockpit** — Day-1 readiness
- **mais-pmi-cockpit** — 100-day PMI dashboard
- **mais-pmi-knowledge-base** ← 本リポジトリ (knowledge layer / 全 tool 共通参照)

---

## license

PoC demo — 設計思想 + コード構造を portfolio 公開、 合成データのみ含む。 商用 deploy は別途相談。
