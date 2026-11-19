# Decision log

Every choice of tool, data design, metric definition, statistical method or threshold, and every deviation from the original brief, is recorded here in the commit that introduced it. Entries are numbered across the whole repository.

### D-001: one repository with three project folders
- **Project / phase:** all, phase 1
- **Decision:** I keep the three projects in a single repository with one top-level Makefile, one CI workflow and one GitHub Pages site that serves each dashboard under its own path (/p1/, /p2/, /p3/).
- **Why:** a reviewer gets one link, one `make all`, one decision log and one place to judge consistency; the shared helpers (SQL runner, dashboard shell, Excel styling) are written once.
- **Alternatives rejected:** three separate repositories, because the decision log and the shared helpers would have to be duplicated and kept in sync, and reproducibility would need three clones; a monorepo with a Python package per project, because hyphenated project folders read better on GitHub and the projects do not import each other.
- **Trade-off / consequence:** the repository is larger and CI rebuilds all three projects on every push (a few minutes); a reader interested in one project still sees the others.

### D-002: DuckDB files plus standalone SQL run by a thin Python runner
- **Project / phase:** all, phase 1
- **Decision:** each project writes its data to a local DuckDB file, and all metrics live in numbered `sql/*.sql` files executed in name order by `shared/db.py`; Python only orchestrates, tests and visualises.
- **Why:** the brief makes SQL the star and forbids servers; DuckDB is an in-process columnar engine with window functions, `QUANTILE_CONT`, `QUALIFY` and fast Parquet/pandas interop, so 400k orders and 1.5M basket lines aggregate in seconds on a laptop.
- **Alternatives rejected:** SQLite, because it lacks percentile functions and is slow on wide analytical scans; PostgreSQL in Docker, because it adds a server and a manual install step; pandas-only metrics, because they would hide the SQL the portfolio is meant to show.
- **Trade-off / consequence:** DuckDB dialect (e.g. `QUALIFY`, `getvariable`) is not 100% portable to other warehouses; the SQL is kept close to ANSI so porting is mostly mechanical.

### D-003: configuration in a per-project TOML file exposed to SQL as variables
- **Project / phase:** all, phase 1
- **Decision:** seeds, sizes, the delivery SLA (default 30 minutes) and every analysis threshold live in `config.toml`; the runner passes them to DuckDB with `SET VARIABLE`, and SQL reads them with `getvariable('name')`.
- **Why:** the same analysis must fit a 10-minute, 30-minute or next-day business, so the SLA cannot be a literal in SQL; TOML is parsed by the standard library (`tomllib`) and is readable by non-engineers.
- **Alternatives rejected:** YAML, because it needs an extra dependency and has surprising type coercions; Jinja-templated SQL, because the `.sql` files would stop being runnable as-is in a DuckDB shell; a `params` table, because every query would need an extra join.
- **Trade-off / consequence:** running a `.sql` file by hand in the DuckDB CLI requires setting the variables first (each file lists the ones it uses in its header).

### D-004: dashboards as single-file Plotly HTML with plotly.js from a pinned CDN
- **Project / phase:** all, phase 1
- **Decision:** each dashboard is one `docs/index.html` with the data embedded as JSON and plotly.js loaded from its pinned CDN build; CI deploys the three files to GitHub Pages.
- **Why:** BI tools cannot be built headlessly in CI; one HTML file with embedded data needs no server and can be opened from disk or Pages; loading plotly.js from the CDN keeps each committed file a few hundred KB instead of about 5 MB, so regenerating it each phase does not bloat git history.
- **Alternatives rejected:** embedding plotly.js inline, because three 5 MB blobs rewritten on every rebuild would dominate the repository size; Dash or Streamlit, because they need a running server; static PNG charts, because the brief asks for filtering and hover.
- **Trade-off / consequence:** viewing a dashboard needs internet access for the plotly.js script; the data itself is fully embedded. KPI CSVs and an Excel workbook carry the same numbers for any BI tool.

### D-005: generated markdown from Jinja2 templates
- **Project / phase:** all, phase 1
- **Decision:** README findings, memos and the found-vs-planted section are rendered from `templates/*.md.j2` using values returned by the SQL and analysis code.
- **Why:** the brief forbids hand-typed figures in prose; templates keep the narrative editable while every number is a variable that changes if the data changes.
- **Alternatives rejected:** f-strings inside Python, because long prose in code is hard to review; notebooks exported to markdown, because they are hard to diff and to run headlessly.
- **Trade-off / consequence:** prose that depends on the direction of a result (e.g. "improved" vs "worsened") needs small conditionals in the template.

### D-006: local working-context file excluded via .git/info/exclude
- **Project / phase:** all, phase 1
- **Decision:** the local working-context file is kept out of version control through `.git/info/exclude` instead of a `.gitignore` entry. This deviates from the brief, which asked for a `.gitignore` entry.
- **Why:** the brief also requires that no committed file names the tool that file belongs to; a `.gitignore` line would be such a mention, while `.git/info/exclude` achieves the same "stays local" result without being committed.
- **Alternatives rejected:** a `.gitignore` entry, because it would itself be a committed mention; a generic pattern such as `*.local.md`, because it would force a rename of the file.
- **Trade-off / consequence:** a fresh clone does not carry the exclusion; anyone recreating the file there must exclude it again.

### D-007: build, test, report order in make
- **Project / phase:** all, phase 1
- **Decision:** each project target runs `pipeline.py build` (generate data, run SQL, run analysis), then `pytest`, then `pipeline.py report` (CSV, Excel, dashboard, memo, README). Make runs with `-eu -o pipefail` so any failure stops the build.
- **Why:** reports should only be rendered from data and metrics that passed the invariant, reconciliation and data-quality tests, so a failing test can never publish wrong numbers.
- **Alternatives rejected:** running tests last, because a broken metric would already have been written into the README and dashboard; a task runner such as invoke or nox, because make is already present on every CI image and laptop.
- **Trade-off / consequence:** `make test` on its own needs the data from a previous `build`.

