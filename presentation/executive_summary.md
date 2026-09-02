# Executive Summary
## AI-Powered Inventory Forecasting & Automated Replenishment System

**Prepared for:** Executive Steering Committee
**Prepared by:** Business Analyst — MSc Management, Singapore Management University
**Date:** 2 September 2026
**Decision requested:** Approve SGD 850,000 implementation to replace static reorder points with forecast-driven automated replenishment across four distribution centres.

---

## 1. The One-Page Case

We hold too much of the wrong inventory and too little of the right inventory, at the same time.

Replenishment across our four regional DCs is governed by static reorder points held in spreadsheets and refreshed roughly quarterly. Analysis of the 1,000 active SKU–warehouse positions shows what that costs us:

| Finding | Value |
|---|---|
| Revenue at risk from stockouts (annualised) | **SGD 10.1M** (3.0% of revenue) |
| SKU–warehouse positions that stocked out YTD | **687 of 1,000** (68.7%) |
| Stockout events YTD | **1,661** |
| Annual inventory carrying cost under current policy | **SGD 3.76M** |
| Working capital tied up in average inventory | **SGD 18.1M** |
| Portfolio inventory turnover | **10.7x** (target 12.5x) |
| Slowest-turning C-class SKUs | **135–300 days** of stock on hand |

The two problems share one root cause: **a fixed threshold cannot respond to demand that moves.**

---

## 2. What We Propose

Replace the static threshold with a nightly AI demand forecast that drives a **dynamic reorder point**, and let the system raise draft purchase orders automatically — with Procurement retaining the approval gate.

| | Today | Proposed |
|---|---|---|
| Review cadence | Weekly, manual | Nightly, automated |
| Reorder point | Fixed 30-day cover | Lead-time demand + statistical safety stock at 95% service level |
| Order sizing | Large, infrequent (manual PO effort ~SGD 550 each) | Economic quantity under automated PO cost (~SGD 450 each) |
| PO creation | Keyed by hand, ~4 min each | Auto-generated draft |
| Planner role | Processes every SKU | Works exceptions ranked by revenue at risk |
| Approval | Informal | Structured Procurement gate, fully audited |

Automation deliberately stops short of autonomy: **no purchase order reaches a supplier without human approval.**

---

## 3. Quantified Benefit

### 3.1 Carrying cost reduction — SGD 776,086 per year (20.7%)

The saving is decomposable, which is what makes it auditable:

| Component | Annual saving | Share | Why it exists |
|---|---|---|---|
| Safety stock reduction | SGD 510,250 | 65.7% | Statistical sizing replaces a flat 30-day buffer |
| Cycle stock reduction | SGD 265,836 | 34.3% | Cheaper automated ordering permits smaller, more frequent orders |
| **Total** | **SGD 776,086** | **100%** | |

**Working capital released: SGD 3.44M** — average inventory value falls from SGD 18.1M to SGD 14.7M, lifting portfolio turnover from **10.7x to 13.2x** and clearing the 12.5x internal target.

### 3.2 Savings are not uniform — and that is the point

| Warehouse | Carrying cost (static) | Carrying cost (AI) | Annual saving | % of baseline | SKUs given *more* stock |
|---|---|---|---|---|---|
| WH-SIN-01 Singapore Central | SGD 1,261,954 | SGD 888,551 | **SGD 373,403** | 29.6% | 19 |
| WH-JHR-02 Johor Bahru | SGD 901,995 | SGD 717,811 | **SGD 184,184** | 20.4% | 32 |
| WH-PEN-04 Penang | SGD 878,327 | SGD 728,490 | **SGD 149,837** | 17.1% | 36 |
| WH-BTM-03 Batam | SGD 713,173 | SGD 644,511 | **SGD 68,662** | 9.6% | 68 |
| **Portfolio** | **SGD 3,755,450** | **SGD 2,979,363** | **SGD 776,086** | **20.7%** | **155** |

Read the last column carefully. For **155 SKU–warehouse positions the model increases inventory**, because the static threshold was under-covering long-lead-time, volatile items. Batam — our longest-lead-time DC — saves least precisely because most of its correction is protective rather than reductive. That is the system working as designed: it reallocates inventory to where it earns its keep, rather than cutting it everywhere.

### 3.3 Service level recovery — SGD 590,000 per year

Stockouts cost SGD 4.21M in lost gross margin annually. Applying two deliberately conservative assumptions — that only **35%** of stockout demand is genuinely lost rather than substituted or backordered, and that the system removes **40%** of stockout events (the BO-02 target) — yields **SGD 589,664** in recovered margin.

---

## 4. Financial Case

| Line | Year 1 |
|---|---|
| Carrying cost reduction | SGD 776,086 |
| Recovered gross margin from fewer stockouts | SGD 589,664 |
| Planner productivity (12 hrs/week released) | SGD 28,080 |
| **Gross annual benefit** | **SGD 1,393,830** |
| Less: annual run cost (cloud, model ops, licences) | (SGD 220,000) |
| **Net annual benefit** | **SGD 1,173,830** |
| One-time implementation | SGD 850,000 |

| Metric | Result |
|---|---|
| **Payback period** | **8.7 months** |
| **Year-1 ROI** | **38.1%** |
| **3-year NPV @ 10%** | **SGD 2,069,141** |
| **3-year ROI** | **314%** |
| **One-time working capital release** | **SGD 3,444,784** |

The working capital release is shown separately because it is a balance-sheet event, not recurring P&L. It is nonetheless the single largest cash item in the case.

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

**Recommended decision: proceed.** The payback sits inside a single financial year, the control environment is strengthened rather than weakened, and the benefit is measurable from source data rather than asserted.

---

## Appendix — Evidence Base

Every figure in this summary is reproducible from the artefacts in this repository:

| Figure | Source |
|---|---|
| Revenue at risk, stockout concentration | `sql/analysis_queries.sql` — Query 1 |
| Carrying cost savings by warehouse | `sql/analysis_queries.sql` — Query 2 |
| Inventory turnover, slow-moving tail | `sql/analysis_queries.sql` — Query 3 |
| Underlying dataset (1,000 rows) | `data/inventory_data.csv`, generated by `data/generate_supply_chain_data.py` |
| Requirements and scope | `docs/BRD.md` |
| Process change | `docs/process_flows.md` |

**Note on data:** this analysis runs on a synthetic dataset engineered to reproduce the failure modes described above. It demonstrates the analytical method and the shape of the business case; the absolute figures would be restated against production data before a real funding decision.
