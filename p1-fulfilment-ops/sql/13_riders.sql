-- 13_riders.sql
-- Business question: do we have the right number of riders online, and how hard are they working?
-- online minutes = rider shift minutes falling in each node-hour
-- busy minutes   = rider_assigned -> delivered plus an equal-length return leg (travel time),
--                  attributed to the hour of assignment
-- utilisation    = busy minutes / online minutes; orders per rider-hour = delivered orders / online hours
--                  (at hourly grain the ratio can exceed 1: trips that run into the next hour count in
--                  the hour they were assigned, so values above 1 mean demand outran online riders)
-- Variables: none.

CREATE OR REPLACE TABLE rider_online_node_hour AS
SELECT node_id, hour_ts, count(*) AS riders_online, count(*) * 60.0 AS online_min
FROM (
    SELECT node_id, unnest(generate_series(shift_start, shift_end - INTERVAL 1 HOUR, INTERVAL 1 HOUR)) AS hour_ts
    FROM rider_shifts
)
GROUP BY ALL;

CREATE OR REPLACE TABLE rider_busy_node_hour AS
SELECT node_id, date_trunc('hour', rider_assigned_ts) AS hour_ts,
       count(*) AS orders_delivered,
       sum(epoch(delivered_ts - rider_assigned_ts) / 60.0 + travel_min) AS busy_min
FROM order_timeline
WHERE timing_valid AND rider_assigned_ts <= delivered_ts
GROUP BY ALL;

CREATE OR REPLACE TABLE kpi_riders_node_hour AS
SELECT coalesce(o.node_id, b.node_id) AS node_id,
       coalesce(o.hour_ts, b.hour_ts) AS hour_ts,
       coalesce(o.riders_online, 0)   AS riders_online,
       coalesce(o.online_min, 0)      AS online_min,
       coalesce(b.busy_min, 0)        AS busy_min,
       coalesce(b.orders_delivered, 0) AS orders_delivered,
       b.busy_min / nullif(o.online_min, 0) AS utilisation
FROM rider_online_node_hour o
FULL JOIN rider_busy_node_hour b USING (node_id, hour_ts);

CREATE OR REPLACE TABLE kpi_riders_node AS
SELECT coalesce(node_id, 'ALL')                    AS node_id,
       sum(online_min) / 60.0                      AS rider_hours,
       sum(orders_delivered)                       AS orders_delivered,
       sum(orders_delivered) / (sum(online_min) / 60.0) AS orders_per_rider_hour,
       sum(busy_min) / sum(online_min)             AS utilisation,
       -- share of rider-hours spent in hours that ran above 90% utilisation
       sum(online_min) FILTER (WHERE utilisation > 0.9) / sum(online_min) AS share_hours_over_90pct
FROM kpi_riders_node_hour
GROUP BY GROUPING SETS ((node_id), ())
ORDER BY node_id = 'ALL', node_id;
