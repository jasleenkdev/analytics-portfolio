-- 10_funnel.sql
-- Business question: where in the checkout funnel do sessions drop, and does it differ by platform,
-- app version or month?
-- funnel_segment_month: sessions reaching each step by platform x app version x month, plus step-to-step
-- conversion. funnel_overall: the same for all sessions. funnel_daily_payment: daily payment success
-- (order_placed / payment_attempt) by platform and version, the input to drop-off detection.
-- Variables: none.

CREATE OR REPLACE TABLE session_steps AS
SELECT s.session_id, s.platform, s.app_version, date_trunc('month', s.session_ts) AS month,
       CAST(s.session_ts AS DATE) AS session_date,
       bool_or(f.step = 'visit')           AS visit,
       bool_or(f.step = 'browse')          AS browse,
       bool_or(f.step = 'add_to_cart')     AS add_to_cart,
       bool_or(f.step = 'checkout')        AS checkout,
       bool_or(f.step = 'payment_attempt') AS payment_attempt,
       bool_or(f.step = 'order_placed')    AS order_placed
FROM sessions s JOIN funnel_events f USING (session_id)
GROUP BY ALL;

CREATE OR REPLACE TABLE funnel_segment_month AS
SELECT platform, app_version, month,
       count(*)                                  AS sessions,
       count(*) FILTER (WHERE browse)            AS browse,
       count(*) FILTER (WHERE add_to_cart)       AS add_to_cart,
       count(*) FILTER (WHERE checkout)          AS checkout,
       count(*) FILTER (WHERE payment_attempt)   AS payment_attempt,
       count(*) FILTER (WHERE order_placed)      AS order_placed,
       count(*) FILTER (WHERE add_to_cart) / count(*)                                       AS session_to_cart,
       count(*) FILTER (WHERE checkout) / nullif(count(*) FILTER (WHERE add_to_cart), 0)    AS cart_to_checkout,
       count(*) FILTER (WHERE payment_attempt) / nullif(count(*) FILTER (WHERE checkout), 0) AS checkout_to_payment,
       count(*) FILTER (WHERE order_placed) / nullif(count(*) FILTER (WHERE payment_attempt), 0) AS payment_success,
       count(*) FILTER (WHERE order_placed) / count(*)                                      AS session_conversion
FROM session_steps
GROUP BY ALL
ORDER BY platform, app_version, month;

CREATE OR REPLACE TABLE funnel_overall AS
WITH totals AS (
    SELECT count(*) AS visit, count(*) FILTER (WHERE browse) AS browse, count(*) FILTER (WHERE add_to_cart) AS add_to_cart,
           count(*) FILTER (WHERE checkout) AS checkout, count(*) FILTER (WHERE payment_attempt) AS payment_attempt,
           count(*) FILTER (WHERE order_placed) AS order_placed
    FROM session_steps
),
long AS (UNPIVOT totals ON visit, browse, add_to_cart, checkout, payment_attempt, order_placed INTO NAME step VALUE sessions)
SELECT step, sessions,
       sessions / first_value(sessions) OVER (ORDER BY sessions DESC) AS share_of_visits,
       sessions / lag(sessions) OVER (ORDER BY sessions DESC)         AS step_conversion
FROM long ORDER BY sessions DESC;

CREATE OR REPLACE TABLE funnel_daily_payment AS
SELECT platform, app_version, session_date,
       count(*) FILTER (WHERE payment_attempt) AS payment_attempts,
       count(*) FILTER (WHERE order_placed)    AS orders
FROM session_steps
GROUP BY ALL ORDER BY platform, app_version, session_date;