### D-008: commit generated reports, not generated data
- **Project / phase:** all, phase 1
- **Decision:** the DuckDB files under each `data/` folder are git-ignored and rebuilt from seeds; KPI CSVs, Excel workbooks, dashboards, memos and READMEs are committed.
- **Why:** the raw data is hundreds of MB but fully reproducible from code; the reports are what a reader browses on GitHub, and committing them makes any drift between runs visible in diffs.
- **Alternatives rejected:** committing Parquet extracts, because they add size without information beyond the seed; committing nothing generated, because the READMEs would then have no findings when browsed online.
- **Trade-off / consequence:** every rebuild rewrites the committed reports, so a change in the generator shows up as a diff across many files.

### D-009: load-driven simulation instead of labelled anomalies
- **Project / phase:** p1, phase 2
- **Decision:** the generator models each delivery stage from operating load: pick time is work content times a queueing multiplier on orders per rostered picker, rider wait is a queueing multiplier on orders per online rider, travel is distance over a weather-dependent speed, and missing items come from an hourly stock position. Planted problems change the inputs (rosters, rider log-ins, replenishment levels, work content) rather than writing "slow" values directly.
- **Why:** the analysis has to root-cause problems the way an analyst would in production, through rosters, utilisation and stock; if anomalies were pasted onto outcomes there would be no mechanism to find, and the decomposition would trivially point at the edited column.
- **Alternatives rejected:** a full discrete-event simulation (e.g. SimPy) of every picker and rider, because 400k orders would take minutes and the extra fidelity adds nothing the questions need; independent random draws per stage plus injected spikes, because it produces anomalies with no upstream cause to discover.
- **Trade-off / consequence:** load is computed per node-hour, so queueing does not carry over between hours; a backlog at 20:59 vanishes at 21:00. That understates how long recovery from a surge takes.

### D-010: planted effects isolated from analysis configuration
- **Project / phase:** p1, phase 2
- **Decision:** planted parameters live in `data_gen/plants.toml`; resolved planted entities (e.g. SKU ids of the stockout cluster) are written to `data/planted_entities.json`; `GROUND_TRUTH.md` is rendered from both. Analysis code reads only `config.toml` and the database.
- **Why:** the brief requires the analysis to discover the problems without reading the ground truth; keeping the plants out of `config.toml` makes that separation checkable with a grep.
- **Alternatives rejected:** a `[plants]` section in `config.toml`, because the analysis loads that file and could silently depend on it; hand-writing `GROUND_TRUTH.md`, because its numbers would drift from the generator.
- **Trade-off / consequence:** two config files per project; anyone changing a plant must re-run the generator to refresh `GROUND_TRUTH.md`.

### D-011: inventory model with daily order-up-to replenishment and tracked fast movers
- **Project / phase:** p1, phase 2
- **Decision:** the 150 fastest-moving SKUs are tracked with hourly on-hand snapshots per node; each is replenished to an order-up-to level at 06:00 (1.6 days of mean demand plus a square-root safety buffer); order lines are filled in placement order until the shelf is empty. Untracked SKUs short-pick at a flat 0.6%.
- **Why:** the brief asks for snapshots on a subset; fast movers drive most missing-item refunds, and an order-up-to policy is the simplest replenishment rule that makes stockouts emerge from demand rather than being drawn at random.
- **Alternatives rejected:** snapshots for all 800 SKUs, because 20M rows add runtime without changing any conclusion; an (s, Q) reorder-point policy with lead times, because lead-time variability is outside the question asked here.
- **Trade-off / consequence:** stockout rate and days of cover are measured only for tracked SKUs, while fill rate covers every line; the README states the two different bases.

### D-012: event model and stage definitions
- **Project / phase:** p1, phase 2
- **Decision:** each order emits `placed`, `picked`, `rider_assigned`, `picked_up`, `delivered` (or `cancelled`) events. Delay stages are defined as picking = placed to picked, rider wait = picked to picked up, travel = picked up to delivered; `rider_assigned` is used for rider busy time only.
- **Why:** the three stages are additive and sum exactly to delivery time, so a decomposition can attribute every late minute; "picked to picked up" is the customer-visible cost of rider shortage regardless of when the assignment happened.
- **Alternatives rejected:** a rider-assigned-to-picked-up stage, because assignment usually happens during picking, which would double-count overlapping time; including the return leg as a stage, because the customer does not experience it.
- **Trade-off / consequence:** a slow assignment that is hidden behind slow picking is attributed to picking; that is the right call for the customer view but understates dispatch problems.

### D-013: scale and operating window for project 1
- **Project / phase:** p1, phase 2
- **Decision:** 12 nodes in 5 zones, 800 SKUs in 12 categories, about 400k orders over 90 days (2026-01-05 to 2026-04-04), operating hours 07:00 to 23:59, with weekday and weekend hourly curves, rain uplift and a small growth trend.
- **Why:** matches the brief's sizing; 90 days gives enough same-hour history for a 14-day rolling baseline and room for a mid-period process change with at least six weeks either side.
- **Alternatives rejected:** a full year, because it multiplies runtime and the operational questions are about recent weeks; 24-hour operation, because night hours would add near-empty cells that only add noise to node-hour scoring.
- **Trade-off / consequence:** no seasonality beyond weekly patterns; results do not speak to holiday peaks.

### D-014: defects as customer-reported refunds with a cause type
- **Project / phase:** p1, phase 2
- **Decision:** the `defects` table holds one row per refund claim with type `late`, `missing_item`, `wrong_item` or `damaged`; every short-picked line produces a `missing_item` refund at line value, 30% of late orders claim a capped credit, wrong-item claims rise with picker load and damage with rain.
- **Why:** operations leads judge defects by refund cost and by cause; linking missing items to stock and wrong items to picker load gives the root-cause analysis something real to connect.
- **Alternatives rejected:** a single defect flag per order, because it cannot be split by type or costed; refunds for every late order, because real customers mostly do not claim.
- **Trade-off / consequence:** late-defect counts understate lateness, so the late rate is always measured from timestamps, and the defect table is used for cost.

