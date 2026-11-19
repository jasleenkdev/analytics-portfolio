# Fulfilment and delivery operations analytics

**Business question:** where and why are we missing the delivery SLA and losing orders to defects, and what should operations change?

> **Simulated data.** Everything here comes from a seeded Python generator (`data_gen/generate.py`, seed 20260105), not from any real company. Assumptions: 12 fulfilment nodes in 5 zones, 800 SKUs in 12 categories, about 400k orders over 90 days from 2026-01-05, Poisson demand with weekday/weekend hourly curves and rain uplift, pick and rider-wait times driven by queueing on rostered pickers and online riders, weather-dependent travel speed, daily order-up-to replenishment for the 150 fastest SKUs, and refund claims for late, missing, wrong and damaged items. The delivery SLA is a config value (30 minutes here).

Dashboard file: [`docs/index.html`](docs/index.html)  |  Memo: [`memo.md`](memo.md)  |  KPI exports: [`outputs/kpi/`](outputs/kpi)  |  Excel: [`outputs/p1_fulfilment_kpis.xlsx`](outputs/p1_fulfilment_kpis.xlsx)

## Headline
87.2% of orders were delivered within 30 minutes (P50 19.4 min, P90 31.7 min), ranging from 77.2% at N07 to 93.1% at N01. 6.9% of delivered orders drew a refund claim and 0.67% of orders were cancelled. Fill rate was 99.33%, rider utilisation 70%.

## Findings
1. **Chronic understaffing at N07 (18:00, 19:00, 20:00, 21:00).** Late rate 36.5% vs 9.5% at peers in the same hours; picking is the driver (+7.0 min per order) with 15.4 orders per rostered picker against 7.2 at peers. 3,179 late orders (6.2% of all late orders) were recoverable at peer pick times. Damaged claims 0.51% vs 0.33% at peers (p < 0.001). Wrong item claims 0.96% vs 0.44% at peers (p < 0.001).1. **Storm episode 2026-02-26 to 2026-02-28 at N04, N05, N10, N11, N12.** Driven by rider wait (+7.0 min per order; picking +0.3); orders 42% above normal for the hour while riders online changed by -19%. 1,435 late orders in 97 flagged node-hours.
1. **Repeat dairy stockouts at N03.** 12 SKUs empty on 77% of days (first zero around 18:00); opening cover 0.74 days vs 2.11 for the same SKUs elsewhere; 3,611 units short, 21.8% of missing-item refunds.
1. **Repeat dairy stockouts at N09.** 12 SKUs empty on 75% of days (first zero around 17:00); opening cover 0.75 days vs 2.11 for the same SKUs elsewhere; 3,050 units short, 18.5% of missing-item refunds.
1. **Step improvement at N02 from 2026-02-19** (permutation p = 0.001). Median pick 6.2 to 3.1 min; difference-in-differences vs the rest of the network: P90 -7.4 min (95% CI -8.6 to -6.1), on-time 12.4 pts.
1. **Data quality.** 5 of 14 checks found issues in the raw feed (duplicate and jittered event re-sends, clock-skewed deliveries, missing rider ids); all are repaired or excluded in the cleaned layer. See [`outputs/data_quality_report.md`](outputs/data_quality_report.md).

Anomaly scan: 17,147 node-hours scored, 1,389 flagged, aggregated into 1 chronic pattern(s), 55 acute incidents and 4 multi-node episodes.

## Found vs planted
The generator plants known effects, listed in [`GROUND_TRUTH.md`](GROUND_TRUTH.md). The analysis was built without reading that file; afterwards `analysis/crosscheck.py` compared the findings with it. Result: **7 hit, 1 partial, 0 missed**, plus 4 detection(s) of things that were not planted.

