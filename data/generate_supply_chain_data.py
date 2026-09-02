"""
Synthetic Supply Chain Inventory Dataset Generator
==================================================

Project : AI-Powered Inventory Forecasting & Automated Replenishment System
Output  : data/inventory_data.csv  (1,000 rows = 250 SKUs x 4 warehouses)
Purpose : Produce a realistic, reproducible dataset that supports the analytics in
          sql/analysis_queries.sql without relying on confidential company data.

DESIGN NOTES
------------
The dataset is engineered to reproduce the two failure modes described in the BRD:

  1. OVERSTOCK on slow movers  - the legacy static policy holds a flat 30-day cover
     regardless of lead time, so short-lead-time / low-volatility SKUs carry far more
     safety stock than a service-level calculation would require.
  2. STOCKOUTS on volatile fast movers - the same flat cover under-protects SKUs with
     long, variable lead times and high demand volatility.

Both policies are modelled explicitly so that savings can be computed rather than assumed:

    Lead_Time_Demand      = Avg_Daily_Demand x Lead_Time_Days
    Static_Reorder_Point  = stale demand estimate x 30 days flat cover   (legacy policy)
    AI_Reorder_Point      = Lead_Time_Demand + z x sigma x sqrt(Lead_Time_Days)
    Safety_Stock          = Reorder_Point - Lead_Time_Demand
    Order_Quantity        = sqrt(2 x Annual_Demand x Ordering_Cost / Holding_Cost)   (EOQ)
    Average_Inventory     = Safety_Stock + Order_Quantity / 2

The carrying-cost delta therefore decomposes into two auditable components (US-05 / AC-05.1):

    Safety stock saving = (Static_Safety_Stock - AI_Safety_Stock) x Holding_Cost_Per_Unit
    Cycle stock saving  = (Static_Order_Qty - AI_Order_Qty) / 2 x Holding_Cost_Per_Unit

The cycle stock component exists because raising a PO manually costs ~SGD 550 in planner
and procurement effort, which drives large infrequent orders; an auto-generated draft PO
costs ~SGD 450 to review and approve, so the economic order quantity - and the cycle stock it implies -
is materially smaller.

REPRODUCIBILITY
---------------
    python3 data/generate_supply_chain_data.py

A fixed RNG seed (42) means every run produces a byte-identical CSV.

DATA DICTIONARY
---------------
    SKU_ID                      Stock keeping unit identifier            (SKU-0001)
    Warehouse_ID                Distribution centre identifier           (WH-SIN-01)
    Product_Category            Merchandise category
    ABC_Class                   Pareto revenue classification            (A / B / C)
    Supplier_ID                 Preferred supplier                       (SUP-012)
    Unit_Cost                   Landed cost per unit, SGD
    Unit_Price                  List selling price per unit, SGD
    Lead_Time_Days              Supplier lead time, days                 [REQUIRED FIELD]
    Lead_Time_Variability_Days  Std deviation of lead time, days
    Avg_Daily_Demand            Mean daily unit demand
    Demand_Std_Dev              Std deviation of daily unit demand
    Units_Sold_YTD              Units sold year to date (243 days)
    Current_Stock               On-hand units today                      [REQUIRED FIELD]
    Stockout_Events_YTD         Count of stockout events YTD             [REQUIRED FIELD]
    Avg_Stockout_Duration_Days  Mean days per stockout event
    Holding_Cost_Per_Unit       Annual carrying cost per unit, SGD       [REQUIRED FIELD]
    Static_Reorder_Point        Legacy manual threshold, units
    Demand_Forecast_AI          AI 30-day forward demand forecast, units [REQUIRED FIELD]
    AI_Reorder_Point            Forecast-driven dynamic threshold, units
    Static_Order_Qty_Units      Economic order quantity under manual PO cost, units
    AI_Order_Qty_Units          Economic order quantity under automated PO cost, units
    Forecast_MAPE_Pct           Trailing 90-day forecast error, percent
    Reorder_Flag                1 when Current_Stock <= AI_Reorder_Point [REQUIRED FIELD]
    Snapshot_Date               As-of date of the extract
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------------
RANDOM_SEED = 42
N_SKUS = 250
SNAPSHOT_DATE = "2026-08-31"
YTD_DAYS = 243                 # 1 Jan 2026 -> 31 Aug 2026
SERVICE_LEVEL_Z = 1.645        # 95% service level, one-tailed normal
STATIC_COVER_DAYS = 30         # legacy flat-cover policy
ANNUAL_HOLDING_RATE = 0.22     # 22% of unit cost per year (capital, storage, insurance, obsolescence)
ORDERING_COST_MANUAL = 550.0   # cost per manually raised PO: keying, chasing, expediting, clearance
ORDERING_COST_AUTOMATED = 450.0  # cost per auto-generated PO: approval review only
DEMAND_SCALE = 0.30            # calibrates the portfolio to a ~SGD 340m regional distributor

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inventory_data.csv")

WAREHOUSES = {
    # id            name                lead-time factor  holding factor  service maturity
    "WH-SIN-01": {"name": "Singapore Central",  "lt_factor": 0.85, "hold_factor": 1.35, "maturity": 1.15},
    "WH-JHR-02": {"name": "Johor Bahru",        "lt_factor": 1.05, "hold_factor": 0.85, "maturity": 0.95},
    "WH-BTM-03": {"name": "Batam",              "lt_factor": 1.30, "hold_factor": 0.70, "maturity": 0.80},
    "WH-PEN-04": {"name": "Penang",             "lt_factor": 1.10, "hold_factor": 0.90, "maturity": 1.00},
}

CATEGORIES = {
    # category            weight  base daily demand  demand CV  unit cost range   base lead time
    "Consumer Electronics": {"w": 0.22, "demand": 34, "cv": 0.55, "cost": (45, 420),  "lt": 21},
    "Industrial Components":{"w": 0.20, "demand": 16, "cv": 0.35, "cost": (18, 260),  "lt": 28},
    "Medical Supplies":     {"w": 0.14, "demand": 26, "cv": 0.30, "cost": (12, 180),  "lt": 17},
    "Automotive Parts":     {"w": 0.16, "demand": 12, "cv": 0.45, "cost": (30, 350),  "lt": 32},
    "FMCG Household":       {"w": 0.18, "demand": 62, "cv": 0.28, "cost": (3,   28),  "lt": 9},
    "Apparel & Textiles":   {"w": 0.10, "demand": 22, "cv": 0.70, "cost": (8,   95),  "lt": 24},
}


def build_sku_master(rng: np.random.Generator) -> pd.DataFrame:
    """Create the SKU-level master data shared across all warehouses."""
    cats = list(CATEGORIES.keys())
    weights = np.array([CATEGORIES[c]["w"] for c in cats], dtype=float)
    weights /= weights.sum()

    category = rng.choice(cats, size=N_SKUS, p=weights)
    sku_id = [f"SKU-{i:04d}" for i in range(1, N_SKUS + 1)]

    base_demand = np.array([CATEGORIES[c]["demand"] for c in category], dtype=float)
    demand_cv = np.array([CATEGORIES[c]["cv"] for c in category], dtype=float)
    base_lead = np.array([CATEGORIES[c]["lt"] for c in category], dtype=float)

    # Lognormal spread produces the long tail of slow movers seen in real portfolios.
    demand_multiplier = rng.lognormal(mean=-0.95, sigma=0.85, size=N_SKUS)
    sku_daily_demand = np.clip(base_demand * demand_multiplier * DEMAND_SCALE, 0.2, None)

    cost_low = np.array([CATEGORIES[c]["cost"][0] for c in category], dtype=float)
    cost_high = np.array([CATEGORIES[c]["cost"][1] for c in category], dtype=float)
    unit_cost = np.round(rng.uniform(cost_low, cost_high), 2)

    # Gross margin varies by category positioning: 22% - 58%.
    gross_margin = rng.uniform(0.22, 0.58, size=N_SKUS)
    unit_price = np.round(unit_cost / (1.0 - gross_margin), 2)

    master = pd.DataFrame(
        {
            "SKU_ID": sku_id,
            "Product_Category": category,
            "Supplier_ID": [f"SUP-{i:03d}" for i in rng.integers(1, 41, size=N_SKUS)],
            "Unit_Cost": unit_cost,
            "Unit_Price": unit_price,
            "_base_daily_demand": sku_daily_demand,
            "_demand_cv": demand_cv,
            "_base_lead_time": base_lead,
        }
    )

    # ABC classification by annual revenue contribution (Pareto: 20% / 30% / 50% of SKUs).
    annual_revenue = master["_base_daily_demand"] * 365.0 * master["Unit_Price"]
    ranked = annual_revenue.rank(ascending=False, method="first")
    master["ABC_Class"] = np.where(
        ranked <= N_SKUS * 0.20, "A", np.where(ranked <= N_SKUS * 0.50, "B", "C")
    )
    return master


def build_rows(master: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Explode the SKU master across warehouses and simulate the inventory position."""
    frames = []
    for wh_id, wh in WAREHOUSES.items():
        df = master.copy()
        df["Warehouse_ID"] = wh_id
        n = len(df)

        # --- Demand at this warehouse -------------------------------------------------
        local_scale = rng.uniform(0.55, 1.45, size=n)
        avg_daily_demand = np.round(df["_base_daily_demand"].to_numpy() * local_scale, 2)
        demand_std = np.round(avg_daily_demand * df["_demand_cv"].to_numpy() * rng.uniform(0.8, 1.25, size=n), 2)

        # --- Supplier lead time -------------------------------------------------------
        lead_time = np.round(
            df["_base_lead_time"].to_numpy() * wh["lt_factor"] * rng.uniform(0.75, 1.30, size=n)
        ).astype(int)
        lead_time = np.clip(lead_time, 3, 75)
        lead_time_var = np.round(lead_time * rng.uniform(0.10, 0.35, size=n), 1)

        # --- Sales YTD ----------------------------------------------------------------
        # Realised sales are suppressed below theoretical demand by lost sales.
        fulfilment_rate = np.clip(rng.normal(0.94, 0.05, size=n), 0.70, 1.0)
        units_sold_ytd = np.round(avg_daily_demand * YTD_DAYS * fulfilment_rate).astype(int)

        # --- Cost of holding ----------------------------------------------------------
        holding_cost = np.round(
            df["Unit_Cost"].to_numpy() * ANNUAL_HOLDING_RATE * wh["hold_factor"], 2
        )
        holding_cost = np.maximum(holding_cost, 0.15)

        # --- Legacy static policy: flat 30-day cover on a stale demand estimate --------
        # The estimate was frozen last quarter, so it drifts away from current demand.
        stale_demand_estimate = avg_daily_demand * rng.normal(1.02, 0.22, size=n).clip(0.55, 1.60)
        static_rop = np.round(stale_demand_estimate * STATIC_COVER_DAYS).astype(int)

        # --- AI policy: lead-time demand + statistical safety stock --------------------
        lead_time_demand = avg_daily_demand * lead_time
        ai_safety_stock = SERVICE_LEVEL_Z * demand_std * np.sqrt(lead_time)
        ai_rop = np.round(lead_time_demand + ai_safety_stock).astype(int)

        # --- Order quantities: EOQ under each policy's ordering cost -------------------
        # Manual PO raising is expensive, which pushes planners toward large, infrequent
        # orders and therefore high cycle stock. Automating PO creation cuts the per-order
        # cost, so the economic order quantity - and half of it, the average cycle stock -
        # falls. This is the second, independent source of carrying cost saving.
        annual_demand = avg_daily_demand * 365.0
        h = np.maximum(holding_cost, 0.15)
        eoq_static = np.sqrt((2.0 * annual_demand * ORDERING_COST_MANUAL) / h)
        eoq_ai = np.sqrt((2.0 * annual_demand * ORDERING_COST_AUTOMATED) / h)
        static_order_qty = np.clip(np.round(eoq_static), 10, None).astype(int)
        ai_order_qty = np.clip(np.round(eoq_ai), 10, None).astype(int)

        # --- AI forecast: 30-day forward demand with realistic error -------------------
        forecast_error = rng.normal(1.0, 0.09, size=n)
        demand_forecast_ai = np.round(avg_daily_demand * 30.0 * forecast_error).astype(int)
        demand_forecast_ai = np.maximum(demand_forecast_ai, 1)
        mape = np.round(np.abs(rng.normal(0.0, 9.5, size=n)) + rng.uniform(1.5, 5.0, size=n), 1)

        # --- Current stock position ---------------------------------------------------
        # Stock cycles between the reorder point and reorder point + order quantity,
        # with a share of SKUs already drawn down below cover.
        cycle_position = rng.beta(2.0, 2.6, size=n)
        current_stock = np.round(static_rop * rng.uniform(0.35, 1.15, size=n) + static_order_qty * cycle_position)
        current_stock = np.clip(current_stock, 0, None).astype(int)

        # --- Stockout history ---------------------------------------------------------
        # Exposure rises when the legacy threshold under-covers lead-time demand and
        # when demand is volatile; warehouse maturity dampens it.
        cover_gap = np.clip((ai_rop - static_rop) / np.maximum(ai_rop, 1.0), 0.0, 1.0)
        volatility = np.clip(demand_std / np.maximum(avg_daily_demand, 0.1), 0.0, 1.5)
        lam = (0.35 + 6.5 * cover_gap + 1.1 * volatility) / wh["maturity"]
        stockout_events = rng.poisson(np.clip(lam, 0.05, 14.0))
        stockout_duration = np.where(
            stockout_events > 0,
            np.round(np.clip(rng.gamma(shape=2.0, scale=lead_time / 12.0), 0.5, 30.0), 1),
            0.0,
        )

        df["Warehouse_Name"] = wh["name"]
        df["Lead_Time_Days"] = lead_time
        df["Lead_Time_Variability_Days"] = lead_time_var
        df["Avg_Daily_Demand"] = avg_daily_demand
        df["Demand_Std_Dev"] = demand_std
        df["Units_Sold_YTD"] = units_sold_ytd
        df["Current_Stock"] = current_stock
        df["Stockout_Events_YTD"] = stockout_events
        df["Avg_Stockout_Duration_Days"] = stockout_duration
        df["Holding_Cost_Per_Unit"] = holding_cost
        df["Static_Reorder_Point"] = static_rop
        df["Demand_Forecast_AI"] = demand_forecast_ai
        df["AI_Reorder_Point"] = ai_rop
        df["Static_Order_Qty_Units"] = static_order_qty
        df["AI_Order_Qty_Units"] = ai_order_qty
        df["Forecast_MAPE_Pct"] = mape
        df["Reorder_Flag"] = (current_stock <= ai_rop).astype(int)
        df["Snapshot_Date"] = SNAPSHOT_DATE

        frames.append(df)

    out = pd.concat(frames, ignore_index=True)
    return out.drop(columns=["_base_daily_demand", "_demand_cv", "_base_lead_time"])


