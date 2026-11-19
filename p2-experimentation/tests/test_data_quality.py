"""Data-quality report recounts and the experiment tables rebuilt in pandas."""
import numpy as np
import pandas as pd
import pytest

from conftest import scalar


def test_dq_report_recounts(con, cfg):
    sim = cfg["sim"]
    report = dict(con.execute("SELECT check_name, failing_rows FROM dq_report").fetchall())
    t0 = pd.Timestamp(sim["experiment_start"])
    t1 = t0 + pd.Timedelta(days=sim["assignment_days"] + sim["observation_days"])
    orders = con.execute("SELECT user_id, order_ts FROM orders").df()
    assigned = set(con.execute("SELECT user_id FROM assignments").df().user_id)
    active = set(orders[(orders.order_ts >= t0) & (orders.order_ts < t1)].user_id)
    assert report["users ordering during the test with no assignment record"] == len(active - assigned)
    panel = con.execute("SELECT count(*) FROM pilot_daily_ops").fetchone()[0]
    expected = sim["pilot_nodes"] * (sim["pilot_pre_days"] + sim["pilot_post_days"])
    assert report["pilot node-days missing from the panel"] == expected - panel


def test_daily_assignment_counts_add_up(con):
    total = scalar(con, "SELECT sum(n_control + n_treatment) FROM dq_assignment_daily")
    assert total == scalar(con, "SELECT count(*) FROM assignments")


def test_exp_users_one_row_per_assigned_user(con):
    assert scalar(con, "SELECT count(*) FROM exp_users") == scalar(con, "SELECT count(DISTINCT user_id) FROM assignments")
    assert scalar(con, "SELECT count(*) FROM exp_users WHERE variant NOT IN ('control', 'treatment') OR tenure IS NULL") == 0


def test_user_metrics_match_pandas(con, cfg):
    days = cfg["sim"]["observation_days"]
    sample = con.execute("SELECT * FROM exp_user_metrics USING SAMPLE 800 ROWS (reservoir, 3)").df()
    orders = con.execute("SELECT * FROM orders WHERE user_id IN (SELECT unnest(?))", [list(sample.user_id)]).df()
    for r in sample.itertuples():
        o = orders[(orders.user_id == r.user_id) & (orders.order_ts >= r.assigned_at)
                   & (orders.order_ts < r.assigned_at + pd.Timedelta(days=days))]
        assert r.orders == len(o)
        assert r.contribution == pytest.approx((o.product_margin + o.delivery_fee - o.delivery_cost).sum(), abs=1e-6)
        assert r.gmv == pytest.approx(o.basket_value.sum(), abs=1e-6)
        assert r.high_margin_orders == int(o.high_margin_basket.sum())


def test_weekly_rows_sum_to_window(con):
    gap = scalar(con, """SELECT count(*) FROM exp_user_metrics m JOIN
                         (SELECT user_id, sum(orders) AS o, sum(contribution) AS c FROM exp_user_week GROUP BY 1) w USING (user_id)
                         WHERE m.orders <> w.o OR abs(m.contribution - w.c) > 1e-6""")
    assert gap == 0


def test_pre_period_has_no_experiment_orders(con, cfg):
    start = cfg["sim"]["experiment_start"]
    pre = con.execute(f"SELECT sum(pre_orders) FROM exp_users").fetchone()[0]
    raw = con.execute(f"""SELECT count(*) FROM orders o JOIN exp_users e USING (user_id)
                          WHERE o.order_ts < TIMESTAMP '{start}'""").fetchone()[0]
    assert pre == raw


def test_pilot_panel_metrics(con, cfg):
    p = con.execute("SELECT * FROM pilot_panel").df()
    assert np.allclose(p.cost_per_order, p.rider_hours * cfg["analysis"]["rider_cost_per_hour"] / p.orders)
    assert np.allclose(p.defect_rate, p.defect_orders / p.orders)
    assert ((p.pct_within_sla >= 0) & (p.pct_within_sla <= 1)).all()
    assert (p.post == (p.rel_day >= 0)).all()