| Planted | What the analysis found | Verdict | Note |
|---|---|---|---|
| A. understaffed picking at N07, hours [18, 19, 20, 21] | chronic pattern at N07 hours [18, 19, 20, 21], driver picking, orders per picker 15.4 vs 7.2; wrong-item rate 0.96% vs 0.44% | hit | 4/4 planted hours recovered |
| B. storm 2026-02-26 to 2026-02-28 at ['N04', 'N05', 'N11', 'N12'], rider-wait driven | episode 2026-02-26 to 2026-02-28 at ['N04', 'N05', 'N10', 'N11', 'N12'], driver rider wait, riders online -19% vs history, weather storm | partial | all planted nodes and days found; extra node(s) ['N10'] in the episode |
| (none planted) | rider wait episode 2026-03-22 at ['N03', 'N05', 'N09'] (10 flagged hours, orders +32% vs history) | unplanted | single-day demand surges outrunning the rider roster; natural Poisson variation in the generator |
| (none planted) | rider wait episode 2026-02-08 at ['N01', 'N04'] (8 flagged hours, orders +41% vs history) | unplanted | single-day demand surges outrunning the rider roster; natural Poisson variation in the generator |
| (none planted) | rider wait episode 2026-03-15 at ['N01', 'N12'] (7 flagged hours, orders +37% vs history) | unplanted | single-day demand surges outrunning the rider roster; natural Poisson variation in the generator |
| C. repeat dairy stockouts at N03 (12 SKUs) | cluster of 12 repeat-stockout dairy SKUs, opening cover 0.74 vs 2.11 days elsewhere | hit | 12/12 SKUs matched, 0 extra |
| C. repeat dairy stockouts at N09 (12 SKUs) | cluster of 12 repeat-stockout dairy SKUs, opening cover 0.75 vs 2.11 days elsewhere | hit | 12/12 SKUs matched, 0 extra |
| D1. 1599 duplicated event rows | 1599 repeated rows removed | hit |  |
| D2. 75 delivered-before-placed orders | 75 flagged and excluded | hit |  |
| D3. 0.1% null rider ids on assignment events | 420 null rider ids found and repaired | hit | count includes nulls copied into duplicated rows |
| E. process change at N02 on 2026-02-19 | change point at N02 on 2026-02-19, pick time -3.17 min vs other nodes | hit | exact date |
| (not planted as part of A) | damaged claims elevated in N07's pattern hours (0.51% vs 0.33%) | unplanted | the generator raises damage in rain; N07's zone (east) was wet in 22% of those hours vs 15% for other zones, so this is weather co-occurring with the pattern, not an understaffing effect |

**Commentary.** The storm episode is reported with one node outside the storm zones because that node had its own sustained rider-wait flags on the same days; the episode rule merges by date and driving stage, not by weather, which is deliberate (an operations lead wants all nodes struggling that day) but makes the episode slightly wider than the planted storm. The other multi-node episodes are real in the data (sustained surges at two or three nodes on one day) but were not planted; they are smaller by an order of magnitude. During this cross-check I found that the analysis had not looked at defect types inside the chronic pattern; I added that check (wrong-item claims are elevated, as planted) and it also surfaced elevated damaged-item claims, which the cross-check traces to weather in that zone rather than to understaffing.

## Method
1. **Clean** (`sql/01_dq_checks.sql`, `sql/02_clean.sql`): DQ report, de-duplicated events, one timeline row per order with exact stage minutes (picking, rider wait, travel).
2. **KPIs** (`sql/10`-`14`): P50/P90 and % within SLA, cancellations, defect rate by type, fill rate, stockout rate, inventory turns and days of cover, rider utilisation and orders per rider-hour, delay decomposition against a same-hour network baseline.
3. **Anomalies** (`sql/20`-`22`): per node-hour, a robust rolling z-score against the node's own same-hour history and a leave-one-out peer z-score against other nodes in the same hour; flagged cells are decomposed by stage and grouped into chronic patterns, incidents and multi-node episodes.
4. **Change points and stock** (`sql/23`-`26`, `analysis/change_points.py`): max-|t| split scan with a permutation test, then difference-in-differences before/after; stockout diagnosis on opening cover versus ordered demand; counterfactual recoverable late orders.
5. **Verification** (`tests/`): generator invariants, SQL KPIs recomputed in pandas, DQ checks on the cleaned layer, anomaly and change-point logic recomputed independently, Excel formulas evaluated and compared with SQL.

Every number in this README and the memo is rendered from `outputs/findings.json`; nothing is typed by hand. Design choices are logged in the repository's `DECISIONS.md`.

## Outputs for BI tools
Power BI, Tableau and Looker cannot be built headlessly, so the dashboard is a single self-contained HTML file deployed to GitHub Pages by CI. The same numbers are exported as CSV (`outputs/kpi/`) and as an Excel workbook whose summary sheet is live `SUMIFS` formulas over the exported facts, ready to load into any BI tool.

## Limitations
- Simulated data: effects are cleaner than in production and there is no seasonality beyond weekly patterns.
- Queueing is modelled per node-hour, so backlogs do not carry across hours; recovery after a surge is understated.
- Stockout rate, turns and days of cover cover only the 150 tracked fast movers; turns are therefore very high and not comparable to whole-store figures.
- Impact estimates hold other stages constant; the change-point test ignores day-to-day autocorrelation (mitigated by an effect-size floor).

## Run it
```
make p1      # from the repository root: generate, SQL, analysis, tests, reports
```
