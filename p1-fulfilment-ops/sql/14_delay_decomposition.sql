-- 14_delay_decomposition.sql
-- Business question: when a node is slow, is it picking, waiting for a rider, or travel?
-- Each order's delivery time is exactly pick + rider wait + travel (tested). A segment's gap to the
-- network is split into the three stage gaps, measured against the network mean for the same
-- hour of day, so a node that only trades at busy hours is not penalised for the hour mix.
-- Also: the late-order view, i.e. which stage overran most on each order that missed the SLA.
-- Variables: sla_minutes.

CREATE OR REPLACE TABLE network_stage_baseline AS
SELECT order_hour,
       avg(pick_min) AS base_pick_min, avg(rider_wait_min) AS base_wait_min, avg(travel_min) AS base_travel_min,
       median(pick_min) AS med_pick_min, median(rider_wait_min) AS med_wait_min, median(travel_min) AS med_travel_min
FROM order_timeline WHERE timing_valid
GROUP BY order_hour;

CREATE OR REPLACE TABLE kpi_delay_decomposition_node AS
WITH per_order AS (
    SELECT t.node_id, t.within_sla,
           t.pick_min, t.rider_wait_min, t.travel_min, t.delivery_min,
           t.pick_min - b.base_pick_min           AS pick_gap,
           t.rider_wait_min - b.base_wait_min     AS wait_gap,
           t.travel_min - b.base_travel_min       AS travel_gap,
           -- the stage that overran its typical (median) duration by the most minutes
           CASE greatest(t.pick_min - b.med_pick_min, t.rider_wait_min - b.med_wait_min, t.travel_min - b.med_travel_min)
               WHEN t.pick_min - b.med_pick_min THEN 'picking'
               WHEN t.rider_wait_min - b.med_wait_min THEN 'rider wait'
               ELSE 'travel' END                  AS main_overrun_stage
    FROM order_timeline t JOIN network_stage_baseline b USING (order_hour)
    WHERE t.timing_valid
)
SELECT node_id,
       count(*)                       AS orders_timed,
       avg(pick_min)                  AS mean_pick_min,
       avg(rider_wait_min)            AS mean_rider_wait_min,
       avg(travel_min)                AS mean_travel_min,
       avg(delivery_min)              AS mean_delivery_min,
       avg(pick_gap)                  AS pick_gap_min,
       avg(wait_gap)                  AS rider_wait_gap_min,
       avg(travel_gap)                AS travel_gap_min,
       count(*) FILTER (WHERE NOT within_sla)                                         AS late_orders,
       count(*) FILTER (WHERE NOT within_sla AND main_overrun_stage = 'picking')    / count(*) FILTER (WHERE NOT within_sla) AS late_share_picking,
       count(*) FILTER (WHERE NOT within_sla AND main_overrun_stage = 'rider wait') / count(*) FILTER (WHERE NOT within_sla) AS late_share_rider_wait,
       count(*) FILTER (WHERE NOT within_sla AND main_overrun_stage = 'travel')     / count(*) FILTER (WHERE NOT within_sla) AS late_share_travel
FROM per_order
GROUP BY node_id
ORDER BY node_id;
