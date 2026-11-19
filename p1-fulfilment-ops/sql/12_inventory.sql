-- 12_inventory.sql
-- Business question: are we losing items to empty shelves, which node-SKUs repeatedly run out,
-- and how hard is stock working (turns, days of cover)?
-- fill rate      = units fulfilled / units ordered on delivered orders (all SKUs)
-- stockout rate  = share of operating hours a tracked node-SKU ends with zero on hand
-- turns          = annualised cost of units sold / average on-hand value at cost (tracked SKUs)
-- days of cover  = average on-hand units / average daily units sold (tracked SKUs)
-- Variables: open_hour, close_hour, stockout_repeat_days.

CREATE OR REPLACE TABLE kpi_fill_node_category AS
SELECT t.node_id, s.category,
       sum(i.qty_ordered)                       AS units_ordered,
       sum(i.qty_fulfilled)                     AS units_fulfilled,
       sum(i.qty_fulfilled) / sum(i.qty_ordered) AS fill_rate,
       sum((i.qty_ordered - i.qty_fulfilled) * i.unit_price) AS short_value
FROM order_items i
JOIN order_timeline t USING (order_id)
JOIN skus s USING (sku_id)
WHERE t.status = 'delivered'
GROUP BY ALL
ORDER BY t.node_id, s.category;

-- hourly stock position joined to the hour's sales for tracked node-SKUs
CREATE OR REPLACE TABLE inv_hourly AS
WITH sold AS (
    SELECT t.node_id, i.sku_id, t.order_hour_ts + INTERVAL 1 HOUR AS snapshot_ts,
           sum(i.qty_fulfilled) AS units_sold
    FROM order_items i JOIN order_timeline t USING (order_id)
    WHERE t.status = 'delivered'
    GROUP BY ALL
)
SELECT v.node_id, v.sku_id, v.snapshot_ts, v.on_hand, v.received_qty,
       coalesce(sd.units_sold, 0) AS units_sold,
       -- an operating hour is one whose end falls between open+1 and close+1
       hour(v.snapshot_ts - INTERVAL 1 HOUR) BETWEEN getvariable('open_hour') AND getvariable('close_hour') AS operating_hour
FROM inventory_snapshots v
LEFT JOIN sold sd USING (node_id, sku_id, snapshot_ts);

CREATE OR REPLACE TABLE kpi_stock_node_sku AS
WITH daily AS (
    SELECT node_id, sku_id, CAST(snapshot_ts - INTERVAL 1 HOUR AS DATE) AS day,
           bool_or(on_hand = 0 AND operating_hour)        AS hit_zero,
           count(*) FILTER (WHERE on_hand = 0 AND operating_hour) AS zero_hours,
           count(*) FILTER (WHERE operating_hour)          AS operating_hours,
           sum(units_sold)                                 AS units_sold,
           avg(on_hand)                                    AS avg_on_hand
    FROM inv_hourly GROUP BY ALL
)
SELECT d.node_id, d.sku_id, s.category, s.unit_cost,
       sum(zero_hours) / sum(operating_hours)          AS stockout_rate,
       avg(CAST(hit_zero AS DOUBLE))                   AS days_with_stockout_share,
       sum(units_sold)                                 AS units_sold,
       avg(avg_on_hand)                                AS avg_on_hand,
       avg(avg_on_hand) / nullif(avg(units_sold), 0)   AS days_of_cover,
       -- annualise sold cost over the observed days
       (sum(units_sold) * s.unit_cost) * 365.0 / count(*) / nullif(avg(avg_on_hand) * s.unit_cost, 0) AS inventory_turns,
       avg(CAST(hit_zero AS DOUBLE)) >= getvariable('stockout_repeat_days') AS repeat_stockout
FROM daily d JOIN skus s USING (sku_id)
GROUP BY d.node_id, d.sku_id, s.category, s.unit_cost;

CREATE OR REPLACE TABLE kpi_inventory_node AS
WITH stock AS (
    SELECT node_id,
           avg(stockout_rate)                                   AS stockout_rate,
           sum(units_sold * unit_cost) * 365.0 / (SELECT count(DISTINCT CAST(snapshot_ts - INTERVAL 1 HOUR AS DATE)) FROM inv_hourly)
               / sum(avg_on_hand * unit_cost)                   AS inventory_turns,
           sum(avg_on_hand) / sum(units_sold / (SELECT count(DISTINCT CAST(snapshot_ts - INTERVAL 1 HOUR AS DATE)) FROM inv_hourly))
                                                                AS days_of_cover,
           count(*) FILTER (WHERE repeat_stockout)              AS repeat_stockout_skus
    FROM kpi_stock_node_sku GROUP BY node_id
),
fill AS (
    SELECT node_id, sum(units_fulfilled) / sum(units_ordered) AS fill_rate, sum(short_value) AS short_value
    FROM kpi_fill_node_category GROUP BY node_id
)
SELECT node_id, f.fill_rate, f.short_value, s.stockout_rate, s.inventory_turns, s.days_of_cover, s.repeat_stockout_skus
FROM fill f JOIN stock s USING (node_id)
ORDER BY node_id;