### D-015: generator invariants tested on the raw data, including determinism
- **Project / phase:** p1, phase 2
- **Decision:** `tests/test_generator.py` checks row counts against config, primary-key uniqueness, 13 foreign-key relations, non-negative stock, valid quantities, the event lifecycle, the time window, that clock-skewed deliveries are a tiny minority in raw data, and that a second run with the same seed into a temporary folder reproduces an identical order table signature.
- **Why:** every downstream metric assumes these invariants; testing determinism directly is the only way to prove `make all` reproduces the published numbers.
- **Alternatives rejected:** asserting "no delivery before order" on the raw table, because the raw feed is deliberately dirty and the guarantee belongs to the cleaned layer (tested with the data-quality SQL); comparing whole-table hashes, because floating-point sums are not order-stable in a parallel engine, so the signature uses integer cents.
- **Trade-off / consequence:** the determinism test regenerates all data and adds about 5 seconds to every test run.

### D-016: de-duplicate events by keeping the earliest row per order and event type
- **Project / phase:** p1, phase 3
- **Decision:** `events_clean` keeps one row per (order, event type), the one with the earliest timestamp (ties broken by event id). Both exact re-sends and re-sends with a few seconds of timestamp jitter are removed by this one rule.
- **Why:** a lifecycle event happens once per order; the first record is the closest to the physical event, and a later re-send can only make a stage look longer than it was.
- **Alternatives rejected:** `SELECT DISTINCT`, because it misses jittered re-sends (half of the duplicates in this feed); keeping the latest row, because it biases stage durations upwards.
- **Trade-off / consequence:** if a real business re-opens and re-picks an order, the second pick is lost; this model has no re-picks, and the DQ report counts how many rows were dropped.

### D-017: exclude impossible timelines from timing KPIs only
- **Project / phase:** p1, phase 3
- **Decision:** orders whose delivered timestamp precedes placement, or whose stages are out of order, get `timing_valid = false` with an `exclusion_reason`; they are left out of delivery-time, SLA and decomposition metrics but kept in order volume, fill rate, defects and refunds.
- **Why:** the order, its items and its refunds really happened; only the clock is wrong, so dropping the whole order would understate volume and refund cost.
- **Alternatives rejected:** imputing the delivered time from the median travel time, because it invents data and hides the clock fault from the people who own it; deleting the orders, because it would bias defect and fill rates.
- **Trade-off / consequence:** timing KPIs and volume KPIs have slightly different denominators (75 orders apart in this dataset); every export names its base.

### D-018: repair null rider ids from the same order
- **Project / phase:** p1, phase 3
- **Decision:** a rider event with a null `rider_id` takes the rider id recorded on the same order's other rider events.
- **Why:** an order is carried by one rider in this business model, so the other events identify the rider with certainty; leaving the gaps would under-count rider busy time in utilisation.
- **Alternatives rejected:** dropping those events, because the order would then look like it was never assigned; attributing them to an "unknown" rider, because it creates a fake rider with no shift.
- **Trade-off / consequence:** in a business with rider hand-overs the rule would be wrong; it would need the hand-over event to be modelled.

### D-019: data-quality checks as a SQL table, recounted independently in tests
- **Project / phase:** p1, phase 3
- **Decision:** `sql/01_dq_checks.sql` writes `dq_report` (check, table, failing rows, total, action), exported as CSV and a generated markdown report; `tests/test_data_quality.py` recounts duplicates and clock-skewed orders in pandas and asserts the cleaned layer is unique, repaired, monotone and sums stage minutes exactly to delivery minutes.
- **Why:** a DQ report that is never checked can silently undercount; recounting in a second engine catches errors in the check SQL itself, and the cleaned-layer tests turn "no impossible timestamps" into a gate for `make all`.
- **Alternatives rejected:** a data-validation framework (e.g. Great Expectations), because it adds a heavy dependency and its own configuration language for about a dozen checks; assertions inside the SQL, because DuckDB has no portable `ASSERT` and failures would be less readable.
- **Trade-off / consequence:** new checks have to be added in two places (SQL and, where it matters, the pandas recount).

### D-020: percentile and SLA definitions
- **Project / phase:** p1, phase 4
- **Decision:** P50/P90 delivery time use `QUANTILE_CONT` (linear interpolation) over orders with a valid timeline; % within SLA is orders delivered within `sla_minutes` divided by timed orders, always computed as a ratio of summed counts (also for the 7-day rolling rate), never as an average of daily rates.
- **Why:** P90 is what customers at the tail feel and what an SLA promise is usually written against; averaging daily percentages would weight a quiet Sunday the same as a peak Friday.
- **Alternatives rejected:** mean delivery time as the headline, because a few very late orders hide behind it; `QUANTILE_DISC`, because it returns an observed value and jumps between days, which makes small trend changes look noisy; approximate quantiles, because exact ones are cheap at this size.
- **Trade-off / consequence:** percentiles cannot be added up across nodes, so the network P90 is computed from orders, and the Excel workbook carries P50/P90 as values while rate formulas stay live.

### D-021: fill rate on all lines, stockout rate on tracked SKUs in operating hours
- **Project / phase:** p1, phase 4
- **Decision:** fill rate = units fulfilled / units ordered on delivered orders (every SKU); stockout rate = share of operating hours a tracked node-SKU ends with zero on hand; a node-SKU is a "repeat stockout" if it hits zero on at least `stockout_repeat_days` (50%) of days.
- **Why:** fill rate is what the customer experiences and is available for every line; stockout rate needs a stock position, which exists only for tracked SKUs; counting closed hours would dilute it with the overnight period when nothing can sell.
- **Alternatives rejected:** stockout rate as share of snapshots including night hours, because 7 of 24 hours are closed; "ever stocked out", because almost every SKU hits zero at least once in 90 days and the flag would not discriminate.
- **Trade-off / consequence:** the two measures have different bases (all SKUs vs the 150 tracked fast movers), which the README states; the 50% repeat threshold is a judgement call kept in config.

### D-022: rider utilisation includes waiting at the node and the return leg
- **Project / phase:** p1, phase 4
- **Decision:** rider busy minutes = rider assigned to delivered plus an estimated return leg equal to the outbound travel time, attributed to the hour of assignment; utilisation = busy minutes / online shift minutes; orders per rider-hour = delivered orders / online hours.
- **Why:** a rider assigned to an order is unavailable from assignment until back at the node, including time spent waiting for a slow pick, so this is the definition that tells capacity planners how many riders an hour needs.
- **Alternatives rejected:** picked-up to delivered only, because it ignores time stuck at the node and the ride back and shows riders as half idle when they are not; GPS-based return times, because the feed has none.
- **Trade-off / consequence:** the return leg is an estimate; slow picking shows up partly as higher rider utilisation, which is real (riders queue at the node) but must not be read as a rider shortage. Calibrating this definition exposed that the generator's rider rostering ignored time waiting at the node, so I corrected the generator's trip-time estimate to match.

