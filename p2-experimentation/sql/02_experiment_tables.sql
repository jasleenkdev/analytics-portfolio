-- 02_experiment_tables.sql
-- Business question: what did each assigned user do in their observation window, and what did they
-- do before the test (the CUPED covariate)?
-- exp_users         one row per assigned user: arm, assignment day, segments, pre-period behaviour
-- exp_user_metrics  orders, GMV, margin, fees, delivery cost and contribution in the user's window
-- exp_user_week     the same by week since assignment (novelty)
-- contribution = product margin + delivery fee charged - delivery cost
-- Variables: experiment_start, pre_period_days, observation_days.

CREATE OR REPLACE TABLE exp_users AS
WITH first_assignment AS (
    SELECT * FROM assignments QUALIFY row_number() OVER (PARTITION BY user_id ORDER BY assigned_at) = 1
),
pre AS (
    SELECT user_id,
           count(*)                                              AS pre_orders,
           sum(basket_value)                                     AS pre_gmv,
           sum(product_margin + delivery_fee - delivery_cost)    AS pre_contribution
    FROM orders
    WHERE order_ts <  CAST(getvariable('experiment_start') AS TIMESTAMP)
      AND order_ts >= CAST(getvariable('experiment_start') AS TIMESTAMP) - to_days(CAST(getvariable('pre_period_days') AS INTEGER))
    GROUP BY user_id
)
SELECT a.user_id, a.variant, a.assigned_at,
       CAST(a.assigned_at AS DATE)                                         AS assign_date,
       date_diff('day', CAST(getvariable('experiment_start') AS DATE), CAST(a.assigned_at AS DATE)) AS assign_day,
       u.platform, u.zone,
       CASE WHEN date_diff('day', u.signup_date, CAST(getvariable('experiment_start') AS DATE)) < 90
            THEN 'new (<90 days)' ELSE 'established' END                 AS tenure,
       coalesce(p.pre_orders, 0)        AS pre_orders,
       coalesce(p.pre_gmv, 0)           AS pre_gmv,
       coalesce(p.pre_contribution, 0)  AS pre_contribution
FROM first_assignment a
JOIN users u USING (user_id)
LEFT JOIN pre p USING (user_id);

CREATE OR REPLACE TABLE exp_orders AS
SELECT o.*, e.variant, e.assign_day,
       1 + CAST(floor(epoch(o.order_ts - e.assigned_at) / 86400 / 7) AS INTEGER) AS week_since_assignment,
       o.product_margin + o.delivery_fee - o.delivery_cost AS contribution
FROM orders o JOIN exp_users e USING (user_id)
WHERE o.order_ts >= e.assigned_at
  AND o.order_ts <  e.assigned_at + to_days(CAST(getvariable('observation_days') AS INTEGER));

CREATE OR REPLACE TABLE exp_user_metrics AS
SELECT e.*,
       count(o.order_id)                                   AS orders,
       coalesce(sum(o.basket_value), 0)                    AS gmv,
       coalesce(sum(o.product_margin), 0)                  AS product_margin,
       coalesce(sum(o.delivery_fee), 0)                    AS fee_revenue,
       coalesce(sum(o.delivery_cost), 0)                   AS delivery_cost,
       coalesce(sum(o.contribution), 0)                    AS contribution,
       count(o.order_id) FILTER (WHERE o.high_margin_basket) AS high_margin_orders,
       count(o.order_id) FILTER (WHERE o.delivery_fee = 0)   AS free_delivery_orders,
       CAST(count(o.order_id) > 0 AS INTEGER)              AS converted
FROM exp_users e LEFT JOIN exp_orders o USING (user_id)
GROUP BY ALL;

CREATE OR REPLACE TABLE exp_user_week AS
WITH weeks AS (SELECT unnest(range(1, CAST(getvariable('observation_days') / 7 AS INTEGER) + 1)) AS week)
SELECT e.user_id, e.variant, e.tenure, w.week,
       count(o.order_id)                     AS orders,
       coalesce(sum(o.contribution), 0)      AS contribution,
       coalesce(sum(o.basket_value), 0)      AS gmv
FROM exp_users e
CROSS JOIN weeks w
LEFT JOIN exp_orders o ON o.user_id = e.user_id AND o.week_since_assignment = w.week
GROUP BY ALL;
