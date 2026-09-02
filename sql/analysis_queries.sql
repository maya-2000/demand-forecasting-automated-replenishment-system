/* =====================================================================================
   AI-Powered Inventory Forecasting & Automated Replenishment System
   Analytical SQL Suite
   -------------------------------------------------------------------------------------
   Source table : inventory_data      (loaded from data/inventory_data.csv, 1,000 rows)
   Grain        : one row per SKU_ID x Warehouse_ID
   Snapshot     : 2026-08-31, YTD covers 243 days (1 Jan - 31 Aug 2026)
   Dialect      : ANSI SQL. Validated on SQLite 3.4x and compatible with PostgreSQL 12+,
                  Snowflake, BigQuery (standard SQL) and Redshift. No vendor-specific
                  functions are used - GREATEST/LEAST are written as CASE expressions and
                  all aggregation uses standard window syntax.

   QUERIES
     1. Total Revenue at Risk from stockouts        -> BRD BO-02, US-04
     2. Carrying cost savings by warehouse          -> BRD BO-01, US-05, FR-10
     3. Inventory turnover across top SKUs          -> BRD BO-04, US-04

   ANALYTICAL CONVENTIONS
     Lead_Time_Demand   = Avg_Daily_Demand x Lead_Time_Days
     Safety_Stock       = GREATEST(Reorder_Point - Lead_Time_Demand, 0)
     Average_Inventory  = Safety_Stock + Order_Quantity / 2
     Annualisation      = YTD value x 365 / 243
   ===================================================================================== */


/* -------------------------------------------------------------------------------------
   TABLE DEFINITION (for reproducing the analysis in a fresh database)
   ------------------------------------------------------------------------------------- */
-- DROP TABLE IF EXISTS inventory_data;
-- CREATE TABLE inventory_data (
--     SKU_ID                     VARCHAR(16)  NOT NULL,
--     Warehouse_ID               VARCHAR(16)  NOT NULL,
--     Warehouse_Name             VARCHAR(64)  NOT NULL,
--     Product_Category           VARCHAR(64)  NOT NULL,
--     ABC_Class                  CHAR(1)      NOT NULL,
--     Supplier_ID                VARCHAR(16)  NOT NULL,
--     Unit_Cost                  DECIMAL(12,2) NOT NULL,
--     Unit_Price                 DECIMAL(12,2) NOT NULL,
--     Lead_Time_Days             INTEGER      NOT NULL,
--     Lead_Time_Variability_Days DECIMAL(8,1) NOT NULL,
--     Avg_Daily_Demand           DECIMAL(12,2) NOT NULL,
--     Demand_Std_Dev             DECIMAL(12,2) NOT NULL,
--     Units_Sold_YTD             INTEGER      NOT NULL,
--     Current_Stock              INTEGER      NOT NULL,
--     Stockout_Events_YTD        INTEGER      NOT NULL,
--     Avg_Stockout_Duration_Days DECIMAL(8,1) NOT NULL,
--     Holding_Cost_Per_Unit      DECIMAL(12,2) NOT NULL,
--     Static_Reorder_Point       INTEGER      NOT NULL,
--     Demand_Forecast_AI         INTEGER      NOT NULL,
--     AI_Reorder_Point           INTEGER      NOT NULL,
--     Static_Order_Qty_Units     INTEGER      NOT NULL,
--     AI_Order_Qty_Units         INTEGER      NOT NULL,
--     Forecast_MAPE_Pct          DECIMAL(6,1) NOT NULL,
--     Reorder_Flag               SMALLINT     NOT NULL,
--     Snapshot_Date              DATE         NOT NULL,
--     PRIMARY KEY (SKU_ID, Warehouse_ID)
-- );
-- \copy inventory_data FROM 'data/inventory_data.csv' WITH (FORMAT csv, HEADER true);


/* =====================================================================================
   QUERY 1 - TOTAL REVENUE AT RISK DUE TO STOCKOUTS
   -------------------------------------------------------------------------------------
   Business question
     How much revenue has the business already lost to stockouts this year, how much is
     still exposed on today's stock position, and which SKUs concentrate that risk?

   Method
     Realised loss    = stockout days x daily demand x unit price
                        (stockout days = events x average duration)
     Forward exposure = the shortfall between today's stock and the demand that will
                        arise before a replenishment could physically arrive, priced at list
     Total at risk    = realised loss + forward exposure

   Window functions demonstrate the Pareto concentration of risk: a running cumulative
   share identifies the minimum set of SKUs that must be fixed to remove 80% of exposure.
   ===================================================================================== */
