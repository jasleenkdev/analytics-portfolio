"""Single-file HTML dashboard shell shared by the three projects.

Data is embedded in the page; plotly.js is loaded from its pinned CDN build (see D-004).
Colours follow one validated palette: categorical slots for identity, a one-hue blue ramp for
magnitude, a blue/red diverging pair around a grey midpoint. Dark mode re-steps the same hues.
"""
from __future__ import annotations

import html
import json

import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs_version

SERIES_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SERIES_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#0ca30c", "#9085e9", "#e66767"]
SEQ_BLUE = [[0.0, "#cde2fb"], [0.25, "#86b6ef"], [0.5, "#3987e5"], [0.75, "#1c5cab"], [1.0, "#0d366b"]]
DIVERGING = [[0.0, "#1c5cab"], [0.25, "#86b6ef"], [0.5, "#f0efec"], [0.75, "#ec8f8f"], [1.0, "#b32d2d"]]
MUTED = "#8a8984"

CSS = """
:root { color-scheme: light;
  --surface-0:#f6f6f4; --surface-1:#fcfcfb; --border:#e3e2de; --text-primary:#0b0b0b;
  --text-secondary:#52514e; --text-muted:#76756f; --accent:#2a78d6; --good:#006300; --critical:#b32d2d; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { color-scheme: dark;
  --surface-0:#121211; --surface-1:#1a1a19; --border:#33332f; --text-primary:#f0efec;
  --text-secondary:#c3c2b7; --text-muted:#9b9a92; --accent:#3987e5; --good:#4cc24c; --critical:#e66767; } }
:root[data-theme="dark"] { color-scheme: dark;
  --surface-0:#121211; --surface-1:#1a1a19; --border:#33332f; --text-primary:#f0efec;
  --text-secondary:#c3c2b7; --text-muted:#9b9a92; --accent:#3987e5; --good:#4cc24c; --critical:#e66767; }
* { box-sizing: border-box; }
body { margin:0; background:var(--surface-0); color:var(--text-primary);
  font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif; }
main { max-width:1180px; margin:0 auto; padding:24px 16px 64px; }
header h1 { font-size:26px; margin:0 0 4px; letter-spacing:-0.01em; }
header p { margin:4px 0; color:var(--text-secondary); max-width:860px; }
.banner { margin:14px 0 22px; padding:10px 14px; border:1px solid var(--border); border-left:4px solid var(--accent);
  background:var(--surface-1); border-radius:6px; color:var(--text-secondary); font-size:14px; }
.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; margin-bottom:24px; }
.tile { background:var(--surface-1); border:1px solid var(--border); border-radius:8px; padding:12px 14px; }
.tile .label { font-size:12px; text-transform:uppercase; letter-spacing:0.04em; color:var(--text-muted); }
.tile .value { font-size:26px; font-weight:650; margin-top:2px; font-variant-numeric:tabular-nums; }
.tile .note { font-size:12.5px; color:var(--text-secondary); }
section { background:var(--surface-1); border:1px solid var(--border); border-radius:8px; padding:16px; margin-bottom:20px; }
section h2 { font-size:18px; margin:0 0 4px; }
section .lede { margin:0 0 10px; color:var(--text-secondary); font-size:14px; max-width:900px; }
.controls { display:flex; flex-wrap:wrap; gap:10px; margin:8px 0 10px; align-items:center; }
.controls label { font-size:13px; color:var(--text-secondary); display:flex; gap:6px; align-items:center; }
.controls select, .controls input { font:inherit; font-size:13px; padding:4px 6px; border-radius:6px;
  border:1px solid var(--border); background:var(--surface-0); color:var(--text-primary); }
.tablewrap { overflow:auto; max-height:520px; border:1px solid var(--border); border-radius:6px; }
table { border-collapse:collapse; width:100%; font-size:13px; font-variant-numeric:tabular-nums; }
th, td { padding:6px 8px; border-bottom:1px solid var(--border); text-align:left; white-space:nowrap; }
th { position:sticky; top:0; background:var(--surface-1); cursor:pointer; color:var(--text-secondary); font-weight:600; }
td.num, th.num { text-align:right; }
.count { font-size:12.5px; color:var(--text-muted); }
footer { color:var(--text-muted); font-size:13px; margin-top:24px; }
.plot { width:100%; }
"""

# re-colour plotly text and grid for dark mode without regenerating figures
THEME_JS = """
(function(){
  const dark = () => document.documentElement.dataset.theme === 'dark' ||
    (document.documentElement.dataset.theme !== 'light' && matchMedia('(prefers-color-scheme: dark)').matches);
  const LIGHT = %s, DARK = %s;
  function apply(){
    const d = dark(), ink = d ? '#c3c2b7' : '#52514e', grid = d ? '#33332f' : '#e3e2de';
    document.querySelectorAll('.js-plotly-plot').forEach(el => {
      const upd = {'font.color': ink, 'xaxis.gridcolor': grid, 'yaxis.gridcolor': grid,
                   'paper_bgcolor': 'rgba(0,0,0,0)', 'plot_bgcolor': 'rgba(0,0,0,0)'};
      Plotly.relayout(el, upd);
      (el.data || []).forEach((tr, i) => {
        const slot = tr.meta && tr.meta.slot;
        if (slot === undefined) return;
        const c = (d ? DARK : LIGHT)[slot];
        const key = tr.type === 'bar' ? 'marker.color' : 'line.color';
        Plotly.restyle(el, {[key]: c}, [i]);
        if (tr.type !== 'bar' && tr.marker) Plotly.restyle(el, {'marker.color': c}, [i]);
      });
    });
  }
  window.addEventListener('load', apply);
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', apply);
})();
""" % (json.dumps(SERIES_LIGHT), json.dumps(SERIES_DARK))