COLUMN_ORDER = [
    "SKU_ID",
    "Warehouse_ID",
    "Warehouse_Name",
    "Product_Category",
    "ABC_Class",
    "Supplier_ID",
    "Unit_Cost",
    "Unit_Price",
    "Lead_Time_Days",
    "Lead_Time_Variability_Days",
    "Avg_Daily_Demand",
    "Demand_Std_Dev",
    "Units_Sold_YTD",
    "Current_Stock",
    "Stockout_Events_YTD",
    "Avg_Stockout_Duration_Days",
    "Holding_Cost_Per_Unit",
    "Static_Reorder_Point",
    "Demand_Forecast_AI",
    "AI_Reorder_Point",
    "Static_Order_Qty_Units",
    "AI_Order_Qty_Units",
    "Forecast_MAPE_Pct",
    "Reorder_Flag",
    "Snapshot_Date",
]


def validate(df: pd.DataFrame) -> None:
    """Fail loudly if the generated data violates a business rule."""
    assert len(df) == N_SKUS * len(WAREHOUSES), "Unexpected row count"
    assert not df.isnull().any().any(), "Null values present in generated dataset"
    assert not df.duplicated(subset=["SKU_ID", "Warehouse_ID"]).any(), "Duplicate SKU-warehouse key"
    assert (df["Current_Stock"] >= 0).all(), "Negative stock generated"
    assert (df["Lead_Time_Days"] > 0).all(), "Non-positive lead time"
    assert (df["Unit_Price"] > df["Unit_Cost"]).all(), "Selling price below cost"
    assert (df["Holding_Cost_Per_Unit"] > 0).all(), "Non-positive holding cost"
    assert (df["Demand_Forecast_AI"] > 0).all(), "Non-positive AI forecast"
    assert (df["AI_Order_Qty_Units"] <= df["Static_Order_Qty_Units"]).all(), "AI EOQ exceeds manual EOQ"
    flag_matches = (df["Reorder_Flag"] == (df["Current_Stock"] <= df["AI_Reorder_Point"]).astype(int)).all()
    assert flag_matches, "Reorder_Flag inconsistent with AI reorder point"


