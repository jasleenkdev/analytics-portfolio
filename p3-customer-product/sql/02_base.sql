-- 02_base.sql
-- Business question: what does each customer's order history look like (sequence, gaps, first
-- experience), and what is each basket line worth?
-- order_facts     one row per order: sequence number (ROW_NUMBER), days since the previous order (LAG),
--                 signup cohort month, months since first order, margin, first-order issue flag
-- customer_facts  one row per ordering customer: cohort, channel, platform, first-order experience, totals
-- line_facts      one row per basket line with revenue and gross margin
-- Variables: none.

CREATE OR REPLACE TABLE line_facts AS
SELECT l.order_id, l.sku_id, s.category, s.perishable, l.qty,
       l.qty * l.unit_price                      AS revenue,
       l.qty * (l.unit_price - l.unit_cost)      AS gross_margin,
       o.node_id, o.customer_id, o.order_ts, CAST(o.order_ts AS DATE) AS order_date
FROM order_lines l JOIN orders o USING (order_id) JOIN skus s USING (sku_id);

CREATE OR REPLACE TABLE order_facts AS
WITH margin AS (SELECT order_id, sum(revenue) AS revenue, sum(gross_margin) AS gross_margin, count(*) AS lines
                FROM line_facts GROUP BY 1),
seq AS (
    SELECT o.*, m.revenue, m.gross_margin, m.lines,
           row_number() OVER (PARTITION BY o.customer_id ORDER BY o.order_ts, o.order_id) AS order_seq,
           date_diff('day', lag(o.order_ts) OVER (PARTITION BY o.customer_id ORDER BY o.order_ts, o.order_id), o.order_ts)
               AS days_since_prev,
           min(o.order_ts) OVER (PARTITION BY o.customer_id) AS first_order_ts
    FROM orders o JOIN margin m USING (order_id)
)
SELECT s.*,
       date_trunc('month', s.first_order_ts)                                   AS cohort_month,
       date_diff('month', date_trunc('month', s.first_order_ts), date_trunc('month', s.order_ts)) AS months_since_first,
       i.issue_type IS NOT NULL                                                AS had_issue
FROM seq s LEFT JOIN (SELECT DISTINCT ON (order_id) order_id, issue_type FROM order_issues) i USING (order_id);

CREATE OR REPLACE TABLE customer_facts AS
SELECT c.customer_id, c.acquisition_channel, c.platform, c.home_node_id, c.signup_date,
       f.cohort_month, f.first_order_ts,
       bool_or(f.had_issue) FILTER (WHERE f.order_seq = 1)   AS first_order_issue,
       count(*)                                              AS orders,
       sum(f.revenue)                                        AS revenue,
       sum(f.gross_margin)                                   AS gross_margin,
       max(f.order_ts)                                       AS last_order_ts,
       min(f.order_ts) FILTER (WHERE f.order_seq = 2)        AS second_order_ts
FROM customers c JOIN order_facts f USING (customer_id)
GROUP BY ALL;