WITH base AS (
    SELECT
        SKU_ID,
        Warehouse_ID,
        Warehouse_Name,
        Product_Category,
        ABC_Class,
        Unit_Price,
        Unit_Cost,
        Avg_Daily_Demand,
        Lead_Time_Days,
        Current_Stock,
        Reorder_Flag,
        Stockout_Events_YTD,
        Avg_Stockout_Duration_Days,
        Stockout_Events_YTD * Avg_Stockout_Duration_Days AS stockout_days_ytd,
        Avg_Daily_Demand * Lead_Time_Days                AS lead_time_demand_units
    FROM inventory_data
),

risk_calc AS (
    SELECT
        b.*,
        /* Realised: units that could not be sold while the SKU was unavailable */
        b.stockout_days_ytd * b.Avg_Daily_Demand                            AS lost_units_ytd,
        b.stockout_days_ytd * b.Avg_Daily_Demand * b.Unit_Price             AS lost_revenue_ytd,
        b.stockout_days_ytd * b.Avg_Daily_Demand
            * (b.Unit_Price - b.Unit_Cost)                                  AS lost_margin_ytd,
        /* Forward: stock on hand cannot cover demand over the replenishment lead time */
        CASE
            WHEN b.Current_Stock < b.lead_time_demand_units
            THEN (b.lead_time_demand_units - b.Current_Stock) * b.Unit_Price
            ELSE 0
        END                                                                 AS forward_exposure_sgd
    FROM base b
),

risk_total AS (
    SELECT
        r.*,
        r.lost_revenue_ytd + r.forward_exposure_sgd AS total_revenue_at_risk
    FROM risk_calc r
),

ranked AS (
    SELECT
        rt.*,
        /* ---- Window functions: portfolio context carried onto every detail row ---- */
        SUM(rt.total_revenue_at_risk)  OVER ()                                   AS portfolio_risk_sgd,
        SUM(rt.total_revenue_at_risk)  OVER (PARTITION BY rt.Warehouse_ID)       AS warehouse_risk_sgd,
        ROW_NUMBER() OVER (ORDER BY rt.total_revenue_at_risk DESC)               AS risk_rank_overall,
        RANK()       OVER (PARTITION BY rt.Warehouse_ID
                           ORDER BY rt.total_revenue_at_risk DESC)               AS risk_rank_in_warehouse,
        NTILE(4)     OVER (ORDER BY rt.total_revenue_at_risk DESC)               AS risk_quartile,
        SUM(rt.total_revenue_at_risk) OVER (
            ORDER BY rt.total_revenue_at_risk DESC
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )                                                                        AS cumulative_risk_sgd
    FROM risk_total rt
)

SELECT
    risk_rank_overall                                          AS rnk,
    SKU_ID,
    Warehouse_ID,
    Product_Category,
    ABC_Class,
    Stockout_Events_YTD                                        AS stockout_events,
    ROUND(stockout_days_ytd, 1)                                AS stockout_days,
    ROUND(lost_units_ytd, 0)                                   AS lost_units_ytd,
    ROUND(lost_revenue_ytd, 2)                                 AS lost_revenue_ytd_sgd,
    ROUND(lost_margin_ytd, 2)                                  AS lost_margin_ytd_sgd,
    ROUND(forward_exposure_sgd, 2)                             AS forward_exposure_sgd,
    ROUND(total_revenue_at_risk, 2)                            AS total_revenue_at_risk_sgd,
    ROUND(100.0 * total_revenue_at_risk / portfolio_risk_sgd, 2)    AS pct_of_portfolio_risk,
    ROUND(100.0 * cumulative_risk_sgd / portfolio_risk_sgd, 2)      AS cumulative_pct_of_risk,
    risk_quartile,
    risk_rank_in_warehouse,
    CASE WHEN Reorder_Flag = 1 THEN 'REORDER NOW' ELSE 'Monitor' END AS recommended_action,
    ROUND(portfolio_risk_sgd, 2)                               AS portfolio_risk_sgd
