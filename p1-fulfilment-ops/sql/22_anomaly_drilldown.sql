-- 22_anomaly_drilldown.sql
-- Business question: for every flagged node-hour, which stage caused the excess delay, and what
-- operating condition (picker load, rider supply, weather) came with it?
-- Excess minutes per stage = cell stage mean - the baseline the cell was flagged against
-- (the node's own history for temporal flags, peers for peer-only flags), both computed in 21.
-- Flagged cells are then grouped into incidents: consecutive or same-day cells of one node with the
-- same driving stage, and chronic patterns: the same node-hour flagged on many days.
-- Variables: chronic_min_day_share, min_incident_hours.

CREATE OR REPLACE TABLE anomaly_drilldown AS
WITH gaps AS (
    SELECT a.*,
           CASE WHEN a.flag_type = 'peer' THEN a.mean_pick_min - a.peer_pick     ELSE a.mean_pick_min - a.hist_pick END     AS pick_excess,
           CASE WHEN a.flag_type = 'peer' THEN a.mean_wait_min - a.peer_wait     ELSE a.mean_wait_min - a.hist_wait END     AS wait_excess,
           CASE WHEN a.flag_type = 'peer' THEN a.mean_travel_min - a.peer_travel ELSE a.mean_travel_min - a.hist_travel END AS travel_excess
    FROM anomaly_flags a
)
SELECT *,
       CASE greatest(pick_excess, wait_excess, travel_excess)
           WHEN pick_excess THEN 'picking' WHEN wait_excess THEN 'rider wait' ELSE 'travel' END AS driver_stage,
       greatest(pick_excess, wait_excess, travel_excess) / nullif(pick_excess + wait_excess + travel_excess, 0) AS driver_share,
       -- order-minutes of delay above the baseline: the size of the problem, not just its z-score
       orders_timed * (pick_excess + wait_excess + travel_excess) AS excess_order_min
FROM gaps;

-- chronic patterns: a node-hour of day flagged on a large share of days
CREATE OR REPLACE TABLE anomaly_chronic AS
WITH days AS (SELECT count(DISTINCT cell_date) AS n FROM node_hour_cells)
SELECT node_id, cell_hour,
       count(*)                                    AS flagged_days,
       count(*) / (SELECT n FROM days)             AS flagged_day_share,
       mode(driver_stage)                          AS driver_stage,
       avg(pick_excess)                            AS pick_excess_min,
       avg(wait_excess)                            AS wait_excess_min,
       avg(travel_excess)                          AS travel_excess_min,
       avg(orders_per_picker)                      AS orders_per_picker,
       avg(peer_orders_per_picker)                 AS peer_orders_per_picker,
       avg(late_rate)                              AS late_rate,
       sum(excess_order_min)                       AS excess_order_min
FROM anomaly_drilldown
GROUP BY node_id, cell_hour
HAVING count(*) >= getvariable('chronic_min_day_share') * (SELECT n FROM days)
ORDER BY node_id, cell_hour;

-- incidents (acute): at least min_incident_hours flagged cells of one node on one day with the same
-- driving stage, excluding the node-hours already explained by a chronic pattern
CREATE OR REPLACE TABLE anomaly_incidents AS
SELECT node_id, zone, cell_date, driver_stage,
       count(*)                          AS flagged_hours,
       min(cell_hour)                    AS first_hour,
       max(cell_hour)                    AS last_hour,
       sum(orders_timed)                 AS orders_affected,
       sum(orders_timed * late_rate)     AS late_orders,
       sum(excess_order_min)             AS excess_order_min,
       avg(mean_delivery_min)            AS mean_delivery_min,
       max(greatest(coalesce(z_temporal, 0), coalesce(z_peer, 0))) AS max_z,
       avg(pick_excess)                  AS pick_excess_min,
       avg(wait_excess)                  AS wait_excess_min,
       avg(travel_excess)                AS travel_excess_min,
       avg(orders_per_picker)            AS orders_per_picker,
       avg(peer_orders_per_picker)       AS peer_orders_per_picker,
       avg(rider_utilisation)            AS rider_utilisation,
       avg(peer_rider_utilisation)       AS peer_rider_utilisation,
       sum(orders_placed) / sum(hist_orders_placed) - 1    AS orders_vs_history,
       sum(riders_online) / sum(hist_riders_online) - 1    AS riders_online_vs_history,
       mode(weather)                     AS weather,
       string_agg(DISTINCT flag_type, '+' ORDER BY flag_type) AS flag_types
FROM anomaly_drilldown d
WHERE NOT EXISTS (SELECT 1 FROM anomaly_chronic c WHERE c.node_id = d.node_id AND c.cell_hour = d.cell_hour)
GROUP BY node_id, zone, cell_date, driver_stage
HAVING count(*) >= getvariable('min_incident_hours');

-- network events: the same driving stage flagged at two or more nodes on the same day
CREATE OR REPLACE TABLE anomaly_events AS
SELECT cell_date, driver_stage,
       count(*)                                     AS nodes_affected,
       string_agg(node_id, ', ' ORDER BY node_id)   AS node_ids,
       string_agg(DISTINCT zone, ', ' ORDER BY zone) AS zones,
       sum(flagged_hours)                           AS flagged_hours,
       sum(orders_affected)                         AS orders_affected,
       sum(late_orders)                             AS late_orders,
       sum(excess_order_min)                        AS excess_order_min,
       sum(wait_excess_min * flagged_hours) / sum(flagged_hours)   AS wait_excess_min,
       sum(pick_excess_min * flagged_hours) / sum(flagged_hours)   AS pick_excess_min,
       sum(travel_excess_min * flagged_hours) / sum(flagged_hours) AS travel_excess_min,
       avg(orders_vs_history)                       AS orders_vs_history,
       avg(riders_online_vs_history)                AS riders_online_vs_history,
       avg(rider_utilisation)                       AS rider_utilisation,
       mode(weather)                                AS weather
FROM anomaly_incidents
GROUP BY cell_date, driver_stage
HAVING count(*) >= 2
ORDER BY excess_order_min DESC;

-- episodes: network events on consecutive days with the same driving stage (gaps and islands)
CREATE OR REPLACE TABLE anomaly_episodes AS
WITH islands AS (
    SELECT *, cell_date - CAST(row_number() OVER (PARTITION BY driver_stage ORDER BY cell_date) AS INTEGER) AS island
    FROM anomaly_events
)
SELECT driver_stage,
       min(cell_date)                                  AS start_date,
       max(cell_date)                                  AS end_date,
       count(*)                                        AS days,
       list_sort(list_distinct(flatten(list(string_split(node_ids, ', '))))) AS node_list,
       sum(flagged_hours)                              AS flagged_hours,
       sum(orders_affected)                            AS orders_affected,
       sum(late_orders)                                AS late_orders,
       sum(excess_order_min)                           AS excess_order_min,
       sum(wait_excess_min * flagged_hours) / sum(flagged_hours)   AS wait_excess_min,
       sum(pick_excess_min * flagged_hours) / sum(flagged_hours)   AS pick_excess_min,
       sum(travel_excess_min * flagged_hours) / sum(flagged_hours) AS travel_excess_min,
       avg(orders_vs_history)                          AS orders_vs_history,
       avg(riders_online_vs_history)                   AS riders_online_vs_history,
       avg(rider_utilisation)                          AS rider_utilisation,
       mode(weather)                                   AS weather
FROM islands
GROUP BY driver_stage, island
ORDER BY excess_order_min DESC;