### D-023: delay decomposition against a same-hour network baseline
- **Project / phase:** p1, phase 4
- **Decision:** for each node (and later each flagged cell) the gap to the network is split into pick, rider-wait and travel gaps, each measured against the network mean for the same hour of day; for late orders I also record which stage overran its typical (median) duration by the most minutes.
- **Why:** stages add exactly to delivery time, so stage gaps add exactly to the delivery-time gap; comparing at the same hour of day stops nodes that trade mostly at peak from looking slow purely because of their hour mix.
- **Alternatives rejected:** a regression of delivery time on stage times, because the stages are the delivery time and the coefficients would all be 1; Shapley-style attribution, because with an additive identity it reduces to the same answer with more code.
- **Trade-off / consequence:** travel gaps mostly reflect delivery distance, which operations cannot change in the short run; the memo therefore focuses on pick and rider-wait gaps.

### D-024: inventory turns annualised at cost, days of cover in units
- **Project / phase:** p1, phase 4
- **Decision:** turns = cost of units sold, annualised over the observed days, divided by average on-hand value at cost; days of cover = average on-hand units / average daily units sold; both on tracked SKUs.
- **Why:** cost-based turns are the finance-standard definition and are not distorted by price differences between categories; days of cover in units is what a replenishment planner reads.
- **Alternatives rejected:** turns at retail price, because margin differences would inflate high-margin categories; cover from end-of-day stock, because it ignores the intraday depletion that causes stockouts.
- **Trade-off / consequence:** tracked SKUs are fast movers replenished daily, so turns are very high (over 100 per year); they are comparable between nodes but not to a whole-store figure that includes slow movers.

### D-025: defect rate counts each order once per defect type over delivered orders
- **Project / phase:** p1, phase 4
- **Decision:** defect rate by type = delivered orders with at least one claim of that type / delivered orders; the "any defect" roll-up counts an order once even if it had several defect types; refund cost is also reported as a share of delivered GMV.
- **Why:** operations teams target "orders with a problem", and one order with two missing lines is one unhappy customer, not two.
- **Alternatives rejected:** claims per order, because multi-line shortages would inflate missing-item rates; including cancelled orders in the denominator, because they cannot carry a delivery defect.
- **Trade-off / consequence:** line-level shortage severity is captured in fill rate and refund value rather than in the defect rate.

### D-026: two complementary z-scores per node-hour
- **Project / phase:** p1, phase 5
- **Decision:** every node-hour with at least 8 timed orders gets (1) a temporal modified z-score against the same node, hour of day and day type (weekday/weekend) over the previous 14 such cells, using rolling median and 1.4826 x MAD, flagged at 3.5; and (2) a peer z-score against the other nodes in the same date-hour (leave-one-out mean and SD), flagged at 3.0. Only slow-side deviations are flagged.
- **Why:** the two questions are different: "is this node worse than it usually is?" catches acute events such as a storm, while "is this node worse than everyone else right now?" catches chronic problems that a node's own history has normalised. My first version used a plain mean/SD temporal window across all days; it flagged weekends against weekday history and let the first storm day inflate the baseline so the second storm day was missed. Median/MAD and day-type partitioning fixed both; 3.5 is the conventional cut-off for MAD-based modified z-scores (Iglewicz and Hoaglin).
- **Alternatives rejected:** seasonal decomposition or a forecasting model per node-hour, because it needs far more history than 90 days and is hard to express in SQL; isolation forest, because it gives no stage-level explanation and no business-readable threshold; a single network-wide z, because it cannot tell chronic from acute.
- **Trade-off / consequence:** queueing makes delays heavy-tailed, so roughly 8% of cells still clear a threshold; individual flags are therefore aggregated (D-027) before anything reaches the memo, and the dashboard table is filterable.

### D-027: chronic patterns, acute incidents, network events and episodes
- **Project / phase:** p1, phase 5
- **Decision:** a node-hour of day flagged on at least 25% of days is a chronic pattern; remaining flags form acute incidents only when one node has at least 3 flagged hours on a day with the same driving stage; incidents at 2 or more nodes on the same day with the same driver form a network event; consecutive event days with the same driver are merged into an episode (gaps and islands).
- **Why:** an operations lead acts on patterns ("evenings at node X", "the storm on these days"), not on 1,400 cells; sustained multi-hour, multi-node clusters are far less likely to be noise than single cells, and separating chronic hours stops a permanent problem from dominating every daily incident list.
- **Alternatives rejected:** ranking raw cells by z, because the top of the list was dominated by small, noisy cells; clustering flags with DBSCAN over (node, time), because the rules above are explainable in one sentence and live in SQL.
- **Trade-off / consequence:** a genuine one-off problem lasting under 3 hours at a single node is not escalated as an incident (it stays visible in the dashboard table); the 25% and 3-hour rules are config values.

### D-028: drill-down against the baseline the cell was flagged on, impact in recoverable orders
- **Project / phase:** p1, phase 5
- **Decision:** a flagged cell's excess minutes are split into pick, rider-wait and travel excess against its own history for temporal flags and against peers for peer-only flags; the driver is the stage with the largest excess. Impact is reported as excess order-minutes and, for chronic patterns, as late orders that would have been on time had the driving stage matched the other nodes at the same hour.
- **Why:** the comparison that triggered the flag is the right reference for explaining it; "recoverable late orders" is a number an operations lead can weigh against the cost of extra staff.
- **Alternatives rejected:** one fixed network baseline for all cells, because a node that always travels further would always look travel-driven; impact as z-score sums, because z has no business unit.
- **Trade-off / consequence:** the counterfactual assumes fixing the stage leaves the others unchanged; in reality faster picking would also shorten rider waiting at the node, so the recoverable count is conservative.

