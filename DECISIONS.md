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
