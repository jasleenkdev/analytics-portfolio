"""SQL KPIs versus an independent pandas recomputation from the raw tables on a sample of nodes."""
import numpy as np
import pandas as pd
import pytest

from conftest import scalar

SAMPLE_NODES = ["N01", "N06", "N11"]


@pytest.fixture(scope="module")
def timeline(con):
    """Rebuild the per-order timeline in pandas straight from the raw event feed."""
    ev = con.execute("""SELECT e.order_id, e.event_type, e.event_ts FROM order_events e JOIN orders o USING (order_id)
                        WHERE o.node_id IN (SELECT unnest(?))""", [SAMPLE_NODES]).df()
    first = ev.groupby(["order_id", "event_type"]).event_ts.min().unstack()
    orders = con.execute("SELECT * FROM orders WHERE node_id IN (SELECT unnest(?))", [SAMPLE_NODES]).df()
    t = orders.set_index("order_id").join(first)
    mins = lambda a, b: (t[b] - t[a]).dt.total_seconds() / 60  # noqa: E731
    t["delivery_min"] = mins("placed", "delivered")
    t["pick_min"] = mins("placed", "picked")
    t["wait_min"] = mins("picked", "picked_up")
    t["travel_min"] = mins("picked_up", "delivered")
    t["valid"] = (t.status == "delivered") & (t.delivered >= t.placed) & (t.picked >= t.placed) \
        & (t.picked_up >= t.picked) & (t.delivered >= t.picked_up)
    return t.reset_index()


def test_delivery_percentiles_and_sla(con, cfg, timeline):
    sql = con.execute("SELECT * FROM kpi_delivery_node WHERE node_id IN (SELECT unnest(?))", [SAMPLE_NODES]).df()
    for _, row in sql.iterrows():
        t = timeline[timeline.node_id == row.node_id]
        v = t[t.valid]
        assert row.orders_placed == len(t)
        assert row.orders_timed == len(v)
        assert row.p50_delivery_min == pytest.approx(np.percentile(v.delivery_min, 50), abs=1e-6)
        assert row.p90_delivery_min == pytest.approx(np.percentile(v.delivery_min, 90), abs=1e-6)
        assert row.pct_within_sla == pytest.approx((v.delivery_min <= cfg["ops"]["sla_minutes"]).mean(), abs=1e-12)
        assert row.cancel_rate == pytest.approx((t.status == "cancelled").mean(), abs=1e-12)


def test_network_rollup_equals_sum_of_nodes(con):
    total = con.execute("SELECT orders_placed, orders_within_sla FROM kpi_delivery_node WHERE node_id = 'ALL'").fetchone()
    parts = con.execute("""SELECT sum(orders_placed), sum(orders_within_sla) FROM kpi_delivery_node
                           WHERE node_id <> 'ALL'""").fetchone()
    assert total == parts


def test_delay_decomposition_adds_up(con, timeline):
    sql = con.execute("SELECT * FROM kpi_delay_decomposition_node WHERE node_id IN (SELECT unnest(?))", [SAMPLE_NODES]).df()
    for _, row in sql.iterrows():
        v = timeline[(timeline.node_id == row.node_id) & timeline.valid]
        assert row.mean_pick_min == pytest.approx(v.pick_min.mean(), rel=1e-9)
        assert row.mean_rider_wait_min == pytest.approx(v.wait_min.mean(), rel=1e-9)
        assert row.mean_travel_min == pytest.approx(v.travel_min.mean(), rel=1e-9)
        assert row.mean_pick_min + row.mean_rider_wait_min + row.mean_travel_min == pytest.approx(row.mean_delivery_min, rel=1e-9)
        assert row.late_share_picking + row.late_share_rider_wait + row.late_share_travel == pytest.approx(1.0)


