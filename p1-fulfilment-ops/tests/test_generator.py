"""Invariants of the raw synthetic data (before any cleaning)."""
import shutil

import pytest

from conftest import scalar
from data_gen.generate import generate


def test_row_counts(con, cfg):
    sim = cfg["sim"]
    assert scalar(con, "SELECT count(*) FROM nodes") == sim["n_nodes"]
    assert scalar(con, "SELECT count(*) FROM skus") == sim["n_skus"]
    orders = scalar(con, "SELECT count(*) FROM orders")
    assert abs(orders / sim["target_orders"] - 1) < 0.02
    assert scalar(con, "SELECT count(*) FROM order_items") > 2 * orders
    tracked = scalar(con, "SELECT count(*) FROM skus WHERE inventory_tracked")
    assert tracked == sim["tracked_skus"]
    assert scalar(con, "SELECT count(*) FROM inventory_snapshots") == sim["n_nodes"] * tracked * sim["days"] * 24


def test_primary_keys_unique(con):
    for table, key in [("nodes", "node_id"), ("skus", "sku_id"), ("riders", "rider_id"), ("orders", "order_id"),
                       ("order_events", "event_id"), ("defects", "defect_id"),
                       ("order_items", "order_id, line_no"), ("inventory_snapshots", "node_id, sku_id, snapshot_ts")]:
        dupes = scalar(con, f"SELECT count(*) - count(DISTINCT ({key})) FROM {table}")
        assert dupes == 0, f"{table} has duplicate {key}"


@pytest.mark.parametrize("child, col, parent, pcol", [
    ("orders", "node_id", "nodes", "node_id"),
    ("order_items", "order_id", "orders", "order_id"),
    ("order_items", "sku_id", "skus", "sku_id"),
    ("order_events", "order_id", "orders", "order_id"),
    ("order_events", "rider_id", "riders", "rider_id"),
    ("rider_shifts", "rider_id", "riders", "rider_id"),
    ("rider_shifts", "node_id", "nodes", "node_id"),
    ("riders", "home_node_id", "nodes", "node_id"),
    ("picker_roster", "node_id", "nodes", "node_id"),
    ("inventory_snapshots", "node_id", "nodes", "node_id"),
    ("inventory_snapshots", "sku_id", "skus", "sku_id"),
    ("defects", "order_id", "orders", "order_id"),
    ("defects", "sku_id", "skus", "sku_id"),
])
def test_foreign_keys(con, child, col, parent, pcol):
    orphans = scalar(con, f"""
        SELECT count(*) FROM {child} c
        WHERE c.{col} IS NOT NULL AND NOT EXISTS (SELECT 1 FROM {parent} p WHERE p.{pcol} = c.{col})""")
    assert orphans == 0


def test_no_negative_stock_and_valid_quantities(con):
    assert scalar(con, "SELECT min(on_hand) FROM inventory_snapshots") >= 0
    assert scalar(con, "SELECT count(*) FROM order_items WHERE qty_fulfilled < 0 OR qty_fulfilled > qty_ordered") == 0
    assert scalar(con, "SELECT count(*) FROM order_items WHERE qty_ordered <= 0 OR unit_price <= 0") == 0


def test_inventory_only_for_tracked_skus(con):
    assert scalar(con, """SELECT count(*) FROM inventory_snapshots i JOIN skus s USING (sku_id)
                           WHERE NOT s.inventory_tracked""") == 0


def test_event_lifecycle(con):
    # delivered orders carry the full lifecycle, cancelled orders never reach the customer
    missing = scalar(con, """
        SELECT count(*) FROM orders o WHERE status = 'delivered' AND (
          SELECT count(DISTINCT event_type) FROM order_events e
          WHERE e.order_id = o.order_id AND event_type IN ('placed','picked','rider_assigned','picked_up','delivered')) < 5""")
    assert missing == 0
    assert scalar(con, """SELECT count(*) FROM order_events e JOIN orders o USING (order_id)
                           WHERE o.status = 'cancelled' AND e.event_type IN ('picked_up', 'delivered')""") == 0


def test_delivery_before_order_is_rare_in_raw_data(con):
    # the raw feed has some clock-skewed rows (cleaned in sql/); they must stay a tiny minority
    bad = scalar(con, """
        SELECT count(DISTINCT d.order_id) FROM order_events d JOIN orders o USING (order_id)
        WHERE d.event_type = 'delivered' AND d.event_ts < o.created_at""")
    delivered = scalar(con, "SELECT count(*) FROM orders WHERE status = 'delivered'")
    assert 0 < bad / delivered < 0.001


def test_timestamps_inside_window(con, cfg):
    start = cfg["sim"]["start_date"]
    out = scalar(con, f"""
        SELECT count(*) FROM orders
        WHERE created_at < DATE '{start}' OR created_at >= DATE '{start}' + INTERVAL {cfg['sim']['days']} DAY""")
    assert out == 0
    hours = con.execute("SELECT min(hour(created_at)), max(hour(created_at)) FROM orders").fetchone()
    assert hours == (cfg["sim"]["open_hour"], cfg["sim"]["close_hour"])


def test_generator_is_deterministic(tmp_path, con):
    project = tmp_path / "p"
    (project / "data_gen").mkdir(parents=True)
    from conftest import PROJECT
    shutil.copy(PROJECT / "config.toml", project / "config.toml")
    shutil.copy(PROJECT / "data_gen" / "plants.toml", project / "data_gen" / "plants.toml")
    db = generate(project)
    from shared.db import connect
    fresh = connect(db, read_only=True)
    sig = "SELECT count(*), sum(round(order_value * 100)::BIGINT), sum(hash(order_id, node_id, created_at) % 1000003) FROM orders"
    assert fresh.execute(sig).fetchone() == con.execute(sig).fetchone()
    fresh.close()
