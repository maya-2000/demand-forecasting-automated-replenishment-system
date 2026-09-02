# Process Flow Diagrams (AS-IS / TO-BE)
## AI-Powered Inventory Forecasting & Automated Replenishment System

**Related documents:** `docs/BRD.md` (BRD-SCM-001), `docs/user_stories.md`
**Notation:** BPMN-style swimlane flows rendered in Mermaid.js. GitHub, GitLab, Notion, Confluence, and VS Code render these natively.

---

## 1. AS-IS Process: Manual Inventory Tracking & Purchase Order Creation

### 1.1 Narrative

Replenishment runs on a **weekly manual cycle**. The Demand Planner exports stock from the ERP into a spreadsheet, compares each SKU against a static reorder point last refreshed at some point in the previous quarter, and applies personal judgement to decide what to order. Purchase orders are keyed by hand into the ERP at roughly four minutes each. Because the review is weekly and the thresholds are stale, a SKU can sit below cover for up to six days before anyone notices, and the first signal is often a customer complaint rather than the process itself.

### 1.2 AS-IS Diagram

```mermaid
flowchart TD
    subgraph WH["Warehouse Operations"]
        A1["Weekly cycle begins<br/>Monday 09:00"]
        A2["Manually count and<br/>reconcile physical stock"]
        A3["Email stock discrepancies<br/>to Demand Planner"]
        A11["Receive goods and<br/>update ERP manually"]
    end

    subgraph DP["Demand Planning"]
        A4["Export stock report<br/>from ERP to Excel"]
        A5["Compare stock against<br/>STATIC reorder point<br/>set last quarter"]
        A6{"Stock below<br/>static threshold?"}
        A7["Apply planner intuition<br/>to set order quantity"]
        A8["Email order request<br/>to Procurement"]
        A12["Wait until next<br/>Monday review"]
    end

    subgraph PR["Procurement"]
        A9["Manually key purchase order<br/>into ERP - approx 4 min per PO"]
        A10["Send PO to supplier<br/>by email"]
    end

    subgraph RISK["Failure Modes"]
        X1["STOCKOUT<br/>Lost sales, expedited freight"]
        X2["OVERSTOCK<br/>Capital locked, holding cost"]
    end

    A1 --> A2 --> A3 --> A4 --> A5 --> A6
    A6 -- "No" --> A12
    A6 -- "Yes" --> A7 --> A8 --> A9 --> A10 --> A11
    A11 --> A12
    A12 -.-> A1

    A12 -. "Demand spike between<br/>weekly reviews" .-> X1
    A5 -. "Threshold too high for<br/>slow-moving SKU" .-> X2
    A7 -. "Buffer padding to<br/>feel safe" .-> X2

    classDef pain fill:#fdecea,stroke:#c0392b,stroke-width:2px,color:#7b241c
    classDef manual fill:#fef9e7,stroke:#b7950b,color:#7d6608
    class X1,X2 pain
    class A2,A4,A5,A7,A9,A11 manual
```

### 1.3 AS-IS Pain Points

| # | Step | Pain Point | Business Impact | BRD Root Cause |
|---|---|---|---|---|
| P1 | Manual stock count | Error-prone, point-in-time only | Decisions made on inaccurate stock | RC-05 |
| P2 | Excel export | No single source of truth; version sprawl | Duplicate and conflicting orders | RC-05 |
| P3 | Static reorder point | Ignores seasonality, trend, and volatility | Simultaneous overstock and stockout | RC-01 |
| P4 | Planner intuition | Inconsistent, undocumented, unauditable | Unpredictable service levels | RC-02 |
| P5 | Manual PO keying | ~4 minutes per PO, ~12 hours per week | Planner capacity consumed by admin | RC-04 |
| P6 | Weekly cadence | Up to 6-day detection lag | Avoidable stockouts | RC-01 |
| P7 | Lead time ignored | Supplier variability unmodelled | In-transit gaps become stockouts | RC-03 |

**Cycle time (AS-IS):** demand signal to PO transmitted = **3 to 9 days**.

---

## 2. TO-BE Process: AI Forecast Integration with Automated PO Triggers

### 2.1 Narrative

The ERP extract lands nightly and feeds an **AI forecasting engine** that produces a 30-day demand projection per SKU per warehouse. The engine computes a **dynamic reorder point** (lead-time demand plus statistically sized safety stock) and evaluates every SKU daily. Breaches raise `Reorder_Flag = 1` and generate a **draft purchase order** automatically. The Demand Planner works only the exception queue, ranked by revenue at risk, and Procurement retains the approval gate before any PO reaches a supplier. Actual demand is fed back to the model, closing the learning loop.

### 2.2 TO-BE Diagram

