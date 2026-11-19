-- 20_assortment.sql
-- Business question: per node, which SKUs should be added, dropped or carried with less depth, and
-- what is the expected impact (as a range, because substitution and cannibalisation are uncertain)?
-- add:     not ranged here; where ranged elsewhere it earns at least this node's category median
--          weekly margin and has an above-median margin rate. Impact = its weekly margin at the other
--          nodes scaled by node size, from (min x (1 - cannibalisation_low)) to max, annualised.
-- drop:    bottom drop_margin_percentile of the node's ranged SKUs by weekly margin, class C, and not
--          part of any strong affinity pair. Impact = margin given up, from (1 - transfer_low) x current to current.
-- reduce depth: perishable node-SKUs with high waste risk that sell at least reduce_min_daily_units a day.
--          Impact = waste cost saved, from waste_saving_low to waste_saving_high of current waste cost.
-- Variables: days, cannibalisation_low, transfer_low, drop_margin_percentile, reduce_min_daily_units,
--            waste_saving_low, waste_saving_high, affinity_min_lift, target_cover_share.

CREATE OR REPLACE TABLE node_sku_perf AS
WITH sold AS (
    SELECT node_id, sku_id, sum(qty) AS units, sum(gross_margin) AS gross_margin
    FROM line_facts GROUP BY ALL
)
SELECT r.node_id, r.sku_id, s.category, s.perishable,
       coalesce(d.units, 0) / (getvariable('days') / 7)        AS units_per_week,
       coalesce(d.gross_margin, 0) / (getvariable('days') / 7) AS margin_per_week,
       (s.unit_price - s.unit_cost) / s.unit_price              AS margin_rate
FROM node_range r JOIN skus s USING (sku_id) LEFT JOIN sold d USING (node_id, sku_id);

CREATE OR REPLACE TABLE node_scale AS
SELECT node_id, sum(units_per_week) / avg(sum(units_per_week)) OVER () AS scale
FROM node_sku_perf GROUP BY node_id;

CREATE OR REPLACE TABLE assortment_add AS
WITH cat_median AS (
    SELECT node_id, category, median(margin_per_week) AS cat_median_margin_week, median(margin_rate) AS cat_median_margin_rate
    FROM node_sku_perf GROUP BY ALL
),
elsewhere AS (
    -- the SKU's performance where it is ranged, normalised to an average-sized node
    SELECT p.sku_id, p.category, any_value(p.margin_rate) AS margin_rate, count(*) AS ranged_nodes,
           min(p.margin_per_week / s.scale) AS min_margin_week_norm,
           max(p.margin_per_week / s.scale) AS max_margin_week_norm,
           median(p.margin_per_week / s.scale) AS median_margin_week_norm
    FROM node_sku_perf p JOIN node_scale s USING (node_id) GROUP BY ALL
),
candidates AS (
    SELECT n.node_id, e.*
    FROM elsewhere e CROSS JOIN nodes n
    WHERE NOT EXISTS (SELECT 1 FROM node_range r WHERE r.node_id = n.node_id AND r.sku_id = e.sku_id)
      AND e.ranged_nodes >= getvariable('add_min_ranged_nodes')
)
SELECT c.node_id, c.sku_id, c.category, 'add' AS action, c.ranged_nodes, c.margin_rate,
       c.median_margin_week_norm * s.scale AS expected_margin_week,
       m.cat_median_margin_week,
       52 * c.min_margin_week_norm * s.scale * (1 - getvariable('cannibalisation_low')) AS impact_low,
       52 * c.max_margin_week_norm * s.scale                                            AS impact_high
FROM candidates c
JOIN node_scale s USING (node_id)
JOIN cat_median m ON m.node_id = c.node_id AND m.category = c.category
WHERE c.median_margin_week_norm * s.scale >= m.cat_median_margin_week
  AND c.margin_rate >= m.cat_median_margin_rate;

CREATE OR REPLACE TABLE assortment_drop AS
WITH ranked AS (
    SELECT p.*, percent_rank() OVER (PARTITION BY p.node_id ORDER BY p.margin_per_week) AS margin_pct_rank
    FROM node_sku_perf p
),
strong_pairs AS (
    SELECT sku_a AS sku_id FROM basket_affinity WHERE lift >= getvariable('affinity_min_lift')
    UNION SELECT sku_b FROM basket_affinity WHERE lift >= getvariable('affinity_min_lift')
)
SELECT r.node_id, r.sku_id, r.category, 'drop' AS action, r.units_per_week, r.margin_per_week, a.abc,
       52 * r.margin_per_week * (1 - getvariable('transfer_low')) AS margin_at_risk_low,
       52 * r.margin_per_week                                     AS margin_at_risk_high,
       coalesce(w.waste_cost, 0)                                  AS waste_cost_avoided
FROM ranked r
JOIN abc_xyz a USING (sku_id)
LEFT JOIN wastage_node_sku w USING (node_id, sku_id)
WHERE r.margin_pct_rank <= getvariable('drop_margin_percentile')
  AND a.abc = 'C'
  AND r.sku_id NOT IN (SELECT sku_id FROM strong_pairs);

CREATE OR REPLACE TABLE assortment_reduce AS
SELECT node_id, sku_id, category, 'reduce depth' AS action, shelf_life_days, days_of_cover, risk_score,
       getvariable('target_cover_share') * shelf_life_days AS target_cover_days,
       avg_daily_sold, units_wasted, waste_cost, waste_rate,
       waste_cost * getvariable('waste_saving_low')  AS impact_low,
       waste_cost * getvariable('waste_saving_high') AS impact_high
FROM wastage_node_sku
WHERE high_risk AND avg_daily_sold >= getvariable('reduce_min_daily_units');

CREATE OR REPLACE TABLE assortment_recommendations AS
SELECT node_id, sku_id, category, action, impact_low, impact_high, 'annual gross margin gained' AS impact_metric
FROM assortment_add
UNION ALL
SELECT node_id, sku_id, category, action, -margin_at_risk_high + waste_cost_avoided, -margin_at_risk_low + waste_cost_avoided,
       'annual gross margin change (negative = given up; frees space)'
FROM assortment_drop
UNION ALL
SELECT node_id, sku_id, category, action, impact_low, impact_high, 'annual waste cost saved'
FROM assortment_reduce;

CREATE OR REPLACE TABLE assortment_node_summary AS
SELECT node_id, action, count(*) AS skus, sum(impact_low) AS impact_low, sum(impact_high) AS impact_high
FROM assortment_recommendations GROUP BY ALL ORDER BY node_id, action;
