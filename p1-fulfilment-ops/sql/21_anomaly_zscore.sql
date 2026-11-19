-- 21_anomaly_zscore.sql
-- Business question: which node-hours were abnormally slow, either against the node's own recent
-- history (something changed) or against the other nodes at the same hour (something is chronically wrong)?
-- Temporal z: the cell's mean delivery minutes vs the same node, same hour of day and same day type
--   (weekday / weekend) over the previous rolling_window_obs such cells (rolling, no look-ahead).
--   Robust: centre = rolling median, scale = 1.4826 x rolling MAD, so yesterday's incident does not
--   inflate the baseline and hide today's.
-- Peer z:     the cell vs all other nodes in the same date-hour (leave-one-out mean and sd).
-- A cell with at least min_orders_per_cell orders is flagged when z_temporal >= robust_z_threshold or
-- z_peer >= zscore_threshold (only slow-side deviations matter operationally).
-- The same windows also give each stage's baseline, used by the drill-down in 22_anomaly_drilldown.sql.
-- Variables: zscore_threshold, robust_z_threshold, rolling_window_obs, min_orders_per_cell.

CREATE OR REPLACE TABLE anomaly_scores AS
WITH base AS (
    SELECT *, dayofweek(cell_date) IN (0, 6) AS is_weekend
    FROM node_hour_cells
    WHERE orders_timed >= getvariable('min_orders_per_cell')
),
temporal AS (
    SELECT *,
           median(mean_delivery_min) OVER w      AS hist_mean,
           1.4826 * mad(mean_delivery_min) OVER w AS hist_sd,
           count(*) OVER w                       AS hist_n,
           median(mean_pick_min) OVER w          AS hist_pick,
           median(mean_wait_min) OVER w          AS hist_wait,
           median(mean_travel_min) OVER w        AS hist_travel,
           median(orders_placed) OVER w          AS hist_orders_placed,
           median(riders_online) OVER w          AS hist_riders_online
    FROM base
    WINDOW w AS (PARTITION BY node_id, cell_hour, is_weekend ORDER BY cell_date
                 ROWS BETWEEN getvariable('rolling_window_obs') PRECEDING AND 1 PRECEDING)
),
peer AS (
    -- leave-one-out peer statistics from window sums: each cell is compared only with the other nodes
    SELECT *,
           (sum(mean_delivery_min) OVER h - mean_delivery_min) / (count(*) OVER h - 1) AS peer_mean,
           sqrt(greatest(
               (sum(mean_delivery_min * mean_delivery_min) OVER h - mean_delivery_min * mean_delivery_min
                - (sum(mean_delivery_min) OVER h - mean_delivery_min) ^ 2 / (count(*) OVER h - 1))
               / (count(*) OVER h - 2), 0))                                             AS peer_sd,
           count(*) OVER h - 1                                                          AS peer_n,
           (sum(mean_pick_min) OVER h - mean_pick_min) / (count(*) OVER h - 1)          AS peer_pick,
           (sum(mean_wait_min) OVER h - mean_wait_min) / (count(*) OVER h - 1)          AS peer_wait,
           (sum(mean_travel_min) OVER h - mean_travel_min) / (count(*) OVER h - 1)      AS peer_travel,
           (sum(orders_per_picker) OVER h - orders_per_picker) / (count(*) OVER h - 1)  AS peer_orders_per_picker,
           (sum(rider_utilisation) OVER h - rider_utilisation) / (count(*) OVER h - 1)  AS peer_rider_utilisation
    FROM temporal
    WINDOW h AS (PARTITION BY hour_ts)
)
SELECT * EXCLUDE (is_weekend),
       CASE WHEN hist_n >= 7 AND hist_sd > 0 THEN (mean_delivery_min - hist_mean) / hist_sd END AS z_temporal,
       CASE WHEN peer_n >= 5 AND peer_sd > 0 THEN (mean_delivery_min - peer_mean) / peer_sd END AS z_peer
FROM peer;

CREATE OR REPLACE TABLE anomaly_flags AS
SELECT *,
       CASE
           WHEN z_temporal >= getvariable('robust_z_threshold') AND z_peer >= getvariable('zscore_threshold') THEN 'both'
           WHEN z_temporal >= getvariable('robust_z_threshold') THEN 'temporal'
           ELSE 'peer'
       END AS flag_type
FROM anomaly_scores
WHERE z_temporal >= getvariable('robust_z_threshold') OR z_peer >= getvariable('zscore_threshold');
