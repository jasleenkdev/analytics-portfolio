"""Synthetic fulfilment and delivery data for project 1.

The simulation is driven by load, not by labels: picking slows down when orders per
rostered picker rise, rider wait grows when orders per online rider rise, travel slows in
rain, and items go missing when on-hand stock runs out. Planted effects (data_gen/plants.toml)
change the inputs to those mechanisms (rosters, rider supply, replenishment levels, process
work content) so that their symptoms emerge in the data the same way real problems would.
"""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent

ZONES = {"north": 3, "south": 2, "east": 2, "west": 3, "central": 2}

# category: (share of SKUs, perishable, shelf-life range in days, price median, gross margin)
CATEGORIES = {
    "produce": (0.12, True, (4, 10), 2.2, 0.38),
    "dairy": (0.09, True, (7, 21), 2.6, 0.30),
    "bakery": (0.06, True, (2, 5), 2.4, 0.45),
    "meat_fish": (0.07, True, (3, 7), 6.5, 0.28),
    "frozen": (0.07, False, (120, 365), 4.0, 0.33),
    "beverages": (0.10, False, (180, 540), 2.0, 0.35),
    "snacks": (0.11, False, (90, 270), 2.3, 0.42),
    "pantry": (0.13, False, (180, 720), 2.8, 0.30),
    "household": (0.08, False, (365, 1095), 4.5, 0.36),
    "personal_care": (0.08, False, (365, 1095), 5.0, 0.44),
    "baby": (0.04, False, (180, 720), 8.0, 0.25),
    "pet": (0.05, False, (180, 720), 6.0, 0.32),
}

# relative demand by operating hour 07..23; weekends are flatter with a later start
WEEKDAY_CURVE = np.array([25, 35, 45, 50, 62, 85, 78, 52, 45, 50, 62, 88, 100, 94, 70, 45, 25], float)
WEEKEND_CURVE = np.array([12, 25, 42, 58, 72, 82, 80, 66, 58, 60, 70, 86, 96, 90, 72, 50, 30], float)


