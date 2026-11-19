# Memo: delivery SLA and defects, last 90 days

**To:** Operations lead  **From:** Operations analytics  **Data:** simulated (seeded generator, not real company data)

**Bottom line.** 87.2% of 397,154 timed orders arrived within the 30-minute SLA (P90 31.7 min); 50,959 were late and 6.9% of delivered orders drew a refund claim (103,507 in refunds, 1.34% of GMV). The analysis points to the following fixable problems.

### 1. N07 is short of pickers from 18:00 to 22:00 on most days
- **Evidence:** in those hours N07 is late on 36.5% of orders versus 9.5% at other nodes in the same hours. The excess is in picking (+7.0 min per order); rider wait (+0.8) is small. Each rostered picker faces 15.4 orders an hour against 7.2 elsewhere.
- **Impact:** 3,179 of its 5,470 late orders in these hours would have been on time with peer-level pick times (6.2% of all late orders in the network).
- **Action:** roster about 2.9 more pickers per hour in this window (about 81 picker-hours a week), then re-check orders per picker weekly.

### 2. 2026-02-26 to 2026-02-28 (storm): a rider-supply failure, not a picking one
- **Evidence:** 5 nodes (N04, N05, N10, N11, N12) had 97 abnormal hours. Orders ran 42% above the usual level for those hours while riders online were 19% below it. Rider wait added 7.0 min per order, travel 3.6 and picking only 0.3.
- **Impact:** 1,435 of 3,211 orders in the flagged hours were late (45%), 35,477 order-minutes of delay above normal.
- **Action:** a bad-weather rider plan: weather-triggered shift incentives booked the day before, a standby pool shared between neighbouring nodes, and a temporary wider delivery promise in the app when riders online fall below plan.

### 3. The same dairy SKUs run out most afternoons at N03 and N09
- **Evidence:** 12 dairy SKUs hit zero on 77% of days at N03, typically by 18:00. The shelf opens with 0.74 days of demand, against 2.11 days for the same SKUs at other nodes: a replenishment-level problem, not a demand spike.
- **Impact:** 6,661 units short and 17,941 in missing-item refunds, 40% of all missing-item refunds in the network.
- **Action:** raise the order-up-to level for these SKUs at these nodes to the network's cover, or add an afternoon top-up; then watch the fill rate of the category at both nodes.

### What to copy: N02 changed something on 2026-02-19
Its median pick time moved from 6.2 to 3.1 min (the rest of the network stayed at 4.7); relative to the rest of the network, P90 delivery moved -7.4 min (95% CI -8.6 to -6.1) and on-time share 12.4 points (10.1 to 14.7). Find out what changed and pilot it at N07 first.

**Caveats.** Impact figures hold the other stages constant, so they are conservative for picking (faster picks also shorten rider waits at the node). 75 orders with impossible timestamps are excluded from timing metrics only. Full method, data-quality report and dashboard: see the project README.
