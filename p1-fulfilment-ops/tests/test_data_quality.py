"""Data-quality checks on the cleaned layer, and an independent recount of the raw issues."""
import numpy as np

from conftest import scalar


def test_dq_report_has_every_check(con):
    rows = con.execute("SELECT count(*), count(DISTINCT check_name) FROM dq_report").fetchone()
    assert rows[0] == rows[1] >= 12


def test_dq_report_counts_match_pandas(con):
    ev = con.execute("SELECT order_id, event_type, event_ts, rider_id FROM order_events").df()
    exact = len(ev) - len(ev.fillna({"rider_id": ""}).drop_duplicates())
    repeated = len(ev) - len(ev[["order_id", "event_type"]].drop_duplicates())
    first = ev.groupby(["order_id", "event_type"]).event_ts.min().unstack()
    skewed = int((first["delivered"] < first["placed"]).sum())
    report = dict(con.execute("SELECT check_name, failing_rows FROM dq_report").fetchall())
    assert report["exact duplicate events"] == exact
    assert report["repeated order/event-type rows (incl. jittered re-sends)"] == repeated
    assert report["delivered before placed"] == skewed


def test_events_clean_unique_and_repaired(con):
    assert scalar(con, """SELECT count(*) FROM (SELECT order_id, event_type FROM events_clean
                           GROUP BY ALL HAVING count(*) > 1)""") == 0
    assert scalar(con, """SELECT count(*) FROM events_clean
                           WHERE event_type IN ('rider_assigned','picked_up','delivered') AND rider_id IS NULL""") == 0


def test_one_timeline_row_per_order(con):
    assert scalar(con, "SELECT count(*) FROM order_timeline") == scalar(con, "SELECT count(*) FROM orders")
    assert scalar(con, "SELECT count(DISTINCT order_id) FROM order_timeline") == scalar(con, "SELECT count(*) FROM orders")


def test_valid_timelines_have_no_impossible_timestamps(con):
    bad = scalar(con, """
        SELECT count(*) FROM order_timeline WHERE timing_valid AND (
            delivered_ts < placed_ts OR picked_ts < placed_ts OR picked_up_ts < picked_ts
            OR delivered_ts < picked_up_ts OR pick_min < 0 OR rider_wait_min < 0 OR travel_min < 0
            OR node_id IS NULL OR placed_ts IS NULL OR delivery_min IS NULL)""")
    assert bad == 0


def test_stages_sum_to_delivery_time(con):
    gap = scalar(con, """SELECT max(abs(pick_min + rider_wait_min + travel_min - delivery_min))
                         FROM order_timeline WHERE timing_valid""")
    assert gap < 1e-6


def test_every_delivered_order_is_valid_or_explained(con):
    unexplained = scalar(con, """SELECT count(*) FROM order_timeline
                                 WHERE status = 'delivered' AND NOT timing_valid AND exclusion_reason IS NULL""")
    assert unexplained == 0
    excluded_share = scalar(con, """SELECT avg(CAST(NOT timing_valid AS DOUBLE)) FROM order_timeline
                                     WHERE status = 'delivered'""")
    assert excluded_share < 0.001


def test_within_sla_flag_matches_threshold(con, cfg):
    sla = cfg["ops"]["sla_minutes"]
    df = con.execute("SELECT delivery_min, within_sla FROM order_timeline WHERE timing_valid USING SAMPLE 20000 ROWS").df()
    assert np.array_equal(df.within_sla.values, (df.delivery_min <= sla).values)
