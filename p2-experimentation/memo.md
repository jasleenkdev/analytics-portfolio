# Memo: free-delivery threshold test and rider-batching pilot

**To:** Growth and operations leads  **From:** Analytics  **Data:** simulated (seeded generator, not real company data)

## 1. Lower free-delivery threshold (40 to 25): **DO NOT LAUNCH**
- **Result:** contribution per user -13.7% (95% CI -15.3% to -12.2%; -2.16 per user over 21 days), even though orders rose 9.9% and GMV 14.2%.
- **Why:** delivery-fee revenue fell 51%, and the mix shifted: the high-margin basket share dropped 9.4 points (30% to 21%) as customers padded baskets to reach the free threshold (18% of treatment orders sit just above it vs 10% in control). Contribution per order fell 22%.
- **The lift fades:** the order lift was 18% in week 1 and 5% in week 3 (decay test p < 0.001), while the contribution gap widened (-8% to -18%).
- **Uncertainty:** the CI excludes zero by a wide margin; to break even, orders would need to rise 28% at the new contribution per order, against 10% observed. A logging fault on 2026-05-07 unbalanced the arms (SRM p = 7.5e-05); that day's 5,453 users were excluded and the split is clean afterwards (p = 0.52). Without CUPED, the estimate is -12.5% before exclusion and -12.7% after.
- **Segments:** only tenure shows a genuinely different response after Holm correction (new customers' order lift 17% vs 8% for established); platform and zone differences are within noise.
- **What would change the call:** a test of a smaller threshold cut or a free-delivery offer limited to new customers (the most responsive group), and a longer holdout to see whether the extra orders persist or pull purchases forward. With CUPED (41% variance reduction) this test could detect a 2.3% change in contribution; detecting a 1% change would need about 145,722 users per arm.

## 2. Rider batching pilot (8 pilot vs 16 control nodes): **DO NOT SCALE AS-IS: FIX THE GUARDRAIL AND EXTEND**
- **Benefit:** rider cost per order -13.0% (95% CI -13.5% to -12.4%), about 382 per node per day at 510 orders a day.
- **Cost:** defect rate 0.60 pp (95% CI 0.49 to 0.71) against a tolerance of 0.3 pp (breached): about 3.1 extra defective orders per node per day. Delivery time 1.5 min; on-time share -1.3 pp (tolerance 2.0 pp, within).
- **Is the comparison fair?** Yes: no pre-period divergence (linear pre-trend p from 0.48 to 0.80) and placebo tests on a fake start date find nothing (p >= 0.28).
- **What would change the call:** a batching rule that excludes fragile or chilled items, or caps the wait for a partner order, re-tested on the same pilot and control nodes for 4 to 6 weeks. If the defect increase falls inside the tolerance while the saving holds, scale. With only 8 pilot nodes, a second wave of nodes would also tighten the cluster-level uncertainty.
