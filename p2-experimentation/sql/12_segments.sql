-- 12_segments.sql
-- Business question: does the effect differ by platform, zone or customer tenure?
-- Descriptive sufficient statistics per segment and arm; the tests (with CUPED and a
-- multiple-comparison correction) run in analysis/stats.py on the user-level table.
-- Variables: none.

CREATE OR REPLACE TABLE exp_segment_summary AS
WITH long AS (
    SELECT 'platform' AS dimension, platform AS segment, * FROM exp_user_metrics
    UNION ALL SELECT 'zone', zone, * FROM exp_user_metrics
    UNION ALL SELECT 'tenure', tenure, * FROM exp_user_metrics
)
SELECT dimension, segment, variant, count(*) AS n,
       avg(orders) AS mean_orders, avg(contribution) AS mean_contribution, var_samp(contribution) AS var_contribution,
       avg(gmv) AS mean_gmv
FROM long GROUP BY ALL ORDER BY dimension, segment, variant;
