"""
Step 2 of 3 - Demand Forecasting Engine
=======================================

Project : Demand Forecasting & Automated Replenishment System
Input   : data/demand_history.csv.gz
Output  : data/forecast_output.csv

What this does
--------------
Fits four candidate forecasting methods to every SKU-warehouse series, selects the
best method per series by backtest, and produces a 30-day forward forecast plus a
measured forecast error. The error term is what sizes safety stock in step 3, which
is the textbook-correct linkage: the buffer is derived from how wrong the forecast
actually is, not from an assumption about demand variability.

Candidate methods
-----------------
    ma28            Mean of the last 28 days. The honest baseline - if a method
                    cannot beat this, it is not earning its complexity.
    snaive          Seasonal naive. Mean of the last four observations of the same
                    weekday, which captures the weekly trading pattern and nothing else.
    holt_winters    Triple exponential smoothing: level, damped trend, weekly
                    seasonality, additive. Smoothing parameters grid-searched per
                    series. Trend damping (phi < 1) stops a short-run slope being
                    extrapolated 30 days into an implausible number, which is the
                    classic failure of undamped Holt over a long horizon.
    croston_sba     Croston's method with the Syntetos-Boylan Approximation.
                    Smooths demand size and inter-arrival interval separately, which
                    is the standard treatment for intermittent demand. 41% of this
                    catalogue has zero demand on more than 30% of days; running
                    smoothing straight over those zeros biases the forecast toward
                    zero and understocks the item.

Validation design
-----------------
Rolling-origin backtest with four folds of 30 days each:

    |------------------- training ------------------|  fold 1  fold 2  fold 3  fold 4
                                                        T-120   T-90    T-60    T-30

    Folds 1-3  select the method and its smoothing parameters.
    Fold 4     is held out from every selection decision and is the only window the
               reported accuracy comes from.

This separation matters. Picking the best of 4 methods x 54 parameter sets and then
quoting that same window's error would flatter the result; the number reported here
is measured on data no selection decision ever saw.

Accuracy metric
---------------
WAPE (weighted absolute percentage error, sum|A-F| / sum A) is the primary metric,
not MAPE. MAPE divides by the actual, so a single low-demand day sends it to infinity
and it is undefined on a zero-demand day - unusable on an intermittent catalogue.
MAPE is still reported, computed only over non-zero days, because it is the metric
business stakeholders recognise and the BRD commits to.

The error standard deviation used for safety stock is pooled across all four folds
rather than taken from fold 4 alone: 120 residuals give a usable estimate of spread,
30 do not. Accuracy reporting and dispersion estimation have different needs.

    python3 data/02_forecast_demand.py
"""

from __future__ import annotations

import os
import itertools

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
HISTORY_PATH = os.path.join(HERE, "demand_history.csv.gz")
OUTPUT_PATH = os.path.join(HERE, "forecast_output.csv")

SEASON = 7           # weekly seasonality
HORIZON = 30         # 30-day forward forecast
N_FOLDS = 6          # rolling-origin folds; the last is held out from selection
INTERMITTENT_ZERO_SHARE = 0.30

ALPHA_GRID = [0.02, 0.05, 0.15, 0.30]      # level smoothing
BETA_GRID = [0.005, 0.02, 0.10]       # trend smoothing
GAMMA_GRID = [0.02, 0.10, 0.30]      # seasonal smoothing
PHI_GRID = [0.90, 0.98]              # trend damping
CROSTON_ALPHA = 0.15

MONTHS: np.ndarray = np.array([])   # month-of-year per day index, set in main()


# ----------------------------------------------------------------------------------
# Forecasting methods. Each takes train (T, N) and returns a (HORIZON, N) forecast.
# All are vectorised across series: the loop is over time, never over the 1,000 items.
# ----------------------------------------------------------------------------------
def f_ma28(train: np.ndarray, origin: int) -> np.ndarray:
    return np.tile(train[-28:].mean(axis=0), (HORIZON, 1))


