-- 20_node_hour_cells.sql
-- Business question: what did each node look like in each operating hour of each day?
-- One row per node x date x hour with volume, SLA, stage means, picker and rider load and weather,
-- the input to anomaly scoring and drill-down.
-- Variables: none.

CREATE OR REPLACE TABLE node_hour_cells AS
WITH orders_h AS (
    SELECT node_id, order_hour_ts AS hour_ts,
           count(*)                                   AS orders_placed,
           count(*) FILTER (WHERE timing_valid)       AS orders_timed,
           count(*) FILTER (WHERE status = 'cancelled') AS orders_cancelled,
           avg(delivery_min) FILTER (WHERE timing_valid)   AS mean_delivery_min,
           avg(CAST(NOT within_sla AS DOUBLE))             AS late_rate,
           avg(pick_min) FILTER (WHERE timing_valid)       AS mean_pick_min,
           avg(rider_wait_min) FILTER (WHERE timing_valid) AS mean_wait_min,
           avg(travel_min) FILTER (WHERE timing_valid)     AS mean_travel_min
    FROM order_timeline GROUP BY ALL
)
SELECT o.node_id, n.zone, o.hour_ts,
       CAST(o.hour_ts AS DATE) AS cell_date, hour(o.hour_ts) AS cell_hour,
       o.* EXCLUDE (node_id, hour_ts),
       p.pickers_rostered,
       o.orders_placed / p.pickers_rostered AS orders_per_picker,
       r.riders_online, r.utilisation      AS rider_utilisation,
       w.condition                         AS weather
FROM orders_h o
JOIN nodes n USING (node_id)
LEFT JOIN picker_roster p USING (node_id, hour_ts)
LEFT JOIN kpi_riders_node_hour r USING (node_id, hour_ts)
LEFT JOIN weather_hourly w ON w.zone = n.zone AND w.hour_ts = o.hour_ts;
