"""Report outputs: workbook formulas reproduce the Python statistics, and the dashboard carries data."""
import json
from pathlib import Path

import pytest
from pycel import ExcelCompiler

# rendered outputs are checked after the report stage (see Makefile)
pytestmark = pytest.mark.outputs

PROJECT = Path(__file__).resolve().parents[1]
WORKBOOK = PROJECT / "outputs" / "p2_experiment_readout.xlsx"
DASHBOARD = PROJECT / "docs" / "index.html"
FINDINGS = PROJECT / "outputs" / "findings.json"


@pytest.fixture(scope="module")
def excel():
    if not WORKBOOK.exists():
        pytest.fail("workbook missing: run `python pipeline.py report` first")
    return ExcelCompiler(filename=str(WORKBOOK), plugins=["excel_stats_plugin"])


def test_promo_formulas_match_readout(excel):
    f = json.loads(FINDINGS.read_text())["promo"]
    raw = {r["metric"]: r for r in f["results"] if r["method"] == "difference in means" and r["population"] == "analysis"}
    for row in range(2, 8):
        metric = excel.evaluate(f"promo_arms!A{row}")
        assert excel.evaluate(f"promo_arms!H{row}") == pytest.approx(raw[metric]["diff"], rel=1e-6, abs=2e-6)
        assert excel.evaluate(f"promo_arms!I{row}") == pytest.approx(raw[metric]["se"], rel=1e-6, abs=2e-6)
        assert excel.evaluate(f"promo_arms!J{row}") == pytest.approx(raw[metric]["ci_low"], rel=1e-3, abs=1e-4)


def test_power_formulas_match_readout(excel):
    p = json.loads(FINDINGS.read_text())["promo"]["power"]
    assert excel.evaluate("power!B8") == pytest.approx(p["mde_abs"], rel=1e-3)
    assert excel.evaluate("power!B10") == pytest.approx(p["mde_abs_cuped"], rel=1e-3)


def test_srm_formulas_flag_the_same_days(excel):
    f = json.loads(FINDINGS.read_text())["promo"]
    daily = f["srm_daily"]
    for row, d in enumerate(daily, start=2):
        assert excel.evaluate(f"srm_daily!F{row}") == pytest.approx(d["p_value"], rel=1e-6, abs=2e-6)
        assert (excel.evaluate(f"srm_daily!G{row}") == "SRM") == d["flagged"]


def test_pilot_raw_did_formula(excel, con):
    two = con.execute("SELECT * FROM pilot_2x2").df().set_index(["pilot_group", "period", "metric"]).value
    for row in range(2, 6):
        m = excel.evaluate(f"pilot_2x2!A{row}")
        expected = (two[("treatment", "after", m)] - two[("treatment", "before", m)]) - (two[("control", "after", m)] - two[("control", "before", m)])
        assert excel.evaluate(f"pilot_2x2!F{row}") == pytest.approx(expected, rel=1e-9)


def test_dashboard_contains_data():
    if not DASHBOARD.exists():
        pytest.fail("dashboard missing: run `python pipeline.py report` first")
    html = DASHBOARD.read_text()
    assert "Simulated data" in html and html.count("Plotly.newPlot") >= 7
    assert 'makeTable("didtable"' in html


def test_narratives_rendered_and_disclose_simulation():
    readme, memo = (PROJECT / "README.md").read_text(), (PROJECT / "memo.md").read_text()
    assert "simulated" in "\n".join(readme.splitlines()[:10]).lower() and "simulated" in memo.lower()
    for text in (readme, memo):
        assert "{{" not in text and "{%" not in text
    f = json.loads(FINDINGS.read_text())
    assert f["promo"]["decision"].upper() in memo and f["pilot"]["decision"].upper() in memo
