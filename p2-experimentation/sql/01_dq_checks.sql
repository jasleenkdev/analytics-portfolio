-- 01_dq_checks.sql
-- Business question: can the assignment log, order feed and pilot panel be trusted for inference?
-- Output: dq_report (one row per check) and dq_assignment_daily (arm counts per assignment day,
-- the input to the per-day sample-ratio test).
-- Variables: experiment_start, assignment_days, observation_days, pilot_start, pilot_pre_days, pilot_post_days.

CREATE OR REPLACE TABLE dq_assignment_daily AS
SELECT CAST(assigned_at AS DATE) AS assign_date,
       count(*) FILTER (WHERE variant = 'control')   AS n_control,
       count(*) FILTER (WHERE variant = 'treatment') AS n_treatment
FROM assignments
GROUP BY ALL
ORDER BY assign_date;

CREATE OR REPLACE TABLE dq_report AS
WITH window_bounds AS (
    SELECT CAST(getvariable('experiment_start') AS TIMESTAMP) AS t0,
           CAST(getvariable('experiment_start') AS TIMESTAMP)
               + to_days(CAST(getvariable('assignment_days') + getvariable('observation_days') AS INTEGER)) AS t1
),
expected_grid AS (
    SELECT n.node_id, CAST(getvariable('pilot_start') AS DATE) + CAST(d AS INTEGER) AS ops_date
    FROM pilot_nodes n
    CROSS JOIN range(CAST(getvariable('pilot_pre_days') + getvariable('pilot_post_days') AS INTEGER)) r(d)
),
checks AS (
    SELECT 'users with more than one assignment row' AS check_name, 'assignments' AS table_name,
           (SELECT count(*) FROM (SELECT user_id FROM assignments GROUP BY 1 HAVING count(*) > 1)) AS failing_rows,
           (SELECT count(*) FROM assignments) AS total_rows, 'keep first assignment' AS action
    UNION ALL
    SELECT 'assignment outside the assignment week', 'assignments',
           count(*) FILTER (WHERE CAST(assigned_at AS DATE) NOT BETWEEN CAST(getvariable('experiment_start') AS DATE)
                            AND CAST(getvariable('experiment_start') AS DATE) + CAST(getvariable('assignment_days') - 1 AS INTEGER)),
           count(*), 'exclude'
    FROM assignments
    UNION ALL
    SELECT 'assignment for an unknown user', 'assignments',
           count(*) FILTER (WHERE u.user_id IS NULL), count(*), 'exclude'
    FROM assignments a LEFT JOIN users u USING (user_id)
    UNION ALL
    SELECT 'users ordering during the test with no assignment record', 'orders',
           count(DISTINCT o.user_id) FILTER (WHERE a.user_id IS NULL),
           count(DISTINCT o.user_id),
           'report: possible lost assignment logs; check the daily split'
    FROM orders o CROSS JOIN window_bounds w LEFT JOIN assignments a USING (user_id)
    WHERE o.order_ts >= w.t0 AND o.order_ts < w.t1
    UNION ALL
    SELECT 'orders with null keys or non-positive basket', 'orders',
           count(*) FILTER (WHERE order_id IS NULL OR user_id IS NULL OR order_ts IS NULL OR basket_value <= 0), count(*), 'exclude'
    FROM orders
    UNION ALL
    SELECT 'duplicate order ids', 'orders', count(*) - count(DISTINCT order_id), count(*), 'drop duplicates'
    FROM orders
    UNION ALL
    SELECT 'pilot node-days missing from the panel', 'pilot_daily_ops',
           count(*) FILTER (WHERE p.node_id IS NULL), count(*), 'keep panel unbalanced; no imputation'
    FROM expected_grid g LEFT JOIN pilot_daily_ops p USING (node_id, ops_date)
    UNION ALL
    SELECT 'pilot rows with impossible counts', 'pilot_daily_ops',
           count(*) FILTER (WHERE orders <= 0 OR rider_hours <= 0 OR orders_within_sla > orders OR defect_orders > orders),
           count(*), 'exclude'
    FROM pilot_daily_ops
)
SELECT check_name, table_name, failing_rows, total_rows,
       round(100.0 * failing_rows / nullif(total_rows, 0), 4) AS failing_pct,
       CASE WHEN failing_rows = 0 THEN 'pass' ELSE 'issue' END AS status, action
FROM checks;
