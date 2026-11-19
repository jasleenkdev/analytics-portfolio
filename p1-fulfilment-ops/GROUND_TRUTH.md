# Ground truth: planted effects in the project 1 generator

This file is rendered from `data_gen/plants.toml` by the generator. The analysis code never reads it or that TOML file; they are used only by the final found-vs-planted cross-check.

Simulation window: 2026-01-05 to 2026-04-04 (90 days), delivery SLA 30 minutes.

## A. Evening understaffing at one node
- **Node:** N07
- **Hours:** 18, 19, 20, 21 (local hour of order placement), every day
- **Mechanism:** pickers rostered at 55% of the forecast-based requirement, so picker utilisation saturates and pick time balloons through queueing. Wrong-item defects also rise with picker load.
- **Expected signature:** high pick-stage minutes and late rate in those node-hours versus peer nodes in the same hours; rider wait and travel normal.

## B. Bad-weather surge where rider wait drives delay
- **Zones:** south, central (nodes N04, N05, N11, N12)
- **Dates:** 2026-02-26, 2026-02-27, 2026-02-28, from 10:00
- **Mechanism:** storm conditions raise demand by 35%, 40% of rider shifts in the window never log in, and travel speed falls to 70% of normal. Pickers are rostered from a weather-aware forecast, so picking holds up.
- **Expected signature:** temporal anomalies at those nodes and dates; the delay decomposition is dominated by rider wait (then travel), not picking; rider utilisation pinned near saturation.

## C. Repeat stockouts of a SKU cluster at two nodes
- **Nodes:** N03, N09
- **SKUs:** the 12 fastest-moving `dairy` SKUs: S0097, S0098, S0099, S0102, S0109, S0111, S0118, S0120, S0128, S0131, S0136, S0150
- **Mechanism:** order-up-to level set at 70% of mean daily demand at those nodes (other node-SKUs: 160% plus safety stock), so the shelf empties most afternoons.
- **Expected signature:** these node-SKUs dominate the stockout rate and missing-item defects; fill rate at the two nodes is lower for that category only.

## D. Data-quality issues to clean
- Duplicate event rows: 0.4% of orders get one duplicated event (half exact copies, half with a 1-29 second timestamp jitter).
- Delivered before placed: 75 delivered orders have the delivered timestamp moved 5-120 minutes before placement (clock skew).
- Missing rider ids: 0.1% of `rider_assigned` events have a null `rider_id`.

## E. Process change that improves one node
- **Node:** N02
- **Change date:** 2026-02-19 (day 45)
- **Mechanism:** picking work content multiplier 1.15 before and 0.75 after the change (relative to the network's 1.0).
- **Expected signature:** a step down in pick time and delivery time at that node from the change date, absent at other nodes.

## Generator assumptions that are not planted anomalies
- Demand: Poisson per node-hour from a weekday/weekend hourly curve, a node size factor, a 0.12% daily growth trend, rain (+12%) and storm uplift.
- Picking: work content of 2.5 + 0.7 minutes per order line, lognormal noise, and a queueing multiplier that is 1.0 at 70% picker utilisation.
- Riders: shifts of up to 5 hours rostered to cover forecast demand at 75% utilisation; 3% random no-shows; rider wait grows with orders per online rider.
- Travel: gamma-distributed distance (node mean 2.4-3.8 km), lognormal speed around 20 km/h, slower in rain (85%) and storms.
- Cancellations: 0.6% at placement plus 25% of orders whose pick plus rider wait exceeds 35 minutes.
- Defects: 30% of late orders claim a late credit; wrong-item and damaged rates rise with picker load and rain respectively; every short-picked line becomes a missing-item refund.
