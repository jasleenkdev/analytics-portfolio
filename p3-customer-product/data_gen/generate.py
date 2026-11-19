"""Synthetic customer, product and inventory data for project 3.

Customers sign up through a channel, order as a Poisson process while active, and churn with a
monthly hazard. Baskets mix a personal repertoire of favourite SKUs (which creates reordering) with
popular SKUs from what the home node ranges. Every order comes from a session that walked the
checkout funnel; non-buying sessions drop out earlier. Each node replenishes ranged SKUs daily to an
order-up-to level; perishables are tracked in FIFO age buckets so stock older than its shelf life is
wasted. Planted effects (data_gen/plants.toml) alter the funnel, churn, basket composition, ranging
and replenishment levels.
"""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
ZONES = ["north", "south", "east", "west", "central", "north", "south", "east"]
CHANNELS = {"organic": 0.34, "paid_search": 0.22, "paid_social": 0.20, "referral": 0.14, "partner": 0.10}
# category: (sku count, perishable, shelf-life range, price median, margin)
CATEGORIES = {
    "produce": (40, True, (5, 9), 2.0, 0.34), "dairy": (34, True, (7, 21), 2.4, 0.28),
    "bakery": (26, True, (2, 5), 2.6, 0.42), "meat_fish": (28, True, (3, 7), 6.8, 0.27),
    "ready_meals": (24, True, (3, 5), 5.5, 0.38), "frozen": (28, False, (120, 365), 4.2, 0.32),
    "beverages": (34, False, (180, 540), 2.1, 0.33), "snacks": (34, False, (90, 270), 2.2, 0.40),
    "pantry": (38, False, (180, 720), 2.9, 0.29), "breakfast": (24, False, (90, 365), 3.6, 0.31),
    "household": (26, False, (365, 1095), 4.6, 0.35), "personal_care": (26, False, (365, 1095), 5.2, 0.43),
    "baby": (16, False, (180, 720), 8.5, 0.24), "pet": (20, False, (180, 720), 6.1, 0.31),
    "premium_deli": (22, True, (10, 30), 7.5, 0.40),
}
STEPS = ["visit", "browse", "add_to_cart", "checkout", "payment_attempt", "order_placed"]


def _load(p: Path) -> dict:
    with open(p, "rb") as f:
        return tomllib.load(f)


def build_catalogue(rng, plants):
    rows, k = [], 1
    for cat, (n, per, (lo, hi), price, margin) in CATEGORIES.items():
        for j in range(n):
            p = round(price * float(rng.lognormal(0, 0.3)), 2)
            m = float(np.clip(margin + rng.normal(0, 0.05), 0.08, 0.6))
            rows.append({"sku_id": f"S{k:03d}", "sku_name": f"{cat}_{j + 1:02d}", "category": cat, "perishable": per,
                         "shelf_life_days": int(rng.integers(lo, hi + 1)), "unit_price": p,
                         "unit_cost": round(p * (1 - m), 2), "popularity": float(rng.lognormal(0, 1.0))})
            k += 1
    skus = pd.DataFrame(rows)
    hg = plants["hidden_gems"]
    gems = skus.index[skus.category == hg["category"]][: hg["n_skus"]]
    skus.loc[gems, "unit_cost"] = (skus.loc[gems, "unit_price"] * (1 - hg["margin"])).round(2)
    skus.loc[gems, "popularity"] = np.quantile(skus.popularity, 0.85)
    return skus, list(skus.sku_id[gems])


def build_ranging(rng, skus, nodes, gems, plants):
    rows = []
    for n in nodes.node_id:
        # every node ranges most SKUs; the long tail is ranged less often
        p_range = np.clip(0.80 + 0.18 * (skus.popularity.rank(pct=True).values), 0, 0.99)
        ranged = rng.random(len(skus)) < p_range
        ranged[skus.sku_id.isin(gems).values] = n in plants["hidden_gems"]["nodes"]
        rows += [{"node_id": n, "sku_id": s} for s in skus.sku_id[ranged]]
    return pd.DataFrame(rows)


