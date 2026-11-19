-- 01_dq_checks.sql
-- Business question: are customers, baskets, funnel events and the stock ledger consistent enough to
-- base retention, assortment and wastage decisions on?
-- Output: dq_report, one row per check.
-- Variables: none.

CREATE OR REPLACE TABLE dq_report AS
WITH step_rank AS (
    SELECT session_id, step,
           CASE step WHEN 'visit' THEN 1 WHEN 'browse' THEN 2 WHEN 'add_to_cart' THEN 3
                     WHEN 'checkout' THEN 4 WHEN 'payment_attempt' THEN 5 WHEN 'order_placed' THEN 6 END AS k
    FROM funnel_events
),
line_totals AS (SELECT order_id, sum(qty * unit_price) AS v FROM order_lines GROUP BY 1),
checks AS (
    SELECT 'orders placed before the customer signed up' AS check_name, 'orders' AS table_name,
           count(*) FILTER (WHERE o.order_ts < c.signup_date) AS failing_rows, count(*) AS total_rows, 'exclude' AS action
    FROM orders o JOIN customers c USING (customer_id)
    UNION ALL
    SELECT 'orders without basket lines', 'orders',
           count(*) FILTER (WHERE l.order_id IS NULL), count(*), 'exclude'
    FROM orders o LEFT JOIN line_totals l USING (order_id)
    UNION ALL
    SELECT 'order value differs from the sum of its lines by more than 0.01', 'orders',
           count(*) FILTER (WHERE abs(o.order_value - l.v) > 0.01), count(*), 'use line totals'
    FROM orders o JOIN line_totals l USING (order_id)
    UNION ALL
    SELECT 'basket lines for SKUs the node does not range', 'order_lines',
           count(*) FILTER (WHERE r.sku_id IS NULL), count(*), 'report'
    FROM order_lines l JOIN orders o USING (order_id) LEFT JOIN node_range r ON r.node_id = o.node_id AND r.sku_id = l.sku_id
    UNION ALL
    SELECT 'basket lines priced differently from the catalogue', 'order_lines',
           count(*) FILTER (WHERE l.unit_price <> s.unit_price OR l.unit_cost <> s.unit_cost), count(*), 'report'
    FROM order_lines l JOIN skus s USING (sku_id)
    UNION ALL
    SELECT 'duplicate funnel events (session, step)', 'funnel_events',
           count(*) - count(DISTINCT (session_id, step)), count(*), 'keep first'
    FROM funnel_events
    UNION ALL
    SELECT 'sessions with a step missing before a later step', 'funnel_events',
           count(*) FILTER (WHERE n <> top), count(*), 'exclude from funnel'
    FROM (SELECT session_id, count(*) AS n, max(k) AS top FROM step_rank GROUP BY 1)
    UNION ALL
    SELECT 'orders whose session never reached order_placed', 'orders',
           count(*) FILTER (WHERE f.session_id IS NULL), count(*), 'report'
    FROM orders o LEFT JOIN (SELECT session_id FROM funnel_events WHERE step = 'order_placed') f USING (session_id)
    UNION ALL
    SELECT 'stock ledger does not balance (closing <> opening - sold - wasted)', 'inventory_daily',
           count(*) FILTER (WHERE closing_on_hand <> opening_on_hand - sold - wasted), count(*), 'exclude'
    FROM inventory_daily
    UNION ALL
    SELECT 'negative stock', 'inventory_daily',
           count(*) FILTER (WHERE least(opening_on_hand, closing_on_hand) < 0), count(*), 'exclude'
    FROM inventory_daily
    UNION ALL
    SELECT 'node-days with lost sales (units ordered but not in stock)', 'inventory_daily',
           count(*) FILTER (WHERE lost_sales > 0), count(*), 'report: short-shipped units'
    FROM inventory_daily
    UNION ALL
    SELECT 'customers who signed up but never ordered', 'customers',
           count(*) FILTER (WHERE o.customer_id IS NULL), count(*), 'keep: counts in funnel and acquisition, not retention'
    FROM customers c LEFT JOIN (SELECT DISTINCT customer_id FROM orders) o USING (customer_id)
)
SELECT check_name, table_name, failing_rows, total_rows,
       round(100.0 * failing_rows / nullif(total_rows, 0), 4) AS failing_pct,
       CASE WHEN failing_rows = 0 THEN 'pass' ELSE 'issue' END AS status, action
FROM checks;