FROM ranked
WHERE risk_rank_overall <= 25          -- top 25 exposures for the exception workbench
ORDER BY risk_rank_overall;


/* =====================================================================================
   QUERY 2 - CARRYING COST SAVINGS PER WAREHOUSE: AI FORECAST vs STATIC THRESHOLDS
   -------------------------------------------------------------------------------------
   Business question
     What annual carrying cost does each warehouse avoid by replacing static reorder
     points with forecast-driven thresholds, and where does the saving actually come from?

   Method
     The saving decomposes into two independently auditable components:

       Safety stock saving = (static safety stock - AI safety stock) x holding cost
         The static policy holds a flat 30-day cover irrespective of demand volatility;
         the AI policy sizes the buffer statistically at a 95% service level.

       Cycle stock saving  = (static order qty - AI order qty) / 2 x holding cost
         Raising a PO manually costs ~SGD 550, which pushes planners toward large,
         infrequent orders. An auto-generated draft PO costs ~SGD 450 to review, so the
         economic order quantity - and half of it, the average cycle stock - falls.

     A negative saving is a legitimate and important result: for long-lead-time, volatile
     SKUs the static threshold was under-covering, and the AI policy correctly invests
     MORE inventory to buy back service level. That trade is surfaced, not hidden.
   ===================================================================================== */
WITH policy_positions AS (
    SELECT
        Warehouse_ID,
        Warehouse_Name,
        SKU_ID,
        ABC_Class,
        Holding_Cost_Per_Unit,
        Unit_Cost,
        Avg_Daily_Demand * Lead_Time_Days AS lead_time_demand_units,
        /* Safety stock implied by each policy, floored at zero (GREATEST equivalent) */
        CASE WHEN Static_Reorder_Point - (Avg_Daily_Demand * Lead_Time_Days) > 0
             THEN Static_Reorder_Point - (Avg_Daily_Demand * Lead_Time_Days)
             ELSE 0 END                                       AS static_safety_units,
        CASE WHEN AI_Reorder_Point - (Avg_Daily_Demand * Lead_Time_Days) > 0
             THEN AI_Reorder_Point - (Avg_Daily_Demand * Lead_Time_Days)
             ELSE 0 END                                       AS ai_safety_units,
        Static_Order_Qty_Units / 2.0                          AS static_cycle_units,
        AI_Order_Qty_Units / 2.0                              AS ai_cycle_units
    FROM inventory_data
),

sku_economics AS (
    SELECT
        p.*,
        (p.static_safety_units + p.static_cycle_units)                          AS static_avg_inventory_units,
        (p.ai_safety_units     + p.ai_cycle_units)                              AS ai_avg_inventory_units,
        (p.static_safety_units + p.static_cycle_units) * p.Holding_Cost_Per_Unit AS static_carrying_cost,
        (p.ai_safety_units     + p.ai_cycle_units)     * p.Holding_Cost_Per_Unit AS ai_carrying_cost,
        (p.static_safety_units - p.ai_safety_units)    * p.Holding_Cost_Per_Unit AS safety_stock_saving,
        (p.static_cycle_units  - p.ai_cycle_units)     * p.Holding_Cost_Per_Unit AS cycle_stock_saving,
        (p.static_safety_units + p.static_cycle_units
         - p.ai_safety_units   - p.ai_cycle_units)     * p.Unit_Cost             AS working_capital_released
    FROM policy_positions p
),

warehouse_rollup AS (
    SELECT
        Warehouse_ID,
        Warehouse_Name,
        COUNT(*)                                            AS sku_count,
        SUM(static_avg_inventory_units)                     AS static_units,
        SUM(ai_avg_inventory_units)                         AS ai_units,
        SUM(static_carrying_cost)                           AS static_carrying_cost,
        SUM(ai_carrying_cost)                               AS ai_carrying_cost,
        SUM(static_carrying_cost) - SUM(ai_carrying_cost)   AS total_saving,
        SUM(safety_stock_saving)                            AS safety_stock_saving,
        SUM(cycle_stock_saving)                             AS cycle_stock_saving,
        SUM(working_capital_released)                       AS working_capital_released,
        SUM(CASE WHEN static_carrying_cost - ai_carrying_cost < 0 THEN 1 ELSE 0 END)
                                                            AS skus_requiring_more_stock
    FROM sku_economics
    GROUP BY Warehouse_ID, Warehouse_Name
)