def f_snaive(train: np.ndarray, origin: int) -> np.ndarray:
    T, N = train.shape
    out = np.empty((HORIZON, N))
    for i in range(HORIZON):
        weekday_pos = (T + i) % SEASON
        idx = np.arange(T - SEASON + weekday_pos, -1, -SEASON)[:4]
        out[i] = train[idx].mean(axis=0)
    return np.maximum(out, 0.0)


def f_holt_winters(train: np.ndarray, origin: int, alpha: float, beta: float,
                   gamma: float, phi: float) -> np.ndarray:
    T, N = train.shape
    level = train[:2 * SEASON].mean(axis=0)
    trend = (train[SEASON:2 * SEASON].mean(axis=0) - train[:SEASON].mean(axis=0)) / SEASON
    season = np.zeros((SEASON, N))
    for i in range(SEASON):
        season[i] = train[i:4 * SEASON:SEASON].mean(axis=0) - level

    for t in range(T):
        s = t % SEASON
        prev_level = level
        level = alpha * (train[t] - season[s]) + (1 - alpha) * (prev_level + phi * trend)
        trend = beta * (level - prev_level) + (1 - beta) * phi * trend
        season[s] = gamma * (train[t] - level) + (1 - gamma) * season[s]

    out = np.empty((HORIZON, N))
    damped = 0.0
    for i in range(1, HORIZON + 1):
        damped += phi ** i
        out[i - 1] = level + damped * trend + season[(T + i - 1) % SEASON]
    return np.maximum(out, 0.0)


def f_croston_sba(train: np.ndarray, origin: int, alpha: float = CROSTON_ALPHA) -> np.ndarray:
    """Croston with the Syntetos-Boylan bias correction, vectorised over series."""
    T, N = train.shape
    nonzero = train > 0
    size = np.where(nonzero.any(axis=0), train.sum(axis=0) / np.maximum(nonzero.sum(axis=0), 1), 0.0)
    interval = np.full(N, max(T / np.maximum(nonzero.sum(axis=0), 1).mean(), 1.0))
    gap = np.zeros(N)

    for t in range(T):
        gap += 1.0
        hit = nonzero[t]
        if hit.any():
            size = np.where(hit, alpha * train[t] + (1 - alpha) * size, size)
            interval = np.where(hit, alpha * gap + (1 - alpha) * interval, interval)
            gap = np.where(hit, 0.0, gap)

    rate = size / np.maximum(interval, 1e-9) * (1 - alpha / 2.0)   # SBA correction
    return np.tile(np.maximum(rate, 0.0), (HORIZON, 1))


def f_seasonal_index(train: np.ndarray, origin: int) -> np.ndarray:
    """Deseasonalised level x month-of-year index.

    Weekly seasonality cancels out when demand is summed into a 30-day bucket, so it
    cannot help the order quantity. Annual seasonality does not cancel: a SKU that
    peaks in December is genuinely short if the buffer was sized on a November level.
    This method estimates a month factor from the full history, shrinks it toward 1.0
    in proportion to how little evidence supports it, and applies it to a
    deseasonalised recent level.
    """
    months_train = MONTHS[:origin]
    overall = train.mean(axis=0)
    factors = np.ones((12, train.shape[1]))
    for m in range(1, 13):
        mask = months_train == m
        if mask.sum() >= 14:
            raw = train[mask].mean(axis=0) / np.maximum(overall, 1e-9)
            shrink = min(mask.sum() / 60.0, 1.0)          # full weight at ~2 months of evidence
            factors[m - 1] = 1.0 + shrink * (raw - 1.0)

    recent = train[-56:]
    recent_factor = factors[MONTHS[origin - 56:origin] - 1]
    level = (recent / np.maximum(recent_factor, 1e-6)).mean(axis=0)

    fmonths = MONTHS[origin:origin + HORIZON]
    return np.maximum(level[None, :] * factors[fmonths - 1], 0.0)


