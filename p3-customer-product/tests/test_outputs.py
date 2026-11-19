"""Workbook formulas reproduce the SQL classification and wastage model; the dashboard carries data."""
import json
from pathlib import Path

import pytest
from pycel import ExcelCompiler

PROJECT = Path(__file__).resolve().parents[1]
WORKBOOK = PROJECT / "outputs" / "p3_assortment_wastage.xlsx"
DASHBOARD = PROJECT / "docs" / "index.html"


@pytest.fixture(scope="module")
def excel():
    if not WORKBOOK.exists():
        pytest.skip("workbook is produced by the report stage")
    return ExcelCompiler(filename=str(WORKBOOK))


def test_abc_xyz_formulas_match_sql(excel, con):
    sql = con.execute("SELECT sku_id, abc, xyz FROM abc_xyz ORDER BY revenue DESC, sku_id").df()
    for row in list(range(2, 40)) + list(range(150, 170)) + list(range(400, len(sql) + 2)):
        r = sql.iloc[row - 2]
        assert excel.evaluate(f"abc_xyz!A{row}") == r.sku_id
        assert excel.evaluate(f"abc_xyz!J{row}") == r.abc, r.sku_id
        assert excel.evaluate(f"abc_xyz!K{row}") == r.xyz, r.sku_id


def test_matrix_counts_match_sql(excel, con):
    m = con.execute("SELECT abc, xyz, skus FROM abc_xyz_matrix").df().set_index(["abc", "xyz"]).skus
    for i, cls in enumerate("ABC", start=2):
        for j, z in enumerate("BCD"):
            assert excel.evaluate(f"abc_xyz_matrix!{z}{i}") == m.get((cls, "XYZ"[j]), 0)


def test_wastage_formulas_match_sql(excel, con):
    sql = con.execute("SELECT node_id, sku_id, risk_score, high_risk, waste_cost FROM wastage_node_sku ORDER BY waste_cost DESC").df()
    reduce_ = set(map(tuple, con.execute("SELECT node_id, sku_id FROM assortment_reduce").df().values))
    for row in range(2, 60):
        r = sql.iloc[row - 2]
        assert excel.evaluate(f"wastage_model!K{row}") == pytest.approx(r.risk_score, rel=1e-9)
        assert (excel.evaluate(f"wastage_model!L{row}") == "high") == bool(r.high_risk)
        assert excel.evaluate(f"wastage_model!N{row}") == pytest.approx(r.waste_cost, rel=1e-9)
        assert (excel.evaluate(f"wastage_model!Q{row}") == "yes") == ((r.node_id, r.sku_id) in reduce_)


def test_depth_cut_saving_total(excel, con):
    low, high = con.execute("SELECT sum(impact_low), sum(impact_high) FROM assortment_reduce").fetchone()
    n = con.execute("SELECT count(*) FROM wastage_node_sku").fetchone()[0]
    assert excel.evaluate(f"wastage_model!R{n + 3}") == pytest.approx(low, rel=1e-9)
    assert excel.evaluate(f"wastage_model!S{n + 3}") == pytest.approx(high, rel=1e-9)


def test_dashboard_contains_data():
    if not DASHBOARD.exists():
        pytest.skip("dashboard is produced by the report stage")
    html = DASHBOARD.read_text()
    assert "Simulated data" in html and html.count("Plotly.newPlot") >= 7
    assert 'makeTable("recs"' in html
