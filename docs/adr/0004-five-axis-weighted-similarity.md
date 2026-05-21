# ADR-0004: Five-axis weighted similarity for PMI case retrieval (industry / culture / size / integration type / financial)

## Status

Accepted (2026-05-22)

## Context

The Assistant dialogue's anchor surface is "5 most-similar past cases" — when a junior consultant asks a natural-language question, the system returns a ranked recommendation grounded in a small set of historical engagements that resemble the queried situation. The retrieval pipeline (see [ADR-0003](0003-five-stage-hybrid-retrieval.md)) produces text-similarity-ranked candidates, but text similarity alone does not capture how a senior consultant judges "similar" — that judgment runs along domain axes.

The repo's premise is that those axes are explicit and weightable. The README "30-second pitch" frames it: "5-axis weighted similarity (industry / scale / culture / financial / integration type) surfaces the closest 2-3 historical cases." This ADR records which axes were chosen, why, what the weights are, and how the similarity function is computed for each axis.

Four constraints frame the decision:

1. **Interpretability** — a senior partner reviewing the Assistant's recommendation must be able to inspect *why* a particular case was surfaced. A black-box similarity model defeats the audit-grade replayability requirement carried over from [ADR-0002](0002-graphrag-self-built.md).
2. **No labelled training corpus** — the PoC works on a synthetic casebook; there is no historical "similar / not similar" pair set to learn weights from.
3. **Mixed feature shapes** — industry is categorical (one-hot), size and financial are ordinal bands, culture and integration type are short categorical taxonomies. The similarity function must compose these correctly.
4. **2-3 case top-K** — the README and product framing commit to surfacing 2-3 cases, not 20. The ranker must produce a top-K that is small and confidently domain-correct.

## Decision

Five axes with hardcoded PoC weights, evaluated independently per axis and combined linearly. The weights are recorded in the `PatternWeight` schema in [src/schema/types.py](../../src/schema/types.py) and consumed by [src/retrieval/multi_axis_similar_cases.py](../../src/retrieval/multi_axis_similar_cases.py):

| Axis | Weight | Feature type | Distance function |
| --- | --- | --- | --- |
| `industry` | 0.30 | Categorical (sector taxonomy) | Exact match → 1.0, mismatch → 0.0 |
| `culture` | 0.25 | Short categorical taxonomy | Exact match → 1.0, mismatch → 0.0 |
| `size` (`SizeBand`) | 0.20 | Ordinal (`under_50` < `50-100` < `100-300` < `300-500` < `500-1000` < `over_1000`) | Step distance → score (`{0: 1.0, 1: 0.7, 2: 0.4, 3+: 0.0}`) |
| `integration_type` | 0.15 | Short categorical taxonomy | Exact match → 1.0, mismatch → 0.0 |
| `financial` (`FinancialBand`) | 0.10 | Ordinal (`5-10` < `10-30` < `30-50` < `50-100` < `over_100`) | Step distance → score (same table as `size`) |

Total weight sums to 1.0; the linear combination produces a similarity score in `[0, 1]`. Top-K is fixed at 2-3 per the product surface ([src/retrieval/multi_axis_similar_cases.py:10](../../src/retrieval/multi_axis_similar_cases.py)).

## Why these axes specifically

