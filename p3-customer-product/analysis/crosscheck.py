"""Found vs planted for project 3. Runs after findings.json is frozen; the only module reading plant files."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from shared.crosscheck import load_truth, row, write

PROJECT = Path(__file__).resolve().parents[1]


def run(con, cfg: dict) -> dict:
    plants, ent, f = load_truth(PROJECT)
    rows = []

    fd = plants["funnel_dropoff"]
    release = (pd.Timestamp(cfg["sim"]["start_date"]) + pd.Timedelta(days=fd["release_day"])).date().isoformat()
    flagged = f["funnel"]["flagged"]
    d = f["funnel"]["dropoff"]
    exact = d and d["platform"] == fd["platform"] and d["app_version"] == fd["app_version"] and d["step"] == "payment_success"
    rows.append(row(f"1. payment success on {fd['platform']} {fd['app_version']} from {release}: "
                    f"{fd['payment_success_before'] * 100:.0f}% to {fd['payment_success_after'] * 100:.0f}%",
                    f"{len(flagged)} of {f['funnel']['tests']} segment-steps flagged" + (
                        f": {d['platform']} {d['app_version']} {d['step']} {d['rate'] * 100:.1f}% vs {d['others_rate'] * 100:.1f}%, first seen {d['first_day']}" if d else ""),
                    "hit" if exact and len(flagged) == 1 and d["first_day"] == release else ("partial" if exact else "miss")))

    rt = plants["retention"]
    model = {m["term"]: m for m in f["retention"]["model"]}
    planted_order = sorted(rt["channel_multiplier"], key=lambda k: rt["channel_multiplier"][k])  # best retention first
    effect = {k: (0.0 if k == "organic" else model[f"channel: {k} (vs organic)"]["marginal_effect_pp"]) for k in planted_order}
    found_order = sorted(effect, key=lambda k: -effect[k])
    rows.append(row("2a. churn by channel: " + " < ".join(f"{k} x{rt['channel_multiplier'][k]}" for k in planted_order),
                    "90-day repeat effect vs organic: " + ", ".join(f"{k} {effect[k]:+.1f} pp" for k in found_order),
                    "hit" if found_order == planted_order else "partial",
                    "ranking matches exactly" if found_order == planted_order else f"found ranking {found_order}"))
    fi = model["first_order_issue"]
    rows.append(row(f"2b. first-order problem multiplies churn x{rt['first_order_issue_multiplier']}",
                    f"{fi['marginal_effect_pp']:+.1f} pp on 90-day repeat (95% CI {fi['ci_low_pp']:+.1f} to {fi['ci_high_pp']:+.1f})",
                    "hit" if fi["ci_high_pp"] < 0 else "miss"))
    android = model.get("platform: android (vs ios)")
    if android and android["p_value"] < 0.05:
        rows.append(row("(not planted as a retention driver)", f"Android {android['marginal_effect_pp']:+.1f} pp on 90-day repeat vs iOS",
                        "unplanted", "a knock-on effect of the planted payment fault: failed payments remove orders, including second orders"))

    planted_pairs = {tuple(sorted(p)) for p in ent["affinity_pairs"]}
    found_pairs = {tuple(sorted((a["sku_a"], a["sku_b"]))) for a in f["affinity"] if a["lift"] >= cfg["analysis"]["affinity_min_lift"]}
    rows.append(row(f"3. {len(planted_pairs)} planted SKU pairs", f"{len(found_pairs)} pairs with lift >= {cfg['analysis']['affinity_min_lift']}",
                    "hit" if found_pairs == planted_pairs else "partial",
                    f"{len(found_pairs & planted_pairs)}/{len(planted_pairs)} recovered, {len(found_pairs - planted_pairs)} extra"))

    wa = {tuple(x) for x in ent["wastage_node_skus"]}
    reduce_ = con.execute("SELECT node_id, sku_id FROM assortment_reduce ORDER BY waste_cost DESC, node_id, sku_id").fetchall()
    top = set(reduce_[: len(wa)])
    rows.append(row(f"4. {len(wa)} overstocked perishable node-SKUs at {sorted({n for n, _ in wa})}",
                    f"{len(reduce_)} reduce-depth recommendations; the top {len(wa)} by waste cost are "
                    f"{'exactly the planted set' if top == wa else f'{len(top & wa)} planted'}",
                    "hit" if wa <= set(reduce_) and top == wa else "partial",
                    f"recall {len(wa & set(reduce_))}/{len(wa)}; the other {len(reduce_) - len(wa)} come from the generator's baseline policy, "
                    "where safety stock pushes cover past shelf life for 2-5 day products; real in the data but not planted"))

    gems = set(ent["hidden_gems"])
    adds = con.execute("SELECT sku_id, sum(impact_high) AS v FROM assortment_add GROUP BY 1 ORDER BY v DESC").df()
    rank = {s: i + 1 for i, s in enumerate(adds.sku_id)}
    in_list = gems & set(adds.sku_id)
    abc = dict(con.execute("SELECT sku_id, abc FROM abc_xyz WHERE sku_id IN (SELECT unnest(?))", [sorted(gems)]).fetchall())
    rows.append(row(f"5. {len(gems)} high-margin {plants['hidden_gems']['category']} SKUs ranged at {plants['hidden_gems']['nodes']} only",
                    f"{len(in_list)}/{len(gems)} in the add list, ranks {sorted(rank[s] for s in in_list)} of {len(adds)} SKUs by impact; network ABC class {sorted(set(abc.values()))}",
                    "hit" if in_list == gems else "partial",
                    "network ABC alone would not have flagged them; per-ranged-node velocity did"))
    return write(PROJECT, rows)
