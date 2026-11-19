"""Synthetic data for project 2: a user-level promotion A/B test and a node-level pilot panel.

Promotion test: users are randomised 50/50 on their first visit in the assignment week. Control keeps
free delivery from the current basket threshold; treatment gets a lower threshold. Users order as a
Poisson process with a personal rate; basket value, basket type (high-margin top-up vs standard) and
delivery fee follow from the policy each user faces. Planted effects (data_gen/plants.toml) change the
treatment response, the margin mix and the assignment log.

Pilot panel: daily operations for 24 nodes, 8 of them switch on rider batching halfway through. All
nodes share weekly seasonality, a trend and daily shocks, so a naive before/after would be biased.
"""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
ZONES = ["north", "south", "east", "west", "central"]


def _load(p: Path) -> dict:
    with open(p, "rb") as f:
        return tomllib.load(f)


def _orders(rng, users, days_from, days_to, rate_mult, policy_threshold, promo, hm_mult, bunch, start):
    """Draw orders for each user between day offsets [days_from, days_to) (arrays, per user)."""
    span = days_to - days_from
    n = rng.poisson(users.rate_per_day.values * span * rate_mult)
    uid = np.repeat(users.index.values, n)
    t = np.repeat(days_from, n) + rng.uniform(0, 1, n.sum()) * np.repeat(span, n)
    u = users.loc[uid]
    hm = rng.random(len(uid)) < u.hm_propensity.values * np.repeat(hm_mult, n)
    basket = u.basket_mean.values * rng.lognormal(0, 0.45, len(uid)) * np.where(hm, 0.7, 1.0)
    thr = np.repeat(policy_threshold, n)
    if bunch is not None:
        window, prob = bunch
        b_mask = np.repeat(users.bunch.values, n)
        near = b_mask & (basket < thr) & (basket >= thr - window) & (rng.random(len(uid)) < prob)
        basket = np.where(near, thr + rng.uniform(0, 4, len(uid)), basket)
    basket = np.round(np.maximum(basket, 4.0), 2)
    margin_rate = np.clip(np.where(hm, 0.36, 0.21) + rng.normal(0, 0.03, len(uid)), 0.05, 0.6)
    fee = np.where(basket >= thr, 0.0, promo["delivery_fee"])
    ts = start + pd.to_timedelta(np.round(t * 86400).astype("int64"), unit="s")
    return pd.DataFrame({
        "user_id": u.user_id.values, "order_ts": ts, "basket_value": basket,
        "items": np.maximum(1, np.round(basket / 4.2 + rng.normal(0, 1.2, len(uid)))).astype(int),
        "high_margin_basket": hm, "product_margin": np.round(basket * margin_rate, 2),
        "delivery_fee": fee, "delivery_cost": promo["delivery_cost"],
    })


def promo_test(rng, cfg, plants):
    sim, promo, pe = cfg["sim"], cfg["promo"], plants["promo_effect"]
    start = pd.Timestamp(sim["experiment_start"])
    n = sim["users"]
    users = pd.DataFrame({
        "user_id": [f"U{i:06d}" for i in range(1, n + 1)],
        "signup_date": start - pd.to_timedelta(np.minimum(rng.exponential(330, n), 1400).astype(int) + 1, unit="D"),
        "platform": rng.choice(["ios", "android", "web"], n, p=[0.45, 0.40, 0.15]),
        "zone": rng.choice(ZONES, n, p=[0.24, 0.18, 0.18, 0.22, 0.18]),
    })
    users["rate_per_day"] = rng.gamma(1.3, 0.75 / 1.3, n) / 7
    users["basket_mean"] = rng.lognormal(np.log(31), 0.35, n)
    users["hm_propensity"] = rng.beta(3, 7, n)
    users["is_new"] = (start - users.signup_date).dt.days < 90
    users["variant"] = np.where(rng.random(n) < 0.5, "treatment", "control")
    # first visit in the assignment week; most users arrive in the first days
    w = np.array([0.30, 0.20, 0.14, 0.11, 0.09, 0.08, 0.08])
    users["assign_day"] = rng.choice(sim["assignment_days"], n, p=w / w.sum())
    users["assigned_at"] = start + pd.to_timedelta(users.assign_day, unit="D") + pd.to_timedelta(rng.integers(6 * 3600, 23 * 3600, n), unit="s")
    users["bunch"] = users.variant.eq("treatment")
    treated = users.variant.eq("treatment").values

    # pre-period: everyone faces the control policy
    pre = _orders(rng, users, np.full(n, -sim["pre_period_days"]), np.zeros(n), 1.0,
                  np.full(n, promo["control_free_threshold"]), promo, np.ones(n), None, start)

    # experiment: three observation weeks from each user's assignment time
    a0 = users.assign_day.values + (users.assigned_at - users.assigned_at.dt.normalize()).dt.total_seconds().values / 86400
    frames = []
    for week, lift in enumerate(pe["order_lift_by_week"]):
        mult = 1 + treated * (lift + users.is_new.values * pe["new_user_extra_lift"])
        thr = np.where(treated, promo["treatment_free_threshold"], promo["control_free_threshold"])
        hm = np.where(treated, pe["high_margin_multiplier"], 1.0)
        frames.append(_orders(rng, users, a0 + 7 * week, a0 + 7 * (week + 1), mult, thr, promo, hm,
                              (pe["bunching_window"], pe["bunching_prob"]), start))
    exp = pd.concat(frames, ignore_index=True)
    orders = pd.concat([pre, exp], ignore_index=True).sort_values(["order_ts", "user_id"], ignore_index=True)
    orders.insert(0, "order_id", [f"O{i:07d}" for i in range(1, len(orders) + 1)])

    # assignment log with the planted logging bug on one day
    srm = plants["srm"]
    lost = (users.assign_day == srm["day"]) & users.variant.eq("control") & (rng.random(n) < srm["lost_control_share"])
    assignments = users.loc[~lost, ["user_id", "variant", "assigned_at"]].reset_index(drop=True)
    users_out = users[["user_id", "signup_date", "platform", "zone"]]
    return users_out, assignments, orders, int(lost.sum())


