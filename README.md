# Analytics portfolio

> **All data in this repository is simulated.** Each project generates its own data with a seeded Python model; nothing here is real company data. The generators' assumptions are listed at the top of each project README.

Three company-agnostic analytics projects for online retail, delivery, marketplace and logistics businesses: SQL-first metrics on DuckDB, KPI dashboards, operational anomaly root-causing, experiment evaluation, and customer, product and inventory analytics, each ending in a one-page memo for a stakeholder.

| Project | Business question | Headline result | Found vs planted |
|---|---|---|---|
| [Fulfilment and delivery operations](p1-fulfilment-ops/) | Where and why are we missing the delivery SLA and losing orders to defects? | 87.2% of orders within the 30-minute SLA; picking at N07 from 18:00 is understaffed (15.4 orders per picker vs 7.2), and peer-level pick times would have put 6.2% of all late orders on time | 7 hit, 1 partial, 0 missed |
| [Experimentation and pilot evaluation](p2-experimentation/) | Launch a lower free-delivery threshold? Scale rider batching? | Threshold: **do not launch** (contribution per user -13.7%, orders 9.9%). Batching: **do not scale as-is: fix the guardrail and extend** (cost -12.4%, defects +0.60 pp) | 12 hit, 1 partial, 0 missed |
| [Customer, product and inventory](p3-customer-product/) | Which customers retain and why; which products deserve more space; how should each node's range change? | First-order problems cut 90-day repeat by 7.4 pts; a payment fault in the android app version 5.4 cost about 14,963 orders; add recommendations worth 141,646 to 220,398 a year | 6 hit, 0 partial, 0 missed |

Dashboards: [`p1`](p1-fulfilment-ops/docs/index.html) | [`p2`](p2-experimentation/docs/index.html) | [`p3`](p3-customer-product/docs/index.html) (single-file HTML; a GitHub Actions workflow publishes them to GitHub Pages)

## What each project contains
- `README.md`: business question first, simulated-data disclosure, findings, method, found vs planted, limitations
- `memo.md`: one page for the stakeholder, with recommendations and stated uncertainty
- `sql/`: numbered, commented DuckDB SQL (CTEs, window functions, NTILE, LAG, rolling windows, percentiles) that defines every metric
- `analysis/`: Python orchestration, statistics, dashboard and workbook builders
- `tests/`: generator invariants, SQL metrics recomputed independently in pandas, data-quality checks, Excel formulas evaluated against SQL
- `outputs/`: KPI CSVs, an Excel workbook with live formulas, the data-quality report and `findings.json`
- `docs/index.html`: the interactive dashboard
- `GROUND_TRUTH.md`: what the generator planted, used only for the final cross-check

## How it works
- **Reproducible:** `make all` creates a virtual environment, generates all data from fixed seeds, runs the SQL and statistics, runs the tests, and renders dashboards, workbooks, memos and READMEs. Any failing test stops the build.
- **Numbers come from code:** every figure in the READMEs and memos is rendered from query results; nothing is typed by hand.
- **Planted ground truth:** each generator injects known problems and effects. The analysis is written without reading them; a separate cross-check scores what was found and the READMEs report hits, partial hits and misses.
- **BI-tool ready:** Power BI, Tableau and Looker cannot be built headlessly, so dashboards are single-file Plotly HTML, and the same numbers are exported as CSV and as Excel workbooks with live formulas for loading into any BI tool.
- **Configurable:** the delivery SLA (30 minutes here), statistical thresholds and business tolerances live in each project's `config.toml`.
- **Decisions logged:** [`DECISIONS.md`](DECISIONS.md) records every choice of tool, data design, metric definition, statistical method and threshold, with the alternatives rejected.

## Run it
```
make all        # everything, about a minute on a laptop
make p1         # or one project: p1, p2, p3
make test       # tests only, on existing data
```
Requires Python 3.11+ and make; no database server, BI tool or manual download.
