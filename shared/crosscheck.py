"""Shared helpers for the found-vs-planted cross-check (the only code allowed to read the plant files)."""
from __future__ import annotations

import json
import tomllib
from pathlib import Path


def load_truth(project_dir: Path) -> tuple[dict, dict, dict]:
    with open(project_dir / "data_gen" / "plants.toml", "rb") as f:
        plants = tomllib.load(f)
    entities = json.loads((project_dir / "data" / "planted_entities.json").read_text())
    findings = json.loads((project_dir / "outputs" / "findings.json").read_text())
    return plants, entities, findings


def row(planted: str, found: str, verdict: str, note: str = "") -> dict:
    assert verdict in {"hit", "partial", "miss", "unplanted"}
    return {"planted": planted, "found": found, "verdict": verdict, "note": note}


def write(project_dir: Path, rows: list[dict]) -> dict:
    summary = {v: sum(r["verdict"] == v for r in rows) for v in ["hit", "partial", "miss", "unplanted"]}
    out = {"rows": rows, "summary": summary}
    (project_dir / "outputs" / "crosscheck.json").write_text(json.dumps(out, indent=2))
    return out