### D-029: change points by a SQL max-|t| scan with a permutation test
- **Project / phase:** p1, phase 5
- **Decision:** for each node, the daily median pick time minus the other nodes' daily median (leave-one-out) is split at every day with at least 14 days either side; the split with the largest Welch t is the candidate. Significance comes from 1,000 day-shuffled permutations of the same scan; a change is reported only if p < 0.01 and the shift is at least 15% of the network median pick time.
- **Why:** taking the maximum over 60 candidate splits inflates t, and a permutation test of the same max statistic gives an honest p-value; differencing against other nodes removes weather and network-wide demand swings; the effect-size floor stops tiny but significant shifts from being reported (one node's real step moves every other node's benchmark slightly, which shows up as small significant shifts elsewhere).
- **Alternatives rejected:** CUSUM charts, because they need a known in-control mean and a tuning constant; PELT or binary segmentation from a change-point library, because one step per node is the question and the scan is transparent SQL; testing a pre-announced date only, because the brief asks to find the change from data.
- **Trade-off / consequence:** one change point per node; a node with two shifts would show only the larger one. Day shuffling ignores autocorrelation, which makes p-values somewhat optimistic; the effect-size floor guards against that.

### D-030: before/after as a difference-in-differences against the rest of the network
- **Project / phase:** p1, phase 5
- **Decision:** for nodes with a detected change, daily median pick, P90 delivery and % within SLA are compared before vs after the change date relative to the rest of the network on the same days; the estimate is the change in the daily node-minus-rest gap with a Welch 95% CI.
- **Why:** a plain before/after would credit the node with any network-wide drift (demand growth, weather); differencing against the same days elsewhere removes it.
- **Alternatives rejected:** synthetic control, because with 11 donor nodes and one change it adds weighting machinery without changing the answer; regression with node and day fixed effects, because with one treated unit it reduces to the same difference with harder-to-read output.
- **Trade-off / consequence:** the CI treats days as independent; daily gaps are mildly autocorrelated, so the interval is somewhat narrow. The effect is many times its standard error here, so the conclusion does not hinge on that.

### D-031: stockout diagnosis on opening cover measured against ordered demand
- **Project / phase:** p1, phase 5
- **Decision:** for every tracked node-SKU I compute opening cover = stock on the shelf at opening / mean daily units ordered, the mean hour the shelf first empties, and short units and value; repeat-stockout SKUs are grouped by node and category and compared with the same SKUs at other nodes.
- **Why:** sales are capped by the stockout itself, so cover measured against sales would look healthy exactly where the shelf is too small; comparing with the same SKUs elsewhere separates "this SKU is volatile everywhere" from "this node's replenishment level is set too low".
- **Alternatives rejected:** demand-forecast error analysis, because the feed has no forecast table; flagging single SKUs, because a buyer or planner acts on a category-at-node pattern.
- **Trade-off / consequence:** missing items for untracked SKUs cannot be diagnosed this way and remain in the "random shorts" background.

### D-032: one findings file feeds every narrative
- **Project / phase:** p1, phase 5
- **Decision:** `analysis/findings.py` collects network KPIs, chronic patterns, episodes, stockout clusters, change points and DQ into `outputs/findings.json` (sorted keys, rounded floats); the README, memo and dashboard read from it.
- **Why:** one source means the memo, README and dashboard cannot disagree, and a diff of one JSON file shows exactly which conclusions moved when the generator or a threshold changes.
- **Alternatives rejected:** each template querying the database directly, because the same number would be computed in several places and could drift.
- **Trade-off / consequence:** adding a new number to prose needs a change in two places (collector and template).

### D-033: dashboard content, palette and interaction
- **Project / phase:** p1, phase 6 (shared by all projects)
- **Decision:** the dashboard opens with six KPI tiles, then a node x hour heatmap with a metric switcher (late rate, pick, rider wait, P90), a stacked delay decomposition per node, the network SLA trend (daily plus 7-day ratio), the anomaly episode table, a filterable and sortable table of all flagged node-hours, the before/after chart for any detected change point, and the repeat-stockout view. Colours come from one validated palette (categorical slots for the three stages, a single-hue blue ramp for the heatmap) with dark-mode steps; tables are filtered with a few lines of vanilla JavaScript over embedded JSON.
- **Why:** the order follows the operations lead's questions: how bad, where and when, which stage, which events, what changed; a heatmap is the densest honest view of 12 nodes x 17 hours; filtering in the browser keeps the page a single static file.
- **Alternatives rejected:** Plotly's own table trace, because it cannot filter; a JavaScript grid library, because it adds another CDN dependency for a 1,400-row table; one chart per node, because twelve small charts hide the comparison the heatmap makes obvious.
- **Trade-off / consequence:** the flagged-cell table renders at most 500 rows at a time (the filter counts all rows); charts are re-coloured for dark mode by a small script rather than being regenerated.

### D-034: Excel workbook as fact sheets plus a formula-driven summary
- **Project / phase:** p1, phase 6
- **Decision:** `outputs/p1_fulfilment_kpis.xlsx` holds node-day, defect, fill and rider facts as values, and a `node_summary` sheet where every count and rate is a `SUMIFS` formula over those facts; an editable SLA target cell drives a "meets/below" column and conditional formatting. P50/P90 are carried as labelled values. A test opens the workbook with a formula engine (pycel) and checks the computed cells against the SQL KPIs.
- **Why:** the brief asks for live formulas, not pasted values; a reviewer can filter or edit a fact row and watch the summary move, and the test proves the formulas reproduce the SQL rather than just being present.
- **Alternatives rejected:** writing computed values with a formula-looking format, because it would fail the "live formulas" requirement; recalculating with LibreOffice in CI, because it adds a large system dependency; percentile formulas over order-level data, because 400k rows would make the file heavy and slow.
- **Trade-off / consequence:** openpyxl does not store cached results, so the file shows values only after the spreadsheet application recalculates on open (Excel and LibreOffice do this automatically).

