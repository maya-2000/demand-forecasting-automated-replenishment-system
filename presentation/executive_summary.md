# Executive Summary
## Demand Forecasting & Automated Replenishment System

**Prepared for:** Executive Steering Committee
**Prepared by:** Business Analyst (MSc Management, Singapore Management University)
**Date:** 2 September 2026
**Decision requested:** Approve SGD 850,000 implementation to replace static reorder points with forecast-driven automated replenishment across four distribution centres.

---

## 1. The One-Page Case

We hold too much of the wrong inventory and too little of the right inventory, at the same time.

Replenishment across our four regional DCs is governed by static reorder points held in spreadsheets and refreshed roughly quarterly. Analysis of the 1,000 active SKU-warehouse positions shows what that costs us:

| Finding | Value |
|---|---|
| Revenue at risk from stockouts (annualised) | **SGD 14.2M** (4.4% of revenue) |
| SKU-warehouse positions that stocked out YTD | **417 of 1,000** (41.7%) |
| Stockout events YTD | **968** |
| Annual inventory carrying cost under current policy | **SGD 3.76M** |
| Working capital tied up in average inventory | **SGD 17.45M** |
| Portfolio inventory turnover | **10.8x** (target 12.5x) |
| Slowest-turning C-class SKUs | **182-372 days** of stock on hand |

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="charts/03-revenue-at-risk-pareto-dark.png">
  <img alt="Stockout exposure is concentrated: the top 25 of 1,000 SKU-warehouse positions carry 31% of total revenue at risk." src="charts/03-revenue-at-risk-pareto-light.png">
</picture>

The two problems share one root cause: **a fixed threshold cannot respond to demand that moves.**

---

## 2. What We Propose

Replace the static threshold with a nightly AI demand forecast that drives a **dynamic reorder point**, and let the system raise draft purchase orders automatically, with Procurement retaining the approval gate.

| | Today | Proposed |
|---|---|---|
| Review cadence | Weekly, manual | Nightly, automated |
| Reorder point | Fixed 30-day cover | Lead-time demand + statistical safety stock at 95% service level |
| Order sizing | Large, infrequent (manual PO effort ~SGD 550 each) | Economic quantity under automated PO cost (~SGD 450 each) |
| PO creation | Keyed by hand, ~4 min each | Auto-generated draft |
| Planner role | Processes every SKU | Works exceptions ranked by revenue at risk |
| Approval | Informal | Structured Procurement gate, fully audited |

Automation stops short of full autonomy by design: **no purchase order reaches a supplier without human approval.**

---

## 3. Quantified Benefit

### 3.1 Carrying cost reduction: SGD 983,926 per year (26.1%)

The saving is decomposable, which is what makes it auditable:

| Component | Annual saving | Share | Why it exists |
|---|---|---|---|
| Safety stock reduction | SGD 739,659 | 75.2% | Statistical sizing replaces a flat 30-day buffer |
| Cycle stock reduction | SGD 244,267 | 24.8% | Cheaper automated ordering permits smaller, more frequent orders |
| **Total** | **SGD 983,926** | **100%** | |

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="charts/02-savings-waterfall-dark.png">
  <img alt="The SGD 983,926 annual saving splits into SGD 739,659 from safety stock reduction and SGD 244,267 from cycle stock reduction." src="charts/02-savings-waterfall-light.png">
</picture>

**Working capital released: SGD 4.12M.** Average inventory value falls from SGD 17.45M to SGD 13.33M, lifting portfolio turnover from **10.8x to 14.1x** and clearing the 12.5x internal target.

### 3.2 Savings are not uniform, and that is the point

| Warehouse | Carrying cost (legacy) | Carrying cost (forecast-driven) | Annual saving | % of baseline | SKUs given *more* stock |
|---|---|---|---|---|---|
| WH-SIN-01 Singapore Central | SGD 1,535,619 | SGD 955,022 | **SGD 580,597** | 37.8% | 34 |
| WH-PEN-04 Penang | SGD 858,595 | SGD 674,779 | **SGD 183,816** | 21.4% | 54 |
| WH-JHR-02 Johor Bahru | SGD 804,473 | SGD 644,687 | **SGD 159,787** | 19.9% | 47 |
| WH-BTM-03 Batam | SGD 566,056 | SGD 506,331 | **SGD 59,725** | 10.6% | 62 |
| **Portfolio** | **SGD 3,764,744** | **SGD 2,780,818** | **SGD 983,926** | **26.1%** | **197** |

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="charts/01-carrying-cost-by-warehouse-dark.png">
  <img alt="Carrying cost by warehouse under both policies, with the saving percentage and the number of SKUs given more stock at each site." src="charts/01-carrying-cost-by-warehouse-light.png">
