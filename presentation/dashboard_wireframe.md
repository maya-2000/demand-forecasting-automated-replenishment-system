# Dashboard Wireframe & Build Guide
## Inventory Performance Command Centre

**Audience:** BI developer building the dashboard in Power BI, Tableau, or Looker
**Traces to:** FR-08, FR-09, FR-10, FR-12 · US-04 (Executive Dashboard), US-03 (Exception Workbench)
**Data source:** `data/inventory_data.csv` → analytics warehouse table `inventory_data`
**Refresh:** Daily at 05:00 SGT, after the nightly forecast batch completes

---

## 1. Design Principles

1. **One screen, one decision.** Page 1 answers "are we winning?" for the executive. Page 2 answers "what do I do today?" for the planner. Do not merge them.
2. **Lead with money, not units.** Every KPI resolves to SGD. Unit counts are supporting detail.
3. **Show the trade-off honestly.** The AI policy *increases* stock on 155 positions. Surface that — a dashboard that only shows reductions will lose credibility the first time a planner spots an increase.
4. **Variance over absolutes.** Every KPI carries its delta versus prior period and versus target. A number without a reference point is not a decision aid.
5. **Colour carries meaning, never decoration.** Red = target missed, amber = at risk, green = on target. Reserve colour for status only; use neutral greys for everything else.
6. **Accessibility.** Do not encode status by colour alone — pair every colour with an icon or text label. Verify contrast in both light and dark themes.

---

## 2. Page 1 — Executive Overview

### 2.1 Layout

```
+=================================================================================================+
|  INVENTORY PERFORMANCE COMMAND CENTRE            Data as of: 31 Aug 2026 05:00 SGT               |
|  [Warehouse: All v]  [Category: All v]  [ABC Class: All v]  [Period: YTD v]                     |
+=================================================================================================+
|                                                                                                 |
|  ROW 1 - KPI STRIP (5 cards, equal width)                                                       |
|  +----------------+----------------+----------------+----------------+----------------+         |
|  | REVENUE AT RISK| ANNUAL CARRYING| WORKING CAPITAL| INVENTORY      | STOCKOUT       |         |
|  |                | COST           | RELEASED       | TURNOVER       | EVENTS YTD     |         |
|  |  SGD 10.1M     |  SGD 2.98M     |  SGD 3.44M     |    13.2x       |     1,661      |         |
|  |  ^ 3.0% of rev |  v 20.7% vs    |  vs static     |  ^ from 10.7x  |  v target -40% |         |
|  |    [RED]       |    static      |    policy      |  target 12.5x  |    [AMBER]     |         |
|  |                |    [GREEN]     |    [GREEN]     |    [GREEN]     |                |         |
|  +----------------+----------------+----------------+----------------+----------------+         |
|                                                                                                 |
|  ROW 2                                                                                          |
|  +---------------------------------------+  +----------------------------------------------+   |
|  | CARRYING COST: STATIC vs AI            |  | REVENUE AT RISK - PARETO CONCENTRATION       |   |
|  | Grouped horizontal bar, by warehouse   |  | Combo: bars = risk SGD, line = cumulative %  |   |
|  |                                        |  |                                              |   |
|  | SIN-01 |########## 1.26M               |  |  SGD                                cum %    |   |
|  |        |#######    0.89M   -29.6%      |  |  |##                              ......100% |   |
|  | JHR-02 |#######    0.90M               |  |  |####                      ......           |   |
|  |        |#####      0.72M   -20.4%      |  |  |######            ......                   |   |
|  | PEN-04 |#######    0.88M               |  |  |########   .......                80% ---- |   |
|  |        |######     0.73M   -17.1%      |  |  |##########.                                |   |
|  | BTM-03 |######     0.71M               |  |  +------------------------------------------ |   |
|  |        |#####      0.64M    -9.6%      |  |    Top 25 SKUs by exposure                   |   |
|  |         [] Static  [] AI-optimised     |  |  Annotation: "Top 25 SKUs = 31% of exposure" |   |
|  +---------------------------------------+  +----------------------------------------------+   |
|                                                                                                 |
|  ROW 3                                                                                          |
|  +---------------------------------------+  +----------------------------------------------+   |
|  | SAVING DECOMPOSITION (waterfall)      |  | TURNOVER vs DAYS ON HAND (scatter)           |   |
|  |                                        |  |                                              |   |
|  | Static CC        3.76M  |##########|   |  |  Turnover                                    |   |
|  |  - Safety stock  -0.51M |    ###   |   |  |   25 |    o o  o   <- A-class, healthy       |   |
|  |  - Cycle stock   -0.27M |     ##   |   |  |   15 |  o o o o o                             |   |
|  | AI carrying cost 2.98M  |########  |   |  |    5 | o                                      |   |
|  |                                        |  |    0 |o o o   <- C-class, 135-300 days [RED]  |   |
|  | Label: 65.7% safety / 34.3% cycle      |  |      +--------------------------------------- |   |
|  +---------------------------------------+  |        0    100   200   300  Days on hand     |   |
|                                              |  Bubble size = inventory value SGD           |   |
|                                              +----------------------------------------------+   |
|                                                                                                 |
|  ROW 4 - FORECAST HEALTH                                                                        |
|  +---------------------------------------------------------------------------------------+     |
|  | MAPE by warehouse and ABC class (heatmap)     |  MODEL WATCHLIST                        |     |
|  |          A      B      C                      |  A-class SKUs, MAPE >25% for 3 cycles   |     |
|  | SIN-01  9.8%  10.4%  11.9%   [green]          |  SKU-0153  19.1%  Consumer Electronics  |     |
|  | JHR-02 10.2%  10.9%  11.4%                    |  SKU-0029  14.2%  Consumer Electronics  |     |
|  | BTM-03 10.6%  11.1%  11.8%                    |  SKU-0060  13.7%  Consumer Electronics  |     |
|  | PEN-04 10.4%  10.7%  11.2%                    |  [Alert Data Science owner]             |     |
|  +---------------------------------------------------------------------------------------+     |
+=================================================================================================+
```