### D-035: KPI CSV exports with stable names
- **Project / phase:** p1, phase 6
- **Decision:** every KPI and analysis table that a BI tool would need is exported to `outputs/kpi/*.csv` with the same name as its DuckDB table, plus the data-quality report.
- **Why:** the dashboards are HTML because BI tools cannot be built headlessly; flat CSVs with one grain per file can be loaded into any BI tool later without touching Python.
- **Alternatives rejected:** Parquet, because spreadsheet users and most BI desktop tools open CSV directly; one wide denormalised extract, because mixing grains (node, node-day, node-hour) invites double counting.
- **Trade-off / consequence:** CSV loses column types; the file names and SQL comments document each grain.

### D-036: memo built around actions, with wording that follows the evidence
- **Project / phase:** p1, phase 7
- **Decision:** the one-page memo gives the network bottom line, then one block per finding (evidence, impact, action), then "what to copy" for any detected improvement and a caveats line. Headlines and actions are chosen by conditions on the data (e.g. "short of pickers" only if picking drives the delay and orders per picker exceed peers by 30%; "rider-supply failure" only if rider wait drives it and riders online fell), never typed for a known answer.
- **Why:** an operations lead reads the first line of each block; the conditions keep the prose honest if the data changes (a different seed or SLA could produce a picking-process problem rather than an understaffing one).
- **Alternatives rejected:** a fixed narrative with numbers slotted in, because it would assert causes the data may not support; a long report, because the brief asks for one page.
- **Trade-off / consequence:** the conditional phrasing is less polished than hand-written prose, and new kinds of findings need a new template branch.

### D-037: public links in one root file
- **Project / phase:** all, phase 7
- **Decision:** repository and Pages URLs live in `portfolio.toml`; templates show the live-dashboard link only when the URL is set.
- **Why:** the links are known only after publishing, and keeping them out of the templates means publishing changes one file and a rebuild.
- **Alternatives rejected:** deriving the URL from the git remote at build time, because a fresh clone of a fork would point at the wrong site; hard-coding the URL in templates, because it breaks the "no hand-typed values" rule in spirit.
- **Trade-off / consequence:** until publishing, READMEs link only to the committed dashboard file.

### D-038: promotion test design with a fixed per-user observation window
- **Project / phase:** p2, phase 8
- **Decision:** about 60k users are randomised 50/50 on their first visit during a 7-day assignment week; each user is measured for exactly 21 days from assignment, so every user has the same exposure and weeks 1-3 since assignment are comparable for the novelty cut. Control keeps free delivery from a basket of 40; treatment gets free delivery from 25.
- **Why:** staggered entry is how real app experiments enrol users; a fixed window per user avoids the bias where early-assigned users contribute more days than late ones, and makes "week since assignment" the natural axis for novelty.
- **Alternatives rejected:** a calendar-window analysis (all orders between two dates), because early and late users would have unequal exposure and novelty would be blurred across calendar weeks; randomising at session level, because a delivery-fee policy has to be stable for a user.
- **Trade-off / consequence:** the experiment needs 28 calendar days to observe 21 days for the last users; effects beyond three weeks are not observed.

