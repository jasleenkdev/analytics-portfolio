"""Change-point significance (permutation test of the max-|t| scan) and before/after for detected nodes."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def scan(y: np.ndarray, min_seg: int) -> tuple[np.ndarray, np.ndarray]:
    """Welch t for every split k (before = y[:k], after = y[k:]) on each row of y (shape: series x days)."""
    y = np.atleast_2d(y)
    n = y.shape[1]
    ks = np.arange(min_seg, n - min_seg + 1)
    c1, c2 = np.cumsum(y, axis=1), np.cumsum(y ** 2, axis=1)
    tot1, tot2 = c1[:, -1:], c2[:, -1:]
    s1, q1 = c1[:, ks - 1], c2[:, ks - 1]
    n1, n2 = ks, n - ks
    m1, m2 = s1 / n1, (tot1 - s1) / n2
    v1 = (q1 - n1 * m1 ** 2) / (n1 - 1)
    v2 = ((tot2 - q1) - n2 * m2 ** 2) / (n2 - 1)
    return ks, (m2 - m1) / np.sqrt(v1 / n1 + v2 / n2)


def permutation_p(y: np.ndarray, min_seg: int, n_perm: int, rng: np.random.Generator) -> tuple[int, float, float]:
    """Best split, its t, and the share of day-shuffled series whose max |t| is at least as large."""
    ks, t = scan(y, min_seg)
    best = int(np.argmax(np.abs(t[0])))
    observed = abs(t[0, best])
    perms = np.array([rng.permutation(y) for _ in range(n_perm)])
    _, tp = scan(perms, min_seg)
    p = (1 + np.sum(np.max(np.abs(tp), axis=1) >= observed)) / (n_perm + 1)
    return int(ks[best]), float(t[0, best]), float(p)


def detect(con, cfg: dict) -> pd.DataFrame:
    a = cfg["analysis"]
    rng = np.random.default_rng(cfg["sim"]["seed"])
    gaps = con.execute("SELECT node_id, day_idx, order_date, pick_gap FROM node_daily_gap ORDER BY node_id, day_idx").df()
    net_median = con.execute("SELECT median(pick_min) FROM order_timeline WHERE timing_valid").fetchone()[0]
    rows = []
    for node, g in gaps.groupby("node_id", sort=True):
        y = g.pick_gap.to_numpy()
        k, t, p = permutation_p(y, a["change_min_segment_days"], a["n_permutations"], rng)
        shift = y[k:].mean() - y[:k].mean()
        rows.append({
            "node_id": node, "split_day_idx": int(g.day_idx.iloc[k]), "split_date": g.order_date.iloc[k],
            "welch_t": t, "p_value": p, "shift_min": shift, "shift_rel": shift / net_median,
            "detected": bool(p < a["change_p_value"] and abs(shift / net_median) >= a["change_min_effect"]),
        })
    return pd.DataFrame(rows)


def before_after(con, node: str, split_date) -> pd.DataFrame:
    """Difference-in-differences of daily node metrics against the rest of the network, with Welch 95% CIs."""
    d = con.execute("SELECT * FROM node_vs_rest_daily WHERE node_id = ? ORDER BY order_date", [node]).df()
    post = d.order_date >= pd.Timestamp(split_date)
    rows = []
    for metric in ["median_pick_min", "p90_delivery_min", "pct_within_sla"]:
        gap = d[metric] - d[f"rest_{metric}"]
        pre_g, post_g = gap[~post], gap[post]
        did = post_g.mean() - pre_g.mean()
        se = np.sqrt(pre_g.var(ddof=1) / len(pre_g) + post_g.var(ddof=1) / len(post_g))
        dof = se ** 4 / ((pre_g.var(ddof=1) / len(pre_g)) ** 2 / (len(pre_g) - 1)
                         + (post_g.var(ddof=1) / len(post_g)) ** 2 / (len(post_g) - 1))
        half = stats.t.ppf(0.975, dof) * se
        rows.append({
            "node_id": node, "metric": metric,
            "node_before": d.loc[~post, metric].mean(), "node_after": d.loc[post, metric].mean(),
            "rest_before": d.loc[~post, f"rest_{metric}"].mean(), "rest_after": d.loc[post, f"rest_{metric}"].mean(),
            "did": did, "ci_low": did - half, "ci_high": did + half,
            "days_before": int((~post).sum()), "days_after": int(post.sum()),
        })
    return pd.DataFrame(rows)


def run(con, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    cp = detect(con, cfg)
    frames = [before_after(con, r.node_id, r.split_date) for r in cp[cp.detected].itertuples()]
    ba = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["node_id", "metric", "node_before", "node_after", "rest_before", "rest_after",
                 "did", "ci_low", "ci_high", "days_before", "days_after"])
    for name, df in [("change_point_results", cp), ("before_after", ba)]:
        con.register("tmp_df", df)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM tmp_df")
        con.unregister("tmp_df")
    return cp, ba
