"""
Step 1 of 3 - Daily Demand History Generator
============================================

Project : Demand Forecasting & Automated Replenishment System
Outputs : data/demand_history.csv.gz   730 days x 1,000 SKU-warehouse series
          data/sku_master.csv          static attributes per SKU-warehouse

Why a daily series rather than a single snapshot
------------------------------------------------
A forecast cannot be built, and forecast accuracy cannot be measured, without history.
This script produces two years of daily demand so that step 2 can fit models on a
training window and score them against a held-out window it never saw.

Each series is built from components a real demand planner would recognise:

    demand(t) = level * trend(t) * weekday(t) * season(t) * promo(t) * noise(t)

    level     lognormal across SKUs, producing the long slow-moving tail of a real catalogue
    trend     small compounding drift, positive or negative, per series
    weekday   day-of-week profile, category specific (FMCG peaks at weekends,
              industrial components peak midweek)
    season    annual sine wave, amplitude and phase by category
    promo     occasional short multi-day uplifts, Poisson-timed
    noise     negative binomial, which gives integer counts, non-negative by
              construction, and the overdispersion real demand shows

Low-volume SKUs therefore produce genuinely intermittent series with many zero days,
which is what forces step 2 to carry a separate model for intermittent demand.

Reproducibility: fixed seed, byte-identical output on every run.

    python3 data/01_generate_demand_history.py
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

RANDOM_SEED = 42
N_SKUS = 250
HISTORY_DAYS = 730                 # two years
SNAPSHOT_DATE = pd.Timestamp("2026-08-31")
ANNUAL_HOLDING_RATE = 0.22
DEMAND_SCALE = 2.00

HERE = os.path.dirname(os.path.abspath(__file__))
HISTORY_PATH = os.path.join(HERE, "demand_history.csv.gz")
MASTER_PATH = os.path.join(HERE, "sku_master.csv")

WAREHOUSES = {
    "WH-SIN-01": {"name": "Singapore Central", "lt_factor": 0.85, "hold_factor": 1.35, "demand_factor": 1.25},
    "WH-JHR-02": {"name": "Johor Bahru",       "lt_factor": 1.05, "hold_factor": 0.85, "demand_factor": 0.95},
    "WH-BTM-03": {"name": "Batam",             "lt_factor": 1.30, "hold_factor": 0.70, "demand_factor": 0.75},
    "WH-PEN-04": {"name": "Penang",            "lt_factor": 1.10, "hold_factor": 0.90, "demand_factor": 1.00},
}

CATEGORIES = {
    #                       weight  base  cost range    lead  weekday profile (Mon..Sun)        annual amp
    "Consumer Electronics": {"w": .22, "d": 34, "c": (7, 62), "lt": 21,
                             "dow": [1.05, 1.00, 1.00, 1.05, 1.20, 1.15, 0.55], "amp": 0.28},
    "Industrial Components":{"w": .20, "d": 16, "c": (3, 39), "lt": 28,
                             "dow": [1.20, 1.25, 1.25, 1.20, 1.05, 0.35, 0.20], "amp": 0.12},
    "Medical Supplies":     {"w": .14, "d": 26, "c": (2, 27), "lt": 17,
                             "dow": [1.10, 1.10, 1.10, 1.10, 1.05, 0.80, 0.75], "amp": 0.18},
    "Automotive Parts":     {"w": .16, "d": 12, "c": (5, 52), "lt": 32,
                             "dow": [1.15, 1.15, 1.15, 1.15, 1.10, 0.70, 0.30], "amp": 0.15},
    "FMCG Household":       {"w": .18, "d": 62, "c": (0.5, 4.2),   "lt": 9,
                             "dow": [0.85, 0.85, 0.90, 1.00, 1.25, 1.45, 1.20], "amp": 0.10},
    "Apparel & Textiles":   {"w": .10, "d": 22, "c": (1.2, 14),   "lt": 24,
                             "dow": [0.80, 0.85, 0.90, 1.00, 1.25, 1.55, 1.15], "amp": 0.45},
}


def build_master(rng: np.random.Generator) -> pd.DataFrame:
    """SKU-level attributes, then exploded across the four warehouses."""
    cats = list(CATEGORIES)
    weights = np.array([CATEGORIES[c]["w"] for c in cats], float)
    weights /= weights.sum()
    category = rng.choice(cats, size=N_SKUS, p=weights)

    base = np.array([CATEGORIES[c]["d"] for c in category], float)
    multiplier = rng.lognormal(-1.35, 1.15, N_SKUS)
    sku_level = np.clip(base * multiplier * DEMAND_SCALE, 0.15, None)

    lo = np.array([CATEGORIES[c]["c"][0] for c in category], float)
    hi = np.array([CATEGORIES[c]["c"][1] for c in category], float)
    unit_cost = np.round(rng.uniform(lo, hi), 2)
    unit_cost = np.maximum(unit_cost, 0.30)
    unit_price = np.round(unit_cost / (1.0 - rng.uniform(0.22, 0.58, N_SKUS)), 2)

    sku = pd.DataFrame({
        "SKU_ID": [f"SKU-{i:04d}" for i in range(1, N_SKUS + 1)],
        "Product_Category": category,
        "Supplier_ID": [f"SUP-{i:03d}" for i in rng.integers(1, 41, N_SKUS)],
        "Unit_Cost": unit_cost,
        "Unit_Price": unit_price,
        "_level": sku_level,
        "_trend": rng.normal(0.0, 0.00035, N_SKUS),        # compounding daily drift
        "_phase": rng.uniform(0, 2 * np.pi, N_SKUS),       # annual seasonality phase
        "_disp": rng.uniform(0.06, 0.30, N_SKUS),          # negative-binomial overdispersion
    })

    rows = []
    for wh_id, wh in WAREHOUSES.items():
        d = sku.copy()
        d["Warehouse_ID"] = wh_id
        d["Warehouse_Name"] = wh["name"]
        d["_level"] = d["_level"] * wh["demand_factor"] * rng.uniform(0.70, 1.30, N_SKUS)
        lt = np.round(np.array([CATEGORIES[c]["lt"] for c in d.Product_Category], float)
                      * wh["lt_factor"] * rng.uniform(0.75, 1.30, N_SKUS))
        d["Lead_Time_Days"] = np.clip(lt, 3, 75).astype(int)
        d["Lead_Time_Variability_Days"] = np.round(d["Lead_Time_Days"] * rng.uniform(0.10, 0.35, N_SKUS), 1)
        d["Holding_Cost_Per_Unit"] = np.maximum(
            np.round(d["Unit_Cost"] * ANNUAL_HOLDING_RATE * wh["hold_factor"], 2), 0.15)
        rows.append(d)
    return pd.concat(rows, ignore_index=True)


def simulate(master: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    """Simulate daily demand for every series at once. Returns (days, series)."""
    n = len(master)
    dates = pd.date_range(end=SNAPSHOT_DATE, periods=HISTORY_DAYS, freq="D")
    t = np.arange(HISTORY_DAYS)

    level = master["_level"].to_numpy()[None, :]
    trend = (1.0 + master["_trend"].to_numpy()[None, :]) ** t[:, None]

    dow_table = np.array([CATEGORIES[c]["dow"] for c in master.Product_Category])   # (n, 7)
    weekday = dow_table[:, dates.dayofweek].T                                        # (days, n)

    amp = np.array([CATEGORIES[c]["amp"] for c in master.Product_Category])[None, :]
    doy = dates.dayofyear.to_numpy()[:, None]
    season = 1.0 + amp * np.sin(2 * np.pi * doy / 365.25 + master["_phase"].to_numpy()[None, :])

    # Promotions: Poisson-timed, 1-3 days long, 1.5x to 3.0x uplift
    promo = np.ones((HISTORY_DAYS, n))
    n_promos = rng.poisson(16, n)                         # roughly 8 per year
    for j in range(n):
        for start in rng.integers(0, HISTORY_DAYS, n_promos[j]):
            end = min(start + rng.integers(1, 4), HISTORY_DAYS)
            promo[start:end, j] *= rng.uniform(1.5, 3.0)

    mu = np.maximum(level * trend * weekday * season * promo, 1e-6)

    # Negative binomial: integer, non-negative, overdispersed relative to Poisson
    disp = master["_disp"].to_numpy()[None, :]
    r = 1.0 / disp
    p = r / (r + mu)
    return rng.negative_binomial(np.broadcast_to(r, mu.shape), p).astype(np.int32)


def main() -> None:
    rng = np.random.default_rng(RANDOM_SEED)
    master = build_master(rng)
    demand = simulate(master, rng)
    dates = pd.date_range(end=SNAPSHOT_DATE, periods=HISTORY_DAYS, freq="D")

    # ABC class from realised annual revenue over the trailing 12 months
    ttm = demand[-365:].sum(axis=0)
    revenue = ttm * master["Unit_Price"].to_numpy()
    sku_rev = pd.Series(revenue).groupby(master["SKU_ID"].to_numpy()).sum()
    rank = sku_rev.rank(ascending=False, method="first")
    abc = pd.Series(np.where(rank <= N_SKUS * 0.20, "A",
                    np.where(rank <= N_SKUS * 0.50, "B", "C")), index=sku_rev.index)
    master["ABC_Class"] = master["SKU_ID"].map(abc)

    history = pd.DataFrame(demand, index=dates, columns=pd.MultiIndex.from_frame(
        master[["SKU_ID", "Warehouse_ID"]]))
    history = (history.stack(["SKU_ID", "Warehouse_ID"], future_stack=True)
                      .rename("Units_Demanded").reset_index()
                      .rename(columns={"level_0": "Date"}))
    history["Date"] = history["Date"].dt.strftime("%Y-%m-%d")
    history = history[["Date", "SKU_ID", "Warehouse_ID", "Units_Demanded"]]

    out_master = master.drop(columns=[c for c in master.columns if c.startswith("_")])
    out_master = out_master[["SKU_ID", "Warehouse_ID", "Warehouse_Name", "Product_Category",
                             "ABC_Class", "Supplier_ID", "Unit_Cost", "Unit_Price",
                             "Lead_Time_Days", "Lead_Time_Variability_Days",
                             "Holding_Cost_Per_Unit"]].sort_values(["Warehouse_ID", "SKU_ID"])

    assert len(history) == HISTORY_DAYS * len(master), "unexpected history row count"
    assert (history.Units_Demanded >= 0).all(), "negative demand generated"
    assert not out_master.isnull().any().any(), "null in master data"

    # mtime=0: gzip stamps the current time into its header by default, which makes
    # the file differ between runs even when the content is identical.
    history.to_csv(HISTORY_PATH, index=False,
                   compression={"method": "gzip", "mtime": 0})
    out_master.to_csv(MASTER_PATH, index=False)

    zero_share = (demand == 0).mean()
    intermittent = ((demand[-365:] == 0).mean(axis=0) > 0.30).sum()
    print("=" * 70)
    print("  DAILY DEMAND HISTORY")
    print("=" * 70)
    print(f"  Series (SKU x warehouse) : {len(master):,}")
    print(f"  Days per series          : {HISTORY_DAYS} ({dates[0].date()} to {dates[-1].date()})")
    print(f"  Rows written             : {len(history):,}")
    print(f"  Zero-demand days         : {zero_share*100:.1f}% of all observations")
    print(f"  Intermittent series      : {intermittent} (>30% zero days in last year)")
    print(f"  Mean daily demand        : {demand.mean():.2f} units")
    print(f"  Annual revenue (TTM)     : SGD {revenue.sum():,.0f}")
    print("=" * 70)
    print(f"  {os.path.relpath(HISTORY_PATH, os.path.dirname(HERE))} "
          f"({os.path.getsize(HISTORY_PATH)/1024/1024:.1f} MB)")
    print(f"  {os.path.relpath(MASTER_PATH, os.path.dirname(HERE))}")


if __name__ == "__main__":
    main()
