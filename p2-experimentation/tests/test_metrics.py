"""Experiment and pilot SQL metrics recomputed in pandas from the raw tables."""
import numpy as np
import pandas as pd
import pytest


@pytest.fixture(scope="module")
def user_frame(con, cfg):
    """Per-user window metrics rebuilt from raw assignments and orders."""
    a = con.execute("SELECT * FROM assignments").df()
    o = con.execute("SELECT * FROM orders").df().merge(a, on="user_id")
    o = o[(o.order_ts >= o.assigned_at) & (o.order_ts < o.assigned_at + pd.Timedelta(days=cfg["sim"]["observation_days"]))]
    o["contribution"] = o.product_margin + o.delivery_fee - o.delivery_cost
    o["week"] = 1 + ((o.order_ts - o.assigned_at).dt.total_seconds() // (7 * 86400)).astype(int)
    per_user = o.groupby("user_id").agg(orders=("order_id", "size"), contribution=("contribution", "sum"),
                                        gmv=("basket_value", "sum"), hm=("high_margin_basket", "sum"))
    users = a.set_index("user_id").join(per_user).fillna({"orders": 0, "contribution": 0.0, "gmv": 0.0, "hm": 0})
    return users, o


def test_arm_summary(con, user_frame):
    users, _ = user_frame
    s = con.execute("SELECT * FROM exp_arm_summary").df().set_index(["variant", "metric"])
    for variant, g in users.groupby("variant"):
        for metric in ["orders", "contribution", "gmv"]:
            row = s.loc[(variant, metric)]
            assert row.n == len(g)
            assert row["mean"] == pytest.approx(g[metric].mean(), rel=1e-9)
            assert row.variance == pytest.approx(g[metric].var(ddof=1), rel=1e-9)


def test_ratio_moments(con, user_frame):
    users, _ = user_frame
    r = con.execute("SELECT * FROM exp_ratio_moments WHERE metric = 'high_margin_share'").df().set_index("variant")
    for variant, g in users.groupby("variant"):
        assert r.loc[variant, "ratio"] == pytest.approx(g.hm.sum() / g.orders.sum(), rel=1e-9)
        assert r.loc[variant, "cov_xy"] == pytest.approx(np.cov(g.hm, g.orders, ddof=1)[0, 1], rel=1e-9)


def test_week_summary(con, user_frame):
    users, o = user_frame
    w = con.execute("SELECT * FROM exp_week_summary").df().set_index(["week", "variant"])
    for (week, variant), g in o.groupby(["week", "variant"]):
        n = (users.variant == variant).sum()
        assert w.loc[(week, variant), "mean_orders"] == pytest.approx(len(g) / n, rel=1e-9)
        assert w.loc[(week, variant), "mean_contribution"] == pytest.approx(g.contribution.sum() / n, rel=1e-9)


def test_segment_summary_partitions_users(con):
    n = con.execute("SELECT count(*) FROM exp_user_metrics").fetchone()[0]
    for dim, total in con.execute("SELECT dimension, sum(n) FROM exp_segment_summary GROUP BY 1").fetchall():
        assert total == n, dim


def test_pilot_2x2(con, cfg):
    d = con.execute("SELECT d.*, n.pilot_group FROM pilot_daily_ops d JOIN pilot_nodes n USING (node_id)").df()
    start = con.execute("SELECT min(start_date) FROM pilot_rollout").fetchone()[0]
    d["period"] = np.where(d.ops_date >= pd.Timestamp(start), "after", "before")
    g = d.groupby(["pilot_group", "period"])[["rider_hours", "orders", "defect_orders"]].sum()
    s = con.execute("SELECT * FROM pilot_2x2").df().set_index(["pilot_group", "period", "metric"]).value
    for (grp, per), row in g.iterrows():
        assert s[(grp, per, "cost_per_order")] == pytest.approx(row.rider_hours * cfg["analysis"]["rider_cost_per_hour"] / row.orders, rel=1e-9)
        assert s[(grp, per, "defect_rate")] == pytest.approx(row.defect_orders / row.orders, rel=1e-9)
