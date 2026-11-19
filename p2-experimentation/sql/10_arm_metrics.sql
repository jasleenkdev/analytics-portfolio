-- 10_arm_metrics.sql
-- Business question: how did the two arms differ on every user-level metric, and what do the
-- sufficient statistics (n, mean, variance) look like for inference?
-- exp_arm_summary: long format, one row per (variant, metric). Ratio metrics (per-order) are built from
-- per-user numerators and denominators so the delta method can be applied in Python.
-- Variables: none.

CREATE OR REPLACE TABLE exp_arm_summary AS
WITH long AS (
    UNPIVOT (
        SELECT variant, orders, gmv, contribution, product_margin, fee_revenue, delivery_cost,
               CAST(converted AS DOUBLE) AS converted, high_margin_orders, pre_contribution, pre_orders
        FROM exp_user_metrics
    ) ON orders, gmv, contribution, product_margin, fee_revenue, delivery_cost, converted, high_margin_orders,
         pre_contribution, pre_orders
    INTO NAME metric VALUE value
)
SELECT variant, metric, count(*) AS n, avg(value) AS mean, var_samp(value) AS variance, sum(value) AS total
FROM long
GROUP BY ALL
ORDER BY metric, variant;

-- per-order ratios with the moments the delta method needs: numerator x, denominator y per user
CREATE OR REPLACE TABLE exp_ratio_moments AS
WITH pairs AS (
    SELECT variant, 'gmv_per_order' AS metric, gmv AS x, orders AS y FROM exp_user_metrics
    UNION ALL SELECT variant, 'contribution_per_order', contribution, orders FROM exp_user_metrics
    UNION ALL SELECT variant, 'high_margin_share', high_margin_orders, orders FROM exp_user_metrics
    UNION ALL SELECT variant, 'free_delivery_share', free_delivery_orders, orders FROM exp_user_metrics
)
SELECT variant, metric, count(*) AS n,
       avg(x) AS mean_x, avg(y) AS mean_y, var_samp(x) AS var_x, var_samp(y) AS var_y, covar_samp(x, y) AS cov_xy,
       sum(x) / sum(y) AS ratio
FROM pairs GROUP BY ALL ORDER BY metric, variant;

-- basket value distribution around the two free-delivery thresholds (bunching check)
CREATE OR REPLACE TABLE exp_basket_hist AS
SELECT variant, floor(basket_value / 2) * 2 AS basket_bin, count(*) AS orders
FROM exp_orders
WHERE basket_value < 80
GROUP BY ALL ORDER BY variant, basket_bin;
