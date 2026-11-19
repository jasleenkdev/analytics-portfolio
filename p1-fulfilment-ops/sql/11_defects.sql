-- 11_defects.sql
-- Business question: which defects cost us most, where, and how often does an order go wrong?
-- defect rate = orders with at least one refund claim of that type / delivered orders.
-- Variables: none.

CREATE OR REPLACE TABLE kpi_defects_node AS
WITH delivered AS (
    SELECT node_id, count(*) AS delivered_orders, sum(order_value) AS delivered_gmv
    FROM order_timeline WHERE status = 'delivered' GROUP BY node_id
),
per_type AS (
    SELECT t.node_id, d.defect_type,
           count(DISTINCT d.order_id) AS orders_with_defect,
           count(*)                   AS claims,
           sum(d.refund_amount)       AS refund_amount
    FROM defects d JOIN order_timeline t USING (order_id)
    GROUP BY ALL
),
types AS (SELECT DISTINCT defect_type FROM defects),
grid AS (SELECT node_id, defect_type FROM delivered CROSS JOIN types)
SELECT g.node_id, g.defect_type,
       dl.delivered_orders,
       coalesce(p.orders_with_defect, 0)                       AS orders_with_defect,
       coalesce(p.claims, 0)                                   AS claims,
       coalesce(p.refund_amount, 0)                            AS refund_amount,
       coalesce(p.orders_with_defect, 0) / dl.delivered_orders AS defect_rate,
       coalesce(p.refund_amount, 0) / dl.delivered_gmv         AS refund_pct_gmv
FROM grid g
JOIN delivered dl USING (node_id)
LEFT JOIN per_type p USING (node_id, defect_type)
ORDER BY g.node_id, g.defect_type;

-- network roll-up by type plus the any-defect rate (an order with two defect types counts once)
CREATE OR REPLACE TABLE kpi_defects_network AS
WITH delivered AS (SELECT count(*) AS n, sum(order_value) AS gmv FROM order_timeline WHERE status = 'delivered')
SELECT defect_type,
       count(DISTINCT order_id)                         AS orders_with_defect,
       count(DISTINCT order_id) / (SELECT n FROM delivered) AS defect_rate,
       sum(refund_amount)                               AS refund_amount,
       sum(refund_amount) / (SELECT gmv FROM delivered) AS refund_pct_gmv
FROM defects
GROUP BY ROLLUP (defect_type)
ORDER BY defect_type NULLS LAST;
