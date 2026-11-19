-- 13_pilot_summary.sql
-- Business question: did pilot nodes move differently from control nodes after the switch-on,
-- and did they move in parallel before it?
-- pilot_weekly  group x week relative to start, order-weighted metrics (the parallel-trends picture)
-- pilot_2x2     group x period means, the raw difference-in-differences table
-- Variables: none.

CREATE OR REPLACE TABLE pilot_weekly AS
SELECT pilot_group, rel_week,
       sum(rider_hours) * 60 / sum(orders)         AS rider_min_per_order,
       sum(cost_per_order * orders) / sum(orders)  AS cost_per_order,
       sum(delivery_min_sum) / sum(orders)         AS mean_delivery_min,
       sum(orders_within_sla) / sum(orders)        AS pct_within_sla,
       sum(defect_orders) / sum(orders)            AS defect_rate,
       sum(orders)                                 AS orders
FROM pilot_panel GROUP BY ALL ORDER BY pilot_group, rel_week;

CREATE OR REPLACE TABLE pilot_2x2 AS
WITH cell AS (
    SELECT pilot_group, CASE WHEN post THEN 'after' ELSE 'before' END AS period,
           sum(cost_per_order * orders) / sum(orders) AS cost_per_order,
           sum(delivery_min_sum) / sum(orders)        AS mean_delivery_min,
           sum(orders_within_sla) / sum(orders)       AS pct_within_sla,
           sum(defect_orders) / sum(orders)           AS defect_rate
    FROM pilot_panel GROUP BY ALL
)
UNPIVOT cell ON cost_per_order, mean_delivery_min, pct_within_sla, defect_rate INTO NAME metric VALUE value;
