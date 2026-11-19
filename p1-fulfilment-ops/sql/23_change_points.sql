-- 23_change_points.sql
-- Business question: did any node's performance shift step-wise during the period (a process change,
-- a new manager, a layout change), and from which day?
-- Series: each node's daily median pick minutes minus the other nodes' daily median, so weather and
-- network-wide demand swings cancel out. Every day is tried as a split point; the split with the largest
-- Welch t between the before and after means is the node's candidate change point. Significance of the
-- scan (which inflates t) is assessed by permutation in analysis/change_points.py.
-- Variables: start_date, change_min_segment_days.

CREATE OR REPLACE TABLE node_daily AS
SELECT node_id, order_date,
       date_diff('day', CAST(getvariable('start_date') AS DATE), order_date) AS day_idx,
       count(*)                           AS orders_timed,
       median(pick_min)                   AS median_pick_min,
       median(rider_wait_min)             AS median_wait_min,
       median(delivery_min)               AS median_delivery_min,
       quantile_cont(delivery_min, 0.9)   AS p90_delivery_min,
       avg(CAST(within_sla AS DOUBLE))    AS pct_within_sla
FROM order_timeline WHERE timing_valid
GROUP BY ALL;

CREATE OR REPLACE TABLE node_daily_gap AS
WITH others AS (
    -- leave-one-out network median: a node's own shift must not move its benchmark
    SELECT n.node_id, t.order_date, median(t.pick_min) AS others_median_pick_min
    FROM order_timeline t JOIN nodes n ON t.node_id <> n.node_id
    WHERE t.timing_valid
    GROUP BY ALL
)
SELECT d.node_id, d.order_date, d.day_idx, d.median_pick_min - o.others_median_pick_min AS pick_gap
FROM node_daily d JOIN others o USING (node_id, order_date);

CREATE OR REPLACE TABLE change_point_scan AS
WITH splits AS (SELECT DISTINCT day_idx AS k FROM node_daily_gap),
seg AS (
    SELECT g.node_id, s.k,
           avg(pick_gap)      FILTER (WHERE day_idx <  k) AS mean_before,
           avg(pick_gap)      FILTER (WHERE day_idx >= k) AS mean_after,
           var_samp(pick_gap) FILTER (WHERE day_idx <  k) AS var_before,
           var_samp(pick_gap) FILTER (WHERE day_idx >= k) AS var_after,
           count(*)           FILTER (WHERE day_idx <  k) AS n_before,
           count(*)           FILTER (WHERE day_idx >= k) AS n_after
    FROM node_daily_gap g CROSS JOIN splits s
    GROUP BY g.node_id, s.k
)
SELECT node_id, k AS split_day_idx,
       CAST(getvariable('start_date') AS DATE) + CAST(k AS INTEGER) AS split_date,
       mean_before, mean_after, n_before, n_after,
       (mean_after - mean_before) / sqrt(var_before / n_before + var_after / n_after) AS welch_t
FROM seg
WHERE n_before >= getvariable('change_min_segment_days') AND n_after >= getvariable('change_min_segment_days');

CREATE OR REPLACE TABLE change_point_best AS
SELECT * FROM change_point_scan
QUALIFY row_number() OVER (PARTITION BY node_id ORDER BY abs(welch_t) DESC) = 1;
