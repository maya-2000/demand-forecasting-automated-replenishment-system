"""
Step 3 of 3 - Inventory Position Snapshot
=========================================

Project : Demand Forecasting & Automated Replenishment System
Inputs  : data/sku_master.csv, data/demand_history.csv.gz, data/forecast_output.csv
Output  : data/inventory_data.csv    1,000 rows, one per SKU-warehouse

What this does
--------------
Replays the last year of real demand through the *legacy* replenishment policy to
produce the current-state snapshot, then computes what the forecast-driven policy
would have set instead.

The important consequence: stockouts are not a random draw. They are what actually
happened when a flat 30-day reorder point met two years of simulated demand. A SKU
stocks out here because its threshold was genuinely too low for its lead time and
volatility, which means "revenue at risk" is a measured outcome rather than an
assumption. Units_Sold_YTD is filled demand, not raw demand, so lost sales are
excluded from revenue exactly as they would be in an ERP.

Policies compared
-----------------
    LEGACY (as-is)
        Reorder point = stale demand estimate x 30 days flat cover, refreshed
        quarterly at best, ignoring both lead time and demand volatility.
        Order quantity = EOQ at the manual PO cost of ~SGD 550.

    FORECAST-DRIVEN (to-be)
        Reorder point = forecast demand over the lead time
                        + z x forecast error sigma x sqrt(lead time)
        The buffer is sized from the error the forecasting engine actually made on
        held-out data (step 2), not from an assumption about demand variability.
        This is the difference between a buffer that is justified and one that is
        asserted.
        Order quantity = EOQ at the automated PO cost of ~SGD 450.

    python3 data/03_build_inventory_snapshot.py
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
MASTER_PATH = os.path.join(HERE, "sku_master.csv")
HISTORY_PATH = os.path.join(HERE, "demand_history.csv.gz")
FORECAST_PATH = os.path.join(HERE, "forecast_output.csv")
OUTPUT_PATH = os.path.join(HERE, "inventory_data.csv")

RANDOM_SEED = 42
SNAPSHOT_DATE = "2026-08-31"
YTD_DAYS = 243                  # 1 Jan 2026 to 31 Aug 2026
SIM_DAYS = 365                  # replay the trailing year through the legacy policy
SERVICE_LEVEL_Z = 1.645         # 95% service level, one-tailed normal
STATIC_COVER_DAYS = 30          # the legacy flat-cover rule
ORDERING_COST_MANUAL = 550.0
ORDERING_COST_AUTOMATED = 450.0


def simulate_legacy_policy(demand: np.ndarray, reorder_point: np.ndarray,
                           order_qty: np.ndarray, lead_time: np.ndarray):
    """Replay demand through an (s, Q) policy. Returns the resulting service outcome.

    Vectorised across series; the loop runs over days only. Unfilled demand is lost,
    not backordered, which matches a distribution business where the customer buys
    elsewhere rather than waiting.
    """
    days, n = demand.shape
    max_lt = int(lead_time.max()) + 2
    arrivals = np.zeros((days + max_lt, n))
    on_hand = (reorder_point + order_qty / 2.0).astype(float)
    on_order = np.zeros(n)
    shortfall = np.zeros((days, n))
    filled = np.zeros((days, n))
    idx = np.arange(n)

    for t in range(days):
        on_hand += arrivals[t]
        on_order -= arrivals[t]
        d = demand[t]
        fill = np.minimum(on_hand, d)
        filled[t] = fill
        shortfall[t] = d - fill
        on_hand -= fill

        place = (on_hand + on_order) <= reorder_point
        if place.any():
            j = idx[place]
            np.add.at(arrivals, (t + lead_time[j] + 1, j), order_qty[j])
            on_order[j] += order_qty[j]

    return on_hand, filled, shortfall


def count_stockout_runs(shortfall: np.ndarray):
    """Number of distinct stockout episodes and their mean length, per series."""
    out = shortfall > 0
    starts = out & ~np.vstack([np.zeros((1, out.shape[1]), bool), out[:-1]])
    events = starts.sum(axis=0)
    days_out = out.sum(axis=0)
    duration = np.divide(days_out, events, out=np.zeros_like(days_out, float), where=events > 0)
    return events.astype(int), np.round(duration, 1)


def main() -> None:
    for path in (MASTER_PATH, HISTORY_PATH, FORECAST_PATH):
        if not os.path.exists(path):
            raise SystemExit(f"{os.path.basename(path)} not found. Run steps 1 and 2 first.")

    rng = np.random.default_rng(RANDOM_SEED)
    master = pd.read_csv(MASTER_PATH)
    forecast = pd.read_csv(FORECAST_PATH)
    hist = pd.read_csv(HISTORY_PATH)
    wide = hist.pivot(index="Date", columns=["SKU_ID", "Warehouse_ID"], values="Units_Demanded").sort_index()
    keys = wide.columns.to_frame(index=False)

    d = keys.merge(master, on=["SKU_ID", "Warehouse_ID"], how="left") \
            .merge(forecast, on=["SKU_ID", "Warehouse_ID"], how="left")
    assert len(d) == len(keys) and not d.isnull().any().any(), "join produced gaps"

    demand = wide.to_numpy(float)[-SIM_DAYS:]
    lead_time = d.Lead_Time_Days.to_numpy().astype(int)
    holding = d.Holding_Cost_Per_Unit.to_numpy()

    # ---- Legacy policy: flat 30-day cover on a stale demand estimate ---------------
    stale_estimate = d.Avg_Daily_Demand.to_numpy() * rng.normal(1.02, 0.22, len(d)).clip(0.55, 1.60)
    static_rop = np.round(stale_estimate * STATIC_COVER_DAYS).astype(int)

    annual_demand = d.Avg_Daily_Demand.to_numpy() * 365.0
    h = np.maximum(holding, 0.15)
    static_qty = np.clip(np.round(np.sqrt(2 * annual_demand * ORDERING_COST_MANUAL / h)), 10, None).astype(int)
    ai_qty = np.clip(np.round(np.sqrt(2 * annual_demand * ORDERING_COST_AUTOMATED / h)), 10, None).astype(int)

    # ---- Replay the year: stockouts are an outcome, not an input ------------------
    print(f"Replaying {SIM_DAYS} days of demand through the legacy policy ...")
    on_hand, filled, shortfall = simulate_legacy_policy(demand, static_rop, static_qty, lead_time)
    events, duration = count_stockout_runs(shortfall[-YTD_DAYS:])

    # ---- Forecast-driven policy: buffer sized from measured forecast error --------
    forecast_daily = d.Forecast_Daily_Rate.to_numpy()
    sigma = d.Forecast_Sigma_Daily.to_numpy()
    ai_safety = SERVICE_LEVEL_Z * sigma * np.sqrt(lead_time)
    ai_rop = np.round(forecast_daily * lead_time + ai_safety).astype(int)

    current_stock = np.round(on_hand).astype(int).clip(min=0)
    out = pd.DataFrame({
        "SKU_ID": d.SKU_ID, "Warehouse_ID": d.Warehouse_ID, "Warehouse_Name": d.Warehouse_Name,
        "Product_Category": d.Product_Category, "ABC_Class": d.ABC_Class, "Supplier_ID": d.Supplier_ID,
        "Unit_Cost": d.Unit_Cost, "Unit_Price": d.Unit_Price,
        "Lead_Time_Days": lead_time, "Lead_Time_Variability_Days": d.Lead_Time_Variability_Days,
        "Avg_Daily_Demand": d.Avg_Daily_Demand, "Demand_Std_Dev": d.Demand_Std_Dev,
        "Units_Sold_YTD": np.round(filled[-YTD_DAYS:].sum(axis=0)).astype(int),
        "Current_Stock": current_stock,
        "Stockout_Events_YTD": events, "Avg_Stockout_Duration_Days": duration,
        "Units_Lost_YTD": np.round(shortfall[-YTD_DAYS:].sum(axis=0)).astype(int),
        "Holding_Cost_Per_Unit": holding,
        "Static_Reorder_Point": static_rop,
        "Demand_Forecast_AI": d.Demand_Forecast_AI, "AI_Reorder_Point": ai_rop,
        "Static_Order_Qty_Units": static_qty, "AI_Order_Qty_Units": ai_qty,
        "Forecast_Model": d.Forecast_Model,
        "Forecast_MAPE_Pct": d.Forecast_MAPE_Pct,
        "Forecast_Bias_Pct": d.Forecast_Bias_Pct,
        "Forecast_Sigma_Daily": d.Forecast_Sigma_Daily,
        "Is_Intermittent": d.Is_Intermittent,
        "Reorder_Flag": (current_stock <= ai_rop).astype(int),
        "Snapshot_Date": SNAPSHOT_DATE,
    })

    # ---- Validation, while the frame still aligns with the demand matrix ----------
    assert len(out) == 1000, "unexpected row count"
    assert not out.isnull().any().any(), "nulls in output"
    assert not out.duplicated(["SKU_ID", "Warehouse_ID"]).any(), "duplicate key"
    assert (out.Current_Stock >= 0).all(), "negative stock"
    assert (out.Unit_Price > out.Unit_Cost).all(), "price below cost"
    assert (out.Demand_Forecast_AI > 0).all(), "non-positive forecast"
    assert (out.AI_Order_Qty_Units <= out.Static_Order_Qty_Units).all(), "automated EOQ exceeds manual"
    assert (out.Avg_Stockout_Duration_Days >= 0).all(), "negative stockout duration"
    assert (out.Units_Sold_YTD.to_numpy() <= np.round(demand[-YTD_DAYS:].sum(axis=0)) + 1).all(), \
        "sold more than was demanded"

    out = out.sort_values(["Warehouse_ID", "SKU_ID"]).reset_index(drop=True)
    out.to_csv(OUTPUT_PATH, index=False)

    ltd = out.Avg_Daily_Demand * out.Lead_Time_Days
    s_ss = (out.Static_Reorder_Point - ltd).clip(lower=0)
    a_ss = (out.AI_Reorder_Point - ltd).clip(lower=0)
    s_cost = ((s_ss + out.Static_Order_Qty_Units / 2) * out.Holding_Cost_Per_Unit).sum()
    a_cost = ((a_ss + out.AI_Order_Qty_Units / 2) * out.Holding_Cost_Per_Unit).sum()
    lost_rev = (out.Units_Lost_YTD * out.Unit_Price).sum()
    revenue = (out.Units_Sold_YTD * out.Unit_Price).sum() * 365 / YTD_DAYS

    print("\n" + "=" * 72)
    print("  INVENTORY SNAPSHOT - current state measured, not assumed")
    print("=" * 72)
    print(f"  Rows                          : {len(out):,}")
    print(f"  Annualised revenue            : SGD {revenue:>14,.0f}")
    print(f"  Stockout events YTD           : {out.Stockout_Events_YTD.sum():,} "
          f"across {int((out.Stockout_Events_YTD > 0).sum())} positions")
    print(f"  Units lost to stockouts YTD   : {out.Units_Lost_YTD.sum():,} "
          f"({out.Units_Lost_YTD.sum()/(out.Units_Sold_YTD.sum()+out.Units_Lost_YTD.sum())*100:.1f}% of demand)")
    print(f"  Revenue lost YTD              : SGD {lost_rev:>14,.0f}")
    print(f"  SKUs flagged for reorder      : {int(out.Reorder_Flag.sum()):,}")
    print(f"  Median forecast MAPE          : {out.Forecast_MAPE_Pct.median():.1f}%")
    print("-" * 72)
    print(f"  Carrying cost, legacy policy  : SGD {s_cost:>14,.0f}")
    print(f"  Carrying cost, forecast-driven: SGD {a_cost:>14,.0f}")
    print(f"  Annual saving                 : SGD {s_cost - a_cost:>14,.0f} "
          f"({(s_cost - a_cost)/s_cost*100:.1f}%)")
    print("=" * 72)
    print(f"  Written to {os.path.relpath(OUTPUT_PATH, os.path.dirname(HERE))}")


if __name__ == "__main__":
    main()
