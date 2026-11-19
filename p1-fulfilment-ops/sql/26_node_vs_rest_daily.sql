-- 26_node_vs_rest_daily.sql
-- Business question: on each day, how did a node compare with the rest of the network?
-- Leave-one-out daily series used for before/after (difference-in-differences) on any node with a
-- detected change point.
-- Variables: none.

CREATE OR REPLACE TABLE node_vs_rest_daily AS
WITH rest AS (
    SELECT n.node_id, t.order_date,
           median(t.pick_min)                 AS rest_median_pick_min,
           quantile_cont(t.delivery_min, 0.9) AS rest_p90_delivery_min,
           avg(CAST(t.within_sla AS DOUBLE))  AS rest_pct_within_sla
    FROM order_timeline t JOIN nodes n ON t.node_id <> n.node_id
    WHERE t.timing_valid
    GROUP BY ALL
)
SELECT d.node_id, d.order_date, d.day_idx,
       d.median_pick_min, d.p90_delivery_min, d.pct_within_sla,
       r.rest_median_pick_min, r.rest_p90_delivery_min, r.rest_pct_within_sla
FROM node_daily d JOIN rest r USING (node_id, order_date)
ORDER BY node_id, order_date;
