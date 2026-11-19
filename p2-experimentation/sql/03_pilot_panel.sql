-- 03_pilot_panel.sql
-- Business question: how did pilot and control nodes perform each day, before and after the switch-on?
-- pilot_panel: one row per node-day with group, post flag, days relative to start and the decision metrics.
-- cost per order = rider hours x rider_cost_per_hour / orders.
-- Variables: rider_cost_per_hour, sla_minutes.

CREATE OR REPLACE TABLE pilot_panel AS
WITH start AS (SELECT min(start_date) AS start_date FROM pilot_rollout)
SELECT d.node_id, n.pilot_group, d.ops_date,
       n.pilot_group = 'treatment'                         AS treated,
       d.ops_date >= s.start_date                          AS post,
       date_diff('day', s.start_date, d.ops_date)          AS rel_day,
       CAST(floor(date_diff('day', s.start_date, d.ops_date) / 7) AS INTEGER) AS rel_week,
       d.orders, d.rider_hours, d.delivery_min_sum, d.orders_within_sla, d.defect_orders,
       d.rider_hours * 60 / d.orders                       AS rider_min_per_order,
       d.rider_hours * getvariable('rider_cost_per_hour') / d.orders AS cost_per_order,
       d.delivery_min_sum / d.orders                       AS mean_delivery_min,
       d.orders_within_sla / d.orders                      AS pct_within_sla,
       d.defect_orders / d.orders                          AS defect_rate
FROM pilot_daily_ops d
JOIN pilot_nodes n USING (node_id)
CROSS JOIN start s
WHERE d.orders > 0 AND d.rider_hours > 0;