def test_defect_rates(con):
    raw = con.execute("""SELECT o.node_id, d.defect_type, d.order_id, d.refund_amount FROM defects d
                         JOIN orders o USING (order_id) WHERE o.node_id IN (SELECT unnest(?))""", [SAMPLE_NODES]).df()
    delivered = con.execute("""SELECT node_id, count(*) AS n FROM orders WHERE status = 'delivered'
                               AND node_id IN (SELECT unnest(?)) GROUP BY 1""", [SAMPLE_NODES]).df().set_index("node_id").n
    expected = raw.groupby(["node_id", "defect_type"]).order_id.nunique() / delivered
    refunds = raw.groupby(["node_id", "defect_type"]).refund_amount.sum()
    sql = con.execute("SELECT * FROM kpi_defects_node WHERE node_id IN (SELECT unnest(?))", [SAMPLE_NODES]).df()
    for _, row in sql.iterrows():
        key = (row.node_id, row.defect_type)
        assert row.defect_rate == pytest.approx(expected.get(key, 0.0), abs=1e-12)
        assert row.refund_amount == pytest.approx(refunds.get(key, 0.0), abs=1e-6)


def test_fill_rate(con):
    raw = con.execute("""SELECT o.node_id, s.category, i.qty_ordered, i.qty_fulfilled FROM order_items i
                         JOIN orders o USING (order_id) JOIN skus s USING (sku_id)
                         WHERE o.status = 'delivered' AND o.node_id IN (SELECT unnest(?))""", [SAMPLE_NODES]).df()
    g = raw.groupby(["node_id", "category"])[["qty_ordered", "qty_fulfilled"]].sum()
    expected = g.qty_fulfilled / g.qty_ordered
    sql = con.execute("SELECT * FROM kpi_fill_node_category WHERE node_id IN (SELECT unnest(?))", [SAMPLE_NODES]).df()
    for _, row in sql.iterrows():
        assert row.fill_rate == pytest.approx(expected[(row.node_id, row.category)], abs=1e-12)


def test_stockout_rate_on_sample_node_skus(con, cfg):
    sample = con.execute("""SELECT node_id, sku_id, stockout_rate FROM kpi_stock_node_sku
                            ORDER BY hash(node_id || sku_id) LIMIT 40""").df()
    snap = con.execute("""SELECT node_id, sku_id, snapshot_ts, on_hand FROM inventory_snapshots
                          WHERE (node_id || sku_id) IN (SELECT unnest(?))""",
                       [list(sample.node_id + sample.sku_id)]).df()
    hour = (snap.snapshot_ts - pd.Timedelta(hours=1)).dt.hour
    op = snap[(hour >= cfg["sim"]["open_hour"]) & (hour <= cfg["sim"]["close_hour"])]
    expected = (op.on_hand == 0).groupby([op.node_id, op.sku_id]).mean()
    for _, row in sample.iterrows():
        assert row.stockout_rate == pytest.approx(expected[(row.node_id, row.sku_id)], abs=1e-12)


def test_orders_per_rider_hour(con):
    shifts = con.execute("SELECT node_id, shift_start, shift_end FROM rider_shifts").df()
    hours = ((shifts.shift_end - shifts.shift_start).dt.total_seconds() / 3600).groupby(shifts.node_id).sum()
    sql = con.execute("SELECT node_id, rider_hours, orders_delivered, orders_per_rider_hour FROM kpi_riders_node").df()
    for _, row in sql[sql.node_id.isin(SAMPLE_NODES)].iterrows():
        assert row.rider_hours == pytest.approx(hours[row.node_id])
        assert row.orders_per_rider_hour == pytest.approx(row.orders_delivered / hours[row.node_id])


def test_rates_are_bounded(con):
    for table, cols in [("kpi_delivery_node", ["pct_within_sla", "cancel_rate"]),
                        ("kpi_inventory_node", ["fill_rate", "stockout_rate"]),
                        ("kpi_defects_node", ["defect_rate"])]:
        for c in cols:
            lo, hi = con.execute(f"SELECT min({c}), max({c}) FROM {table}").fetchone()
            assert 0 <= lo <= hi <= 1, f"{table}.{c} out of [0, 1]"
    assert scalar(con, "SELECT min(utilisation) FROM kpi_riders_node") > 0
