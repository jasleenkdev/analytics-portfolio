"""Rendering helpers: markdown templates and CSV exports."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, StrictUndefined


def _fmt_num(value, digits: int = 1) -> str:
    return f"{value:,.{digits}f}"


def _fmt_pct(value, digits: int = 1) -> str:
    return f"{value * 100:.{digits}f}%"


def _fmt_int(value) -> str:
    return f"{int(round(value)):,d}"


def template_env(template_dir: Path) -> Environment:
    env = Environment(loader=FileSystemLoader(template_dir), undefined=StrictUndefined,
                      keep_trailing_newline=True, trim_blocks=True, lstrip_blocks=True)
    env.filters.update(num=_fmt_num, pct=_fmt_pct, int=_fmt_int)
    return env


def render(template_dir: Path, name: str, out: Path, **context) -> Path:
    out.write_text(template_env(template_dir).get_template(name).render(**context), encoding="utf-8")
    return out


def md_table(df: pd.DataFrame, formats: dict | None = None) -> str:
    """Small markdown table writer (avoids an extra dependency on tabulate)."""
    formats = formats or {}
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, row in df.iterrows():
        cells = [formats[c](row[c]) if c in formats else str(row[c]) for c in cols]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def export_csv(con, queries: dict[str, str], out_dir: Path) -> dict[str, pd.DataFrame]:
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = {}
    for name, sql in queries.items():
        df = con.execute(sql).df()
        df.to_csv(out_dir / f"{name}.csv", index=False, float_format="%.6g")
        frames[name] = df
    return frames
