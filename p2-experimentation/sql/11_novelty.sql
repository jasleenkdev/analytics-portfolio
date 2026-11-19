-- 11_novelty.sql
-- Business question: does the treatment effect fade as the promotion stops being new?
-- Sufficient statistics per variant and week since assignment (every user has all weeks).
-- Variables: none.

CREATE OR REPLACE TABLE exp_week_summary AS
SELECT week, variant,
       count(*) AS n,
       avg(orders) AS mean_orders, var_samp(orders) AS var_orders,
       avg(contribution) AS mean_contribution, var_samp(contribution) AS var_contribution,
       avg(gmv) AS mean_gmv
FROM exp_user_week
GROUP BY ALL ORDER BY week, variant;
