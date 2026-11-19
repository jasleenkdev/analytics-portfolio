-- 24_stockout_diagnosis.sql
-- Business question: which node-SKUs run out again and again, is it a demand spike or a
-- replenishment-level problem, and what does it cost in missing items?
-- opening cover = stock on the shelf at opening / mean daily units ordered (ordered, not sold, because
-- sales are capped by the stockout itself). Cover below 1 day means the shelf cannot last a normal day.
-- Variables: open_hour, start_date.

CREATE OR REPLACE TABLE stockout_node_sku AS
WITH days AS (SELECT count(DISTINCT CAST(snapshot_ts - INTERVAL 1 HOUR AS DATE)) AS n FROM inventory_snapshots),
demand AS (
    SELECT t.node_id, i.sku_id,
           sum(i.qty_ordered)                                     AS units_ordered,
           sum(i.qty_ordered - i.qty_fulfilled)                   AS units_short,
           sum((i.qty_ordered - i.qty_fulfilled) * i.unit_price)  AS short_value
    FROM order_items i JOIN order_timeline t USING (order_id)
    WHERE t.status = 'delivered'
    GROUP BY ALL
),
opening AS (
    -- the snapshot taken at the end of the hour before opening holds the replenished shelf
    SELECT node_id, sku_id, avg(on_hand) AS opening_stock
    FROM inventory_snapshots WHERE hour(snapshot_ts) = getvariable('open_hour')
    GROUP BY ALL
),
first_zero AS (
    SELECT node_id, sku_id, avg(first_zero_hour) AS mean_first_zero_hour
    FROM (
        SELECT node_id, sku_id, CAST(snapshot_ts - INTERVAL 1 HOUR AS DATE) AS day,
               min(hour(snapshot_ts - INTERVAL 1 HOUR)) FILTER (WHERE on_hand = 0 AND operating_hour) AS first_zero_hour
        FROM inv_hourly GROUP BY ALL
    )
    WHERE first_zero_hour IS NOT NULL
    GROUP BY ALL
)
SELECT k.node_id, k.sku_id, k.category, k.stockout_rate, k.days_with_stockout_share, k.repeat_stockout,
       d.units_ordered / (SELECT n FROM days)                 AS daily_units_ordered,
       o.opening_stock,
       o.opening_stock / nullif(d.units_ordered / (SELECT n FROM days), 0) AS opening_cover_days,
       d.units_short, d.short_value,
       f.mean_first_zero_hour
FROM kpi_stock_node_sku k
JOIN demand d USING (node_id, sku_id)
JOIN opening o USING (node_id, sku_id)
LEFT JOIN first_zero f USING (node_id, sku_id);

-- clusters: repeat-stockout SKUs grouped by node and category, compared with the same SKUs elsewhere
CREATE OR REPLACE TABLE stockout_clusters AS
WITH repeat AS (SELECT * FROM stockout_node_sku WHERE repeat_stockout),
same_skus_elsewhere AS (
    SELECT r.node_id, r.category,
           avg(s.opening_cover_days)   AS other_nodes_cover_days,
           avg(s.stockout_rate)        AS other_nodes_stockout_rate
    FROM repeat r JOIN stockout_node_sku s ON s.sku_id = r.sku_id AND s.node_id <> r.node_id
    GROUP BY ALL
)
SELECT r.node_id, r.category,
       count(*)                                  AS repeat_skus,
       string_agg(r.sku_id, ', ' ORDER BY r.sku_id) AS sku_ids,
       avg(r.stockout_rate)                      AS stockout_rate,
       avg(r.days_with_stockout_share)           AS days_with_stockout_share,
       avg(r.opening_cover_days)                 AS opening_cover_days,
       e.other_nodes_cover_days,
       e.other_nodes_stockout_rate,
       avg(r.mean_first_zero_hour)               AS mean_first_zero_hour,
       sum(r.units_short)                        AS units_short,
       sum(r.short_value)                        AS short_value
FROM repeat r JOIN same_skus_elsewhere e USING (node_id, category)
GROUP BY r.node_id, r.category, e.other_nodes_cover_days, e.other_nodes_stockout_rate
ORDER BY short_value DESC;
