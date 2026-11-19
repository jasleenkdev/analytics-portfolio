-- 11_retention.sql
-- Business question: which customers come back, how quickly, and what distinguishes the ones who stay?
-- cohort_retention  first-order cohort month x months since first order: share of the cohort ordering
--                   in that month (classic triangle)
-- repeat_curve      share of customers with a second order within N days, for customers observable N days
-- retention_drivers 90-day repeat rate by acquisition channel, platform and first-order experience
-- Day differences are calendar days (date_diff counts midnight boundaries).
-- Variables: as_of_date.

CREATE OR REPLACE TABLE cohort_retention AS
WITH sizes AS (SELECT cohort_month, count(*) AS cohort_size FROM customer_facts GROUP BY 1),
active AS (SELECT cohort_month, months_since_first, count(DISTINCT customer_id) AS active_customers
           FROM order_facts GROUP BY ALL)
SELECT a.cohort_month, a.months_since_first, s.cohort_size, a.active_customers,
       a.active_customers / s.cohort_size AS retention
FROM active a JOIN sizes s USING (cohort_month)
ORDER BY a.cohort_month, a.months_since_first;

CREATE OR REPLACE TABLE repeat_curve AS
WITH horizons AS (SELECT unnest([7, 14, 30, 60, 90, 120, 180]) AS days)
SELECT h.days,
       count(*)                                                                         AS customers_observable,
       count(*) FILTER (WHERE date_diff('day', c.first_order_ts, c.second_order_ts) <= h.days) / count(*) AS repeat_rate
FROM customer_facts c CROSS JOIN horizons h
WHERE date_diff('day', c.first_order_ts, CAST(getvariable('as_of_date') AS TIMESTAMP)) >= h.days
GROUP BY h.days ORDER BY h.days;

CREATE OR REPLACE TABLE retention_drivers AS
WITH eligible AS (
    SELECT *, date_diff('day', first_order_ts, second_order_ts) <= 90 AS repeat_90d,
           CASE WHEN first_order_issue THEN 'problem on first order' ELSE 'clean first order' END AS first_experience
    FROM customer_facts
    WHERE date_diff('day', first_order_ts, CAST(getvariable('as_of_date') AS TIMESTAMP)) >= 90
),
long AS (
    SELECT 'acquisition_channel' AS driver, acquisition_channel AS level, repeat_90d FROM eligible
    UNION ALL SELECT 'platform', platform, repeat_90d FROM eligible
    UNION ALL SELECT 'first_order_experience', first_experience, repeat_90d FROM eligible
)
SELECT driver, level, count(*) AS customers,
       avg(CAST(coalesce(repeat_90d, false) AS DOUBLE)) AS repeat_rate_90d
FROM long GROUP BY ALL ORDER BY driver, repeat_rate_90d DESC;