### 2.2 KPI Card Specification

| # | KPI | Calculation | Target | Status thresholds |
|---|---|---|---|---|
| 1 | Revenue at Risk | `SUM(stockout_days × Avg_Daily_Demand × Unit_Price)` annualised, plus forward exposure | < 1.0% of revenue | Red > 2%, Amber 1–2%, Green < 1% |
| 2 | Annual Carrying Cost | `SUM((safety_stock + order_qty/2) × Holding_Cost_Per_Unit)` under AI policy | −15% vs static | Green if reduction ≥ 15% |
| 3 | Working Capital Released | `SUM((static_avg_inv − ai_avg_inv) × Unit_Cost)` | Track only | Informational |
| 4 | Inventory Turnover | `annual_COGS / average_inventory_value` | ≥ 12.5x | Red < 10x, Amber 10–12.5x, Green ≥ 12.5x |
| 5 | Stockout Events YTD | `SUM(Stockout_Events_YTD)` | −40% vs baseline | Red > baseline, Green ≤ 60% of baseline |

---

## 3. Page 2 — Planner Exception Workbench

Operational screen, ranked by business impact. This is the planner's daily starting point (US-03).

```
+=================================================================================================+
|  EXCEPTION WORKBENCH — 91 SKUs flagged for reorder        [Warehouse v] [Category v] [My SKUs]  |
+=================================================================================================+
|  [ 91 FLAGGED ]  [ 12 MANUAL REVIEW ]  [ 38 OVERRIDES MTD ]  [ SGD 498K FORWARD EXPOSURE ]      |
+-------------------------------------------------------------------------------------------------+
| Rnk | SKU      | WH     | Stock | AI ROP | Fcst 30d | LT | Risk SGD  | Suggested Qty | Action    |
|-----|----------|--------|-------|--------|----------|----|-----------|---------------|-----------|
|  1  | SKU-0208 | BTM-03 |   412 |    980 |    1,240 | 38 |  158,851  |    1,977      | [Approve] |
|  2  | SKU-0212 | PEN-04 |   180 |    465 |      520 | 31 |  131,321  |      890      | [Approve] |
|  3  | SKU-0004 | BTM-03 |   940 |  1,310 |    1,680 | 29 |  130,576  |    2,340      | [Approve] |
|     |          |        |       |        |          |    |           |               |           |
|  Row expands to show: demand history sparkline, forecast vs actual, supplier, open POs,          |
|  MAPE, stockout history, and the override panel.                                                |
+-------------------------------------------------------------------------------------------------+
|  OVERRIDE PANEL (expanded row)                                                                  |
|  Suggested: 1,977 units    Override to: [______]    Reason code: [ Select... v ]  * required    |
|  Reason codes: PROMOTION_PLANNED | PROMOTION_ENDED | SUPPLIER_MOQ | CASH_CONSTRAINT |            |
|                NPI_TRANSITION | QUALITY_HOLD | KNOWN_ONE_OFF_ORDER                              |
|  Justification: [_________________________________________________]  * required                 |
|                                          [ Cancel ]  [ Save override & submit for approval ]    |
+=================================================================================================+
```

**Behavioural rules**

- Default sort: `total_revenue_at_risk DESC` (Query 1). Never sort by SKU ID by default — that buries the money.
- Bulk approve is available only for draft POs below the configurable value threshold (FR-15).
- Override without a reason code is rejected client-side and server-side (AC-03.2).
- The **Manual Review** tab holds SKUs excluded for insufficient history (AC-03.4) and is visually separated so those never inflate automation statistics.

---

## 4. Data Model for the BI Layer

