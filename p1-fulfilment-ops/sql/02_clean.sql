-- 02_clean.sql
-- Business question: what does one trustworthy row per order look like?
-- Builds the cleaned layer every KPI reads from:
--   events_clean     one row per (order, event type), earliest timestamp, rider id repaired
--   order_timeline   one row per order with stage timestamps, stage minutes and a validity flag
--   dq_excluded_orders  orders kept out of timing KPIs, with the reason
-- Variables: sla_minutes.

CREATE OR REPLACE TABLE events_clean AS
WITH ranked AS (
    SELECT *,
           -- the order's rider from any rider event, used to repair null rider ids
           max(rider_id) OVER (PARTITION BY order_id) AS order_rider_id
    FROM order_events
)
SELECT event_id, order_id, event_type, event_ts,
       coalesce(rider_id, CASE WHEN event_type IN ('rider_assigned', 'picked_up', 'delivered')
                               THEN order_rider_id END) AS rider_id
FROM ranked
QUALIFY row_number() OVER (PARTITION BY order_id, event_type ORDER BY event_ts, event_id) = 1;

CREATE OR REPLACE TABLE order_timeline AS
WITH pivoted AS (
    SELECT order_id,
           max(event_ts) FILTER (WHERE event_type = 'placed')         AS placed_ts,
           max(event_ts) FILTER (WHERE event_type = 'picked')         AS picked_ts,
           max(event_ts) FILTER (WHERE event_type = 'rider_assigned') AS rider_assigned_ts,
           max(event_ts) FILTER (WHERE event_type = 'picked_up')      AS picked_up_ts,
           max(event_ts) FILTER (WHERE event_type = 'delivered')      AS delivered_ts,
           max(event_ts) FILTER (WHERE event_type = 'cancelled')      AS cancelled_ts,
           max(rider_id)                                              AS rider_id
    FROM events_clean GROUP BY order_id
),
timeline AS (
SELECT o.order_id, o.node_id, n.zone, o.status, o.n_lines, o.order_value, o.distance_km,
       p.placed_ts,
       CAST(p.placed_ts AS DATE) AS order_date,
       date_trunc('hour', p.placed_ts) AS order_hour_ts,
       hour(p.placed_ts) AS order_hour,
       p.picked_ts, p.rider_assigned_ts, p.picked_up_ts, p.delivered_ts, p.cancelled_ts, p.rider_id,
       epoch(p.picked_ts - p.placed_ts) / 60.0       AS pick_min,
       epoch(p.picked_up_ts - p.picked_ts) / 60.0    AS rider_wait_min,
       epoch(p.delivered_ts - p.picked_up_ts) / 60.0 AS travel_min,
       epoch(p.delivered_ts - p.placed_ts) / 60.0    AS delivery_min,
       CASE
           WHEN o.status <> 'delivered' THEN 'not delivered'
           WHEN p.delivered_ts IS NULL OR p.picked_up_ts IS NULL OR p.picked_ts IS NULL THEN 'missing stage event'
           WHEN p.delivered_ts < p.placed_ts THEN 'delivered before placed'
           WHEN p.picked_ts < p.placed_ts OR p.picked_up_ts < p.picked_ts OR p.delivered_ts < p.picked_up_ts
               THEN 'stage out of order'
       END AS exclusion_reason
FROM orders o
JOIN nodes n USING (node_id)
JOIN pivoted p USING (order_id)
)
SELECT *,
       exclusion_reason IS NULL AS timing_valid,
       CASE WHEN exclusion_reason IS NULL THEN delivery_min <= getvariable('sla_minutes') END AS within_sla
FROM timeline;

CREATE OR REPLACE TABLE dq_excluded_orders AS
SELECT order_id, node_id, placed_ts, delivered_ts, exclusion_reason
FROM order_timeline
WHERE status = 'delivered' AND NOT timing_valid;
