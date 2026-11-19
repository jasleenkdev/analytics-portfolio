"""Invariants of the raw synthetic experiment and pilot data."""
import shutil

import pytest

from conftest import PROJECT, scalar
from data_gen.generate import generate
from shared.db import connect


def test_row_counts(con, cfg):
    sim = cfg["sim"]
    assert scalar(con, "SELECT count(*) FROM users") == sim["users"]
    n_assigned = scalar(con, "SELECT count(*) FROM assignments")
    assert 0.95 * sim["users"] < n_assigned <= sim["users"]
    assert scalar(con, "SELECT count(*) FROM pilot_nodes") == sim["pilot_nodes"]
    assert scalar(con, "SELECT count(*) FROM pilot_rollout") == sim["pilot_treated"]
    days = sim["pilot_pre_days"] + sim["pilot_post_days"]
    rows = scalar(con, "SELECT count(*) FROM pilot_daily_ops")
    assert sim["pilot_nodes"] * days - 10 <= rows <= sim["pilot_nodes"] * days


def test_keys_unique(con):
    for table, key in [("users", "user_id"), ("assignments", "user_id"), ("orders", "order_id"),
                       ("pilot_nodes", "node_id"), ("pilot_daily_ops", "node_id, ops_date")]:
        assert scalar(con, f"SELECT count(*) - count(DISTINCT ({key})) FROM {table}") == 0, table


@pytest.mark.parametrize("child, col, parent, pcol", [
    ("assignments", "user_id", "users", "user_id"),
    ("orders", "user_id", "users", "user_id"),
    ("pilot_rollout", "node_id", "pilot_nodes", "node_id"),
    ("pilot_daily_ops", "node_id", "pilot_nodes", "node_id"),
])
def test_foreign_keys(con, child, col, parent, pcol):
    assert scalar(con, f"SELECT count(*) FROM {child} c WHERE NOT EXISTS (SELECT 1 FROM {parent} p WHERE p.{pcol} = c.{col})") == 0


def test_assignment_window_and_variants(con, cfg):
    sim = cfg["sim"]
    lo, hi = con.execute("SELECT min(assigned_at)::DATE, max(assigned_at)::DATE FROM assignments").fetchone()
    assert str(lo) == sim["experiment_start"]
    assert (hi - lo).days == sim["assignment_days"] - 1
    assert {r[0] for r in con.execute("SELECT DISTINCT variant FROM assignments").fetchall()} == {"control", "treatment"}


def test_order_values_valid(con, cfg):
    assert scalar(con, "SELECT count(*) FROM orders WHERE basket_value <= 0 OR items < 1 OR product_margin < 0") == 0
    fee = cfg["promo"]["delivery_fee"]
    assert scalar(con, f"SELECT count(*) FROM orders WHERE delivery_fee NOT IN (0, {fee})") == 0


def test_pilot_panel_valid(con):
    bad = scalar(con, """SELECT count(*) FROM pilot_daily_ops WHERE orders <= 0 OR rider_hours <= 0
                         OR orders_within_sla > orders OR defect_orders > orders OR delivery_min_sum <= 0""")
    assert bad == 0
    assert scalar(con, "SELECT count(DISTINCT start_date) FROM pilot_rollout") == 1


def test_generator_is_deterministic(tmp_path, con):
    (tmp_path / "data_gen").mkdir()
    shutil.copy(PROJECT / "config.toml", tmp_path / "config.toml")
    shutil.copy(PROJECT / "data_gen" / "plants.toml", tmp_path / "data_gen" / "plants.toml")
    fresh = connect(generate(tmp_path), read_only=True)
    sig = "SELECT count(*), sum(round(basket_value * 100)::BIGINT), sum(hash(order_id, user_id, order_ts) % 1000003) FROM orders"
    assert fresh.execute(sig).fetchone() == con.execute(sig).fetchone()
    fresh.close()
