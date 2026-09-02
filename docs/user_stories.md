# User Stories & Acceptance Criteria
## AI-Powered Inventory Forecasting & Automated Replenishment System

**Related document:** `docs/BRD.md` (BRD-SCM-001 v1.0)
**Format:** Standard user story + Gherkin (Given / When / Then) acceptance criteria
**Estimation:** Story points, modified Fibonacci

---

## Personas

| Persona | Role | Primary Goal |
|---|---|---|
| **Priya** | Demand Planner | Right stock, right place, minimum firefighting |
| **Wei Ming** | Warehouse Operations Manager | Avoid stockouts and emergency freight |
| **Ravi** | Procurement Officer | Approve accurate POs quickly, control spend |
| **Sarah** | VP Supply Chain (Executive) | Working capital efficiency and service levels |
| **Daniel** | Finance Business Partner | Auditable, defensible savings numbers |

---

## US-01 — Nightly AI Demand Forecast

> **As a** Demand Planner (Priya),
> **I want** the system to generate a 30-day AI demand forecast for every SKU at every warehouse each night,
> **So that** my replenishment decisions are based on projected demand rather than a static threshold set last quarter.

**Priority:** Must Have  **Points:** 8  **Traces to:** FR-01, FR-02, FR-13, NFR-01, NFR-05

### Acceptance Criteria

**AC-01.1 — Forecast is generated for all eligible SKUs**
```gherkin
Given 1,000 active SKU-warehouse pairs each have at least 6 months of sales history
When the nightly forecast batch runs at 02:00 SGT
Then a Demand_Forecast_AI value in units for the next 30 days is stored for every one of the 1,000 pairs
And the batch completes before 03:00 SGT
```

**AC-01.2 — Dynamic reorder point is derived from the forecast**
```gherkin
Given a SKU has an Avg_Daily_Demand of 20 units and a Lead_Time_Days of 10
And the configured service level for its warehouse is 95%
When the forecast batch computes the dynamic reorder point
Then the reorder point equals (20 x 10) + Safety_Stock
And Safety_Stock is derived from the forecast error at the 95% service level
And the computed value is stored with the run timestamp and model version
```

**AC-01.3 — SKUs with insufficient history are excluded, not guessed**
```gherkin
Given a SKU has only 3 months of sales history
When the nightly forecast batch runs
Then no Demand_Forecast_AI is produced for that SKU
And the SKU is routed to the manual review queue with reason "INSUFFICIENT_HISTORY"
```

**AC-01.4 — Upstream data failure fails safe**
```gherkin
Given the ERP nightly extract has not landed by 02:00 SGT
When the forecast batch attempts to start
Then the batch does not run against stale data
And the previous day's reorder points remain in force
And an alert is raised to Data Engineering and the Demand Planner
```

---

## US-02 — Automated Reorder Flag & Draft Purchase Order

> **As a** Warehouse Operations Manager (Wei Ming),
> **I want** the system to flag SKUs that have breached their dynamic reorder point and raise a draft purchase order automatically,
> **So that** replenishment is triggered the day stock falls below cover, instead of waiting for the weekly manual spreadsheet review.

**Priority:** Must Have  **Points:** 13  **Traces to:** FR-03, FR-04, FR-05, FR-15

### Acceptance Criteria

**AC-02.1 — Flag is raised at or below the reorder point**
```gherkin
Given SKU-0421 at warehouse WH-SIN-01 has a dynamic reorder point of 250 units
And its Current_Stock is 240 units
When the daily replenishment evaluation runs
Then Reorder_Flag is set to 1 for SKU-0421 at WH-SIN-01
And the flag record stores the stock level and reorder point that triggered it
```

**AC-02.2 — No flag above the reorder point**
```gherkin
Given SKU-0422 has a dynamic reorder point of 250 units
And its Current_Stock is 260 units
When the daily replenishment evaluation runs
Then Reorder_Flag remains 0 for SKU-0422
And no draft purchase order is created
```

**AC-02.3 — Draft PO is created with a complete, suggested order**
```gherkin
Given SKU-0421 has been flagged for reorder
When the automated replenishment step executes
Then a draft purchase order is created within 5 minutes
And it contains the SKU, warehouse, suggested order quantity, preferred supplier, unit cost, and expected receipt date
And the draft PO status is "PENDING_APPROVAL"
```

**AC-02.4 — No PO reaches a supplier without human approval**
```gherkin
Given a draft purchase order is in status "PENDING_APPROVAL"
When any automated process attempts to transmit it to the supplier
Then transmission is blocked
And the PO is transmitted only after a user holding the Procurement role approves it
```

**AC-02.5 — Duplicate orders are prevented**
```gherkin
Given SKU-0421 already has an open purchase order covering 400 units
And its Current_Stock is still below the dynamic reorder point
When the daily replenishment evaluation runs
Then the on-order quantity is included in the available position
And a second draft purchase order is not created for the same demand
```

---

## US-03 — Planner Exception Workbench with Controlled Override

> **As a** Demand Planner (Priya),
> **I want** a single prioritised worklist of flagged SKUs where I can review and override suggested order quantities with a recorded reason,
> **So that** I can apply commercial judgement the model does not have, while keeping every deviation auditable.

**Priority:** Must Have  **Points:** 8  **Traces to:** FR-06, FR-07, FR-14, NFR-02, NFR-09

### Acceptance Criteria

