# Customer, product and inventory analytics

**Business question:** which customers retain and why, which products and categories deserve more space, and how should each node's assortment change?

> **Simulated data.** Everything comes from a seeded Python generator (`data_gen/generate.py`, seed 20250101), not from any real company. Assumptions: 80000 customers signing up through 365 days from 2025-01-01 via five acquisition channels; Poisson ordering with a gamma-distributed personal rate while active and an exponential lifetime set by a monthly churn hazard; baskets of 1 + Poisson(4.8) lines, 55% from a personal repertoire of 12 favourite SKUs; 420 SKUs in 15 categories ranged differently across 8 nodes; a six-step checkout funnel; daily order-up-to replenishment with FIFO ageing and write-off for perishables.

Dashboard file: [`docs/index.html`](docs/index.html)  |  Memo: [`memo.md`](memo.md)  |  CSV: [`outputs/kpi/`](outputs/kpi)  |  Excel: [`outputs/p3_assortment_wastage.xlsx`](outputs/p3_assortment_wastage.xlsx)

## Headline
76,479 ordering customers; 46.7% reorder within 30 days and 67.0% within 90. Of first-order cohorts with at least six months of history, 43.3% order again in month 1 and 17.0% in month 6. 146 class-A SKUs carry 80% of revenue. Perishable waste cost 284,290 (10.2% of units received).

## Findings
1. **Retention drivers.** In a logistic model of 90-day repeat (n = 53,631, base rate 67.0%): a problem on the first order -7.4 pp (95% CI -8.6 to -6.1); paid_social -5.7 pp, partner -2.6 pp, paid_search -1.6 pp, referral +2.1 pp versus organic; Android -1.6 pp versus iOS. First-basket size has no detectable effect (+0.16 pp per log unit, p = 0.66).
1. **Funnel drop-off.** Of 16 segment-step tests (Holm-corrected), one stands out: android app 5.4 converts payment attempts to orders at 71.7% vs 93.0% elsewhere (-21.3 pp), from 2025-08-18. Estimated 14,963 lost orders (534,631 in basket value at an average basket of 35.73).
1. **RFM.** champions: 20% of customers, 42% of margin; at risk: 21% of customers, 25% of margin; loyal: 19% of customers, 22% of margin; hibernating: 19% of customers, 5% of margin; new or promising: 13% of customers, 4% of margin; needs attention: 8% of customers, 2% of margin.
1. **Basket affinity.** 6 pairs reach lift >= 2.0 with at least 100 shared orders: S114 (meat_fish) + S390 (pet) lift 28.2, S158 (frozen) + S217 (snacks) lift 25.9, S005 (produce) + S082 (bakery) lift 22.7, S365 (baby) + S410 (premium_deli) lift 13.1, S262 (pantry) + S372 (baby) lift 8.8, S374 (baby) + S391 (pet) lift 5.8.
1. **Under-ranged high-margin SKUs.** S401, S402, S403, S399, S400, S404 (premium_deli, about 52% margin) are ranged at 2 nodes only and sit in class B at network level, yet sell above the median SKU's velocity where ranged; they lead the add list. All 86 add recommendations: 141,646 to 220,398 annual gross margin.
1. **Perishable overstock.** 107 node-SKUs hold more cover than shelf life while selling at least 1 unit a day, wasting 106,027 (37% of all waste). Largest: N02/S149 (ready_meals, cover 10.3 days vs 5-day shelf life), N02/S150 (ready_meals, cover 10.2 days vs 5-day shelf life), N06/S149 (ready_meals, cover 10.6 days vs 5-day shelf life), N02/S139 (ready_meals, cover 10.0 days vs 5-day shelf life). Saving from cutting depth: 53,013 to 95,424 a year.
1. **Drop candidates.** 299 node-SKUs (bottom decile margin at their node, class C, no strong affinity) change annual margin by -8,777 to 2,938 net of waste avoided (negative = margin given up), freeing space for the adds.

## Found vs planted
The generator plants known effects, listed in [`GROUND_TRUTH.md`](GROUND_TRUTH.md). The analysis was built without reading that file; afterwards `analysis/crosscheck.py` compared the findings with it. Result: **6 hit, 0 partial, 0 missed**, plus 1 detection(s) of things that were not planted.

