-- 12_rfm.sql
-- Business question: who are our best, slipping and lost customers right now?
-- Recency, frequency and monetary value as of as_of_date, scored 1-5 with NTILE (5 = best), then
-- mapped to named segments with simple, explainable rules. customer_id breaks ties so reruns are identical.
-- Variables: as_of_date, rfm_bins.

CREATE OR REPLACE TABLE rfm AS
WITH base AS (
    SELECT customer_id, acquisition_channel,
           date_diff('day', last_order_ts, CAST(getvariable('as_of_date') AS TIMESTAMP)) AS recency_days,
           orders AS frequency, gross_margin AS monetary
    FROM customer_facts
),
scored AS (
    SELECT *,
           ntile(getvariable('rfm_bins')) OVER (ORDER BY recency_days DESC, customer_id) AS r_score,
           ntile(getvariable('rfm_bins')) OVER (ORDER BY frequency, monetary, customer_id) AS f_score,
           ntile(getvariable('rfm_bins')) OVER (ORDER BY monetary, customer_id) AS m_score
    FROM base
)
SELECT *,
       CASE
           WHEN r_score >= 4 AND f_score >= 4                 THEN 'champions'
           WHEN r_score >= 3 AND f_score >= 3                 THEN 'loyal'
           WHEN r_score >= 4 AND f_score <= 2                 THEN 'new or promising'
           WHEN r_score <= 2 AND f_score >= 3                 THEN 'at risk'
           WHEN r_score = 3 AND f_score <= 2                  THEN 'needs attention'
           ELSE 'hibernating'
       END AS segment
FROM scored;

CREATE OR REPLACE TABLE rfm_segments AS
SELECT segment, count(*) AS customers, count(*) / sum(count(*)) OVER () AS share_customers,
       sum(monetary) / sum(sum(monetary)) OVER () AS share_margin,
       avg(recency_days) AS mean_recency_days, avg(frequency) AS mean_orders, avg(monetary) AS mean_margin
FROM rfm GROUP BY segment ORDER BY share_margin DESC;