### D-039: user behaviour model for the promotion test
- **Project / phase:** p2, phase 8
- **Decision:** each user orders as a Poisson process with a gamma-distributed personal rate, has a lognormal personal basket size, and a beta-distributed propensity for small high-margin "top-up" baskets (36% vs 21% product margin). A 28-day pre-period is generated under the control policy for every user. Each order carries product margin, delivery fee charged and delivery cost.
- **Why:** gamma-Poisson gives the over-dispersed, heavy-tailed order counts real platforms see, which is what makes variance reduction (CUPED) worthwhile; the high-margin basket type is the mechanism through which a free-delivery threshold can cannibalise margin; the pre-period is the covariate CUPED and the power analysis need.
- **Alternatives rejected:** normally distributed per-user spend, because it understates variance and would make every test look over-powered; modelling individual SKUs, because the decision depends on basket economics, not on product mix detail (that is project 3's subject).
- **Trade-off / consequence:** users do not churn or acquire during the test, so the analysis cannot speak to retention effects of the promotion.

### D-040: pilot as a daily node panel with shared shocks
- **Project / phase:** p2, phase 8
- **Decision:** the rider-batching pilot is a daily panel of 24 nodes (8 randomly chosen treated) over 56 days before and 56 days after the switch-on date, with orders, rider hours, delivery minutes, orders within SLA and defect orders per node-day. All nodes share weekly seasonality, a growth trend and daily shocks; busier days are slower everywhere.
- **Why:** operational pilots are evaluated on node aggregates; shared shocks make a naive before/after comparison wrong and a control group necessary, which is the point of a difference-in-differences design.
- **Alternatives rejected:** order-level pilot data, because the decision metrics are node-day rates and order rows would add volume without information; non-random selection of pilot nodes, because it would require a selection model that distracts from the method the brief asks for.
- **Trade-off / consequence:** 8 treated clusters is a small number for cluster-robust inference; the analysis states this and uses a placebo test as a sanity check.

### D-041: sample-ratio mismatch planted as lost assignment-log rows
- **Project / phase:** p2, phase 8
- **Decision:** the SRM is created by dropping a share of control assignment records on one assignment day; the users and their orders still exist.
- **Why:** this is the most common real cause of SRM (a logging or redirect bug on one arm), and it is the realistic hard case: the remaining users look normal and the bias is invisible unless the split itself is tested.
- **Alternatives rejected:** an unequal randomisation probability for the whole test, because it is detectable but has no root cause to localise; deleting whole users, because real logging bugs do not delete customers.
- **Trade-off / consequence:** the analysis can detect and localise the bad day, but cannot recover the lost control users, so it must decide whether to exclude that day's cohort.

### D-042: contribution margin per user as the promotion's primary metric
- **Project / phase:** p2, phase 9
- **Decision:** the primary metric is contribution per assigned user over the 21-day window, where contribution = product margin + delivery fee charged - delivery cost; orders, GMV, conversion and average basket are secondary; high-margin basket share is a guardrail. Users with no orders count as zero.
- **Why:** a free-delivery threshold almost always raises orders and GMV, because it gives money away; the business question is whether it pays, which only a margin metric net of lost fees and serving cost answers. Per assigned user (not per ordering user) keeps the randomisation unit and the analysis unit the same.
- **Alternatives rejected:** GMV or orders per user as primary, because they reward the promotion for its cost; contribution per order, because it ignores the extra orders the promotion generates and its denominator is itself affected by treatment.
- **Trade-off / consequence:** contribution is noisier than order counts, so the test needs variance reduction (CUPED) and a power check; long-term effects (retention, basket habits) are outside a 21-day window.

### D-043: assignment-log checks before any inference
- **Project / phase:** p2, phase 9
- **Decision:** `sql/01_dq_checks.sql` checks duplicate or out-of-window assignments, unknown users, users who ordered during the test without an assignment record, order validity, and missing or impossible pilot node-days; it also writes daily arm counts for a per-day sample-ratio test. The pilot panel's missing node-days are left missing (unbalanced panel), not imputed.
- **Why:** an experiment readout is only as trustworthy as its assignment log; "active but unassigned" users are a direct symptom of a logging bug on one arm, and the daily split localises it. Fixed-effects regression handles an unbalanced panel natively, so imputing three days would only add invented data.
- **Alternatives rejected:** checking the overall split only, because it detects but cannot localise a one-day bug; forward-filling missing pilot days, because it would understate variance.
- **Trade-off / consequence:** the "active but unassigned" check needs the full user list; in production this would come from the exposure log rather than the user table.

### D-044: SQL produces sufficient statistics, Python does the inference
- **Project / phase:** p2, phase 10
- **Decision:** the SQL layer returns, per arm (and per week, segment, pilot group), the count, mean, variance and totals of every metric, plus for per-order ratios the per-user numerator and denominator moments (means, variances, covariance). Statistical tests read these tables or the user-level table; nothing statistical is computed in SQL.
- **Why:** sufficient statistics are exactly what a warehouse is good at and what a stats library needs; keeping tests in Python (scipy/statsmodels) avoids re-implementing t-distributions in SQL and keeps every test independently checkable.
- **Alternatives rejected:** pulling raw orders into pandas and aggregating there, because it hides the metric definitions from the SQL review; computing z-tests in SQL, because the CI and correction logic would be untestable against reference implementations.
- **Trade-off / consequence:** two layers to read; each SQL file states which Python step consumes it.

### D-045: per-order ratio metrics analysed with the delta method
- **Project / phase:** p2, phase 10
- **Decision:** metrics such as basket value per order, contribution per order and high-margin basket share are ratios of per-user sums (sum of numerators / sum of denominators); their variance uses the delta method on per-user numerator and denominator moments.
- **Why:** the randomisation unit is the user, so orders from one user are correlated; treating orders as independent observations would understate the standard error.
- **Alternatives rejected:** an order-level t-test, because it violates independence and overstates significance; averaging per-user ratios, because users with one order would weigh as much as heavy users and users with no orders would have to be dropped.
- **Trade-off / consequence:** the delta method is a first-order approximation; with tens of thousands of users per arm the error is negligible.

### D-046: SRM handling: test the split overall and per day, exclude the bad day's cohort
- **Project / phase:** p2, phase 11
- **Decision:** a chi-square goodness-of-fit test against the designed 50/50 split runs on the whole assignment log (alarm at p < 0.001) and on each assignment day (Bonferroni across days). If the overall test fails, users assigned on flagged days are removed from both arms, and the split is re-tested on the remaining population; the pre-exclusion estimate is reported alongside for transparency.
- **Why:** an SRM means the arms are no longer comparable, so no effect estimate can be trusted until the cause is localised; dropping the whole affected cohort from both arms keeps the remaining comparison randomised, while dropping only the over-represented arm would not.
- **Alternatives rejected:** re-weighting the affected day, because the missing control users are not missing at random from the analyst's point of view (we cannot know who was lost); ignoring the SRM because the estimate barely moves, because in production the size of the bias is unknown in advance; a 0.05 threshold, because SRM checks run on every experiment and a strict alarm avoids constant false stops.
- **Trade-off / consequence:** about 10% of users are dropped (that day's cohort), which costs power; the readout shows both populations.

### D-047: inference stack for the promotion test
- **Project / phase:** p2, phase 11
- **Decision:** Welch t-tests with 95% CIs for every user-level metric; CUPED with the same metric in the 28-day pre-period as covariate (theta pooled across arms) for contribution, orders and GMV; delta-method CIs for per-order ratios; power reported as the minimum detectable effect at 80% power for the realised sample, raw and after CUPED. Primary decision on the CUPED contribution estimate.
- **Why:** Welch does not assume equal variances, which matters when the treatment changes spend dispersion; CUPED with the pre-period of the same metric is the standard, unbiased variance-reduction method and here removes about 40% of the variance; reporting MDE tells a stakeholder what the test could and could not have seen.
- **Alternatives rejected:** Mann-Whitney, because it tests distributions rather than the mean that the P&L depends on; regression adjustment with many covariates, because CUPED with one strong covariate captures most of the gain with an easier explanation; a bootstrap for every metric, because the sample is large and the analytical intervals agree with it (tested).
- **Trade-off / consequence:** CUPED needs pre-period history, so brand-new users get the covariate 0, which weakens the adjustment for them.

### D-048: novelty as effect by week since assignment plus a direct decay test
- **Project / phase:** p2, phase 11
- **Decision:** effects are estimated separately for weeks 1, 2 and 3 after each user's assignment, and decay is tested directly as the treatment-control difference in each user's (week 1 minus week 3) orders.
- **Why:** comparing week-level estimates by eye cannot tell decay from noise; the per-user difference uses each user as their own control and gives one p-value for "the effect is fading".
- **Alternatives rejected:** calendar-week cuts, because users enter on different days; fitting an exponential decay curve, because three points cannot identify a shape and the decision only needs to know whether week 3 is lower than week 1.
- **Trade-off / consequence:** the steady-state effect is approximated by week 3; a longer holdout would be needed to know where it settles.

### D-049: segment cuts with CUPED, Holm correction and interaction tests
- **Project / phase:** p2, phase 11
- **Decision:** effects are estimated per platform, zone and tenure (new vs established) on CUPED-adjusted outcomes; p-values are Holm-corrected within each metric's family of segment tests; heterogeneity itself is tested with a treatment x segment interaction (robust SE), also Holm-corrected across the three dimensions.
- **Why:** a large average effect makes every segment "significant", which says nothing about whether segments differ; the interaction test answers the real question (is the effect different here?) and the correction stops one of ten segments from being reported as special by chance.
- **Alternatives rejected:** Bonferroni, because it is uniformly less powerful than Holm with the same family-wise guarantee; Benjamini-Hochberg, because a launch decision targeting a segment needs family-wise control, not a false discovery rate; no correction, because ten segments at 5% give about a 40% chance of at least one false positive.
- **Trade-off / consequence:** small segments (web users) have low power, so "no significant difference" there is weak evidence of no difference.

### D-050: pilot evaluated with two-way fixed-effects difference-in-differences
- **Project / phase:** p2, phase 11
- **Decision:** each pilot metric is regressed on treated x post with node and date fixed effects and node-clustered standard errors; parallel trends are checked with an event study (weekly leads and lags, joint F test on the leads with cluster degrees of freedom) and a single-parameter linear pre-trend test; a placebo test re-runs the DiD on pre-period data with a fake start 28 days earlier. The parallel-trends gate uses the linear pre-trend and the placebo; the joint lead test is reported.
- **Why:** date fixed effects absorb the shared seasonality and shocks; clustering by node respects that days within a node are correlated; the event study shows the shape, while the single slope test is the most powerful check against the divergence that would actually bias the estimate. The chi-square version of the joint test rejected for delivery minutes even though no single lead was significant, a known over-rejection with 24 clusters, so I switched to the F version and kept the slope test as the gate.
- **Alternatives rejected:** a plain before/after on pilot nodes, because shared shocks would be counted as pilot effect; synthetic control, because with 8 treated nodes and a clean randomised control group it adds complexity for no bias reduction; wild cluster bootstrap, because it is not available in the pinned libraries and the CIs are far from the decision thresholds.
- **Trade-off / consequence:** with 24 clusters the clustered SEs are approximate; conclusions are drawn only where the CI is far from zero and from the guardrail tolerance. I also changed the generator so that busy days add delivery minutes equally at every node (it previously scaled by node level), which matches the stated assumption of a shared shock.

### D-051: decision rules written down before reading the results
- **Project / phase:** p2, phase 11
- **Decision:** promotion: launch if the CUPED contribution-per-user CI is above zero and the high-margin-share guardrail is not significantly down; do not launch if the CI is entirely below zero; otherwise extend. Pilot: scale if cost per order falls significantly, no guardrail is breached and parallel trends hold; if cost falls but a guardrail is breached (defect rate up significantly and by more than 0.3 pp, or SLA down significantly and by more than 2 pp), do not scale as-is but fix and extend; otherwise do not scale.
- **Why:** coding the rule removes the temptation to argue for a result after seeing it, and states the business trade-off (how much defect increase is acceptable for the saving) explicitly for stakeholders to challenge.
- **Alternatives rejected:** a single p-value threshold on the primary metric, because it ignores guardrails; an expected-value calculation monetising defects, because the cost of a defect (refund plus churn) is not in the data and would be an invented number.
- **Trade-off / consequence:** the tolerances (0.3 pp defects, 2 pp SLA) are judgement calls held in config; a different business could reasonably set them differently and get a different call.

### D-052: experiment workbook computes the tests, not just the inputs
- **Project / phase:** p2, phase 12
- **Decision:** `outputs/p2_experiment_readout.xlsx` stores per-arm n, mean and variance, daily assignment counts, power inputs and the pilot 2x2 means as values, and computes difference, standard error, CI, p-value, significance, MDE, required sample size, per-day SRM chi-square p-values and the raw difference-in-differences as formulas driven by editable alpha, power and SRM-threshold cells. Tests evaluate the formulas (with scipy-backed implementations of `NORM.S.INV`, `NORM.S.DIST` and `CHISQ.DIST.RT`, which the formula engine lacks) and compare them with the Python readout.
- **Why:** a stakeholder can change alpha or the target power and see the conclusions move, which is the most useful thing a spreadsheet adds to an experiment readout; testing the formulas proves the sheet agrees with the README.
- **Alternatives rejected:** exporting result rows as values, because it violates the live-formula requirement and teaches nothing; reproducing the fixed-effects DiD in Excel, because regression with 130 dummies is not a spreadsheet task (the sheet shows the raw 2x2 and labels the difference).
- **Trade-off / consequence:** the sheet uses a normal approximation instead of Welch t; with over 26k users per arm the difference is in the fourth decimal.

### D-053: experiment dashboard built around the decision
- **Project / phase:** p2, phase 12
- **Decision:** tiles state both calls first, then a forest plot of every promotion metric (relative effect with CI), the novelty chart, the per-day SRM chart, the basket-value histogram with both thresholds, segment forest plot plus Holm and interaction tables, pilot weekly trends with a metric switcher, the event-study chart and the DiD table with pre-trend and placebo results.
- **Why:** a forest plot shows sign, size and uncertainty of many metrics at once on one axis; each later chart answers one challenge a stakeholder would raise (is the split valid, will it fade, who responds, are the pilot groups comparable).
- **Alternatives rejected:** bar charts of arm means, because they hide uncertainty and need one axis per metric; a dual-axis chart of cost and defects, because two scales on one chart invite false visual correlations.
- **Trade-off / consequence:** relative effects for ratio metrics and share metrics sit on the same axis as money metrics, so the hover text gives the exact meaning of each row.

### D-054: one memo, one call per experiment, each with "what would change the call"
- **Project / phase:** p2, phase 13
- **Decision:** the memo gives each experiment a single capitalised call taken from the coded decision rule, then result, mechanism, uncertainty (CI, power, SRM handling, fairness checks) and a "what would change the call" line naming the specific follow-up test or data.
- **Why:** stakeholders act on the call; the uncertainty line tells them how firm it is, and naming the follow-up turns a "no" into a next step (a targeted offer for the responsive segment, a defect-safe batching rule).
- **Alternatives rejected:** reporting p-values without a recommendation, because the brief asks for a decision; recommending a specific alternative threshold, because the test did not measure one and the number would be invented.
- **Trade-off / consequence:** the follow-up suggestions are qualitative; their value can only be known by running them.
