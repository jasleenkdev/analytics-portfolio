# Ground truth: planted effects in the project 2 generator

Rendered from `data_gen/plants.toml` and `data/planted_entities.json` by the generator. The analysis never reads either; they are used only by the final found-vs-planted cross-check.

## Experiment A: free-delivery threshold (40.0 -> 25.0)
Users: 60000 randomised 50/50 on first visit between 2026-05-04 and 2026-05-10; each observed for 21 days.

1. **Sample-ratio mismatch on one day.** On assignment day 3 (2026-05-07), 35% of control assignments were dropped from the assignment log (1135 users). Those users still exist and still order; they are just missing from `assignments`. Expected signature: overall SRM; the daily split is balanced except on that day.
2. **Novelty effect.** Treatment lifts the order rate by 0.15, 0.07, 0.03 (relative) in weeks 1, 2 and 3 after assignment. Expected signature: a lift that decays week by week.
3. **Heterogeneous effect.** Users who signed up less than 90 days before the test get an extra 0.08 lift in every week. Platform and zone have no true effect differences.
4. **Cannibalisation of high-margin baskets.** In treatment, the probability that an order is a high-margin (small, top-up) basket is multiplied by 0.7. Expected signature: lower high-margin share and lower product margin per order in treatment.
5. **Threshold bunching.** In treatment, 50% of baskets within 6.0 below the new threshold are topped up to just above it.
- **Net truth:** more orders and GMV, lower contribution margin per user (lost fees + cheaper basket mix). The right call is not to launch at this threshold.

## Experiment B: rider-batching pilot
24 nodes, 8 treated (N01, N02, N04, N05, N08, N16, N18, N23), 56 days before and 56 days after 2026-03-02.

1. **Cost benefit.** Rider minutes per order change by -12% at treated nodes after the start.
2. **Guardrail regression.** Defect rate rises by 0.6 percentage points at treated nodes; mean delivery time rises by 1.4 min; % within SLA changes by -1.5 points.
3. **Parallel trends hold.** Treated and control nodes share seasonality, trend and daily shocks; there is no pre-period divergence, so a placebo test should find nothing.
4. **Data gap.** Control node(s) N21 lose days 20, 21, 22 of the panel (unbalanced panel).
- **Net truth:** the pilot saves rider cost but breaches the defect guardrail; it should not be scaled as-is.