| Planted | What the analysis found | Verdict | Note |
|---|---|---|---|
| 1. payment success on android 5.4 from 2025-08-18: 93% to 72% | 1 of 16 segment-steps flagged: android 5.4 payment_success 71.7% vs 93.0%, first seen 2025-08-18 | hit |  |
| 2a. churn by channel: referral x0.6 < organic x0.85 < paid_search x1.0 < partner x1.2 < paid_social x1.5 | 90-day repeat effect vs organic: referral +2.1 pp, organic +0.0 pp, paid_search -1.6 pp, partner -2.6 pp, paid_social -5.7 pp | hit | ranking matches exactly |
| 2b. first-order problem multiplies churn x1.8 | -7.4 pp on 90-day repeat (95% CI -8.6 to -6.1) | hit |  |
| (not planted as a retention driver) | Android -1.6 pp on 90-day repeat vs iOS | unplanted | a knock-on effect of the planted payment fault: failed payments remove orders, including second orders |
| 3. 6 planted SKU pairs | 6 pairs with lift >= 2.0 | hit | 6/6 recovered, 0 extra |
| 4. 14 overstocked perishable node-SKUs at ['N02', 'N06'] | 107 reduce-depth recommendations; the top 14 by waste cost are exactly the planted set | hit | recall 14/14; the other 93 come from the generator's baseline policy, where safety stock pushes cover past shelf life for 2-5 day products; real in the data but not planted |
| 5. 6 high-margin premium_deli SKUs ranged at ['N01', 'N05'] only | 6/6 in the add list, ranks [1, 2, 3, 4, 5, 7] of 44 SKUs by impact; network ABC class ['B'] | hit | network ABC alone would not have flagged them; per-ranged-node velocity did |


**Commentary.** Every planted effect was recovered. The main precision issue is wastage: the reduce-depth list is much longer than the planted overstock because the baseline replenishment policy itself over-covers very short-life products; those recommendations are valid for the simulated data, and ranking by waste cost puts the planted cases first. Two design choices made during the build mattered for the hits: XYZ on node-level variability (network weekly demand was too smooth to classify) and velocity per ranged node (network ABC rates the under-ranged premium SKUs as ordinary).

## Method
1. **SQL** (`sql/`): data-quality checks; base layer with order sequence (ROW_NUMBER), days between orders (LAG) and first-order cohorts; funnel by platform x version x month (conditional aggregation); cohort triangle, repeat curve and retention by driver; RFM with NTILE quintiles; ABC on cumulative revenue (window SUM) and XYZ on median node-level weekly CV; pair affinity via a basket self-join (support, confidence, lift); wastage risk as days of cover over shelf life; per-node add / drop / reduce-depth rules with impact ranges.
2. **Python** (`analysis/findings.py`): two-proportion tests of every segment-step against the rest with Holm correction; logistic regression of 90-day repeat with average marginal effects.
3. **Verification** (`tests/`): generator invariants (ledger balance, no negative stock, ranging, funnel prefixes, FK integrity), SQL metrics recomputed in pandas, rule checks on every recommendation, and the Excel formulas evaluated against SQL.

Every number in this README and the memo is rendered from `outputs/findings.json`. Design choices are logged in the repository's `DECISIONS.md`.

## Outputs for BI tools
Power BI, Tableau and Looker cannot be built headlessly, so the dashboard is a single self-contained HTML file deployed to GitHub Pages by CI. The tables are exported as CSV (`outputs/kpi/`, including per-customer RFM scores) and as an Excel workbook whose ABC-XYZ classification and wastage model are live formulas over editable thresholds.

## Limitations
- Simulated data: no seasonality, promotions, price changes or substitution behaviour; churn is permanent.
- Add/drop impacts rest on assumed cannibalisation (30%) and substitution (50%) rather than a measured ranging test.
- Retention drivers are associations from a model; the first-order effect would need an experiment to confirm in real data.
- XYZ uses median node-level variability, which partly reflects how widely a SKU is ranged.

## Run it
```
make p3      # from the repository root
```
