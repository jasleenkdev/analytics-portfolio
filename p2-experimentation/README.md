# Experimentation and pilot evaluation

**Business questions:** should we launch a lower free-delivery threshold, and should we scale a rider-batching pilot?

> **Simulated data.** Everything comes from a seeded Python generator (`data_gen/generate.py`, seed 20260504), not from any real company. Assumptions: 60000 users with gamma-Poisson order rates, lognormal basket sizes and a propensity for small high-margin baskets; a 28-day pre-period under the current policy; users randomised 50/50 on first visit during a 7-day assignment week and observed for 21 days; delivery fee 3.49 below the free threshold and a cost to serve of 3.8 per order. The pilot is a daily panel of 24 nodes (8 randomly chosen for batching) over 56 days before and 56 after the switch-on, with shared seasonality and shocks.

**Live dashboard:** https://jasleenkdev.github.io/analytics-portfolio/p2/  |  Dashboard file: [`docs/index.html`](docs/index.html)  |  Memo: [`memo.md`](memo.md)  |  CSV: [`outputs/kpi/`](outputs/kpi)  |  Excel: [`outputs/p2_experiment_readout.xlsx`](outputs/p2_experiment_readout.xlsx)

## Answers
| Question | Call | Key evidence |
|---|---|---|
| Lower free-delivery threshold 40 to 25 | **do not launch** | contribution per user -13.7% (95% CI -15.3% to -12.2%) despite orders 9.9% |
| Scale rider batching | **do not scale as-is: fix the guardrail and extend** | cost per order -12.4%, defect rate 0.60 pp vs 0.3 pp tolerance |

## Findings: promotion test
1. **Sample-ratio mismatch.** The overall split (28,952 control vs 29,913 treatment) fails the SRM test (p = 7.5e-05). The per-day test isolates 2026-05-07; the data-quality check also finds 816 users who ordered during the test with no assignment record, consistent with lost control logs. Excluding that day's cohort from both arms restores balance (p = 0.52).
1. **Primary metric.** Contribution per user -2.16 (-13.7%, 95% CI -15.3% to -12.2%) with CUPED, which cut variance by 41%. The minimum detectable effect was 3.0% raw and 2.3% with CUPED, so the test was well powered.
1. **Volume up, economics down.** Orders 9.9%, GMV 14.2%, share of users ordering 2.6 pts; but fee revenue -51% and contribution per order -22%. Break-even would need 28% more orders.
1. **Cannibalisation of high-margin baskets.** High-margin basket share 30.4% in control vs 20.9% in treatment (delta-method CI -10.0 to -8.9 pts). Baskets bunch just above the new threshold: 18.2% of treatment orders vs 9.9% of control orders fall in the 4 units above it.
1. **Novelty.** Order lift by week since assignment: week 1 17.8%, week 2 11.3%, week 3 5.0% (decay test p < 0.001). Contribution effect by week: -7.8%, -12.6%, -17.5%.
1. **Segments.** orders x platform: Holm p = 0.159; orders x zone: Holm p = 0.169; orders x tenure: Holm p = 0.029; contribution x platform: Holm p = 0.066; contribution x zone: Holm p = 0.323; contribution x tenure: Holm p = 0.066. Only tenure differs after correction: new customers' order lift 17.0% vs 7.7% for established customers.

## Findings: rider-batching pilot
| Metric | DiD estimate | 95% CI | Relative | Pre-trend p | Placebo p |
|---|---|---|---|---|---|
| cost_per_order | -0.7483 | -0.7802 to -0.7164 | -12.4% | 0.48 | 0.76 |
| mean_delivery_min | 1.4684 | 1.3919 to 1.5450 | 5.9% | 0.70 | 0.28 |
| defect_rate | 0.0060 | 0.0049 to 0.0071 | 16.8% | 0.60 | 0.94 |
| pct_within_sla | -0.0133 | -0.0160 to -0.0106 | -1.5% | 0.80 | 0.86 |

Two-way fixed effects (node and date) with node-clustered errors; 8 pilot and 16 control nodes. The cost saving is real, but the defect guardrail is breached: its whole CI lies above zero and the estimate exceeds the 0.3 pp tolerance. Parallel trends hold on the linear pre-trend and placebo tests; the joint test of weekly leads gives p between 0.015 and 0.31 across metrics with no individual pre-period week significant (see the event-study chart).

## Found vs planted
The generator plants known effects, listed in [`GROUND_TRUTH.md`](GROUND_TRUTH.md). The analysis was built without reading that file; afterwards `analysis/crosscheck.py` compared the findings with it. Result: **12 hit, 1 partial, 0 missed**, plus 0 detection(s) of things that were not planted.

