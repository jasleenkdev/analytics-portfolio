"""Project 2 pipeline. `build`: data, SQL, statistics. `report`: CSV, Excel, dashboard, memo, README."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from analysis import report as report_stage
from analysis import run_sql
from data_gen import ground_truth
from data_gen.generate import generate

HERE = Path(__file__).resolve().parent


def build() -> None:
    print("generating synthetic data")
    generate(HERE)
    ground_truth.render(HERE)
    print("running SQL:", ", ".join(run_sql.run()))


def report() -> None:
    report_stage.run()


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "build"
    t0 = time.time()
    {"build": build, "report": report}[stage]()
    print(f"{stage} finished in {time.time() - t0:.1f}s")