TABLE_JS = """
function makeTable(id, rows, cols, filters, numeric){
  const root = document.getElementById(id), ctl = root.querySelector('.controls'),
        body = root.querySelector('tbody'), head = root.querySelector('thead tr'), count = root.querySelector('.count');
  let sortCol = null, asc = false;
  const sel = {};
  filters.forEach(f => {
    const vals = [...new Set(rows.map(r => r[f]))].sort();
    const lab = document.createElement('label'); lab.textContent = f.replaceAll('_',' ');
    const s = document.createElement('select');
    s.innerHTML = '<option value="">all</option>' + vals.map(v => `<option>${v}</option>`).join('');
    s.onchange = () => { sel[f] = s.value; draw(); };
    lab.appendChild(s); ctl.appendChild(lab);
  });
  const search = document.createElement('input'); search.placeholder = 'search'; search.oninput = draw;
  const sl = document.createElement('label'); sl.textContent = 'text'; sl.appendChild(search); ctl.appendChild(sl);
  cols.forEach(c => { const th = document.createElement('th'); th.textContent = c.replaceAll('_',' ');
    if (numeric.includes(c)) th.className = 'num';
    th.onclick = () => { asc = sortCol === c ? !asc : false; sortCol = c; draw(); }; head.appendChild(th); });
  function fmt(v){ return (typeof v === 'number') ? (Number.isInteger(v) ? v.toLocaleString() : v.toFixed(2)) : (v ?? ''); }
  function draw(){
    const q = search.value.toLowerCase();
    let r = rows.filter(x => filters.every(f => !sel[f] || String(x[f]) === sel[f]) &&
      (!q || cols.some(c => String(x[c]).toLowerCase().includes(q))));
    if (sortCol) r = r.slice().sort((a,b) => (a[sortCol] > b[sortCol] ? 1 : -1) * (asc ? 1 : -1));
    body.innerHTML = r.slice(0, 500).map(x => '<tr>' + cols.map(c =>
      `<td${numeric.includes(c) ? ' class="num"' : ''}>${fmt(x[c])}</td>`).join('') + '</tr>').join('');
    count.textContent = `${r.length.toLocaleString()} rows` + (r.length > 500 ? ' (first 500 shown)' : '');
  }
  draw();
}
"""


def style_fig(fig: go.Figure, height: int = 380) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=36, b=8),
        font=dict(family="system-ui, -apple-system, Segoe UI, Roboto, sans-serif", size=12, color="#52514e"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        hoverlabel=dict(font_size=12), bargap=0.25,
    )
    fig.update_xaxes(gridcolor="#e3e2de", zeroline=False, linecolor="#c3c2b7")
    fig.update_yaxes(gridcolor="#e3e2de", zeroline=False, linecolor="#c3c2b7")
    return fig


def series(slot: int) -> dict:
    """Colour plus metadata so the theme script can re-step the slot for dark mode."""
    return {"color": SERIES_LIGHT[slot], "meta": {"slot": slot}}


def fig_html(fig: go.Figure, div_id: str) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False, div_id=div_id,
                       config={"displaylogo": False, "responsive": True})


def table_block(div_id: str, df: pd.DataFrame, filters: list[str]) -> str:
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.strftime("%Y-%m-%d %H:%M").str.replace(" 00:00", "", regex=False)
        elif pd.api.types.is_float_dtype(df[c]):
            df[c] = df[c].round(3)
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    rows = json.loads(df.to_json(orient="records", date_format="iso"))
    return (f'<div id="{div_id}"><div class="controls"></div><div class="count"></div>'
            f'<div class="tablewrap"><table><thead><tr></tr></thead><tbody></tbody></table></div></div>'
            f"<script>makeTable({json.dumps(div_id)}, {json.dumps(rows)}, {json.dumps(list(df.columns))}, "
            f"{json.dumps(filters)}, {json.dumps(numeric)});</script>")


def tile(label: str, value: str, note: str = "") -> str:
    return (f'<div class="tile"><div class="label">{html.escape(label)}</div>'
            f'<div class="value">{html.escape(value)}</div><div class="note">{html.escape(note)}</div></div>')


def section(title: str, lede: str, body: str) -> str:
    return f'<section><h2>{html.escape(title)}</h2><p class="lede">{lede}</p>{body}</section>'


def page(title: str, subtitle: str, disclosure: str, tiles: list[str], sections: list[str], footer: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<script src="https://cdn.plot.ly/plotly-{get_plotlyjs_version()}.min.js" charset="utf-8"></script>
<style>{CSS}</style>
<script>{TABLE_JS}</script>
</head><body><main>
<header><h1>{html.escape(title)}</h1><p>{subtitle}</p></header>
<div class="banner">{disclosure}</div>
<div class="tiles">{''.join(tiles)}</div>
{''.join(sections)}
<footer>{footer}</footer>
</main><script>{THEME_JS}</script></body></html>
"""