| Planted | What the analysis found | Verdict | Note |
|---|---|---|---|
| A1. SRM: 1135 control assignments lost on 2026-05-07 | SRM detected (p = 7.5e-05); flagged day(s) ['2026-05-07']; balanced after exclusion (p = 0.52) | hit |  |
| A2. novelty: order lift by week [0.15, 0.07, 0.03] (+0.08 for new users) | decay test p 1e-04 or smaller; estimates wk1 +17.8% (+15.2 to +20.4), wk2 +11.3% (+8.8 to +13.9), wk3 +5.0% (+2.5 to +7.5) | hit | expected given 23% new users: wk1 +16.9%, wk2 +8.9%, wk3 +4.9%; 3/3 weekly CIs contain the expected lift |
| A3. heterogeneity: new users respond more; platform and zone do not differ | interaction tests significant after Holm: ['tenure'] | hit | no false positives on platform or zone |
| A4. cannibalisation: high-margin basket probability x0.7 | high-margin share 30.4% to 20.9% (ratio 0.69) | hit |  |
| A5. bunching: 50% of baskets within 6.0 below the new threshold topped up | orders just above the new threshold: 18.2% (treatment) vs 9.9% (control); just below: 8.3% vs 16.5% | hit |  |
| A6. net truth: do not launch | decision: do not launch | hit |  |
| B1. rider minutes per order -12% | cost per order -12.4% (95% CI -13.0 to -11.9) | hit | first version divided by the pre-period level and overstated the saving (-13.0%); fixed in the cross-check to use the post-period counterfactual |
| B2. defect rate pp +0.6 | DiD +0.60 (95% CI +0.49 to +0.71) | hit |  |
| B2. delivery minutes +1.4 | DiD +1.47 (95% CI +1.39 to +1.54) | hit |  |
| B2. % within SLA pp -1.5 | DiD -1.33 (95% CI -1.60 to -1.05) | hit |  |
| B3. parallel trends hold; placebo should be null | linear pre-trend p >= 0.48; placebo p >= 0.28; joint weekly-lead test p < 0.05 for ['mean_delivery_min'] | partial | the joint lead test raised a false alarm with 24 clusters; the decision gate (slope and placebo) was right |
| B4. 3 missing node-days at ['N21'] | 3 missing node-days found; panel kept unbalanced | hit | count found; the node is not named in the report |
| B5. net truth: do not scale as-is | decision: do not scale as-is: fix the guardrail and extend | hit |  |


**Commentary.** Two things changed because of this cross-check. The pilot's relative saving was first computed against the pilot nodes' pre-period cost; because costs drift up over time this overstated the saving, so relative effects now use the post-period counterfactual. And the joint test of weekly pre-period leads flags delivery minutes even though no single lead is significant and the planted data has parallel trends; I keep it visible as a known false-alarm risk with few clusters rather than tuning it away.

## Method
1. **SQL** (`sql/`): data-quality checks and daily arm counts; experiment tables (one row per assigned user with pre-period covariates and 21-day window metrics; user x week for novelty); sufficient statistics per arm, week and segment; per-order ratio moments; pilot node-day panel, weekly series and the raw 2x2.
2. **Statistics** (`analysis/stats.py`, `analysis/findings.py`): chi-square SRM test overall and per day; power and minimum detectable effect; Welch difference in means with 95% CIs; CUPED; delta-method ratios; novelty by week with a per-user decay test; segment effects with Holm correction and interaction tests; two-way fixed-effects DiD with node-clustered errors, event study, linear pre-trend test and placebo; guardrails and decision rules fixed in code (`analysis/findings.py`).
3. **Verification** (`tests/`): generator invariants; SQL metrics recomputed in pandas from raw tables; statistics checked against scipy, a bootstrap, an A/A simulation and synthetic panels with a known effect; Excel formulas evaluated and compared with the Python readout.

Every number in this README and the memo is rendered from `outputs/findings.json`. Design choices are logged in the repository's `DECISIONS.md`.

## Outputs for BI tools
Power BI, Tableau and Looker cannot be built headlessly, so the dashboard is a single self-contained HTML file published to GitHub Pages (`make pages` pushes the built site to the `gh-pages` branch). The sufficient statistics and results are exported as CSV (`outputs/kpi/`) and as an Excel workbook where CIs, p-values, power, SRM tests and the raw DiD are live formulas.

## Limitations
- Simulated data: no churn, no long-term habit change, and users do not interact with each other (no network effects or rider-capacity spillovers between arms).
- 21-day windows cannot show whether the extra orders are pulled forward from later weeks.
- 8 treated clusters make cluster-robust errors approximate; conclusions are drawn only where intervals are far from decision thresholds.
- Guardrail tolerances are business judgements held in config; a different tolerance can change the pilot call.

## Run it
```
make p2      # from the repository root
```
