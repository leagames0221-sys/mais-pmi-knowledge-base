# T5 Discovery Brief — MAIS / T5 PMI knowledge base (PMI Ontology 本体)

> Spec-Driven Workflow Stage 1 (Discovery) deliverable。
> AI 起草 judgment ★★ tier (本 turn、 user handoff 「step 1 から literal 開始」 明示で proceed)、 本 brief 確定後 Stage 2 (Requirements) 移行。

---

## 1. PJ Identity (sibling 位置付け)

- **scope**: M&A advisory engagement 提案 § T5 application — **PMI knowledge base / PMI Ontology 本体** PoC 試作
- **target**: プレゼン demo ready、 4 週で動く版完成、 Assistant 型対話 literal 動作 (junior コンサル query → AI context + 引用 + 推奨)
- **移植先**: client infrastructure (後日)、 本 repo は試作 only
- **sibling**: T1 (マッチング、 完成度 100%) + T2 (DD、 完成度 100%) + T3 (Day-1、 完成度 100%) + T4 (100 日 cockpit、 完成度 100%) と MAIS ecosystem 共通基盤 (internal ADR) を citation reference で literal 共有
- **5th sibling 位置付け**: original proposal line 477 「単独 tool ではなく、 T1-T4 が共通で参照する business knowledge layer」、 「internal AI orchestration + Ontology module を enterprise scale に拡張する path が現実的」、 original proposal line 486 「過去 PMI を構造化する作業は他に先んじて着手する意味が大きい」 (推奨順 1 位、 user 実行順は T1-T4 → T5 で literal 進行)

## 2. T5 unique 性質 (T1-T4 と literal 異なる architectural scope)

T5 = **「単独 tool ではない」 (original proposal line 477 literal 明示)** = T1-T4 が 「使う」 対象ではなく、 T1-T4 が **「共通参照する business knowledge layer」**。 ただし PoC scope では:
- **single-direction** (T1-T4 → T5 一方向 inherit) で literal 表現
- T5 API design は T1-T4 referenceable な future-proof pattern (移植段階で T1-T4 が逆方向に T5 を query する API 拡張 path 確保、 doctrine: future-proof 順守)
- T5 PoC 内部に T1-T4 mock client は literal 不要 (PoC = T1-T4 過去 output sample を input data として ingest、 双方向 dependency 不発)

## 3. 機密度 + 取扱方針

- **PII**: 合成 PMI case data + 合成 paper RAG corpus only、 実 M&A PMI 案件 / 実 top-tier consulting firm/top-tier PMI advisor/top-tier consulting firm paper / 実 担当者連絡先 / 実顧客社名 literal 一切扱わない
- **credential**: ANTHROPIC_API_KEY のみ (.env、 gitignore 必須、 Week 3 Assistant LLM call phase で active 化)
- **doctrine: sandbox-check**: 試作 scope + 合成データ only のため host PC OK (real PMI case + real paper 投入時に Docker / sandbox 化必須、 paper license 個別 confirm 必須)

## 4. 採用 stack 10+ 件 (doctrine: prior-art-first + doctrine: external-source-audit 順守、 Week 1 audit gate 通過後 active)

### T5 新規採用 1 件 + T1-T4 inherit 7 件 + internal inherit 1 件 + MAIS 自作 1 件 = 10 件 literal

#### T5 新規採用 1 件

| # | ひな形 | license | 役割 | red flag | tier |
|---|---|---|---|---|---|
| ① | **多軸 weighted similarity 自作 detector** (業種 / 規模 / 文化 / 財務 / 統合 type 5 dim、 weight tunable、 PoC = literal hardcode、 移植 = learning-based) | MAIS 内部 (T5 自作) | 「過去のうち最も類似する 2-3 件」 を多軸 auto-surface (original proposal line 461) | None (自作、 5-stage hybrid 上の application layer) | ★★★ (Week 2 implement) |

#### T1-T4 inherit 7 件 (既 audit 済、 本 PJ で literal reuse のみ)

