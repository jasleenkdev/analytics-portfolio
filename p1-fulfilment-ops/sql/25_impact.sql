-- 25_impact.sql
-- Business question: how many late orders would we have avoided if each chronic problem were fixed?
-- For chronic node-hours, every order's delivery time is reduced by the cell's excess over the other
-- nodes at the same date-hour in the driving stage (never below zero); an order is recoverable if that
-- brings it inside the SLA. Event-level impact uses the excess order-minutes from the drill-down.
-- Variables: sla_minutes.

CREATE OR REPLACE TABLE impact_chronic AS
WITH chronic AS (SELECT node_id, cell_hour, driver_stage FROM anomaly_chronic),
peer AS (
    SELECT c.node_id, h.hour_ts,
           avg(h.mean_pick_min) AS peer_pick, avg(h.mean_wait_min) AS peer_wait, avg(h.mean_travel_min) AS peer_travel,
           avg(h.late_rate) AS peer_late_rate
    FROM node_hour_cells h JOIN chronic c ON h.node_id <> c.node_id AND h.cell_hour = c.cell_hour
    GROUP BY ALL
),
cells AS (
    SELECT h.node_id, h.hour_ts, c.driver_stage, p.peer_late_rate,
           CASE c.driver_stage WHEN 'picking'    THEN h.mean_pick_min - p.peer_pick
                               WHEN 'rider wait' THEN h.mean_wait_min - p.peer_wait
                               ELSE h.mean_travel_min - p.peer_travel END AS stage_excess
    FROM node_hour_cells h
    JOIN chronic c ON h.node_id = c.node_id AND h.cell_hour = c.cell_hour
    JOIN peer p ON p.node_id = h.node_id AND p.hour_ts = h.hour_ts
)
SELECT t.node_id, c.driver_stage,
       string_agg(DISTINCT CAST(t.order_hour AS VARCHAR), ',' ORDER BY CAST(t.order_hour AS VARCHAR)) AS hours,
       count(*)                                         AS orders_timed,
       count(*) FILTER (WHERE NOT t.within_sla)         AS late_orders,
       avg(CAST(NOT t.within_sla AS DOUBLE))            AS late_rate,
       avg(c.peer_late_rate)                            AS peer_late_rate,
       count(*) FILTER (WHERE NOT t.within_sla
                        AND t.delivery_min - greatest(c.stage_excess, 0) <= getvariable('sla_minutes')) AS recoverable_late_orders,
       avg(greatest(c.stage_excess, 0))                 AS mean_stage_excess_min
FROM order_timeline t
JOIN cells c ON t.node_id = c.node_id AND t.order_hour_ts = c.hour_ts
WHERE t.timing_valid
GROUP BY t.node_id, c.driver_stage;