```
                       +----------------------+
                       |    dim_warehouse     |
                       |----------------------|
                       | Warehouse_ID   (PK)  |
                       | Warehouse_Name       |
                       | Country / Region     |
                       +----------+-----------+
                                  |
+---------------------+           |            +----------------------+
|      dim_sku        |           |            |     dim_supplier     |
|---------------------|           |            |----------------------|
| SKU_ID        (PK)  |           |            | Supplier_ID    (PK)  |
| Product_Category    |           |            | Lead_Time_Days       |
| ABC_Class           |           |            +----------+-----------+
| Unit_Cost           |           |                       |
| Unit_Price          |           |                       |
+----------+----------+           |                       |
           |                      |                       |
           +----------+-----------+-----------------------+
                      |
          +-----------v--------------------------------+
          |          fact_inventory_position           |
          |--------------------------------------------|
          | SKU_ID, Warehouse_ID, Snapshot_Date  (PK)  |
          | Current_Stock, Units_Sold_YTD              |
          | Stockout_Events_YTD, Avg_Stockout_Duration |
          | Holding_Cost_Per_Unit                      |
          | Static_Reorder_Point, AI_Reorder_Point     |
          | Static_Order_Qty_Units, AI_Order_Qty_Units |
          | Demand_Forecast_AI, Forecast_MAPE_Pct      |
          | Reorder_Flag                               |
          +--------------------------------------------+
```

Star schema, daily snapshot grain. The flat `inventory_data.csv` in this repository is the denormalised equivalent — it collapses the three dimensions into the fact table for portability.

---

## 5. Core DAX / Calculated Measures

```
-- Safety stock implied by each policy
Static Safety Stock = MAX( 0, [Static_Reorder_Point] - ([Avg_Daily_Demand] * [Lead_Time_Days]) )
AI Safety Stock     = MAX( 0, [AI_Reorder_Point]     - ([Avg_Daily_Demand] * [Lead_Time_Days]) )

-- Average inventory position
Static Avg Inventory = [Static Safety Stock] + DIVIDE([Static_Order_Qty_Units], 2)
AI Avg Inventory     = [AI Safety Stock]     + DIVIDE([AI_Order_Qty_Units], 2)

-- Headline KPIs
Annual Carrying Cost (AI)     = SUMX(fact, [AI Avg Inventory]     * fact[Holding_Cost_Per_Unit])
Annual Carrying Cost (Static) = SUMX(fact, [Static Avg Inventory] * fact[Holding_Cost_Per_Unit])
Carrying Cost Saving          = [Annual Carrying Cost (Static)] - [Annual Carrying Cost (AI)]
Saving %                      = DIVIDE([Carrying Cost Saving], [Annual Carrying Cost (Static)])

Working Capital Released = SUMX(fact, ([Static Avg Inventory] - [AI Avg Inventory]) * RELATED(dim_sku[Unit_Cost]))

Annual COGS        = SUMX(fact, fact[Units_Sold_YTD] * RELATED(dim_sku[Unit_Cost])) * DIVIDE(365, 243)
Inventory Turnover = DIVIDE([Annual COGS], SUMX(fact, [AI Avg Inventory] * RELATED(dim_sku[Unit_Cost])))
Days On Hand       = DIVIDE(365, [Inventory Turnover])

Revenue At Risk = SUMX(
    fact,
    fact[Stockout_Events_YTD] * fact[Avg_Stockout_Duration_Days]
        * fact[Avg_Daily_Demand] * RELATED(dim_sku[Unit_Price])
) * DIVIDE(365, 243)

Forward Exposure = SUMX(
    fact,
    VAR LTD = fact[Avg_Daily_Demand] * fact[Lead_Time_Days]
    RETURN IF( fact[Current_Stock] < LTD, (LTD - fact[Current_Stock]) * RELATED(dim_sku[Unit_Price]), 0 )
)

SKUs Flagged     = CALCULATE( COUNTROWS(fact), fact[Reorder_Flag] = 1 )
SKUs Given More  = CALCULATE( COUNTROWS(fact), [AI Avg Inventory] > [Static Avg Inventory] )
```

---

## 6. Build Sequence

| Sprint | Deliverable |
|---|---|
| 1 | Star schema modelled; `fact_inventory_position` loading daily from the warehouse |
| 2 | Page 1 KPI strip and carrying-cost comparison chart, validated against Query 2 |
| 3 | Pareto and turnover scatter, validated against Queries 1 and 3 |
| 4 | Page 2 exception workbench with drill-through and the override panel |
| 5 | MAPE heatmap, model watchlist, and alerting (FR-12) |
| 6 | Row-level security by warehouse; UAT with each named persona; performance tuning to the 3-second P95 target (NFR-02) |

---

## 7. Validation Checklist

Before sign-off, every dashboard figure must reconcile to the SQL suite:

- [ ] Page 1 carrying cost by warehouse **=** Query 2 `ai_carrying_cost_sgd`
- [ ] Page 1 saving % **=** Query 2 `saving_pct_of_baseline` (portfolio: 20.67%)
- [ ] Pareto top-25 exposure **=** Query 1 `cumulative_pct_of_risk` at rank 25
- [ ] Turnover KPI **=** Query 3 portfolio-weighted `turnover_ai` (13.2x)
- [ ] Flagged SKU count **=** `SUM(Reorder_Flag)` (91)
- [ ] "SKUs given more stock" **=** Query 2 `skus_now_better_protected` (155)
- [ ] Every KPI card shows a "data as of" timestamp within the last 24 hours (AC-04.1)