SELECT
    w.Warehouse_ID,
    w.Warehouse_Name,
    w.sku_count,
    ROUND(w.static_carrying_cost, 2)                                    AS static_carrying_cost_sgd,
    ROUND(w.ai_carrying_cost, 2)                                        AS ai_carrying_cost_sgd,
    ROUND(w.total_saving, 2)                                            AS annual_saving_sgd,
    ROUND(100.0 * w.total_saving / w.static_carrying_cost, 2)           AS saving_pct_of_baseline,
    ROUND(w.safety_stock_saving, 2)                                     AS from_safety_stock_sgd,
    ROUND(w.cycle_stock_saving, 2)                                      AS from_cycle_stock_sgd,
    ROUND(100.0 * w.safety_stock_saving / w.total_saving, 1)            AS pct_saving_from_safety_stock,
    ROUND(w.working_capital_released, 2)                                AS working_capital_released_sgd,
    w.skus_requiring_more_stock                                         AS skus_now_better_protected,
    /* ---- Window functions: rank each warehouse against the portfolio ---- */
    RANK() OVER (ORDER BY w.total_saving DESC)                          AS saving_rank,
    ROUND(SUM(w.total_saving) OVER (), 2)                               AS portfolio_saving_sgd,
    ROUND(100.0 * w.total_saving / SUM(w.total_saving) OVER (), 2)      AS pct_of_portfolio_saving,
    ROUND(100.0 * SUM(w.total_saving) OVER () / SUM(w.static_carrying_cost) OVER (), 2)
                                                                        AS portfolio_saving_pct,
    ROUND(w.total_saving - AVG(w.total_saving) OVER (), 2)              AS variance_vs_avg_warehouse
FROM warehouse_rollup w
ORDER BY annual_saving_sgd DESC;


/* =====================================================================================
   QUERY 3 - INVENTORY TURNOVER RATIO ACROSS TOP SKUs
   -------------------------------------------------------------------------------------
   Business question
     Which of our highest-revenue SKUs are turning capital efficiently, and which are
     dragging the portfolio below the 12.5x internal target?

   Method
     Turnover = annualised COGS / average inventory value
     COGS is annualised from 243 YTD days: Units_Sold_YTD x Unit_Cost x 365 / 243
     Average inventory value is evaluated under both policies so the turnover uplift
     delivered by the AI policy is visible per SKU.

     Rows are aggregated from SKU x warehouse grain up to SKU grain, then benchmarked
     against the category average using a partitioned window - a SKU turning at 6x is
     healthy in Automotive Parts and poor in FMCG, so the absolute number alone misleads.

     The result set deliberately covers two segments. Ranking by revenue alone is
     self-fulfilling: high-revenue SKUs are high-velocity by construction and always look
     healthy. The trapped working capital sits in the slow-turning tail, so the query
     returns the top 30 SKUs by revenue AND the 15 slowest-turning SKUs, tagged by segment,
     so the executive sees both the value concentration and the efficiency problem.
   ===================================================================================== */
WITH sku_warehouse AS (
    SELECT
        SKU_ID,
        Product_Category,
        ABC_Class,
        Unit_Cost,
        Unit_Price,
        Units_Sold_YTD,
        Units_Sold_YTD * Unit_Cost  * 365.0 / 243.0 AS annual_cogs_sgd,
        Units_Sold_YTD * Unit_Price * 365.0 / 243.0 AS annual_revenue_sgd,
        (CASE WHEN Static_Reorder_Point - (Avg_Daily_Demand * Lead_Time_Days) > 0
              THEN Static_Reorder_Point - (Avg_Daily_Demand * Lead_Time_Days)
              ELSE 0 END + Static_Order_Qty_Units / 2.0) * Unit_Cost AS static_avg_inv_value,
        (CASE WHEN AI_Reorder_Point - (Avg_Daily_Demand * Lead_Time_Days) > 0
              THEN AI_Reorder_Point - (Avg_Daily_Demand * Lead_Time_Days)
              ELSE 0 END + AI_Order_Qty_Units / 2.0) * Unit_Cost     AS ai_avg_inv_value,
        Stockout_Events_YTD,
        Forecast_MAPE_Pct
    FROM inventory_data
),