def _load(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def _queue_factor(rho: np.ndarray, target: float, cap: float) -> np.ndarray:
    """Waiting multiplier that is 1 at the target utilisation and explodes towards saturation."""
    return (1 - target) / (1 - np.minimum(rho, cap))


def build_nodes(rng):
    rows, i = [], 1
    for zone, n in ZONES.items():
        for _ in range(n):
            rows.append({
                "node_id": f"N{i:02d}",
                "zone": zone,
                "size_factor": round(float(rng.uniform(0.75, 1.3)), 3),
                "mean_distance_km": round(float(rng.uniform(2.4, 3.8)), 2),
            })
            i += 1
    nodes = pd.DataFrame(rows)
    return nodes


def build_skus(rng, n_skus, plants):
    names = list(CATEGORIES)
    shares = np.array([CATEGORIES[c][0] for c in names])
    counts = np.floor(shares / shares.sum() * n_skus).astype(int)
    counts[np.argmax(counts)] += n_skus - counts.sum()
    cat = np.repeat(names, counts)
    perishable = np.array([CATEGORIES[c][1] for c in cat])
    lo = np.array([CATEGORIES[c][2][0] for c in cat])
    hi = np.array([CATEGORIES[c][2][1] for c in cat])
    shelf = rng.integers(lo, hi + 1)
    price = np.round(np.array([CATEGORIES[c][3] for c in cat]) * rng.lognormal(0, 0.35, n_skus), 2)
    margin = np.clip(np.array([CATEGORIES[c][4] for c in cat]) + rng.normal(0, 0.05, n_skus), 0.08, 0.65)
    popularity = rng.lognormal(0, 1.1, n_skus)
    skus = pd.DataFrame({
        "sku_id": [f"S{i:04d}" for i in range(1, n_skus + 1)],
        "category": cat,
        "perishable": perishable,
        "shelf_life_days": shelf,
        "price": price,
        "unit_cost": np.round(price * (1 - margin), 2),
        "popularity": popularity,
    })
    # the planted cluster is made of the category's fastest movers so they sit in the tracked subset
    cl = plants["stockout_cluster"]
    idx = skus.index[skus.category == cl["category"]]
    top = skus.loc[idx].sort_values("popularity", ascending=False).index[: cl["n_skus"]]
    skus.loc[top, "popularity"] = np.maximum(skus.loc[top, "popularity"], np.quantile(popularity, 0.97))
    return skus


def build_weather(rng, days, start, plants):
    zones = list(ZONES)
    hours = days * 24
    cond = np.zeros((len(zones), hours), dtype=int)  # 0 clear, 1 rain, 2 storm
    for z in range(len(zones)):
        state = 0
        for h in range(hours):
            # two-state Markov chain gives multi-hour rain spells
            state = int(rng.random() < (0.85 if state else 0.025))
            cond[z, h] = state
    st = plants["storm"]
    for z, zone in enumerate(zones):
        if zone in st["zones"]:
            for d in range(st["start_day"], st["start_day"] + st["days"]):
                cond[z, d * 24 + st["first_hour"]: d * 24 + 24] = 2
    precip = np.where(cond == 0, 0.0, np.where(cond == 1, rng.gamma(2, 1.2, cond.shape), rng.gamma(6, 2.0, cond.shape)))
    ts = pd.date_range(start, periods=hours, freq="h")
    weather = pd.DataFrame({
        "zone": np.repeat(zones, hours),
        "hour_ts": np.tile(ts, len(zones)),
        "condition": np.array(["clear", "rain", "storm"])[cond.ravel()],
        "precip_mm": np.round(precip.ravel(), 1),
    })
    return weather, {z: cond[i] for i, z in enumerate(zones)}


def generate(project_dir: Path = PROJECT) -> Path:
    cfg = _load(project_dir / "config.toml")
    plants = _load(project_dir / "data_gen" / "plants.toml")
    sim, ops = cfg["sim"], cfg["ops"]
    rng = np.random.default_rng(sim["seed"])
    start = pd.Timestamp(sim["start_date"])
    days, open_h, close_h = sim["days"], sim["open_hour"], sim["close_hour"]
    op_hours = np.arange(open_h, close_h + 1)

    nodes = build_nodes(rng)
    skus = build_skus(rng, sim["n_skus"], plants)
    weather, cond_by_zone = build_weather(rng, days, start, plants)
    n_nodes = len(nodes)

    # ---- demand: expected orders per node x day x operating hour -------------------------
    dow = (start.day_of_week + np.arange(days)) % 7
    weekend = dow >= 5
    curve = np.where(weekend[:, None], WEEKEND_CURVE / WEEKEND_CURVE.sum() * 1.12, WEEKDAY_CURVE / WEEKDAY_CURVE.sum())
    trend = 1 + 0.0012 * np.arange(days)
    zone_cond = np.stack([cond_by_zone[z] for z in nodes.zone])          # node x hour-of-sim
    cond_ndh = zone_cond.reshape(n_nodes, days, 24)[:, :, op_hours]       # node x day x op-hour
    weather_mult = np.select([cond_ndh == 1, cond_ndh == 2], [1.12, plants["storm"]["demand_multiplier"]], 1.0)
    lam = nodes.size_factor.values[:, None, None] * (curve * trend[:, None])[None] * weather_mult
    lam *= sim["target_orders"] / lam.sum()
    counts = rng.poisson(lam)

    # ---- staffing: pickers rostered from a weather-aware forecast ------------------------
    items_mean = 3.6
    work_mean = 2.5 + 0.7 * items_mean
    pickers = np.maximum(2, np.ceil(lam * work_mean / (60 * ops["picker_target_utilisation"])))
    us = plants["understaffing"]
    us_node = int(nodes.index[nodes.node_id == us["node_id"]][0])
    us_cols = [h - open_h for h in us["hours"]]
    pickers[us_node][:, us_cols] = np.maximum(1, np.round(pickers[us_node][:, us_cols] * us["picker_ratio"]))

    # ---- riders: shifts cover the forecast; storms cause log-off ------------------------
    # rider busy time per order: waiting at the node (~8 min) plus the delivery leg and the return leg
    trip_mean = 2 * (nodes.mean_distance_km.values * 1.1 / 20 * 60 + 2) + 8
    req = np.ceil(lam * trip_mean[:, None, None] / (60 * ops["rider_target_utilisation"])).astype(int)
    shift_len = 5
    st = plants["storm"]
    shift_rows, rider_rows = [], []
    riders_online = np.zeros_like(counts)
    rider_counter = 1
    for n in range(n_nodes):
        need_max = 0
        node_shifts = []
        for d in range(days):
            active = np.zeros(len(op_hours) + shift_len, int)
            starts = []
            for h in range(len(op_hours)):
                while active[h] < req[n, d, h]:
                    length = min(shift_len, len(op_hours) - h)
                    active[h:h + length] += 1
                    starts.append((h, length))
            need_max = max(need_max, len(starts))
            node_shifts.append(starts)
        pool = [f"R{rider_counter + k:04d}" for k in range(int(np.ceil(need_max * 1.4)))]
        rider_counter += len(pool)
        for rid in pool:
            rider_rows.append({"rider_id": rid, "home_node_id": nodes.node_id[n],
                               "vehicle": rng.choice(["bike", "e-bike", "scooter"], p=[0.25, 0.45, 0.30])})
        storm_node = nodes.zone[n] in st["zones"]
        for d, starts in enumerate(node_shifts):
            chosen = rng.choice(pool, size=len(starts), replace=False)
            for (h, length), rid in zip(starts, chosen):
                in_storm = storm_node and st["start_day"] <= d < st["start_day"] + st["days"] and op_hours[h] + length > st["first_hour"]
                drop_p = st["rider_dropout"] if in_storm else 0.03
                if rng.random() < drop_p:
                    continue
                riders_online[n, d, h:h + length] += 1
                s_ts = start + pd.Timedelta(days=d, hours=int(op_hours[h]))
                shift_rows.append({"rider_id": rid, "node_id": nodes.node_id[n],
                                   "shift_start": s_ts, "shift_end": s_ts + pd.Timedelta(hours=length)})
    riders = pd.DataFrame(rider_rows)
    rider_shifts = pd.DataFrame(shift_rows)

    # ---- orders -----------------------------------------------------------------------------
    flat = counts.ravel()
    cell = np.repeat(np.arange(flat.size), flat)
    n_idx, d_idx, h_idx = np.unravel_index(cell, counts.shape)
    n_orders = cell.size
    minute = rng.integers(0, 3600, n_orders) / 60  # whole seconds, so rounding never spills into the next hour
    placed_min = d_idx * 1440 + op_hours[h_idx] * 60 + minute
    order_sort = np.argsort(placed_min, kind="stable")
    n_idx, d_idx, h_idx, placed_min, cell = (a[order_sort] for a in (n_idx, d_idx, h_idx, placed_min, cell))
    n_items = 1 + rng.poisson(items_mean - 1, n_orders)

    # picking: work content x noise x queueing at the node-hour's picker load
    work = 2.5 + 0.7 * n_items
    pc = plants["process_change"]
    pc_node = int(nodes.index[nodes.node_id == pc["node_id"]][0])
    pc_mask = n_idx == pc_node
    work[pc_mask] *= np.where(d_idx[pc_mask] < pc["change_day"], pc["work_before"], pc["work_after"])
    workload = np.bincount(cell, weights=work, minlength=flat.size).reshape(counts.shape)
    rho_pick = workload / (pickers * 60)
    g_pick = _queue_factor(rho_pick, ops["picker_target_utilisation"], 0.93)
    pick_min = work * rng.lognormal(0, 0.3, n_orders) * (0.6 + 0.4 * g_pick[n_idx, d_idx, h_idx])

    # rider wait: queueing on orders per online rider
    rho_rider = counts * trip_mean[:, None, None] / (np.maximum(riders_online, 1) * 60)
    g_rider = _queue_factor(rho_rider, ops["rider_target_utilisation"], 0.95)
    gr = g_rider[n_idx, d_idx, h_idx]
    wait_min = rng.lognormal(np.log(2.5), 0.5, n_orders) * (0.4 + 0.6 * gr)
    assign_min = np.minimum(rng.uniform(0.3, 1.5, n_orders) * (0.5 + 0.5 * gr), pick_min + wait_min - 0.2)

    # travel: distance / speed, slower in rain and storms
    c = cond_ndh[n_idx, d_idx, h_idx]
    dist = rng.gamma(3, nodes.mean_distance_km.values[n_idx] / 3)
    speed = rng.lognormal(np.log(20), 0.2, n_orders) * np.select([c == 1, c == 2], [0.85, st["speed_multiplier"]], 1.0)
    travel_min = dist / speed * 60 + 2

    # cancellations: a small base rate at placement plus impatience when the order waits long
    long_wait = (pick_min + wait_min) > 35
    cancel_early = rng.random(n_orders) < 0.006
    cancel_wait = ~cancel_early & long_wait & (rng.random(n_orders) < 0.25)
    delivered = ~(cancel_early | cancel_wait)

    order_ids = np.arange(1, n_orders + 1)
    to_ts = lambda m: start + pd.to_timedelta(np.round(m * 60).astype("int64"), unit="s")  # noqa: E731
    picked_m = placed_min + pick_min
    assigned_m = placed_min + assign_min
    pickedup_m = picked_m + wait_min
    delivered_m = pickedup_m + travel_min

    # rider for each order: a random rider online at that node-hour (fallback: any home rider)
    shift_key = rider_shifts.assign(
        n=rider_shifts.node_id.map({v: i for i, v in enumerate(nodes.node_id)}),
        d=(rider_shifts.shift_start - start).dt.days,
        h0=rider_shifts.shift_start.dt.hour - open_h,
        h1=rider_shifts.shift_end.dt.hour - open_h,
    )
    online = {}
    for r in shift_key.itertuples():
        for h in range(r.h0, r.h1):
            online.setdefault((r.n, r.d, h), []).append(r.rider_id)
    home = riders.groupby("home_node_id").rider_id.apply(list).to_dict()
    u = rng.random(n_orders)
    rider_of = np.empty(n_orders, dtype=object)
    for i in range(n_orders):
        cands = online.get((n_idx[i], d_idx[i], h_idx[i])) or home[nodes.node_id[n_idx[i]]]
        rider_of[i] = cands[int(u[i] * len(cands))]

    # ---- order lines and stock-driven fulfilment ------------------------------------------
    line_order = np.repeat(np.arange(n_orders), n_items)
    p = skus.popularity.values / skus.popularity.sum()
    line_sku = rng.choice(len(skus), size=line_order.size, p=p)
    qty = 1 + rng.binomial(2, 0.2, line_order.size)
    lines = pd.DataFrame({"o": line_order, "sku": line_sku, "qty": qty,
                          "node": n_idx[line_order], "day": d_idx[line_order], "t": placed_min[line_order]})
    tracked = np.argsort(-skus.popularity.values)[: sim["tracked_skus"]]
    # cancelled orders are never picked, so only delivered orders draw down stock
    is_tracked = np.isin(lines.sku.values, tracked) & delivered[lines.o.values]

    # tracked node-SKUs: replenished to an order-up-to level S every morning before opening
    daily = lines[is_tracked].groupby(["node", "sku"]).qty.sum() / days
    cl = plants["stockout_cluster"]
    cl_nodes = set(nodes.index[nodes.node_id.isin(cl["node_ids"])])
    cl_skus = set(skus.loc[skus.category == cl["category"], "popularity"].nlargest(cl["n_skus"]).index)
    cover = pd.Series(1.6, index=daily.index)
    hit = [(n in cl_nodes and s in cl_skus) for n, s in daily.index]
    cover[hit] = cl["cover_ratio"]
    S = np.ceil(daily * cover + 2 * np.sqrt(daily) * (cover > 1)).rename("S")

    tl = lines[is_tracked].sort_values(["node", "sku", "day", "t"]).join(S, on=["node", "sku"])
    cum = tl.groupby(["node", "sku", "day"]).qty.cumsum()
    before = cum - tl.qty
    tl["filled"] = np.clip(tl.S - before, 0, tl.qty).astype(int)
    filled = np.where(rng.random(len(lines)) < 0.006, 0, lines.qty.values)  # untracked: random shorts
    filled = pd.Series(filled, index=lines.index)
    filled.loc[tl.index] = tl.filled
    filled[~delivered[lines.o.values]] = 0
    lines["filled"] = filled.values

    # hourly snapshots for tracked node-SKUs: on-hand at the end of each hour, reset at 06:00
    sold = (tl.assign(hour=((tl.t // 60) % 24).astype(int))
            .groupby(["node", "sku", "day", "hour"]).filled.sum())
    idx = pd.MultiIndex.from_product([range(n_nodes), tracked, range(days), range(24)], names=["node", "sku", "day", "hour"])
    snap = sold.reindex(idx, fill_value=0).reset_index(name="sold")
    snap = snap.join(S, on=["node", "sku"])
    snap["S"] = snap.S.fillna(0)
    snap["after_reset"] = snap.hour >= 6
    snap["cum_sold"] = snap.groupby(["node", "sku", "day"]).sold.cumsum()
    snap["on_hand"] = np.where(snap.after_reset, snap.S - snap.cum_sold, 0).astype(int)
    # stock left at day end carries over into the night; receipts top it up to S at 06:00
    prev_close = snap[snap.hour == 23].set_index(["node", "sku", "day"]).on_hand
    carry = prev_close.groupby(level=[0, 1]).shift(1).reindex(pd.MultiIndex.from_frame(snap[["node", "sku", "day"]])).fillna(0).values
    snap["on_hand"] = np.where(snap.after_reset, snap.on_hand, carry).astype(int)
    snap["received"] = np.where(snap.hour == 6, snap.S - carry, 0).astype(int)
    inventory = pd.DataFrame({
        "node_id": nodes.node_id.values[snap.node.values],
        "sku_id": skus.sku_id.values[snap.sku.values],
        "snapshot_ts": start + pd.to_timedelta(snap.day * 24 + snap.hour + 1, unit="h"),
        "on_hand": snap.on_hand.values,
        "received_qty": snap.received.values,
    })

    order_items = pd.DataFrame({
        "order_id": order_ids[lines.o.values],
        "line_no": lines.groupby("o").cumcount().values + 1,
        "sku_id": skus.sku_id.values[lines.sku.values],
        "qty_ordered": lines.qty.values,
        "qty_fulfilled": lines.filled.values,
        "unit_price": skus.price.values[lines.sku.values],
    })
    value = np.bincount(lines.o, weights=lines.qty * skus.price.values[lines.sku.values], minlength=n_orders)

    orders = pd.DataFrame({
        "order_id": order_ids,
        "node_id": nodes.node_id.values[n_idx],
        "customer_id": rng.integers(1, sim["customers"] + 1, n_orders),
        "created_at": to_ts(placed_min),
        "n_lines": n_items,
        "order_value": np.round(value, 2),
        "distance_km": np.round(dist, 2),
        "status": np.where(delivered, "delivered", "cancelled"),
    })

    # ---- events ----------------------------------------------------------------------------
    ev = [pd.DataFrame({"order_id": order_ids, "event_type": "placed", "event_ts": to_ts(placed_min), "rider_id": None})]
    picked_mask = delivered | cancel_wait
    ev.append(pd.DataFrame({"order_id": order_ids[picked_mask], "event_type": "picked",
                            "event_ts": to_ts(picked_m[picked_mask]), "rider_id": None}))
    ev.append(pd.DataFrame({"order_id": order_ids[picked_mask], "event_type": "rider_assigned",
                            "event_ts": to_ts(assigned_m[picked_mask]), "rider_id": rider_of[picked_mask]}))
    ev.append(pd.DataFrame({"order_id": order_ids[delivered], "event_type": "picked_up",
                            "event_ts": to_ts(pickedup_m[delivered]), "rider_id": rider_of[delivered]}))
    ev.append(pd.DataFrame({"order_id": order_ids[delivered], "event_type": "delivered",
                            "event_ts": to_ts(delivered_m[delivered]), "rider_id": rider_of[delivered]}))
    cancel_m = np.where(cancel_early, placed_min + rng.uniform(1, 5, n_orders), placed_min + 35 + rng.uniform(0, 5, n_orders))
    cancelled = ~delivered
    ev.append(pd.DataFrame({"order_id": order_ids[cancelled], "event_type": "cancelled",
                            "event_ts": to_ts(cancel_m[cancelled]), "rider_id": None}))
    events = pd.concat(ev, ignore_index=True)

    # ---- defects ---------------------------------------------------------------------------
    total_min = pick_min + wait_min + travel_min
    late = delivered & (total_min > ops["sla_minutes"]) & (rng.random(n_orders) < 0.30)
    rho_cell = rho_pick[n_idx, d_idx, h_idx]
    wrong = delivered & (rng.random(n_orders) < 0.004 * (1 + 3 * np.clip(rho_cell - 0.7, 0, None)))
    damaged = delivered & (rng.random(n_orders) < 0.003 * np.select([c == 1, c == 2], [1.8, 2.5], 1.0))
    report_ts = lambda m: to_ts(delivered_m[m] + rng.uniform(5, 180, m.sum()))  # noqa: E731
    d_rows = [
        pd.DataFrame({"order_id": order_ids[late], "defect_type": "late", "sku_id": None,
                      "refund_amount": np.round(np.minimum(value[late] * 0.15, 6.0), 2), "reported_ts": report_ts(late)}),
        pd.DataFrame({"order_id": order_ids[wrong], "defect_type": "wrong_item", "sku_id": None,
                      "refund_amount": np.round(value[wrong] * rng.uniform(0.1, 0.3, wrong.sum()), 2), "reported_ts": report_ts(wrong)}),
        pd.DataFrame({"order_id": order_ids[damaged], "defect_type": "damaged", "sku_id": None,
                      "refund_amount": np.round(value[damaged] * rng.uniform(0.05, 0.25, damaged.sum()), 2), "reported_ts": report_ts(damaged)}),
    ]
    short = order_items[(order_items.qty_fulfilled < order_items.qty_ordered) & delivered[order_items.order_id.values - 1]]
    short_m = np.zeros(n_orders, bool)
    short_m[short.order_id.values - 1] = True
    d_rows.append(pd.DataFrame({
        "order_id": short.order_id.values, "defect_type": "missing_item", "sku_id": short.sku_id.values,
        "refund_amount": np.round((short.qty_ordered - short.qty_fulfilled).values * short.unit_price.values, 2),
        "reported_ts": to_ts(delivered_m[short.order_id.values - 1] + 1),
    }))
    defects = pd.concat(d_rows, ignore_index=True).sort_values(["reported_ts", "order_id"], ignore_index=True)
    defects.insert(0, "defect_id", np.arange(1, len(defects) + 1))

    # ---- planted data-quality issues ---------------------------------------------------------
    dq = plants["data_quality"]
    n_dup = int(dq["duplicate_event_rate"] * n_orders)
    dup = events.sample(n=n_dup, random_state=sim["seed"]).copy()
    jitter = rng.random(n_dup) < 0.5
    dup.loc[jitter, "event_ts"] = dup.loc[jitter, "event_ts"] + pd.to_timedelta(rng.integers(1, 30, jitter.sum()), unit="s")
    events = pd.concat([events, dup], ignore_index=True)
    skew_orders = rng.choice(order_ids[delivered], size=dq["delivered_before_placed"], replace=False)
    skew = events.event_type.eq("delivered") & events.order_id.isin(skew_orders)
    events.loc[skew, "event_ts"] = to_ts(placed_min[events.loc[skew, "order_id"].values - 1] - rng.uniform(5, 120, skew.sum()))
    null_r = events.event_type.eq("rider_assigned") & (rng.random(len(events)) < dq["null_rider_rate"])
    events.loc[null_r, "rider_id"] = None
    events = events.sort_values(["event_ts", "order_id"], kind="stable", ignore_index=True)
    events.insert(0, "event_id", np.arange(1, len(events) + 1))

    picker_roster = pd.DataFrame({
        "node_id": np.repeat(nodes.node_id.values, days * len(op_hours)),
        "hour_ts": np.tile((start + pd.to_timedelta((np.arange(days)[:, None] * 24 + op_hours[None]).ravel(), unit="h")).values, n_nodes),
        "pickers_rostered": pickers.ravel().astype(int),
    })

    skus_out = skus.drop(columns="popularity")
    skus_out["inventory_tracked"] = skus_out.index.isin(tracked)

    data_dir = project_dir / "data"
    data_dir.mkdir(exist_ok=True)
    db_path = data_dir / "fulfilment.duckdb"
    db_path.unlink(missing_ok=True)
    con = duckdb.connect(str(db_path))
    tables = {
        "nodes": nodes, "skus": skus_out, "riders": riders, "rider_shifts": rider_shifts,
        "picker_roster": picker_roster, "weather_hourly": weather, "orders": orders,
        "order_items": order_items, "order_events": events, "inventory_snapshots": inventory, "defects": defects,
    }
    for name, df in tables.items():
        con.register("tmp_df", df)
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM tmp_df")
        con.unregister("tmp_df")
    con.close()
    # resolved planted entities, for GROUND_TRUTH.md and the final cross-check only
    (data_dir / "planted_entities.json").write_text(json.dumps({
        "stockout_cluster_skus": sorted(skus.sku_id[sorted(cl_skus)].tolist()),
        "storm_nodes": sorted(nodes.node_id[nodes.zone.isin(st["zones"])].tolist()),
    }, indent=2))
    for name, df in tables.items():
        print(f"  {name:20s} {len(df):>10,d} rows")
    return db_path


if __name__ == "__main__":
    generate()
