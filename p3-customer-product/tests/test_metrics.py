"""Funnel, retention, RFM, ABC-XYZ, affinity and wastage SQL recomputed in pandas from raw tables."""
import numpy as np
import pandas as pd
import pytest

from conftest import scalar


def test_funnel_counts(con):
    f = con.execute("SELECT step, count(*) AS n FROM funnel_events GROUP BY 1").df().set_index("step").n
    sql = con.execute("SELECT step, sessions FROM funnel_overall").df().set_index("step").sessions
    for step, n in f.items():
        assert sql[step] == n
    seg = con.execute("""SELECT s.platform, s.app_version, count(*) FILTER (WHERE f.step = 'payment_attempt') AS att,
                         count(*) FILTER (WHERE f.step = 'order_placed') AS ok
                         FROM funnel_events f JOIN sessions s USING (session_id) GROUP BY ALL""").df()
    sm = con.execute("SELECT platform, app_version, sum(payment_attempt) AS att, sum(order_placed) AS ok FROM funnel_segment_month GROUP BY ALL").df()
    m = seg.merge(sm, on=["platform", "app_version"])
    assert (m.att_x == m.att_y).all() and (m.ok_x == m.ok_y).all()


def test_cohort_retention_for_one_cohort(con):
    o = con.execute("SELECT customer_id, order_ts FROM orders").df()
    first = o.groupby("customer_id").order_ts.min().dt.to_period("M")
    o["cohort"] = o.customer_id.map(first)
    o["k"] = (o.order_ts.dt.to_period("M") - o.cohort).apply(lambda x: x.n)
    cohort = pd.Period("2025-03", "M")
    size = (first == cohort).sum()
    expected = o[o.cohort == cohort].groupby("k").customer_id.nunique() / size
    sql = con.execute("SELECT months_since_first, retention FROM cohort_retention WHERE cohort_month = DATE '2025-03-01'").df()
    for r in sql.itertuples():
        assert r.retention == pytest.approx(expected[r.months_since_first], rel=1e-9)


def test_repeat_curve(con, cfg):
    o = con.execute("SELECT customer_id, order_ts FROM orders ORDER BY customer_id, order_ts, order_id").df()
    g = o.groupby("customer_id").order_ts
    first, second = g.min(), g.apply(lambda s: s.iloc[1] if len(s) > 1 else pd.NaT)
    as_of = pd.Timestamp(cfg["analysis"]["as_of_date"])
    sql = con.execute("SELECT * FROM repeat_curve").df()
    for r in sql.itertuples():
        # DuckDB date_diff('day') counts calendar-day boundaries, so compare normalised dates
        obs = (as_of - first.dt.normalize()).dt.days >= r.days
        rep = ((second.dt.normalize() - first.dt.normalize()).dt.days <= r.days) & obs
        assert r.customers_observable == obs.sum()
        assert r.repeat_rate == pytest.approx(rep.sum() / obs.sum(), rel=1e-9)


def test_rfm_scores(con, cfg):
    rfm = con.execute("SELECT * FROM rfm").df()
    bins = cfg["analysis"]["rfm_bins"]
    for col in ["r_score", "f_score", "m_score"]:
        counts = rfm[col].value_counts()
        assert set(counts.index) == set(range(1, bins + 1)) and counts.max() - counts.min() <= 1
    # higher recency score means a more recent last order
    means = rfm.groupby("r_score").recency_days.mean()
    assert means.is_monotonic_decreasing
    assert scalar(con, "SELECT sum(customers) FROM rfm_segments") == len(rfm)


def test_abc_classes(con, cfg):
    a = cfg["analysis"]
    df = con.execute("SELECT sku_id, revenue, abc FROM abc_xyz").df().sort_values(["revenue", "sku_id"], ascending=[False, True])
    before = (df.revenue.cumsum() - df.revenue) / df.revenue.sum()
    expected = np.where(before < a["abc_a_share"], "A", np.where(before < a["abc_b_share"], "B", "C"))
    assert (expected == df.abc.values).all()


def test_xyz_uses_median_node_cv(con):
    sku = con.execute("SELECT sku_id, weekly_cv FROM abc_xyz ORDER BY revenue DESC LIMIT 1 OFFSET 40").fetchone()
    w = con.execute("SELECT node_id, units FROM node_sku_weekly WHERE sku_id = ?", [sku[0]]).df()
    cv = w.groupby("node_id").units.agg(lambda u: u.std(ddof=0) / u.mean())
    assert sku[1] == pytest.approx(cv.median(), rel=1e-9)


def test_affinity_lift_for_top_pairs(con):
    top = con.execute("SELECT * FROM basket_affinity ORDER BY lift DESC LIMIT 5").df()
    n = scalar(con, "SELECT count(*) FROM orders")
    for r in top.itertuples():
        orders_a = set(con.execute("SELECT order_id FROM order_lines WHERE sku_id = ?", [r.sku_a]).df().order_id)
        orders_b = set(con.execute("SELECT order_id FROM order_lines WHERE sku_id = ?", [r.sku_b]).df().order_id)
        both = len(orders_a & orders_b)
        assert r.together == both
        assert r.lift == pytest.approx((both / n) / ((len(orders_a) / n) * (len(orders_b) / n)), rel=1e-9)
        assert r.confidence_a_to_b == pytest.approx(both / len(orders_a), rel=1e-9)


def test_wastage_cover(con):
    sample = con.execute("SELECT * FROM wastage_node_sku USING SAMPLE 30 ROWS (reservoir, 9)").df()
    for r in sample.itertuples():
        d = con.execute("SELECT opening_on_hand, sold, wasted FROM inventory_daily WHERE node_id = ? AND sku_id = ?",
                        [r.node_id, r.sku_id]).df()
        assert r.units_wasted == d.wasted.sum()
        if d.sold.mean() > 0:
            assert r.days_of_cover == pytest.approx(d.opening_on_hand.mean() / d.sold.mean(), rel=1e-9)
