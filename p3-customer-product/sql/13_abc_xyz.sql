-- 13_abc_xyz.sql
-- Business question: which SKUs carry the revenue (ABC) and how predictable is their demand (XYZ)?
-- And, because ranging differs by node, how fast does each SKU sell where it is actually ranged?
-- ABC: cumulative revenue share by SKU (window SUM ordered by revenue). XYZ: coefficient of variation
-- of weekly units at each node where the SKU is ranged (zeros included), median across those nodes:
-- replenishment is planned per node, and network totals smooth away the variability that matters.
-- Velocity per ranged node-week normalises for ranging.
-- Variables: abc_a_share, abc_b_share, xyz_x_cv, xyz_y_cv, start_date, days.

CREATE OR REPLACE TABLE node_sku_weekly AS
WITH weeks AS (SELECT unnest(range(0, CAST(ceil(getvariable('days') / 7) AS INTEGER))) AS week),
sold AS (
    SELECT node_id, sku_id,
           CAST(floor(date_diff('day', CAST(getvariable('start_date') AS DATE), order_date) / 7) AS INTEGER) AS week,
           sum(qty) AS units
    FROM line_facts GROUP BY ALL
)
SELECT r.node_id, r.sku_id, w.week, coalesce(d.units, 0) AS units
FROM node_range r CROSS JOIN weeks w
LEFT JOIN sold d ON d.node_id = r.node_id AND d.sku_id = r.sku_id AND d.week = w.week;

CREATE OR REPLACE TABLE abc_xyz AS
WITH rev AS (
    SELECT s.sku_id, s.category, s.unit_price, s.unit_cost, s.perishable, s.shelf_life_days,
           coalesce(sum(l.revenue), 0) AS revenue, coalesce(sum(l.gross_margin), 0) AS gross_margin,
           coalesce(sum(l.qty), 0) AS units
    FROM skus s LEFT JOIN line_facts l USING (sku_id) GROUP BY ALL
),
cum AS (
    SELECT *, sum(revenue) OVER (ORDER BY revenue DESC, sku_id ROWS UNBOUNDED PRECEDING) / sum(revenue) OVER () AS cum_share
    FROM rev
),
var AS (
    SELECT sku_id, median(cv) AS weekly_cv
    FROM (SELECT node_id, sku_id, stddev_pop(units) / nullif(avg(units), 0) AS cv FROM node_sku_weekly GROUP BY ALL)
    GROUP BY sku_id
),
ranged AS (SELECT sku_id, count(*) AS ranged_nodes FROM node_range GROUP BY 1)
SELECT c.*, v.weekly_cv, coalesce(r.ranged_nodes, 0) AS ranged_nodes,
       gross_margin / nullif(revenue, 0) AS margin_rate,
       CASE WHEN cum_share - revenue / sum(revenue) OVER () < getvariable('abc_a_share') THEN 'A'
            WHEN cum_share - revenue / sum(revenue) OVER () < getvariable('abc_b_share') THEN 'B' ELSE 'C' END AS abc,
       CASE WHEN v.weekly_cv <= getvariable('xyz_x_cv') THEN 'X'
            WHEN v.weekly_cv <= getvariable('xyz_y_cv') THEN 'Y' ELSE 'Z' END AS xyz,
       units / nullif(r.ranged_nodes, 0) / (getvariable('days') / 7) AS units_per_ranged_node_week,
       gross_margin / nullif(r.ranged_nodes, 0) / (getvariable('days') / 7) AS margin_per_ranged_node_week
FROM cum c LEFT JOIN var v USING (sku_id) LEFT JOIN ranged r USING (sku_id)
ORDER BY revenue DESC;

CREATE OR REPLACE TABLE abc_xyz_matrix AS
SELECT abc, xyz, count(*) AS skus, sum(revenue) / (SELECT sum(revenue) FROM abc_xyz) AS revenue_share
FROM abc_xyz GROUP BY ALL ORDER BY abc, xyz;
