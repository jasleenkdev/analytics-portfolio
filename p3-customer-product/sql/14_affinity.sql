-- 14_affinity.sql
-- Business question: which products are bought together more than chance would predict?
-- For every SKU pair in the same basket: support = share of orders containing both; confidence(A->B) =
-- orders with both / orders with A; lift = support / (support A x support B). Only pairs seen in at
-- least affinity_min_orders orders are kept, so lift is not driven by tiny counts.
-- Variables: affinity_min_orders.

CREATE OR REPLACE TABLE sku_order_counts AS
SELECT sku_id, count(DISTINCT order_id) AS orders FROM line_facts GROUP BY 1;

CREATE OR REPLACE TABLE basket_affinity AS
WITH n AS (SELECT count(*) AS orders FROM orders),
pairs AS (
    SELECT a.sku_id AS sku_a, b.sku_id AS sku_b, count(*) AS together
    FROM line_facts a JOIN line_facts b ON a.order_id = b.order_id AND a.sku_id < b.sku_id
    GROUP BY ALL
    HAVING count(*) >= getvariable('affinity_min_orders')
)
SELECT p.sku_a, sa.category AS category_a, p.sku_b, sb.category AS category_b, p.together,
       p.together / n.orders                                         AS support,
       p.together / ca.orders                                        AS confidence_a_to_b,
       p.together / cb.orders                                        AS confidence_b_to_a,
       (p.together / n.orders) / ((ca.orders / n.orders) * (cb.orders / n.orders)) AS lift
FROM pairs p CROSS JOIN n
JOIN sku_order_counts ca ON ca.sku_id = p.sku_a
JOIN sku_order_counts cb ON cb.sku_id = p.sku_b
JOIN skus sa ON sa.sku_id = p.sku_a
JOIN skus sb ON sb.sku_id = p.sku_b
ORDER BY lift DESC;