```mermaid
flowchart TD
    subgraph SRC["Data Layer - Automated"]
        B1["ERP nightly extract<br/>02:00 SGT"]
        B2["Validate and load<br/>stock, sales, lead times"]
        B3{"Data quality<br/>>= 98% pass?"}
        B4["Quarantine bad records<br/>and alert Data Engineering"]
    end

    subgraph AI["AI Forecast Engine - Automated"]
        B5["Generate 30-day demand forecast<br/>per SKU per warehouse"]
        B6["Compute dynamic reorder point<br/>= Avg Daily Demand x Lead Time<br/>+ Safety Stock at 95% service level"]
        B7["Publish Demand_Forecast_AI<br/>and forecast error"]
    end

    subgraph ENG["Replenishment Engine - Automated"]
        B8["Evaluate Current_Stock<br/>against dynamic reorder point"]
        B9{"Current_Stock <=<br/>dynamic reorder point?"}
        B10["Set Reorder_Flag = 1"]
        B11["Net off open purchase orders<br/>to prevent duplicates"]
        B12["Auto-generate DRAFT PO<br/>with suggested quantity"]
        B13["Continue monitoring<br/>next daily cycle"]
    end

    subgraph PLN["Demand Planner - Exception Only"]
        B14["Review exception workbench<br/>ranked by revenue at risk"]
        B15{"Override<br/>required?"}
        B16["Adjust quantity<br/>with mandatory reason code"]
        B17["Confirm draft PO"]
    end

    subgraph PRC["Procurement - Control Gate"]
        B18{"Approve<br/>purchase order?"}
        B19["Transmit PO to supplier<br/>via EDI or API"]
        B20["Reject and return<br/>with comments"]
    end

    subgraph OUT["Outcome & Learning Loop"]
        B21["Goods received<br/>and ERP auto-updated"]
        B22["Executive dashboard refresh<br/>cost, stockouts, turnover, MAPE"]
        B23["Actual demand fed back<br/>to retrain model monthly"]
    end

    B1 --> B2 --> B3
    B3 -- "No" --> B4
    B4 -.-> B1
    B3 -- "Yes" --> B5 --> B6 --> B7 --> B8 --> B9
    B9 -- "No" --> B13
    B13 -.-> B8
    B9 -- "Yes" --> B10 --> B11 --> B12 --> B14 --> B15
    B15 -- "Yes" --> B16 --> B17
    B15 -- "No" --> B17
    B17 --> B18
    B18 -- "Approved" --> B19 --> B21 --> B22 --> B23
    B18 -- "Rejected" --> B20
    B20 -.-> B14
    B23 -.-> B5

    classDef auto fill:#eafaf1,stroke:#1e8449,stroke-width:2px,color:#145a32
    classDef human fill:#eaf2f8,stroke:#2471a3,stroke-width:2px,color:#1a5276
    classDef gate fill:#fef5e7,stroke:#ca6f1e,stroke-width:2px,color:#7e5109
    class B1,B2,B5,B6,B7,B8,B10,B11,B12,B13,B21,B22,B23 auto
    class B14,B16,B17 human
    class B18,B19,B20 gate
```

### 2.3 Replenishment Trigger Sequence

```mermaid
sequenceDiagram
    autonumber
    participant ERP as ERP System
    participant AI as AI Forecast Engine
    participant RE as Replenishment Engine
    participant PL as Demand Planner
    participant PO as Procurement
    participant SUP as Supplier

    ERP->>AI: Nightly stock, sales and lead-time extract
    AI->>AI: Generate 30-day demand forecast
    AI->>RE: Publish forecast and dynamic reorder point
    RE->>ERP: Read Current_Stock and open POs
    RE->>RE: Evaluate stock vs reorder point
    alt Stock at or below reorder point
        RE->>RE: Set Reorder_Flag = 1
        RE->>PL: Create draft PO in exception workbench
        PL->>PL: Review, optionally override with reason code
        PL->>PO: Submit for approval
        alt Approved
            PO->>SUP: Transmit purchase order
            SUP-->>ERP: Confirm order and delivery date
        else Rejected
            PO-->>PL: Return with comments
        end
    else Stock above reorder point
        RE->>RE: No action, re-evaluate next cycle
    end
    ERP-->>AI: Actual demand for model retraining
```

### 2.4 AS-IS vs TO-BE Comparison

| Dimension | AS-IS | TO-BE | Improvement |
|---|---|---|---|
| Review cadence | Weekly, manual | Daily, automated | 7x faster detection |
| Reorder point basis | Static, quarterly | Dynamic, nightly forecast | Adaptive to demand |
| Safety stock method | Planner intuition | Statistical, service-level driven | Consistent, auditable |
| Lead-time handling | Ignored | Modelled in reorder point | Closes in-transit gap |
| PO creation | Manual keying, ~4 min | Auto-generated draft | ~80% effort reduction |
| PO approval | Informal / verbal | Structured approval gate | Control strengthened |
| Planner focus | All SKUs, transactional | Exceptions ranked by risk | Capacity redeployed |
| Cycle time (signal to PO) | 3-9 days | Under 24 hours | Up to 90% reduction |
| Auditability | Email and spreadsheet trail | Full immutable audit log | Audit-ready |
| Reporting | Monthly manual deck | Daily automated dashboard | Faster correction |

### 2.5 Controls Retained by Design

Automation stops short of full autonomy in Phase 1, by design:

1. **Human approval gate:** no PO reaches a supplier without Procurement approval (FR-05, OOS-05).
2. **Mandatory override reason codes:** planner judgement is permitted but always recorded (FR-06).
3. **Data quality gate:** a failed extract keeps the previous day's thresholds in force instead of acting on bad data (AC-01.4).
4. **Duplicate-order netting:** open POs are netted off before a new draft is raised (AC-02.5).
5. **Model degradation alerting:** sustained MAPE breaches escalate to a human owner (FR-12).
