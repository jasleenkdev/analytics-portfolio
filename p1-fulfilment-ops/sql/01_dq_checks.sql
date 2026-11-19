-- 01_dq_checks.sql
-- Business question: can the raw order, event, stock and refund feeds be trusted, and which
-- rows must be repaired or excluded before any KPI is computed?
-- Output: dq_report, one row per check with the number of failing rows and the action taken.
-- Variables: none.

CREATE OR REPLACE TABLE dq_report AS
WITH
placed AS (
    SELECT order_id, min(event_ts) AS placed_ts
    FROM order_events WHERE event_type = 'placed' GROUP BY order_id
),
-- exact duplicates: the same event re-sent by the producer
exact_dupes AS (
    SELECT count(*) - count(DISTINCT (order_id, event_type, event_ts, coalesce(rider_id, ''))) AS n
    FROM order_events
),
-- any repeated (order, event type), which also catches re-sends with a jittered timestamp
repeated_events AS (
    SELECT coalesce(sum(cnt - 1), 0) AS n
    FROM (SELECT order_id, event_type, count(*) AS cnt FROM order_events GROUP BY ALL HAVING count(*) > 1)
),
first_events AS (
    SELECT order_id, event_type, min(event_ts) AS ts
    FROM order_events GROUP BY ALL
),
stage_ts AS (
    SELECT order_id,
           max(ts) FILTER (WHERE event_type = 'placed')    AS placed_ts,
           max(ts) FILTER (WHERE event_type = 'picked')    AS picked_ts,
           max(ts) FILTER (WHERE event_type = 'picked_up') AS picked_up_ts,
           max(ts) FILTER (WHERE event_type = 'delivered') AS delivered_ts
    FROM first_events GROUP BY order_id
),
checks AS (
    SELECT 'exact duplicate events' AS check_name, 'order_events' AS table_name,
           (SELECT n FROM exact_dupes) AS failing_rows,
           (SELECT count(*) FROM order_events) AS total_rows,
           'drop: keep one row per order and event type' AS action
    UNION ALL
    SELECT 'repeated order/event-type rows (incl. jittered re-sends)', 'order_events',
           (SELECT n FROM repeated_events), (SELECT count(*) FROM order_events),
           'drop: keep the earliest timestamp per order and event type'
    UNION ALL
    SELECT 'delivered before placed', 'order_events',
           count(*) FILTER (WHERE delivered_ts < placed_ts), count(*) FILTER (WHERE delivered_ts IS NOT NULL),
           'exclude from timing KPIs; keep for volume, defect and stock KPIs'
    FROM stage_ts
    UNION ALL
    SELECT 'stage out of order (picked<placed, picked_up<picked or delivered<picked_up)', 'order_events',
           count(*) FILTER (WHERE picked_ts < placed_ts OR picked_up_ts < picked_ts OR delivered_ts < picked_up_ts),
           count(*) FILTER (WHERE delivered_ts IS NOT NULL),
           'exclude from timing KPIs'
    FROM stage_ts
    UNION ALL
    SELECT 'rider event with null rider_id', 'order_events',
           count(*) FILTER (WHERE rider_id IS NULL),
           count(*),
           'fill from the same order''s other rider events'
    FROM order_events WHERE event_type IN ('rider_assigned', 'picked_up', 'delivered')
    UNION ALL
    SELECT 'order without a placed event', 'orders',
           count(*) FILTER (WHERE p.order_id IS NULL), count(*), 'exclude'
    FROM orders o LEFT JOIN placed p USING (order_id)
    UNION ALL
    SELECT 'placed event differs from order header by more than 1 minute', 'orders',
           count(*) FILTER (WHERE abs(epoch(p.placed_ts - o.created_at)) > 60), count(*), 'report only'
    FROM orders o JOIN placed p USING (order_id)
    UNION ALL
    SELECT 'delivered status without delivered event', 'orders',
           count(*) FILTER (WHERE s.delivered_ts IS NULL), count(*), 'exclude from timing KPIs'
    FROM orders o JOIN stage_ts s USING (order_id) WHERE o.status = 'delivered'
    UNION ALL
    SELECT 'null keys in orders', 'orders',
           count(*) FILTER (WHERE order_id IS NULL OR node_id IS NULL OR created_at IS NULL), count(*), 'exclude'
    FROM orders
    UNION ALL
    SELECT 'order lines with fulfilled > ordered or non-positive quantity', 'order_items',
           count(*) FILTER (WHERE qty_fulfilled > qty_ordered OR qty_ordered <= 0 OR qty_fulfilled < 0), count(*), 'exclude'
    FROM order_items
    UNION ALL
    SELECT 'order lines whose SKU is missing from the catalogue', 'order_items',
           count(*) FILTER (WHERE s.sku_id IS NULL), count(*), 'exclude'
    FROM order_items i LEFT JOIN skus s USING (sku_id)
    UNION ALL
    SELECT 'negative on-hand stock', 'inventory_snapshots',
           count(*) FILTER (WHERE on_hand < 0), count(*), 'exclude'
    FROM inventory_snapshots
    UNION ALL
    SELECT 'refund on a cancelled order', 'defects',
           count(*) FILTER (WHERE o.status = 'cancelled'), count(*), 'report only'
    FROM defects d JOIN orders o USING (order_id)
    UNION ALL
    SELECT 'non-positive refund amount', 'defects',
           count(*) FILTER (WHERE refund_amount <= 0), count(*), 'report only'
    FROM defects
)
SELECT check_name, table_name, failing_rows, total_rows,
       round(100.0 * failing_rows / nullif(total_rows, 0), 4) AS failing_pct,
       CASE WHEN failing_rows = 0 THEN 'pass' ELSE 'issue' END AS status,
       action
FROM checks;
