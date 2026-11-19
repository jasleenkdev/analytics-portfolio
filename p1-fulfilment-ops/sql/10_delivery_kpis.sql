-- 10_delivery_kpis.sql
-- Business question: how fast do we deliver, how often do we meet the SLA, and where do we lose orders?
-- Grain: kpi_delivery_node_day (node x day) and kpi_delivery_node (node, whole period) plus a network row.
-- P50/P90 come from QUANTILE_CONT over valid timelines; cancellations count every order placed.
-- Variables: sla_minutes.

CREATE OR REPLACE TABLE kpi_delivery_node_day AS
SELECT node_id,
       order_date,
       count(*)                                              AS orders_placed,
       count(*) FILTER (WHERE status = 'cancelled')          AS orders_cancelled,
       count(*) FILTER (WHERE timing_valid)                  AS orders_timed,
       count(*) FILTER (WHERE within_sla)                    AS orders_within_sla,
       sum(delivery_min) FILTER (WHERE timing_valid)         AS delivery_min_sum,
       quantile_cont(delivery_min, 0.5) FILTER (WHERE timing_valid) AS p50_delivery_min,
       quantile_cont(delivery_min, 0.9) FILTER (WHERE timing_valid) AS p90_delivery_min,
       sum(order_value)                                      AS gmv_placed
FROM order_timeline
GROUP BY ALL;

CREATE OR REPLACE TABLE kpi_delivery_node AS
WITH per_node AS (
    SELECT node_id,
           count(*)                                               AS orders_placed,
           count(*) FILTER (WHERE status = 'cancelled')           AS orders_cancelled,
           count(*) FILTER (WHERE timing_valid)                   AS orders_timed,
           count(*) FILTER (WHERE within_sla)                     AS orders_within_sla,
           quantile_cont(delivery_min, 0.5) FILTER (WHERE timing_valid) AS p50_delivery_min,
           quantile_cont(delivery_min, 0.9) FILTER (WHERE timing_valid) AS p90_delivery_min,
           avg(delivery_min) FILTER (WHERE timing_valid)          AS mean_delivery_min,
           sum(order_value) FILTER (WHERE status = 'cancelled')   AS gmv_cancelled
    FROM order_timeline
    GROUP BY GROUPING SETS ((node_id), ())
)
SELECT coalesce(node_id, 'ALL')                          AS node_id,
       orders_placed, orders_cancelled, orders_timed, orders_within_sla,
       orders_within_sla / orders_timed                  AS pct_within_sla,
       orders_cancelled / orders_placed                  AS cancel_rate,
       p50_delivery_min, p90_delivery_min, mean_delivery_min, gmv_cancelled
FROM per_node
ORDER BY node_id = 'ALL', node_id;

-- node x hour-of-day profile (the heatmap): which hours break the SLA at which node?
CREATE OR REPLACE TABLE kpi_node_hour_profile AS
SELECT node_id, order_hour,
       count(*) FILTER (WHERE timing_valid)                          AS orders_timed,
       avg(CAST(within_sla AS DOUBLE))                               AS pct_within_sla,
       quantile_cont(delivery_min, 0.9) FILTER (WHERE timing_valid)  AS p90_delivery_min,
       avg(pick_min) FILTER (WHERE timing_valid)                     AS mean_pick_min,
       avg(rider_wait_min) FILTER (WHERE timing_valid)               AS mean_rider_wait_min,
       avg(travel_min) FILTER (WHERE timing_valid)                   AS mean_travel_min
FROM order_timeline
GROUP BY ALL
ORDER BY node_id, order_hour;

-- weekly network trend with a 7-day rolling SLA rate built from daily counts (not an average of rates)
CREATE OR REPLACE TABLE kpi_network_daily AS
WITH daily AS (
    SELECT order_date,
           sum(orders_placed)     AS orders_placed,
           sum(orders_timed)      AS orders_timed,
           sum(orders_within_sla) AS orders_within_sla,
           sum(orders_cancelled)  AS orders_cancelled
    FROM kpi_delivery_node_day GROUP BY order_date
)
SELECT *,
       orders_within_sla / orders_timed AS pct_within_sla,
       sum(orders_within_sla) OVER w7 / sum(orders_timed) OVER w7 AS pct_within_sla_7d
FROM daily
WINDOW w7 AS (ORDER BY order_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)
ORDER BY order_date;