def summarise(df: pd.DataFrame) -> None:
    """Print the profile a BA would sanity-check before handing the extract to analytics."""
    lead_time_demand = df["Avg_Daily_Demand"] * df["Lead_Time_Days"]
    static_ss = (df["Static_Reorder_Point"] - lead_time_demand).clip(lower=0)
    ai_ss = (df["AI_Reorder_Point"] - lead_time_demand).clip(lower=0)
    static_cost = (static_ss + df["Static_Order_Qty_Units"] / 2.0) * df["Holding_Cost_Per_Unit"]
    ai_cost = (ai_ss + df["AI_Order_Qty_Units"] / 2.0) * df["Holding_Cost_Per_Unit"]
    revenue_at_risk = (
        df["Stockout_Events_YTD"] * df["Avg_Stockout_Duration_Days"] * df["Avg_Daily_Demand"] * df["Unit_Price"]
    )

    print("\n" + "=" * 74)
    print("  SYNTHETIC INVENTORY DATASET - GENERATION SUMMARY")
    print("=" * 74)
    print(f"  Rows generated              : {len(df):,}")
    print(f"  Distinct SKUs               : {df['SKU_ID'].nunique():,}")
    print(f"  Warehouses                  : {df['Warehouse_ID'].nunique()}")
    print(f"  Snapshot date               : {SNAPSHOT_DATE} (YTD = {YTD_DAYS} days)")
    print("-" * 74)
    print(f"  SKUs flagged for reorder    : {int(df['Reorder_Flag'].sum()):,} "
          f"({df['Reorder_Flag'].mean() * 100:.1f}% of portfolio)")
    print(f"  Total stockout events YTD   : {int(df['Stockout_Events_YTD'].sum()):,}")
    print(f"  SKU-warehouse pairs at risk : {int((df['Stockout_Events_YTD'] > 0).sum()):,}")
    print(f"  Mean lead time              : {df['Lead_Time_Days'].mean():.1f} days")
    print(f"  Mean forecast MAPE          : {df['Forecast_MAPE_Pct'].mean():.1f}%")
    print("-" * 74)
    print(f"  Revenue at risk (YTD)       : SGD {revenue_at_risk.sum():>14,.0f}")
    print(f"  Carrying cost - static      : SGD {static_cost.sum():>14,.0f}")
    print(f"  Carrying cost - AI policy   : SGD {ai_cost.sum():>14,.0f}")
    print(f"  Modelled annual saving      : SGD {static_cost.sum() - ai_cost.sum():>14,.0f} "
          f"({(static_cost.sum() - ai_cost.sum()) / static_cost.sum() * 100:.1f}%)")
    print("=" * 74)
    print("  ABC mix:")
    for cls, grp in df.groupby("ABC_Class"):
        print(f"    Class {cls}: {len(grp):>4,} rows | "
              f"revenue share {grp['Units_Sold_YTD'].mul(grp['Unit_Price']).sum() / df['Units_Sold_YTD'].mul(df['Unit_Price']).sum() * 100:>5.1f}%")
    print("=" * 74 + "\n")


def main() -> None:
    rng = np.random.default_rng(RANDOM_SEED)
    master = build_sku_master(rng)
    df = build_rows(master, rng)
    df = df[COLUMN_ORDER].sort_values(["Warehouse_ID", "SKU_ID"]).reset_index(drop=True)

    validate(df)
    df.to_csv(OUTPUT_PATH, index=False)
    summarise(df)
    print(f"  Written to: {OUTPUT_PATH}\n")


if __name__ == "__main__":
    main()
