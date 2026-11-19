"""Report outputs: the Excel formulas recompute the SQL KPIs, and the dashboard carries data."""
import json
import re
from pathlib import Path

import pytest
from pycel import ExcelCompiler

# rendered outputs are checked after the report stage (see Makefile)
pytestmark = pytest.mark.outputs

PROJECT = Path(__file__).resolve().parents[1]
WORKBOOK = PROJECT / "outputs" / "p1_fulfilment_kpis.xlsx"
DASHBOARD = PROJECT / "docs" / "index.html"


@pytest.fixture(scope="module")
def excel():
    if not WORKBOOK.exists():
        pytest.fail("workbook missing: run `python pipeline.py report` first")
    return ExcelCompiler(filename=str(WORKBOOK))


def test_workbook_formulas_match_sql(excel, con):
    kpi = con.execute("SELECT * FROM kpi_delivery_node").df().set_index("node_id")
    fill = con.execute("""SELECT node_id, sum(units_fulfilled) / sum(units_ordered) AS fill_rate
                          FROM kpi_fill_node_category GROUP BY 1""").df().set_index("node_id").fill_rate
    riders = con.execute("SELECT * FROM kpi_riders_node").df().set_index("node_id")
    missing = con.execute("SELECT node_id, defect_rate FROM kpi_defects_node WHERE defect_type = 'missing_item'").df().set_index("node_id").defect_rate
    for row, node in enumerate(list(kpi.index[kpi.index != "ALL"]) + ["ALL"], start=2):
        assert excel.evaluate(f"node_summary!A{row}") == node
        assert excel.evaluate(f"node_summary!B{row}") == kpi.loc[node, "orders_placed"]
        assert excel.evaluate(f"node_summary!E{row}") == pytest.approx(kpi.loc[node, "pct_within_sla"], rel=1e-9)
        assert excel.evaluate(f"node_summary!G{row}") == pytest.approx(kpi.loc[node, "cancel_rate"], rel=1e-9)
        assert excel.evaluate(f"node_summary!H{row}") == pytest.approx(kpi.loc[node, "mean_delivery_min"], rel=1e-6)
        assert excel.evaluate(f"node_summary!Q{row}") == pytest.approx(riders.loc[node, "utilisation"], rel=1e-6)
        if node != "ALL":
            assert excel.evaluate(f"node_summary!K{row}") == pytest.approx(missing[node], rel=1e-9)
            assert excel.evaluate(f"node_summary!P{row}") == pytest.approx(fill[node], rel=1e-9)


def test_workbook_cells_are_formulas(excel):
    from openpyxl import load_workbook
    ws = load_workbook(WORKBOOK)["node_summary"]
    for col in "BCDEFGHKLMNOPQR":
        assert str(ws[f"{col}2"].value).startswith("="), f"node_summary!{col}2 is not a formula"


def test_dashboard_contains_data():
    if not DASHBOARD.exists():
        pytest.fail("dashboard missing: run `python pipeline.py report` first")
    html = DASHBOARD.read_text()
    assert "<title>" in html and "Simulated data" in html
    assert html.count("Plotly.newPlot") >= 5
    rows = re.search(r'makeTable\("anomalies", (\[.*?\]), \[', html, re.S)
    assert rows and len(json.loads(rows.group(1))) > 100


def test_narratives_rendered_and_disclose_simulation():
    readme, memo = (PROJECT / "README.md").read_text(), (PROJECT / "memo.md").read_text()
    assert "simulated" in "\n".join(readme.splitlines()[:10]).lower()
    assert "simulated" in memo.lower()
    for text in (readme, memo):
        assert "{{" not in text and "{%" not in text
    findings = json.loads((PROJECT / "outputs" / "findings.json").read_text())
    assert f"{findings['network']['pct_within_sla'] * 100:.1f}%" in readme
