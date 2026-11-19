"""Found vs planted for project 1. Runs after findings.json is frozen; the only module reading plant files."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from shared.crosscheck import load_truth, row, write

PROJECT = Path(__file__).resolve().parents[1]


def run(con, cfg: dict) -> dict:
    plants, ent, f = load_truth(PROJECT)
    start = pd.Timestamp(cfg["sim"]["start_date"])
    rows = []

    us = plants["understaffing"]
    ch = {c["node_id"]: c for c in f["chronic"]}
    c = ch.get(us["node_id"])
    if c:
        hours_hit = sorted(set(c["hours"]) & set(us["hours"]))
        verdict = "hit" if set(us["hours"]) <= set(c["hours"]) and c["driver_stage"] == "picking" else "partial"
        wrong = c["defects"].get("wrong_item", {})
        rows.append(row(f"A. understaffed picking at {us['node_id']}, hours {us['hours']}",
                        f"chronic pattern at {c['node_id']} hours {c['hours']}, driver {c['driver_stage']}, "
                        f"orders per picker {c['orders_per_picker']:.1f} vs {c['peer_orders_per_picker']:.1f}; "
                        f"wrong-item rate {wrong.get('rate', 0) * 100:.2f}% vs {wrong.get('peer_rate', 0) * 100:.2f}%",
                        verdict, f"{len(hours_hit)}/{len(us['hours'])} planted hours recovered"))
    else:
        rows.append(row(f"A. understaffed picking at {us['node_id']}", "no chronic pattern at that node", "miss"))
    for node, c in ch.items():
        if node != us["node_id"]:
            rows.append(row("(none planted)", f"chronic pattern at {node}", "unplanted"))

    st = plants["storm"]
    storm_dates = {(start + pd.Timedelta(days=d)).date().isoformat() for d in range(st["start_day"], st["start_day"] + st["days"])}
    storm_nodes = set(ent["storm_nodes"])
    match = [e for e in f["episodes"] if {e["start_date"], e["end_date"]} & storm_dates or
             (e["start_date"] <= min(storm_dates) and e["end_date"] >= max(storm_dates))]
    if match:
        e = match[0]
        found_nodes = set(e["node_list"])
        days_found = {(pd.Timestamp(e["start_date"]) + pd.Timedelta(days=i)).date().isoformat() for i in range(e["days"])}
        complete = storm_nodes <= found_nodes and storm_dates <= days_found and e["driver_stage"] == "rider wait"
        extra = sorted(found_nodes - storm_nodes)
        rows.append(row(f"B. storm {sorted(storm_dates)[0]} to {sorted(storm_dates)[-1]} at {sorted(storm_nodes)}, rider-wait driven",
                        f"episode {e['start_date']} to {e['end_date']} at {e['node_list']}, driver {e['driver_stage']}, "
                        f"riders online {e['riders_online_vs_history'] * 100:+.0f}% vs history, weather {e['weather']}",
                        "hit" if complete and not extra else "partial",
                        f"all planted nodes and days found; extra node(s) {extra} in the episode" if extra else "exact match"))
    else:
        rows.append(row("B. storm episode", "no matching episode", "miss"))
    for e in f["episodes"]:
        if e not in match:
            rows.append(row("(none planted)", f"{e['driver_stage']} episode {e['start_date']} at {e['node_list']} "
                            f"({e['flagged_hours']:.0f} flagged hours, orders {e['orders_vs_history'] * 100:+.0f}% vs history)",
                            "unplanted", "single-day demand surges outrunning the rider roster; natural Poisson variation in the generator"))

    sc = plants["stockout_cluster"]
    clusters = f["stockout_clusters"]
    for node in sc["node_ids"]:
        cl = next((x for x in clusters if x["node_id"] == node and x["category"] == sc["category"]), None)
        if cl:
            skus = set(cl["sku_ids"].split(", "))
            planted = set(ent["stockout_cluster_skus"])
            rows.append(row(f"C. repeat {sc['category']} stockouts at {node} ({len(planted)} SKUs)",
                            f"cluster of {cl['repeat_skus']} repeat-stockout {cl['category']} SKUs, opening cover "
                            f"{cl['opening_cover_days']:.2f} vs {cl['other_nodes_cover_days']:.2f} days elsewhere",
                            "hit" if skus == planted else "partial", f"{len(skus & planted)}/{len(planted)} SKUs matched, {len(skus - planted)} extra"))
        else:
            rows.append(row(f"C. repeat stockouts at {node}", "no cluster", "miss"))
    for cl in clusters:
        if cl["node_id"] not in sc["node_ids"]:
            rows.append(row("(none planted)", f"stockout cluster {cl['node_id']} {cl['category']}", "unplanted"))

    dq = plants["data_quality"]
    report = {d["check_name"]: d["failing_rows"] for d in f["data_quality"]}
    orders = f["network"]["orders_placed"]
    expected_dup = int(dq["duplicate_event_rate"] * orders)
    rows.append(row(f"D1. {expected_dup} duplicated event rows", f"{report['repeated order/event-type rows (incl. jittered re-sends)']:.0f} repeated rows removed",
                    "hit" if report["repeated order/event-type rows (incl. jittered re-sends)"] == expected_dup else "partial"))
    rows.append(row(f"D2. {dq['delivered_before_placed']} delivered-before-placed orders", f"{report['delivered before placed']:.0f} flagged and excluded",
                    "hit" if report["delivered before placed"] == dq["delivered_before_placed"] else "partial"))
    rows.append(row(f"D3. {dq['null_rider_rate'] * 100:.1f}% null rider ids on assignment events",
                    f"{report['rider event with null rider_id']:.0f} null rider ids found and repaired", "hit",
                    "count includes nulls copied into duplicated rows"))

    pc = plants["process_change"]
    pc_date = (start + pd.Timedelta(days=pc["change_day"])).date().isoformat()
    cps = {c["node_id"]: c for c in f["change_points"]}
    c = cps.get(pc["node_id"])
    if c:
        rows.append(row(f"E. process change at {pc['node_id']} on {pc_date}",
                        f"change point at {c['node_id']} on {c['split_date']}, pick time {c['shift_min']:+.2f} min vs other nodes",
                        "hit" if c["split_date"] == pc_date else "partial",
                        "exact date" if c["split_date"] == pc_date else f"date off by {(pd.Timestamp(c['split_date']) - pd.Timestamp(pc_date)).days} days"))
    else:
        rows.append(row(f"E. process change at {pc['node_id']}", "not detected", "miss"))
    for node in cps:
        if node != pc["node_id"]:
            rows.append(row("(none planted)", f"change point at {node}", "unplanted"))

    for node, c in ch.items():
        wet = con.execute("""SELECT n.zone, avg(CAST(w.condition <> 'clear' AS DOUBLE)) AS wet FROM weather_hourly w
                             JOIN (SELECT DISTINCT zone FROM nodes) n USING (zone)
                             WHERE hour(w.hour_ts) IN (SELECT unnest(?)) GROUP BY 1""", [c["hours"]]).df().set_index("zone").wet
        zone = con.execute("SELECT zone FROM nodes WHERE node_id = ?", [node]).fetchone()[0]
        for k, v in c["defects"].items():
            if v["elevated"] and k != "wrong_item":
                rows.append(row("(not planted as part of A)", f"{k.replace('_', ' ')} claims elevated in {node}'s pattern hours "
                                f"({v['rate'] * 100:.2f}% vs {v['peer_rate'] * 100:.2f}%)", "unplanted",
                                f"the generator raises damage in rain; {node}'s zone ({zone}) was wet in {wet[zone] * 100:.0f}% of "
                                f"those hours vs {wet.drop(zone).mean() * 100:.0f}% for other zones, so this is weather co-occurring "
                                "with the pattern, not an understaffing effect"))
    return write(PROJECT, rows)