| # | ひな形 | license | inherit 元 | 役割 |
|---|---|---|---|---|
| ② | LangGraph 1.2.0+ + langgraph-checkpoint 4.1.0+ | MIT | T3 ADR-201 + T4 ADR-301 (CVE-2026-28277 元削除済 pin) | DAG-based query → retrieval → similar case → Assistant recommendation orchestrator |
| ③ | LlamaIndex CitationQueryEngine | MIT | T2 ADR-101 | citation infra (paper / case retrieval link back) |
| ④ | sentence-transformers >=5.4,<6.0 + faiss-cpu + rank-bm25 + cross-encoder | mixed (Apache-2.0 中心) | T1 ADR-005 + T2 起源 cross-PJ template | 5-stage hybrid pipeline (multi-axis case retrieval + paper RAG) |
| ⑤ | transformers >=5.0,<6.0 | Apache-2.0 | T2 起源 cross-PJ template (CVE-2026-1839 fix 込み) | embedding base + cross-encoder |
| ⑥ | docling >=2.0,<3.0 | MIT | T2 ADR-101 | paper / case 文書 parsing (Excel/Word/PPT/PDF) |
| ⑦ | LLMProvider Protocol (MockProvider / Claude / Gemini swap) | (T1 既存) | T1 ADR-005 + T4 ADR-304 | Stage 5 LLM listwise rerank + Assistant recommendation、 試作 = MockProvider |
| ⑧ | TTS engine video pipeline (まお おちついた + Playwright + ffmpeg + auto-sync) | LGPL-3.0 / Apache-2.0 | cross-PJ universal SSoT | 機能紹介動画 (cross-PJ SSoT 経由 literal 即適用) |

#### internal inherit 1 件 (internal、 internal ADR で audit + literal reference)

| # | ひな形 | license | 役割 |
|---|---|---|---|
| ⑨ | internal AI orchestration **ontology module** (`(internal config)/internal_kb/ontology/{types,interfaces,link_types,action_types}.yaml`) | (internal) | Object Type / Property / Link Type / Action Type pattern literal inherit、 M&A PMI domain に scale up (PoC = 概念 inherit のみ、 移植 = literal Object Type 統合) |

#### MAIS 自作 1 件 (競合優位 core)

| # | ひな形 | license | 役割 |
|---|---|---|---|
| ⑩ | MAIS 自作 **PMI case ADR schema + Decision/Outcome 構造化 layer** | MAIS 内部 | 過去 PMI 案件の意思決定 / 失敗 / 修正 / 成果を ADR (Architecture Decision Record) 形式で構造化 (original proposal line 459) |

## 5. 2026.5 deeper scan 結論

### Assistant 型対話 採用 — **5-stage hybrid + LLMProvider listwise CoT + audit log** literal 確定

OSS 「1:1 一致」 Assistant pattern (junior コンサル query → context + 引用 + 推奨) は **literal ZERO** (top-tier consulting firm 内部 + top-tier consulting firm 内部 deployment、 OSS 公開なし)。 ただし decomposed prior art として:
- query → retrieval = 5-stage hybrid pipeline (T1-T4 既 inherit)
- context retrieval = LlamaIndex CitationQueryEngine (T2 inherit、 link back 標準)
- listwise recommendation = LLMProvider Protocol + Claude CoT (T4 既 inherit)
- audit log = T1-T4 vault audit pattern inherit + Assistant query trace 自作

→ literal 全 component inherit + Assistant composition layer のみ T5 自作 = doctrine: waste-zero + doctrine: prior-art-first 順守。

### 多軸類似 case auto-surface 採用 — **5-stage hybrid + 自作 weighted similarity detector** literal 確定

多軸 similarity の機械学習 ground truth = MAIS 内部過去 PMI 16 社実績 (移植段階で literal active)、 PoC 段階は **weight literal hardcode** (業種 0.30 + 規模 0.20 + 文化 0.20 + 財務 0.15 + 統合 type 0.15) + 5 dim cosine similarity aggregate。 移植段階で learning-based 化 path 確保 (doctrine: future-proof)。

### Ontology layer 採用 — **internal AI orchestration ontology inherit** literal 確定

original proposal line 477 「internal AI orchestration + Ontology module を enterprise scale に拡張する path が現実的」 literal 順守。 existing internal ontology layer (`(internal config)/internal_kb/ontology/{types,interfaces,link_types,action_types}.yaml`、 doctrine: ontology-first doctrine 起源) を 「**概念 inherit + M&A PMI domain extension**」 で T5 に literal scale up。 PoC 段階 = T5 内 Object Type 6 件 (PMICase + Decision + Outcome + Pattern + Reference Paper + Assistant Query) を internal ontology pattern に整合させて起草、 移植段階 = internal ontology に M&A PMI Object Type を literal 統合する path。

### RAG paper ingestion 採用 — **docling + 合成 paper corpus** literal 確定 (PoC scope)