def generate(project_dir: Path = PROJECT) -> Path:
    cfg = _load(project_dir / "config.toml")
    plants = _load(project_dir / "data_gen" / "plants.toml")
    sim = cfg["sim"]
    rng = np.random.default_rng(sim["seed"])
    start, days = pd.Timestamp(sim["start_date"]), sim["days"]

    nodes = pd.DataFrame({"node_id": [f"N{i:02d}" for i in range(1, sim["n_nodes"] + 1)], "zone": ZONES[: sim["n_nodes"]],
                          "size_factor": np.round(rng.uniform(0.7, 1.4, sim["n_nodes"]), 3)})
    skus, gems = build_catalogue(rng, plants)
    ranging = build_ranging(rng, skus, nodes, gems, plants)

    # ---- customers --------------------------------------------------------------------------
    n = sim["customers"]
    growth = np.linspace(0.7, 1.3, days)
    signup_day = rng.choice(days, n, p=growth / growth.sum())
    channel = rng.choice(list(CHANNELS), n, p=list(CHANNELS.values()))
    platform = rng.choice(["ios", "android", "web"], n, p=[0.42, 0.43, 0.15])
    home = rng.choice(nodes.node_id, n, p=(nodes.size_factor / nodes.size_factor.sum()).values)
    rate = rng.gamma(1.5, 0.95 / 1.5, n) / 30            # orders per day while active
    ret = plants["retention"]
    first_issue = rng.random(n) < 0.10                    # missing or late first order
    hazard = ret["base_monthly_churn"] * np.vectorize(ret["channel_multiplier"].get)(channel) \
        * np.where(first_issue, ret["first_order_issue_multiplier"], 1.0)
    lifetime = rng.exponential(30 / hazard)
    active_end = np.minimum(signup_day + lifetime, days)
    customers = pd.DataFrame({"customer_id": [f"C{i:06d}" for i in range(1, n + 1)],
                              "signup_date": start + pd.to_timedelta(signup_day, unit="D"),
                              "acquisition_channel": channel, "platform": platform, "home_node_id": home})

    # ---- intended orders: the first at signup, then Poisson while active --------------------
    extra = rng.poisson(rate * (active_end - signup_day))
    cust_idx = np.concatenate([np.arange(n), np.repeat(np.arange(n), extra)])
    t = np.concatenate([signup_day + rng.uniform(0.3, 0.95, n),
                        np.repeat(signup_day, extra) + rng.uniform(0, 1, extra.sum()) * np.repeat(active_end - signup_day, extra)])
    keep = t < days
    cust_idx, t = cust_idx[keep], t[keep]
    order_sort = np.lexsort((cust_idx, t))
    cust_idx, t = cust_idx[order_sort], t[order_sort]

    # ---- funnel: payment failures on the planted app version remove intended orders ---------
    fd = plants["funnel_dropoff"]
    is_android = platform[cust_idx] == fd["platform"]
    adopt = np.clip((t - fd["release_day"]) / fd["adoption_days"], 0, 1)
    on_new = is_android & (rng.random(len(t)) < adopt)
    version = np.where(platform[cust_idx] == "android", np.where(on_new, fd["app_version"], "5.3"),
                       np.where(platform[cust_idx] == "ios", "7.2", "web"))
    p_success = np.where(on_new, fd["payment_success_after"], fd["payment_success_before"])
    paid = rng.random(len(t)) < p_success
    # sessions for intended orders reach payment; unpaid ones end there
    buy_sessions = pd.DataFrame({"c": cust_idx, "t": t, "version": version, "max_step": np.where(paid, 5, 4)})
    n_browse = int(len(t) * 1.4)
    bc = rng.choice(n, n_browse)
    bt = signup_day[bc] + rng.uniform(0, 1, n_browse) * (active_end[bc] + 20 - signup_day[bc])
    ok = bt < days
    bc, bt = bc[ok], bt[ok]
    b_android = platform[bc] == "android"
    b_new = b_android & (rng.random(len(bt)) < np.clip((bt - fd["release_day"]) / fd["adoption_days"], 0, 1))
    browse_sessions = pd.DataFrame({
        "c": bc, "t": bt,
        "version": np.where(platform[bc] == "android", np.where(b_new, fd["app_version"], "5.3"),
                            np.where(platform[bc] == "ios", "7.2", "web")),
        "max_step": rng.choice([0, 1, 2, 3], len(bt), p=[0.30, 0.36, 0.24, 0.10])})
    sessions = pd.concat([buy_sessions, browse_sessions], ignore_index=True).sort_values(["t", "c"], ignore_index=True)
    sessions["session_id"] = [f"X{i:07d}" for i in range(1, len(sessions) + 1)]
    sess_ts = start + pd.to_timedelta(np.round(sessions.t.values * 86400).astype("int64"), unit="s")
    reps = sessions.max_step.values + 1
    step_idx = np.concatenate([np.arange(k) for k in reps]) if len(reps) else np.array([], int)
    funnel = pd.DataFrame({"session_id": np.repeat(sessions.session_id.values, reps),
                           "step": np.array(STEPS)[step_idx],
                           "event_ts": np.repeat(sess_ts, reps) + pd.to_timedelta(step_idx * 45, unit="s")})
    sessions_out = pd.DataFrame({"session_id": sessions.session_id, "customer_id": customers.customer_id.values[sessions.c],
                                 "session_ts": sess_ts, "platform": platform[sessions.c], "app_version": sessions.version})

    # ---- orders and basket lines ------------------------------------------------------------
    placed = sessions[sessions.max_step == 5].reset_index(drop=True)
    oc, ot = placed.c.values, placed.t.values
    n_orders = len(placed)
    node_of = home[oc]
    order_ids = np.array([f"O{i:07d}" for i in range(1, n_orders + 1)])
    sku_index = {s: i for i, s in enumerate(skus.sku_id)}
    ranged_by_node = {nd: np.array([sku_index[s] for s in g.sku_id]) for nd, g in ranging.groupby("node_id")}
    pop = skus.popularity.values
    # repertoire: each customer's favourite SKUs among what their node ranges
    repertoire = np.zeros((n, sim["repertoire_size"]), int)
    for nd, idx in ranged_by_node.items():
        who = np.where(home == nd)[0]
        w = pop[idx] / pop[idx].sum()
        repertoire[who] = rng.choice(idx, size=(len(who), sim["repertoire_size"]), p=w)
    n_lines = 1 + rng.poisson(4.8, n_orders)
    lo = np.repeat(np.arange(n_orders), n_lines)
    from_rep = rng.random(len(lo)) < sim["repertoire_share"]
    line_sku = repertoire[oc[lo], rng.integers(0, sim["repertoire_size"], len(lo))]
    for nd, idx in ranged_by_node.items():
        m = (~from_rep) & (node_of[lo] == nd)
        w = pop[idx] / pop[idx].sum()
        line_sku[m] = rng.choice(idx, m.sum(), p=w)
    # planted affinities: pairs inside the same node range, partner joins the basket on purpose
    af = plants["affinity"]
    core = skus[(skus.popularity > np.quantile(pop, 0.4)) & ~skus.sku_id.isin(gems)]
    cats = core.category.unique()
    pairs = []
    for _ in range(af["pairs"]):
        c1, c2 = rng.choice(cats, 2, replace=False)
        a = rng.choice(core.sku_id[core.category == c1])
        b = rng.choice(core.sku_id[core.category == c2])
        pairs.append((a, b))
    add_o, add_s = [], []
    for a, b in pairs:
        ia, ib = sku_index[a], sku_index[b]
        has_a = np.unique(lo[line_sku == ia])
        joins = has_a[rng.random(len(has_a)) < af["p_add_partner"]]
        add_o.append(joins)
        add_s.append(np.full(len(joins), ib))
    lo = np.concatenate([lo] + add_o)
    line_sku = np.concatenate([line_sku] + add_s)
    lines = pd.DataFrame({"o": lo, "s": line_sku, "qty": 1 + rng.binomial(2, 0.18, len(lo))})
    lines = lines.groupby(["o", "s"], as_index=False).qty.sum()
    # partners are only kept where the node ranges them
    rng_set = set(zip(ranging.node_id, ranging.sku_id.map(sku_index)))
    lines = lines[[(node_of[o], s) in rng_set for o, s in zip(lines.o.values, lines.s.values)]].reset_index(drop=True)
    lines["line_no"] = lines.groupby("o").cumcount() + 1
    value = np.bincount(lines.o, weights=lines.qty * skus.unit_price.values[lines.s], minlength=n_orders)
    orders = pd.DataFrame({"order_id": order_ids, "customer_id": customers.customer_id.values[oc],
                           "session_id": placed.session_id.values, "node_id": node_of,
                           "order_ts": start + pd.to_timedelta(np.round(ot * 86400).astype("int64"), unit="s"),
                           "order_value": np.round(value, 2)})
    order_lines = pd.DataFrame({"order_id": order_ids[lines.o], "line_no": lines.line_no.values,
                                "sku_id": skus.sku_id.values[lines.s], "qty": lines.qty.values,
                                "unit_price": skus.unit_price.values[lines.s], "unit_cost": skus.unit_cost.values[lines.s]})

    # order issues: base rates for every order; first orders follow each customer's drawn experience
    first = ~pd.Series(oc).duplicated().values
    issue = np.where(first, first_issue[oc], rng.random(n_orders) < 0.08)
    kind = rng.choice(["missing_item", "late_delivery"], n_orders, p=[0.45, 0.55])
    issues = pd.DataFrame({"order_id": order_ids[issue], "issue_type": kind[issue]})

    # ---- daily inventory with FIFO ageing for perishables -----------------------------------
    day = np.floor(ot).astype(int)
    dem = pd.DataFrame({"node": node_of[lines.o.values], "s": lines.s.values, "d": day[lines.o.values], "q": lines.qty.values})
    pairs_df = ranging.assign(s=ranging.sku_id.map(sku_index)).rename(columns={"node_id": "node"})[["node", "s"]].reset_index(drop=True)
    pair_key = {(a, b): i for i, (a, b) in enumerate(zip(pairs_df.node, pairs_df.s))}
    P = len(pairs_df)
    D = np.zeros((P, days))
    dg = dem.groupby(["node", "s", "d"]).q.sum().reset_index()
    D[[pair_key[(a, b)] for a, b in zip(dg.node, dg.s)], dg.d.values] = dg.q.values
    mean_d = D.mean(axis=1)
    shelf = skus.shelf_life_days.values[pairs_df.s]
    per = skus.perishable.values[pairs_df.s]
    cover = np.where(per, np.minimum(2.0, 0.5 * shelf), 4.0)
    wa = plants["wastage"]
    waste_pairs = []
    for nd in wa["nodes"]:
        cand = pairs_df[(pairs_df.node == nd) & np.isin(skus.category.values[pairs_df.s], wa["categories"])]
        top = cand.assign(m=mean_d[cand.index]).sort_values("m", ascending=False).head(wa["skus_per_node"])
        waste_pairs += list(top.index)
    cover[waste_pairs] = wa["cover_vs_shelf_life"] * shelf[waste_pairs]
    # perishables carry thin safety stock (spoilage risk), ambient goods a generous buffer
    z = np.where(per, 0.8, 2.5)
    S = np.ceil(mean_d * cover + z * np.sqrt(mean_d * np.maximum(cover, 1)) + 1)
    max_age = int(min(shelf[per].max(), 60)) + 1 if per.any() else 1
    buckets = np.zeros((P, max_age + 1))     # buckets[:, a] = units aged a days
    rec, sold, wasted, lost, opening = (np.zeros((P, days)) for _ in range(5))
    for d in range(days):
        on_hand = buckets.sum(axis=1)
        receipt = np.maximum(S - on_hand, 0)
        buckets[:, 0] += receipt
        rec[:, d] = receipt
        opening[:, d] = buckets.sum(axis=1)
        need = D[:, d].copy()
        for a in range(max_age, -1, -1):        # sell oldest first
            take = np.minimum(buckets[:, a], need)
            buckets[:, a] -= take
            need -= take
        sold[:, d] = D[:, d] - need
        lost[:, d] = need
        # age everything by a day; perishable units past shelf life are written off
        buckets[:, 1:] = buckets[:, :-1].copy()
        buckets[:, 0] = 0
        ages = np.arange(max_age + 1)[None, :]
        expired = per[:, None] & (ages > shelf[:, None])
        wasted[:, d] = (buckets * expired).sum(axis=1)
        buckets[expired] = 0
    inv = pd.DataFrame({
        "node_id": np.repeat(pairs_df.node.values, days), "sku_id": np.repeat(skus.sku_id.values[pairs_df.s], days),
        "stock_date": np.tile((start + pd.to_timedelta(np.arange(days), unit="D")).values, P),
        "opening_on_hand": opening.ravel().astype(int), "received": rec.ravel().astype(int),
        "sold": sold.ravel().astype(int), "lost_sales": lost.ravel().astype(int), "wasted": wasted.ravel().astype(int),
    })
    inv["closing_on_hand"] = inv.opening_on_hand - inv.sold - inv.wasted

    data = project_dir / "data"
    data.mkdir(exist_ok=True)
    db = data / "customer_product.duckdb"
    db.unlink(missing_ok=True)
    con = duckdb.connect(str(db))
    tables = {"nodes": nodes, "skus": skus.drop(columns="popularity"), "node_range": ranging, "customers": customers,
              "sessions": sessions_out, "funnel_events": funnel, "orders": orders, "order_lines": order_lines,
              "order_issues": issues, "inventory_daily": inv}
    for name, df in tables.items():
        con.register("tmp_df", df)
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM tmp_df")
        con.unregister("tmp_df")
    con.close()
    (data / "planted_entities.json").write_text(json.dumps({
        "affinity_pairs": [list(p) for p in pairs],
        "wastage_node_skus": sorted([[pairs_df.node[i], skus.sku_id[pairs_df.s[i]]] for i in waste_pairs]),
        "hidden_gems": gems,
    }, indent=2))
    for name, df in tables.items():
        print(f"  {name:16s} {len(df):>10,d} rows")
    return db


if __name__ == "__main__":
    generate()
