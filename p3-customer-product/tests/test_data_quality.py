"""Data-quality report recounts and the base layer rebuilt in pandas."""
import numpy as np
import pandas as pd
import pytest

from conftest import scalar


def test_dq_report_complete_and_recounted(con):
    report = dict(con.execute("SELECT check_name, failing_rows FROM dq_report").fetchall())
    assert len(report) >= 12
    never = scalar(con, "SELECT count(*) FROM customers WHERE customer_id NOT IN (SELECT customer_id FROM orders)")
    assert report["customers who signed up but never ordered"] == never
    lost = scalar(con, "SELECT count(*) FROM inventory_daily WHERE lost_sales > 0")
    assert report["node-days with lost sales (units ordered but not in stock)"] == lost


def test_structural_checks_pass(con):
    failing = con.execute("""SELECT check_name FROM dq_report WHERE status = 'issue'
                             AND action NOT LIKE 'report:%' AND action NOT LIKE 'keep:%'""").fetchall()
    assert failing == []


def test_order_sequence_and_gaps(con):
    sample = con.execute("SELECT customer_id FROM customer_facts WHERE orders >= 3 USING SAMPLE 300 ROWS (reservoir, 5)").df()
    o = con.execute("SELECT customer_id, order_id, order_ts FROM orders WHERE customer_id IN (SELECT unnest(?))",
                    [list(sample.customer_id)]).df().sort_values(["customer_id", "order_ts", "order_id"])
    o["seq"] = o.groupby("customer_id").cumcount() + 1
    o["gap"] = (o.order_ts.dt.normalize() - o.groupby("customer_id").order_ts.shift().dt.normalize()).dt.days
    sql = con.execute("SELECT order_id, order_seq, days_since_prev FROM order_facts WHERE customer_id IN (SELECT unnest(?))",
                      [list(sample.customer_id)]).df().set_index("order_id")
    m = o.set_index("order_id").join(sql)
    assert (m.seq == m.order_seq).all()
    assert np.allclose(m.gap.fillna(-1), m.days_since_prev.astype(float).fillna(-1))


def test_first_order_issue_flag(con):
    o = con.execute("""SELECT o.customer_id, o.order_id, o.order_ts, i.order_id IS NOT NULL AS issue
                       FROM orders o LEFT JOIN (SELECT DISTINCT order_id FROM order_issues) i USING (order_id)""").df()
    first = o.sort_values(["customer_id", "order_ts", "order_id"]).groupby("customer_id").head(1).set_index("customer_id").issue
    sql = con.execute("SELECT customer_id, first_order_issue FROM customer_facts").df().set_index("customer_id").first_order_issue
    assert (first.sort_index() == sql.sort_index()).all()


def test_margins_add_up(con):
    a = con.execute("SELECT sum(gross_margin), sum(revenue) FROM line_facts").fetchone()
    b = con.execute("SELECT sum(qty * (unit_price - unit_cost)), sum(qty * unit_price) FROM order_lines").fetchone()
    assert a == pytest.approx(b, rel=1e-9)
    assert scalar(con, "SELECT count(*) FROM order_facts") == scalar(con, "SELECT count(*) FROM orders")