実 top-tier consulting firm/top-tier PMI advisor/top-tier consulting firm paper download = license 個別 confirm 必須 (PoC scope 外)。 PoC = **合成 paper corpus 50 件** (Faker + LLM-generated abstract、 top-tier consulting firm/top-tier PMI advisor/top-tier consulting firm 業界 pattern を 5 dim 多軸網羅、 RAG retrieval + Citation link back full active)。 移植段階 = 実 paper individual license confirm + ingestion path (doctrine: client-no-recovery 順守、 paper publisher license 個別)。

## 6. internal ADR 共通 doctrine 6 component inherit (citation reference のみ、 重複起草禁止)

1. brand identity — MAIS / T5 Knowledge、 黒金 / Noto Serif JP / 年輪 SVG / tagline 「経営の責務を、 次の人へ。」
2. visual identity — 金 (`#d4af37` 等) × 黒、 motif + layout literal 不変
3. data 共通 doctrine — 会員制 two-sided + **PII/Op 分離** (T5 PII = 担当者氏名 / 顧客社名 / paper signatory、 Op = redact 済 PMI case structure / Decision / Outcome / paper abstract redacted) + 7-layer security
4. AI pipeline 共通 doctrine — 5-stage hybrid + LLMProvider Protocol (T5 = case retrieval + paper RAG + Assistant recommendation)
5. 動画 pipeline 共通 doctrine — TTS engine まお おちついた + auto-sync + 90s timeout (cross-PJ universal SSoT、 2026-05-13 完成、 **英字 brand 名 literal カタカナ化必須** = T4 2026-05-14 catch inherit)
6. infra / drift 防止 共通 doctrine — drift CI + pip-audit + Dependabot + e2e_smoke + internal knowledge base 5 file + cross-PJ python-ml-stack Standard Pin

## 7. T5 固有拡張 (internal ADR+、 重複起草禁止)

- **internal ADR**: T5 PJ scope 確定 (本 brief literal 反映、 本 turn 起草)
- **internal ADR**: 採用 OSS 10 件 audit + internal ontology inherit + Week 1 requirements + cross-PJ python-ml-stack Standard Pin literal apply (本 turn 起草)
- **internal ADR**: T4 → T5 入出力契約 schema + T1/T2/T3 → T5 cross-stage inherit + 「単独 tool ではない」 unique 性質を single-direction PoC で literal 表現 (本 turn 起草)
- **internal ADR**: T5 Object Type 6 件 (PMICase / Decision / Outcome / Pattern / Reference Paper / Assistant Query、 internal ADR § 3 PII/Op 分離 pattern 適用、 Week 1 起草)
- **internal ADR**: LangGraph state graph + 多軸 weighted similarity detector 自作 (5 dim weight + cosine aggregate、 Week 2 起草)
- **internal ADR**: Assistant 型対話 audit log + RAG paper ingestion + Citation link back (Week 3 起草)

## 8. 4 週 PoC roadmap

| Week | 着手 task | deliverable |
|---|---|---|
| **Week 0** | GitHub PRIVATE repo 作成 + scaffold 全 file + drift CI / pip-audit / Dependabot active + internal ADR/401/402 起草 | green CI / internal knowledge base 5 file / 本 Discovery brief literal 採択 |
| **Week 1** | 採用 10 stack audit (internal ontology inherit verify + T1-T4 inherit verify + 新規 1 件 = 多軸 weighted similarity detector audit) + Requirements (EARS) + Object Type 6 件 internal ADR + 合成 PMI case data 生成 (30 件 case + 200 件 Decision + 200 件 Outcome + 20 件 Pattern + 50 件 paper corpus) + T1-T4 → T5 ingestion implementation | internal ADR/402/403 / `src/` 13 module dir + `tests/` |
| **Week 2** | LangGraph state graph 実装 (query → retrieval → similar case → Assistant) + 多軸 weighted similarity detector 自作 (5 dim weight + cosine aggregate) + MockProvider Assistant recommendation smoke | internal ADR / state graph + similar case auto-surface literal 動作 + smoke test |
| **Week 3** | RAG paper ingestion (docling parse + chunk + embed + LlamaIndex index) + Assistant 型対話 full active (audit log emit + Citation link back) + Claude LLM swap (MockProvider → Claude listwise CoT) | internal ADR / Assistant dialogue + RAG retrieval + audit trail full literal 動作 |
| **Week 4** | FastAPI/Jinja UI (knowledge base search + Assistant dialogue + similar case panel + 黒金 brand CSS) + Vault Pattern (担当者氏名 + 顧客社名 + paper signatory vault) + e2e_smoke + 動画 pipeline (SCENES T5 版、 cross-PJ SSoT 経由 literal 即適用、 16 scene 程度、 narration カタカナ化 順守) | `out_video/mais_mantle_demo.mp4` (T5) + e2e_smoke 18+ step PASS + プレゼン ready |