The five axes correspond to the variables a senior PMI consultant cites when explaining why two engagements are or are not comparable. They are also the five fields most consistently present in the PMI case taxonomy (see [src/schema/types.py](../../src/schema/types.py)'s `PMICase` model).

### Why these weights (0.30 / 0.25 / 0.20 / 0.15 / 0.10)

`industry` weighted highest because cross-industry pattern transfer in PMI is empirically weak — a manufacturing PMI playbook does not usefully predict a financial-services PMI outcome, irrespective of size or financial match. `culture` second because culture mismatch is the most-cited PMI failure cause in the integration literature (see references). `size` third because operational scale shapes integration tempo. `integration_type` fourth because absorbed vs preserved vs symbiotic vs holding-only is mostly determined by the prior two. `financial` lowest because financial band is the weakest predictor of *integration similarity* (it predicts deal economics, not integration shape).

These weights are PoC hardcoded; a learning-based path is the explicit forward wedge — see "Consequences / Negative" below.

## Why ordinal bands instead of raw numbers (for `size` and `financial`)

Raw employee count or revenue produces a continuous distance metric that overweights small numerical gaps near band boundaries (a 49-employee vs 51-employee case would be "very different" on raw distance, but PMI-relevant decisions cluster within the same band). Ordinal bands reflect the way senior consultants actually reason — "small / mid-cap / large" — and produce a stable distance function.

The 3-step table (`{0: 1.0, 1: 0.7, 2: 0.4, 3+: 0.0}`) is empirically calibrated against the synthetic casebook so that within-band cases dominate the top-5 and across-three-band cases drop out.

## Alternatives considered

### Cosine similarity on a single embedding vector spanning all fields (rejected)

- **Pros**: simple, single distance function, fewer hyperparameters.
- **Cons**: collapses the five axes into a black box; defeats interpretability (the senior partner cannot see *which* axis caused the surface). Also requires a labelled corpus to choose the encoder + projection, which the PoC does not have.
- **Why rejected**: violates the interpretability constraint. The Assistant's recommendation surface must show per-axis scores, not just a final number.

### Equal weights across all five axes (rejected)

- **Pros**: no judgment calls about which axis matters more.
- **Cons**: empirically, equal weights surfaced industry-mismatched cases when culture + size + integration + financial all happened to match — exactly the wrong outcome per the senior-consultant heuristic.
- **Why rejected**: the senior heuristic explicitly says industry mismatch dominates other matches.

### Learning-based weights (logistic regression / gradient boosting on labelled pairs) (rejected for PoC; forward wedge)

- **Pros**: weights come from data, not from a hand-tuned heuristic.
- **Cons**: requires a labelled "these two cases are similar / not similar" corpus, which the synthetic PoC does not have. Customer-deployment would have this corpus from the firm's historical engagement reviews.
- **Why rejected for PoC**: no training labels available. **Documented as the next step** for the deployment-tier path; the `PatternWeight` schema is shaped to accept learned weights without code changes.

### Drop ordinal bands, use raw numbers (rejected)

- **Pros**: more granular.
- **Cons**: see "Why ordinal bands" above — raw distance is brittle at band boundaries and does not match how consultants reason.
- **Why rejected**: gains in granularity are illusory; lose interpretability and stability.

### More axes (10+ axes with finer-grained taxonomies) (rejected)

- **Pros**: in principle, more axes could capture more of the senior-consultant heuristic.
- **Cons**: each additional axis adds a weight hyperparameter and a feature-engineering surface; the synthetic casebook does not have stable signal for additional axes; the README commitment is 5 axes.
- **Why rejected**: scope discipline. The five axes already cover the senior heuristic per the integration literature; adding more dilutes the per-axis signal without buying recall.

## Consequences

### Positive

- Per-axis scores flow into the Assistant's response, so the recommendation surface can show *why* a case was top-ranked (e.g., "industry + culture + size all matched; financial differs"). This is what makes the surface auditable.
- Schema-encoded weights mean a customer deployment can replace the PoC weights with learned weights by writing a single Pydantic instance, no code change.
- Ordinal bands are stable under small data perturbations — adding or removing a single case does not reorder the top-K.

### Negative

- Weights are PoC heuristics, not learned. They are calibrated by inspection on the synthetic casebook + integration-literature consensus, not by a held-out validation set. Documented gap; the customer-deployment swap path is to learn weights from the firm's review history.
- Categorical axes (industry / culture / integration_type) use exact-match similarity, which has no smoothing — a sector hierarchy ("manufacturing" ⊃ "automotive" ⊃ "EV components") is not modelled. Real-deployment improvement path: replace exact-match with a sector-tree distance.

### Reversibility

The axis set, weights, and distance functions are all isolated to [src/retrieval/multi_axis_similar_cases.py](../../src/retrieval/multi_axis_similar_cases.py) and the schema in [src/schema/types.py](../../src/schema/types.py). Replacing the hardcoded `PatternWeight` with a learned weight vector is a Pydantic-instance change; replacing exact-match with a sector-tree distance is a per-axis function swap. The Assistant's downstream consumer does not change.

## References

- [Larsson & Finkelstein, "Integrating strategic, organizational, and human resource perspectives on mergers and acquisitions"](https://journals.aom.org/doi/10.5465/amr.1999.1893923) — origin of the culture-mismatch-as-dominant-failure-mode citation
- [Haspeslagh & Jemison, *Managing Acquisitions: Creating Value Through Corporate Renewal* (1991)](https://www.hbs.edu/faculty/Pages/item.aspx?num=10193) — origin of the integration-type taxonomy (absorption / preservation / symbiosis / holding)
- [Pablo, "Determinants of acquisition integration level: A decision-making perspective"](https://journals.aom.org/doi/10.5465/256787) — empirical grounding for the size + integration-type interaction
- [Bauer & Matzler, "Antecedents of M&A success: The role of strategic complementarity, cultural fit, and degree and speed of integration"](https://doi.org/10.1002/smj.2091) — culture-fit weight grounding
- Code: [src/retrieval/multi_axis_similar_cases.py](../../src/retrieval/multi_axis_similar_cases.py), [src/schema/types.py](../../src/schema/types.py)
