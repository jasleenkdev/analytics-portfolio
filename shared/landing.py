"""Render the root README from the three projects' findings and cross-checks."""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

from shared.reporting import render

ROOT = Path(__file__).resolve().parents[1]


def _load(project: str, name: str) -> dict:
    return json.loads((ROOT / project / "outputs" / name).read_text())


def build() -> Path:
    p1, p2, p3 = (_load(p, "findings.json") for p in ("p1-fulfilment-ops", "p2-experimentation", "p3-customer-product"))
    cc1, cc2, cc3 = (_load(p, "crosscheck.json") for p in ("p1-fulfilment-ops", "p2-experimentation", "p3-customer-product"))
    res = {(r["metric"], r["method"]): r for r in p2["promo"]["results"] if r["population"] == "analysis"}
    with open(ROOT / "portfolio.toml", "rb") as f:
        links = tomllib.load(f)["links"]
    return render(ROOT / "shared", "README.md.j2", ROOT / "README.md",
                  p1=p1, p2=p2, p3=p3, cc1=cc1, cc2=cc2, cc3=cc3, links=links,
                  p2_primary=res[("contribution", "CUPED")], p2_orders=res[("orders", "CUPED")],
                  p2_cost=next(d for d in p2["pilot"]["did"] if d["metric"] == "cost_per_order"),
                  p3_fi=next(m for m in p3["retention"]["model"] if m["term"] == "first_order_issue"),
                  p3_add=next(s for s in p3["assortment"]["summary"] if s["action"] == "add"))


if __name__ == "__main__":
    print(f"wrote {build()}")
