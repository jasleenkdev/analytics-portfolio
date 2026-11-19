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
