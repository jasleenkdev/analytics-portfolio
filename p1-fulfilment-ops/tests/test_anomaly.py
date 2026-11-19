"""Anomaly scoring, drill-down and change-point logic, recomputed independently."""
import numpy as np
import pandas as pd
import pytest

from analysis.change_points import permutation_p, scan
from conftest import scalar


@pytest.fixture(scope="module")
def cells(con, cfg):
    df = con.execute("SELECT * FROM node_hour_cells WHERE orders_timed >= ?",
                     [cfg["analysis"]["min_orders_per_cell"]]).df()
    df["is_weekend"] = pd.to_datetime(df.cell_date).dt.day_of_week >= 5
    return df


def test_peer_z_leave_one_out(con, cells):
    scores = con.execute("SELECT node_id, hour_ts, z_peer FROM anomaly_scores USING SAMPLE 300 ROWS (reservoir, 7)").df()
    for r in scores.itertuples():
        others = cells[(cells.hour_ts == r.hour_ts) & (cells.node_id != r.node_id)].mean_delivery_min
        me = cells[(cells.hour_ts == r.hour_ts) & (cells.node_id == r.node_id)].mean_delivery_min.iloc[0]
        expected = (me - others.mean()) / others.std(ddof=1) if len(others) >= 5 else None
        if expected is None:
            assert pd.isna(r.z_peer)
        else:
            assert r.z_peer == pytest.approx(expected, rel=1e-6)


def test_temporal_z_uses_only_past_same_hour_same_daytype(con, cells, cfg):
    window = cfg["analysis"]["rolling_window_obs"]
    scores = con.execute("SELECT node_id, hour_ts, z_temporal FROM anomaly_scores USING SAMPLE 300 ROWS (reservoir, 11)").df()
    for r in scores.itertuples():
        me = cells[(cells.node_id == r.node_id) & (cells.hour_ts == r.hour_ts)].iloc[0]
        hist = cells[(cells.node_id == r.node_id) & (cells.cell_hour == me.cell_hour)
                     & (cells.is_weekend == me.is_weekend) & (cells.hour_ts < r.hour_ts)].sort_values("hour_ts").tail(window)
        y = hist.mean_delivery_min
        scale = 1.4826 * np.median(np.abs(y - y.median())) if len(y) else 0
        if len(y) < 7 or scale == 0:
            assert pd.isna(r.z_temporal)
        else:
            assert r.z_temporal == pytest.approx((me.mean_delivery_min - y.median()) / scale, rel=1e-6)


def test_flags_respect_thresholds(con, cfg):
    a = cfg["analysis"]
    below = scalar(con, """SELECT count(*) FROM anomaly_flags
                           WHERE coalesce(z_temporal, -1e9) < ? AND coalesce(z_peer, -1e9) < ?""",
                   [a["robust_z_threshold"], a["zscore_threshold"]])
    assert below == 0
    missed = scalar(con, """SELECT count(*) FROM anomaly_scores s WHERE (z_temporal >= ? OR z_peer >= ?)
                            AND NOT EXISTS (SELECT 1 FROM anomaly_flags f WHERE f.node_id = s.node_id AND f.hour_ts = s.hour_ts)""",
                    [a["robust_z_threshold"], a["zscore_threshold"]])
    assert missed == 0


def test_drilldown_stage_excess_adds_up(con):
    df = con.execute("SELECT * FROM anomaly_drilldown").df()
    peer = df.flag_type == "peer"
    base = np.where(peer, df.peer_pick + df.peer_wait + df.peer_travel, df.hist_pick + df.hist_wait + df.hist_travel)
    total = df.pick_excess + df.wait_excess + df.travel_excess
    assert np.allclose(total, df.mean_delivery_min - base)
    winner = df[["pick_excess", "wait_excess", "travel_excess"]].idxmax(axis=1).map(
        {"pick_excess": "picking", "wait_excess": "rider wait", "travel_excess": "travel"})
    assert (winner == df.driver_stage).all()


def test_incidents_exclude_chronic_node_hours(con, cfg):
    # every incident's hour count equals its non-chronic flagged cells, so chronic hours never leak in
    mismatched = scalar(con, """
        WITH acute AS (
            SELECT d.node_id, d.cell_date, d.driver_stage, count(*) AS n FROM anomaly_drilldown d
            WHERE NOT EXISTS (SELECT 1 FROM anomaly_chronic c WHERE c.node_id = d.node_id AND c.cell_hour = d.cell_hour)
            GROUP BY ALL)
        SELECT count(*) FROM anomaly_incidents i JOIN acute a USING (node_id, cell_date, driver_stage)
        WHERE a.n <> i.flagged_hours""")
    assert mismatched == 0
    assert scalar(con, "SELECT min(flagged_hours) FROM anomaly_incidents") >= cfg["analysis"]["min_incident_hours"]


def test_python_scan_matches_sql_scan(con, cfg):
    sql_best = con.execute("SELECT node_id, split_day_idx, welch_t FROM change_point_best ORDER BY node_id").df()
    gaps = con.execute("SELECT node_id, day_idx, pick_gap FROM node_daily_gap ORDER BY node_id, day_idx").df()
    for r in sql_best.itertuples():
        g = gaps[gaps.node_id == r.node_id]
        ks, t = scan(g.pick_gap.to_numpy(), cfg["analysis"]["change_min_segment_days"])
        best = int(np.argmax(np.abs(t[0])))
        assert int(g.day_idx.iloc[ks[best]]) == r.split_day_idx
        assert t[0, best] == pytest.approx(r.welch_t, rel=1e-9)


def test_permutation_test_separates_step_from_noise():
    rng = np.random.default_rng(1)
    noise = rng.normal(0, 1, 90)
    step = noise + np.r_[np.zeros(50), np.full(40, -1.5)]
    k, t, p = permutation_p(step, 14, 500, rng)
    assert k == 50 and t < 0 and p < 0.01
    _, _, p_noise = permutation_p(noise, 14, 500, rng)
    assert p_noise > 0.05


def test_before_after_is_a_difference_in_differences(con):
    ba = con.execute("SELECT * FROM before_after").df()
    assert len(ba) > 0
    expected = (ba.node_after - ba.node_before) - (ba.rest_after - ba.rest_before)
    assert np.allclose(ba.did, expected)
    assert (ba.ci_low < ba.did).all() and (ba.did < ba.ci_high).all()
