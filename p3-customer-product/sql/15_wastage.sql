-- 15_wastage.sql
-- Business question: where are we stocking perishables deeper than they can sell before expiry, and
-- what does it cost?
-- days of cover = average opening stock / average daily units sold; risk score = cover / shelf life
-- (above 1 means the shelf holds more than can sell before the oldest unit expires).
-- Variables: wastage_risk_threshold, target_cover_share.

CREATE OR REPLACE TABLE wastage_node_sku AS
SELECT i.node_id, i.sku_id, s.category, s.shelf_life_days, s.unit_cost,
       avg(i.opening_on_hand)                        AS avg_opening_stock,
       avg(i.sold)                                   AS avg_daily_sold,
       sum(i.received)                               AS units_received,
       sum(i.wasted)                                 AS units_wasted,
       sum(i.wasted) * s.unit_cost                   AS waste_cost,
       sum(i.wasted) / nullif(sum(i.received), 0)    AS waste_rate,
       avg(i.opening_on_hand) / nullif(avg(i.sold), 0)                      AS days_of_cover,
       avg(i.opening_on_hand) / nullif(avg(i.sold), 0) / s.shelf_life_days  AS risk_score,
       avg(i.opening_on_hand) / nullif(avg(i.sold), 0) / s.shelf_life_days >= getvariable('wastage_risk_threshold') AS high_risk
FROM inventory_daily i JOIN skus s USING (sku_id)
WHERE s.perishable
GROUP BY i.node_id, i.sku_id, s.category, s.shelf_life_days, s.unit_cost;

CREATE OR REPLACE TABLE wastage_node_category AS
SELECT node_id, category, sum(units_wasted) AS units_wasted, sum(waste_cost) AS waste_cost,
       sum(units_wasted) / sum(units_received) AS waste_rate,
       count(*) FILTER (WHERE high_risk) AS high_risk_skus, count(*) AS skus
FROM wastage_node_sku GROUP BY ALL ORDER BY waste_cost DESC, node_id, category;
