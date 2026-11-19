"""Invariants of the raw synthetic customer, basket, funnel and inventory data."""
import shutil

import pytest

from conftest import PROJECT, scalar
from data_gen.generate import generate
from shared.db import connect


def test_row_counts(con, cfg):
    s = cfg["sim"]
    assert scalar(con, "SELECT count(*) FROM customers") == s["customers"]
    assert scalar(con, "SELECT count(*) FROM skus") == s["n_skus"]
    assert scalar(con, "SELECT count(*) FROM nodes") == s["n_nodes"]
    assert scalar(con, "SELECT count(DISTINCT category) FROM skus") == 15
    assert 1_300_000 < scalar(con, "SELECT count(*) FROM order_lines") < 1_800_000
    assert scalar(con, "SELECT count(*) FROM inventory_daily") == scalar(con, "SELECT count(*) FROM node_range") * s["days"]


def test_keys_unique(con):
    for table, key in [("customers", "customer_id"), ("skus", "sku_id"), ("orders", "order_id"), ("sessions", "session_id"),
                       ("order_lines", "order_id, line_no"), ("order_lines", "order_id, sku_id"),
                       ("node_range", "node_id, sku_id"), ("funnel_events", "session_id, step"),
                       ("inventory_daily", "node_id, sku_id, stock_date")]:
        assert scalar(con, f"SELECT count(*) - count(DISTINCT ({key})) FROM {table}") == 0, f"{table}({key})"


@pytest.mark.parametrize("child, col, parent, pcol", [
    ("orders", "customer_id", "customers", "customer_id"), ("orders", "session_id", "sessions", "session_id"),
    ("orders", "node_id", "nodes", "node_id"), ("order_lines", "order_id", "orders", "order_id"),
    ("order_lines", "sku_id", "skus", "sku_id"), ("sessions", "customer_id", "customers", "customer_id"),
    ("funnel_events", "session_id", "sessions", "session_id"), ("order_issues", "order_id", "orders", "order_id"),
    ("customers", "home_node_id", "nodes", "node_id"), ("node_range", "sku_id", "skus", "sku_id"),
])
def test_foreign_keys(con, child, col, parent, pcol):
    assert scalar(con, f"SELECT count(*) FROM {child} c WHERE NOT EXISTS (SELECT 1 FROM {parent} p WHERE p.{pcol} = c.{col})") == 0


def test_lines_only_for_ranged_skus(con):
    assert scalar(con, """SELECT count(*) FROM order_lines l JOIN orders o USING (order_id)
                          WHERE NOT EXISTS (SELECT 1 FROM node_range r WHERE r.node_id = o.node_id AND r.sku_id = l.sku_id)""") == 0


def test_orders_follow_signup_and_funnel(con):
    assert scalar(con, "SELECT count(*) FROM orders o JOIN customers c USING (customer_id) WHERE o.order_ts < c.signup_date") == 0
    assert scalar(con, """SELECT count(*) FROM orders o WHERE NOT EXISTS
                          (SELECT 1 FROM funnel_events f WHERE f.session_id = o.session_id AND f.step = 'order_placed')""") == 0
    # every session's steps are a prefix of the funnel: no step without the previous one
    gaps = scalar(con, """SELECT count(*) FROM (SELECT session_id, count(*) n, max(CASE step WHEN 'visit' THEN 1 WHEN 'browse' THEN 2
                          WHEN 'add_to_cart' THEN 3 WHEN 'checkout' THEN 4 WHEN 'payment_attempt' THEN 5 ELSE 6 END) top
                          FROM funnel_events GROUP BY 1) WHERE n <> top""")
    assert gaps == 0


def test_inventory_balances_and_is_never_negative(con):
    assert scalar(con, "SELECT min(least(opening_on_hand, closing_on_hand, received, sold, wasted, lost_sales)) FROM inventory_daily") >= 0
    assert scalar(con, "SELECT count(*) FROM inventory_daily WHERE closing_on_hand <> opening_on_hand - sold - wasted") == 0
    assert scalar(con, """SELECT count(*) FROM inventory_daily i JOIN skus s USING (sku_id)
                          WHERE NOT s.perishable AND i.wasted > 0""") == 0


def test_sales_match_basket_lines(con):
    # units sold plus lost sales in the stock ledger equal the units customers put in baskets
    ledger = scalar(con, "SELECT sum(sold + lost_sales) FROM inventory_daily")
    baskets = scalar(con, "SELECT sum(qty) FROM order_lines")
    assert ledger == baskets


def test_generator_is_deterministic(tmp_path, con):
    (tmp_path / "data_gen").mkdir()
    shutil.copy(PROJECT / "config.toml", tmp_path / "config.toml")
    shutil.copy(PROJECT / "data_gen" / "plants.toml", tmp_path / "data_gen" / "plants.toml")
    fresh = connect(generate(tmp_path), read_only=True)
    sig = "SELECT count(*), sum(qty), sum(hash(order_id, sku_id) % 1000003) FROM order_lines"
    assert fresh.execute(sig).fetchone() == con.execute(sig).fetchone()
    fresh.close()