sku_level AS (
    SELECT
        SKU_ID,
        Product_Category,
        ABC_Class,
        COUNT(*)                        AS warehouse_count,
        SUM(Units_Sold_YTD)             AS units_sold_ytd,
        SUM(annual_revenue_sgd)         AS annual_revenue_sgd,
        SUM(annual_cogs_sgd)            AS annual_cogs_sgd,
        SUM(static_avg_inv_value)       AS static_avg_inv_value,
        SUM(ai_avg_inv_value)           AS ai_avg_inv_value,
        SUM(Stockout_Events_YTD)        AS stockout_events_ytd,
        AVG(Forecast_MAPE_Pct)          AS avg_forecast_mape
    FROM sku_warehouse
    GROUP BY SKU_ID, Product_Category, ABC_Class
),

turnover AS (
    SELECT
        s.*,
        s.annual_cogs_sgd / NULLIF(s.static_avg_inv_value, 0) AS static_turnover,
        s.annual_cogs_sgd / NULLIF(s.ai_avg_inv_value, 0)     AS ai_turnover
    FROM sku_level s
),

benchmarked AS (
    SELECT
        t.*,
        365.0 / NULLIF(t.ai_turnover, 0)                                     AS days_on_hand_ai,
        /* ---- Window functions: rank, quartile and category benchmark ---- */
        RANK()   OVER (ORDER BY t.annual_revenue_sgd DESC)                   AS revenue_rank,
        NTILE(4) OVER (ORDER BY t.ai_turnover DESC)                          AS turnover_quartile,
        AVG(t.ai_turnover) OVER (PARTITION BY t.Product_Category)            AS category_avg_turnover,
        RANK()   OVER (PARTITION BY t.Product_Category
                       ORDER BY t.ai_turnover DESC)                          AS rank_in_category,
        RANK()   OVER (ORDER BY t.ai_turnover ASC)                           AS slowest_turn_rank,
        AVG(t.ai_turnover) OVER ()                                           AS portfolio_avg_turnover
    FROM turnover t
)

SELECT
    CASE
        WHEN revenue_rank <= 30 AND slowest_turn_rank <= 15 THEN 'TOP REVENUE + SLOW TURN'
        WHEN revenue_rank <= 30                             THEN 'TOP REVENUE'
        ELSE                                                     'SLOWEST TURNING'
    END                                                     AS review_segment,
    revenue_rank,
    slowest_turn_rank,
    SKU_ID,
    Product_Category,
    ABC_Class,
    warehouse_count,
    units_sold_ytd,
    ROUND(annual_revenue_sgd, 2)                            AS annual_revenue_sgd,
    ROUND(annual_cogs_sgd, 2)                               AS annual_cogs_sgd,
    ROUND(static_avg_inv_value, 2)                          AS static_avg_inventory_sgd,
    ROUND(ai_avg_inv_value, 2)                              AS ai_avg_inventory_sgd,
    ROUND(static_turnover, 2)                               AS turnover_static,
    ROUND(ai_turnover, 2)                                   AS turnover_ai,
    ROUND(ai_turnover - static_turnover, 2)                 AS turnover_uplift,
    ROUND(days_on_hand_ai, 1)                               AS days_on_hand_ai,
    ROUND(category_avg_turnover, 2)                         AS category_avg_turnover,
    ROUND(ai_turnover - category_avg_turnover, 2)           AS variance_vs_category,
    rank_in_category,
    turnover_quartile,
    stockout_events_ytd,
    ROUND(avg_forecast_mape, 1)                             AS avg_forecast_mape_pct,
    CASE
        WHEN ai_turnover < 5.0                    THEN 'CRITICAL - capital trapped, review order policy'
        WHEN ai_turnover < 12.5                   THEN 'BELOW TARGET - reduce cover'
        WHEN ai_turnover < category_avg_turnover  THEN 'ON TARGET - lagging category peers'
        ELSE 'LEADING - at or above category benchmark'
    END                                                     AS turnover_assessment
FROM benchmarked
WHERE revenue_rank <= 30                -- value concentration: top 30 SKUs by annual revenue
   OR slowest_turn_rank <= 15           -- efficiency drag: 15 slowest-turning SKUs
ORDER BY review_segment, revenue_rank, slowest_turn_rank;