def pilot_panel(rng, cfg, plants):
    sim, pe = cfg["sim"], plants["pilot_effect"]
    n, days = sim["pilot_nodes"], sim["pilot_pre_days"] + sim["pilot_post_days"]
    start = pd.Timestamp(sim["pilot_start"])
    nodes = pd.DataFrame({"node_id": [f"N{i:02d}" for i in range(1, n + 1)],
                          "zone": rng.choice(ZONES, n),
                          "size": rng.uniform(250, 600, n).round(0)})
    treated_ids = rng.choice(nodes.node_id, sim["pilot_treated"], replace=False)
    nodes["pilot_group"] = np.where(nodes.node_id.isin(treated_ids), "treatment", "control")
    d = np.arange(days)
    season = 1 + 0.12 * np.isin((start.day_of_week + d) % 7, [4, 5]) - 0.05 * ((start.day_of_week + d) % 7 == 0)
    trend = 1 + 0.0015 * d
    shock = rng.normal(0, 0.04, days)       # shared across nodes, e.g. weather or marketing
    node_rmin = rng.normal(24, 1.5, n)      # rider minutes per order
    node_dmin = rng.normal(22, 1.2, n)
    node_def = rng.uniform(0.026, 0.038, n)
    node_sla = rng.uniform(0.86, 0.92, n)
    rows = []
    post = d >= sim["pilot_pre_days"]
    for i, nd in nodes.iterrows():
        tr = nd.pilot_group == "treatment"
        on = tr & post
        orders = rng.poisson(nd["size"] * season * trend * np.exp(shock))
        busy = 1 + 0.6 * (season * trend * np.exp(shock) - 1)    # busier days are slower everywhere
        rmin = node_rmin[i] * busy * (1 + pe["rider_min_per_order"] * on) * rng.lognormal(0, 0.03, days)
        dmin = node_dmin[i] * busy + pe["delivery_min"] * on + rng.normal(0, 0.6, days)
        dp = np.clip(node_def[i] * busy + pe["defect_rate_pp"] / 100 * on, 0.001, 0.2)
        sp = np.clip(node_sla[i] - 0.15 * (busy - 1) + pe["sla_pp"] / 100 * on, 0.5, 0.99)
        rows.append(pd.DataFrame({
            "node_id": nd.node_id, "ops_date": start + pd.to_timedelta(d, unit="D"), "orders": orders,
            "rider_hours": np.round(orders * rmin / 60, 1),
            "delivery_min_sum": np.round(orders * dmin, 1),
            "orders_within_sla": rng.binomial(orders, sp),
            "defect_orders": rng.binomial(orders, dp),
        }))
    panel = pd.concat(rows, ignore_index=True)
    gaps = rng.choice(nodes.node_id[nodes.pilot_group == "control"], plants["pilot_data_quality"]["control_nodes_with_gaps"], replace=False)
    gap_days = start + pd.to_timedelta(plants["pilot_data_quality"]["missing_days"], unit="D")
    panel = panel[~(panel.node_id.isin(gaps) & panel.ops_date.isin(gap_days))].reset_index(drop=True)
    pilot = pd.DataFrame({"node_id": treated_ids, "pilot": "rider_batching",
                          "start_date": start + pd.Timedelta(days=sim["pilot_pre_days"])}).sort_values("node_id")
    return nodes[["node_id", "zone", "pilot_group"]], pilot, panel, sorted(gaps.tolist())


def generate(project_dir: Path = PROJECT) -> Path:
    cfg = _load(project_dir / "config.toml")
    plants = _load(project_dir / "data_gen" / "plants.toml")
    rng = np.random.default_rng(cfg["sim"]["seed"])
    users, assignments, orders, lost = promo_test(rng, cfg, plants)
    nodes, pilot, panel, gaps = pilot_panel(rng, cfg, plants)
    data = project_dir / "data"
    data.mkdir(exist_ok=True)
    db = data / "experiments.duckdb"
    db.unlink(missing_ok=True)
    con = duckdb.connect(str(db))
    tables = {"users": users, "assignments": assignments, "orders": orders,
              "pilot_nodes": nodes, "pilot_rollout": pilot, "pilot_daily_ops": panel}
    for name, df in tables.items():
        con.register("tmp_df", df)
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM tmp_df")
        con.unregister("tmp_df")
    con.close()
    (data / "planted_entities.json").write_text(json.dumps({
        "lost_control_assignments": lost, "pilot_treated_nodes": sorted(pilot.node_id.tolist()),
        "pilot_nodes_with_gaps": gaps}, indent=2))
    for name, df in tables.items():
        print(f"  {name:18s} {len(df):>10,d} rows")
    return db


if __name__ == "__main__":
    generate()