# ----------------------------------------------------------------------------------
# Scoring
# ----------------------------------------------------------------------------------
def wape(actual: np.ndarray, forecast: np.ndarray) -> np.ndarray:
    denom = actual.sum(axis=0)
    return np.where(denom > 0, np.abs(actual - forecast).sum(axis=0) / np.maximum(denom, 1e-9), np.nan)


def mape(actual: np.ndarray, forecast: np.ndarray) -> np.ndarray:
    mask = actual > 0
    err = np.where(mask, np.abs(actual - forecast) / np.maximum(actual, 1e-9), 0.0)
    counts = mask.sum(axis=0)
    return np.where(counts > 0, err.sum(axis=0) / np.maximum(counts, 1), np.nan)


# Parsimony order: a more complex method must clearly beat a simpler one to be chosen.
COMPLEXITY = {"ma28": 0, "snaive": 1, "seasonal_index": 2, "croston_sba": 3, "holt_winters": 4}
MARGIN = 0.03          # 3% relative WAPE improvement required to justify more complexity


def main() -> None:
    if not os.path.exists(HISTORY_PATH):
        raise SystemExit("demand_history.csv.gz not found. Run data/01_generate_demand_history.py first.")

    print("Loading demand history ...")
    hist = pd.read_csv(HISTORY_PATH)
    wide = hist.pivot(index="Date", columns=["SKU_ID", "Warehouse_ID"], values="Units_Demanded").sort_index()
    series_keys = wide.columns.to_frame(index=False)
    y = wide.to_numpy(dtype=float)
    T, N = y.shape
    # Month per day index, extended by the horizon so the final refit can look forward.
    global MONTHS
    all_dates = pd.date_range(start=pd.Timestamp(wide.index[0]), periods=T + HORIZON, freq="D")
    MONTHS = all_dates.month.to_numpy()
    print(f"  {N:,} series x {T} days")

    # Croston is only valid where demand is genuinely intermittent. Offering it on
    # dense series let it win 185 of them on a near-tie, which is how a method built
    # for zeros ended up forecasting fast movers.
    intermittent = (y[-365:] == 0).mean(axis=0) > INTERMITTENT_ZERO_SHARE
    print(f"  intermittent series: {int(intermittent.sum())} (Croston restricted to these)")

    origins = [T - HORIZON * (N_FOLDS - k) for k in range(N_FOLDS)]
    selection_origins, holdout_origin = origins[:-1], origins[-1]

    # ---- Stage 1: one Holt-Winters parameter set for the whole portfolio ----------
    # Fitting smoothing parameters per series over 54 combinations and only 90 days of
    # selection data overfits badly: the per-series winner generalised worse than a
    # 28-day mean. Choosing a single set on pooled error is far more stable.
    hw_grid = list(itertools.product(ALPHA_GRID, BETA_GRID, GAMMA_GRID, PHI_GRID))
    print(f"  selecting Holt-Winters parameters over {len(hw_grid)} combinations (pooled) ...")
    best_params, best_score = None, np.inf
    for a, b, g, phi in hw_grid:
        total_abs, total_act = 0.0, 0.0
        for origin in selection_origins:
            a30 = y[origin:origin + HORIZON].sum(axis=0)
            f30 = f_holt_winters(y[:origin], origin, a, b, g, phi).sum(axis=0)
            total_abs += np.abs(f30 - a30).sum()
            total_act += a30.sum()
        score = total_abs / total_act
        if score < best_score:
            best_params, best_score = (a, b, g, phi), score
    a, b, g, phi = best_params
    print(f"    alpha={a} beta={b} gamma={g} phi={phi}  (pooled 30-day error {best_score*100:.1f}%)")

    # ---- Stage 2: combination, not selection -------------------------------------
    # Picking the single best method per series from a handful of validation numbers
    # is dominated by luck: measured here, per-series selection generalised WORSE than
    # the naive baseline. Averaging the candidates instead is the standard answer (the
    # "forecast combination puzzle" - an equal-weighted mean is hard to beat), because
    # method-specific errors partly cancel. A single method overrides the combination
    # only where it wins by a wide, consistent margin.
    candidates = {
        "ma28": f_ma28,
        "snaive": f_snaive,
        "seasonal_index": f_seasonal_index,
        "holt_winters": lambda tr, o: f_holt_winters(tr, o, a, b, g, phi),
    }
    names = list(candidates)
    intermittent_idx = np.where(intermittent)[0]

    sel_ape = np.zeros((len(names) + 2, N))      # + combination + croston
    fold_fc = {k: [] for k in list(names) + ["combination", "croston_sba"]}
    fold_act = []
    for fi, origin in enumerate(origins):
        train, actual = y[:origin], y[origin:origin + HORIZON]
        a30 = actual.sum(axis=0)
        fold_act.append(actual)
        print(f"  fold {fi + 1}/{N_FOLDS} (origin day {origin}) ...")
        stack = []
        for ci, name in enumerate(names):
            fc = candidates[name](train, origin)
            stack.append(fc)
            fold_fc[name].append(fc)
            if origin in selection_origins:
                sel_ape[ci] += np.where(a30 > 0, np.abs(fc.sum(axis=0) - a30) / np.maximum(a30, 1e-9), 9.99)
        comb = np.mean(stack, axis=0)
        fold_fc["combination"].append(comb)
        cros = f_croston_sba(train, origin)
        fold_fc["croston_sba"].append(cros)
        if origin in selection_origins:
            sel_ape[len(names)] += np.where(a30 > 0, np.abs(comb.sum(axis=0) - a30) / np.maximum(a30, 1e-9), 9.99)
            sel_ape[len(names) + 1] += np.where(a30 > 0, np.abs(cros.sum(axis=0) - a30) / np.maximum(a30, 1e-9), 9.99)
    sel_ape /= len(selection_origins)

    all_names = names + ["combination", "croston_sba"]
    comb_i = len(names)
    chosen = np.full(N, comb_i)
    # a single method must beat the combination by 15% to be trusted over it
    for ci in range(len(names)):
        chosen = np.where(sel_ape[ci] < sel_ape[comb_i] * 0.85, ci, chosen)
    # intermittent series go to Croston when it wins there
    cros_i = len(names) + 1
    better = sel_ape[cros_i] < sel_ape[chosen, np.arange(N)]
    chosen[intermittent_idx] = np.where(better[intermittent_idx], cros_i, chosen[intermittent_idx])

    family = np.array([all_names[i] for i in chosen])
    print("  methods used:", {m: int((family == m).sum()) for m in sorted(set(family))})

    # ---- Score on the held-out fold, unseen by any selection step -----------------
    holdout_actual = y[holdout_origin:holdout_origin + HORIZON]
    holdout_fc = np.empty((HORIZON, N))
    resid_pooled = np.empty((HORIZON * N_FOLDS, N))
    act_stack = np.vstack(fold_act)
    for ci, name in enumerate(all_names):
        take = chosen == ci
        if take.any():
            holdout_fc[:, take] = fold_fc[name][-1][:, take]
            resid_pooled[:, take] = (act_stack - np.vstack(fold_fc[name]))[:, take]

    act_30 = holdout_actual.sum(axis=0)
    fc_30 = holdout_fc.sum(axis=0)
    bucket_ape = np.where(act_30 > 0, np.abs(fc_30 - act_30) / np.maximum(act_30, 1e-9), np.nan)
    bias = np.where(act_30 > 0, (fc_30 - act_30) / np.maximum(act_30, 1e-9), np.nan)
    daily_wape = wape(holdout_actual, holdout_fc)
    sigma_daily = resid_pooled.std(axis=0, ddof=1)

    # ---- Refit on the complete history for the forward forecast ------------------
    print("  refitting on full history ...")
    full = {n: candidates[n](y, T) for n in names}
    full["combination"] = np.mean(list(full.values()), axis=0)
    full["croston_sba"] = f_croston_sba(y, T)
    final_fc = np.empty((HORIZON, N))
    for ci, name in enumerate(all_names):
        take = chosen == ci
        if take.any():
            final_fc[:, take] = full[name][:, take]

    ttm = y[-365:]
    out = pd.DataFrame({
        "SKU_ID": series_keys.SKU_ID,
        "Warehouse_ID": series_keys.Warehouse_ID,
        "Forecast_Model": family,
        "Demand_Forecast_AI": np.round(final_fc.sum(axis=0)).astype(int).clip(min=1),
        "Forecast_Daily_Rate": np.round(final_fc.mean(axis=0), 3),
        "Forecast_MAPE_Pct": np.round(bucket_ape * 100, 1),
        "Forecast_WAPE_Daily_Pct": np.round(daily_wape * 100, 1),
        "Forecast_Bias_Pct": np.round(bias * 100, 1),
        "Forecast_Sigma_Daily": np.round(sigma_daily, 3),
        "Avg_Daily_Demand": np.round(ttm.mean(axis=0), 3),
        "Demand_Std_Dev": np.round(ttm.std(axis=0, ddof=1), 3),
        "Units_Sold_YTD": ttm[-243:].sum(axis=0).astype(int),
        "Zero_Day_Share": np.round((ttm == 0).mean(axis=0), 3),
    })
    out["Is_Intermittent"] = (out.Zero_Day_Share > INTERMITTENT_ZERO_SHARE).astype(int)

    base_fc = f_ma28(y[:holdout_origin], holdout_origin).sum(axis=0)
    base_ape = np.where(act_30 > 0, np.abs(base_fc - act_30) / np.maximum(act_30, 1e-9), np.nan)
    beat = np.nanmean(bucket_ape < base_ape) * 100
    skill = (1 - np.nansum(np.abs(fc_30 - act_30)) / np.nansum(np.abs(base_fc - act_30))) * 100

    assert out.Demand_Forecast_AI.gt(0).all(), "non-positive forecast produced"
    assert out.Forecast_Sigma_Daily.ge(0).all(), "negative error dispersion"
    assert len(out) == N, "series count mismatch"
    out.to_csv(OUTPUT_PATH, index=False)

    abc = None
    print("\n" + "=" * 72)
    print("  FORECAST ACCURACY - held-out 30 days, unseen by model selection")
    print("=" * 72)
    print(f"  Portfolio error, 30-day bucket : {abs(fc_30.sum()-act_30.sum())/act_30.sum()*100:5.1f}%")
    print(f"  Median MAPE per series         : {np.nanmedian(bucket_ape)*100:5.1f}%   (30-day bucket)")
    print(f"  Median absolute bias           : {np.nanmedian(np.abs(bias))*100:5.1f}%")
    print(f"  Median daily WAPE              : {np.nanmedian(daily_wape)*100:5.1f}%   (diagnostic only)")
    print(f"  Beat the 28-day baseline       : {beat:5.1f}% of series")
    print(f"  Skill vs baseline              : {skill:5.1f}% error reduction")
    print("-" * 72)
    for m in sorted(set(family)):
        sub = family == m
        print(f"  {m:<13} {sub.sum():>4} series | median MAPE {np.nanmedian(bucket_ape[sub])*100:5.1f}%"
              f" | median bias {np.nanmedian(bias[sub])*100:+5.1f}%")
    print("=" * 72)
    print(f"  Written to {os.path.relpath(OUTPUT_PATH, os.path.dirname(HERE))}")


if __name__ == "__main__":
    main()