**AC-03.1 — Worklist is prioritised by business impact**
```gherkin
Given 45 SKUs are flagged for reorder today
When Priya opens the exception workbench
Then all 45 flagged SKUs are listed
And they are sorted in descending order of revenue at risk
And the page renders within 3 seconds
```

**AC-03.2 — Override requires a reason code**
```gherkin
Given Priya is reviewing a draft PO with a suggested quantity of 500 units
When she changes the quantity to 300 units
And she attempts to save without selecting a reason code
Then the save is rejected
And a validation message requires a reason code and justification
```

**AC-03.3 — Override is captured in the audit trail**
```gherkin
Given Priya changes a suggested quantity from 500 to 300 units
And she selects reason code "PROMOTION_ENDED" with a justification note
When she saves the override
Then the audit trail records the user, timestamp, original quantity, revised quantity, reason code, and justification
And the revised quantity flows to the draft purchase order
```

**AC-03.4 — Manual-queue SKUs are visibly separated**
```gherkin
Given 12 SKUs were excluded from forecasting for insufficient history
When Priya opens the exception workbench
Then those 12 SKUs appear in a separate "Manual Review" tab with their exclusion reason
And they are not counted in the automated flag statistics
```

---

## US-04 — Executive Inventory Performance Dashboard

> **As the** VP of Supply Chain (Sarah),
> **I want** a daily dashboard showing carrying cost, stockout events, inventory turnover, revenue at risk, and forecast accuracy by warehouse,
> **So that** I can see whether the AI replenishment policy is delivering the committed working capital and service level benefits without waiting for the monthly deck.

**Priority:** Must Have  **Points:** 5  **Traces to:** FR-08, FR-09, FR-10, FR-12

### Acceptance Criteria

**AC-04.1 — Executive KPIs are present and current**
```gherkin
Given the nightly analytics refresh has completed
When Sarah opens the executive dashboard
Then she sees total carrying cost, stockout events YTD, portfolio inventory turnover, and total revenue at risk
And each KPI displays its variance against the prior period and against target
And the dashboard shows a "data as of" timestamp within the last 24 hours
```

**AC-04.2 — Results are decomposable by warehouse**
```gherkin
Given the dashboard is displaying portfolio-level KPIs
When Sarah filters to warehouse WH-JHR-02
Then every KPI recalculates for that warehouse only
And the AI-versus-static carrying cost comparison is shown for that warehouse
```

**AC-04.3 — Forecast accuracy is transparent**
```gherkin
Given 90 days of forecast and actual demand history exist
When Sarah views the forecast accuracy panel
Then MAPE is displayed at portfolio, warehouse, and ABC-class level
And A-class SKUs with MAPE above 25% are highlighted as exceptions
```

**AC-04.4 — Sustained model degradation raises an alert**
```gherkin
Given an A-class SKU has recorded MAPE above 25% for three consecutive forecast cycles
When the third cycle completes
Then an alert is sent to the Demand Planner and the Data Science owner
And the SKU is listed in the dashboard's "Model Watchlist"
```

---

## US-05 — Auditable Savings & Benefits Reporting

> **As a** Finance Business Partner (Daniel),
> **I want** the carrying cost savings of the AI policy versus the previous static thresholds to be calculated from source data with a full audit trail,
> **So that** I can defend the reported working capital release in the quarterly business review and in internal audit.

**Priority:** Should Have  **Points:** 5  **Traces to:** FR-10, FR-11, NFR-08, BO-01

### Acceptance Criteria

**AC-05.1 — Savings are computed against a frozen baseline**
```gherkin
Given the static reorder point baseline was frozen at project kick-off
When the monthly benefits report is generated
Then carrying cost savings are calculated as (baseline average inventory - AI average inventory) x Holding_Cost_Per_Unit
And the result is reported per warehouse and for the total portfolio
```

**AC-05.2 — Every reported figure is traceable to source records**
```gherkin
Given Daniel is reviewing a reported saving of SGD 184,000 for WH-SIN-01
When he drills into the figure
Then he can view the contributing SKU-level records, their holding cost rates, and both inventory positions
And each record shows the model version and run timestamp that produced it
```

**AC-05.3 — Overrides are visible in the benefits calculation**
```gherkin
Given planners applied 38 manual overrides during the reporting month
When the benefits report is generated
Then the report states the number and net unit impact of overrides
And savings attributable to overridden lines are disclosed separately from model-driven savings
```

**AC-05.4 — Audit history is retained and immutable**
```gherkin
Given a forecast run and its resulting POs completed 18 months ago
When an internal auditor requests the inputs, thresholds, and approvals for that run
Then the complete record is retrievable
And no record has been altered since creation
```

---

## Traceability Summary

| User Story | Functional Requirements | Business Objective |
|---|---|---|
| US-01 | FR-01, FR-02, FR-13 | BO-05 |
| US-02 | FR-03, FR-04, FR-05, FR-15 | BO-02, BO-03 |
| US-03 | FR-06, FR-07, FR-14 | BO-02, BO-03 |
| US-04 | FR-08, FR-09, FR-10, FR-12 | BO-01, BO-04, BO-05 |
| US-05 | FR-10, FR-11 | BO-01, BO-04 |

---

## Definition of Done

A story is Done when:

1. All acceptance criteria pass in UAT with business sign-off from the named persona's function.
2. Unit and integration tests are written and passing in CI.
3. Relevant non-functional targets (performance, security, audit) are evidenced.
4. Audit logging is implemented for every state change introduced by the story.
5. User documentation and training material are updated.
6. The story is demonstrated in sprint review and accepted by the Product Owner.