## 9. T4 → T5 入出力契約 (sibling 連携 literal 設計、 internal ADR reference)

T4 (mais-pmi-cockpit、 完成度 100%) の literal 完成 API output:
- **CockpitProject** (CP-XXXXXX)
- **KpiDefinition / KpiSnapshot** (KP/KS-XXXXXX)
- **DriverInsight** (DR-XXXXXX、 + driver_factors + citation_array + redacted insight statement)
- **NextAction** (NA-XXXXXX、 + audience_mapping + priority_rank + status)
- **SentimentEvent** (SE-XXXXXX、 + sentiment_score + topic_tag + redacted excerpt)
- **VendorContract / SaasLicense** (VC/SL-XXXXXX、 + overlap_candidate)
- **RetentionRisk** (RT-XXXXXX、 + dimension + triggered_jp_patterns + mitigation_recommendation_redacted)

T5 が **入力として literal 流用** (T4 1 件 cockpit lifecycle = T5 1 件 PMI case lifecycle と analogical):
- T4 `CockpitProject` (1 件 100 日 cockpit) → T5 `PMICase` (PMI-XXXXXXXXX、 1 件 PMI 案件 lifecycle root、 DD-stage + Day-1 + Day-100 統合 + final outcome)
- T4 `DriverInsight` + `NextAction` (rationale → outcome pair) → T5 `Decision` (DEC-XXXXXX、 ADR 形式) + `Outcome` (OUT-XXXXXX、 success/failure/partial)
- T4 `SentimentEvent` (退職率 sentiment) → T5 PMICase culture dimension (多軸類似 case auto-surface 入力)
- T4 `VendorContract / SaasLicense` (vendor 統合機会) → T5 PMICase financial dimension
- T4 `RetentionRisk` (jp_pattern 連携) → T5 PMICase culture + business_practice dimension cross
- T1-T3 過去出力も同 pattern (T1 ProfileOp/CompanyOp = sourcing stage record / T2 DDP/Q/A/CIT = DD stage record / T3 IntegrationPlan/RiskScore/CommunicationKit = integration stage record) で T5 PMICase に inherit

→ T1-T4 → T5 mapping table を T5 operational DB に literal 保存、 T1-T4 API output は 既 redact 済 literal 前提。

## 10. 制約 (T1/T2/T3/T4 と同)

- ✅ 無料 + クレカ不要範囲のみ
- ✅ 合成 PMI case data + 合成 paper RAG corpus only (実 PMI 案件 / 実 paper literal 不在)
- ✅ consumer laptop 完走前提 (doctrine: consumer-hw)
- ✅ internal ADR+ で T5 固有起草、 internal ADR 重複禁止
- ✅ T1-T4 API output literal 流用設計 (single-direction PoC)
- ✅ internal AI orchestration ontology = 概念 inherit のみ、 literal import 禁止 (PoC repo 独立性)
- ✅ 実 paper RAG ingestion = PoC scope 外 (移植 phase user 明示 gate + license 個別 confirm)

## 11. 受託 deploy 前 ★★★ 化 残 task (T1/T2/T3/T4/T5 共通、 後日)

- TTS engine 1 週間 stability dry-run
- default model `22e8ed77-94fe-4ef2-871f-a86f94e9a579` literal 商用 license 確認
- 顧客案件 sandbox dry-run (doctrine: client-no-recovery)
- LangGraph + LlamaIndex + docling + HF Transformers の 2026 advisory 履歴 sweep (doctrine: external-source-audit)
- 大型案件 = external pentesting 推奨
- Layer 5 dep-review.yml GHAS active 化 (3 path、 受託契約時 user 判断)
- **T5 固有**: 実 top-tier consulting firm/top-tier PMI advisor/top-tier consulting firm paper RAG ingestion 段階 = paper license literal 確認必須 (PoC = 合成 paper、 移植 = 実 paper 個別 license)
- **T5 固有**: internal AI orchestration → PMI Ontology literal 統合 path 評価 (受託契約段階で user gate)