</picture>

Read the last column carefully. For **197 SKU-warehouse positions the model increases inventory**, because the static threshold was under-covering long-lead-time, volatile items. Batam, our longest-lead-time DC, saves the least, because most of its correction adds protection instead of stripping stock out. That is the system working as designed: it reallocates inventory to where it earns its keep, rather than cutting it everywhere.

### 3.3 Service level recovery: SGD 590,000 per year

Stockouts cost SGD 6.16M in lost gross margin annually. Two conservative assumptions apply here: only **35%** of stockout demand is genuinely lost rather than substituted or backordered, and the system removes **40%** of stockout events (the BO-02 target). Together they give **SGD 862,467** in recovered margin.

---

## 4. Financial Case

| Line | Year 1 |
|---|---|
| Carrying cost reduction | SGD 983,926 |
| Recovered gross margin from fewer stockouts | SGD 862,467 |
| Planner productivity (12 hrs/week released) | SGD 28,080 |
| **Gross annual benefit** | **SGD 1,874,472** |
| Less: annual run cost (cloud, model ops, licences) | (SGD 220,000) |
| **Net annual benefit** | **SGD 1,654,472** |
| One-time implementation | SGD 850,000 |

| Metric | Result |
|---|---|
| **Payback period** | **6.2 months** |
| **Year-1 ROI** | **94.6%** |
| **3-year NPV @ 10%** | **SGD 3,264,428** |
| **3-year ROI** | **484%** |
| **One-time working capital release** | **SGD 4,116,922** |

The working capital release is shown separately because it is a balance-sheet event, not recurring P&L. It is nonetheless the single largest cash item in the case.

---

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="charts/05-roi-payback-dark.png">
  <img alt="Cumulative net position over 24 months, crossing breakeven at 6.2 months." src="charts/05-roi-payback-light.png">
</picture>

---

## 5. Risks and How They Are Controlled

| Risk | Control |
|---|---|
| Planners distrust the forecast and override it systematically | 4-week shadow run; override rate tracked as an adoption KPI; published accuracy |
| Automated ordering creates a costly error at scale | Mandatory Procurement approval gate; daily PO value cap; anomaly alerting |
| Poor lead-time master data degrades the reorder points | Data remediation sprint before go-live; ongoing lead-time variance monitoring |
| Forecast degrades under promotions or demand shocks | MAPE alerting at 25% for three consecutive cycles; manual override always available |
| Savings are quietly re-spent on buffer stock | Finance tracks working capital release as a governed KPI with monthly reporting |

---

## 6. What We Are Asking For

1. **Approve** SGD 850,000 implementation funding and SGD 220,000 annual run cost.
2. **Confirm** Procurement retains PO approval authority in Phase 1 (no change to control environment).
3. **Endorse** the four-DC pilot scope, with a Phase 2 decision gate at month 9 covering raw materials and retail store replenishment.

**Recommended decision: proceed.** The payback sits inside a single financial year, the control environment gets stronger instead of weaker, and the benefit is measurable from source data rather than asserted.

---

## Appendix: Evidence Base

Every figure in this summary is reproducible from the artefacts in this repository:

| Figure | Source |
|---|---|
| Revenue at risk, stockout concentration | `sql/analysis_queries.sql`, Query 1 |
| Carrying cost savings by warehouse | `sql/analysis_queries.sql`, Query 2 |
| Inventory turnover, slow-moving tail | `sql/analysis_queries.sql`, Query 3 |
| Underlying dataset (1,000 rows) | `data/inventory_data.csv`, built by `data/run_pipeline.py` |
| Forecast accuracy, held-out validation | `data/02_forecast_demand.py` |
| Every chart in this summary | `presentation/generate_charts.py` |
| Requirements and scope | `docs/BRD.md` |
| Process change | `docs/process_flows.md` |

**Note on data:** this analysis runs on a synthetic dataset engineered to reproduce the failure modes described above. It demonstrates the analytical method and the shape of the business case; the absolute figures would be restated against production data before a real funding decision.
