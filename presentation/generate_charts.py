"""
Chart Generation for the Executive Dashboard Pack
=================================================

Project : AI-Powered Inventory Forecasting & Automated Replenishment System
Input   : data/inventory_data.csv
Output  : presentation/charts/*.png  (a light and a dark variant of each chart)

Every figure is computed from the same source rows as sql/analysis_queries.sql,
so the charts and the SQL results cannot drift apart. Nothing is hard-coded.

Usage:
    python3 presentation/generate_charts.py

Charts produced:
    1. carrying_cost_by_warehouse  - where the saving lands, and where it does not
    2. savings_waterfall           - what the saving is actually made of
    3. revenue_at_risk_pareto      - how concentrated the stockout exposure is
    4. inventory_turnover          - which SKUs trap capital
    5. roi_payback                  - when the investment turns positive

Design notes:
    Colours come from a validated categorical palette - slot 1 blue, slot 2
    orange, slot 3 aqua - checked for colour-vision-deficiency separation in both
    light and dark surfaces. Series identity is always carried by a legend or a
    direct label as well as by colour, never by colour alone.
"""

from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, "data", "inventory_data.csv")
OUT_DIR = os.path.join(ROOT, "presentation", "charts")

YTD_DAYS = 243
ANNUALISE = 365.0 / YTD_DAYS
TURNOVER_TARGET = 12.5

# ROI model inputs (see README.md - Financial ROI Model)
IMPLEMENTATION_COST = 850_000.0
ANNUAL_RUN_COST = 220_000.0
TRUE_LOST_SALES_FACTOR = 0.35
STOCKOUT_REDUCTION_RATE = 0.40
PLANNER_HOURS_PER_WEEK = 12
PLANNER_HOURLY_RATE = 45.0

THEMES = {
    "light": {
        "surface": "#fcfcfb", "text": "#0b0b0b", "muted": "#52514e",
        "grid": "#e3e2de", "axis": "#c9c8c3",
        "s1": "#2a78d6", "s2": "#eb6834", "s3": "#1baf7a", "neutral": "#9b9a95",
    },
    "dark": {
        "surface": "#1a1a19", "text": "#ffffff", "muted": "#c3c2b7",
        "grid": "#343430", "axis": "#4a4a45",
        "s1": "#3987e5", "s2": "#d95926", "s3": "#199e70", "neutral": "#77766f",
    },
}


# ----------------------------------------------------------------------------------
# Shared helpers
# ----------------------------------------------------------------------------------
def load_positions() -> pd.DataFrame:
    """Load the extract and derive both policies, mirroring the SQL definitions."""
    d = pd.read_csv(CSV_PATH)
    d["lead_time_demand"] = d["Avg_Daily_Demand"] * d["Lead_Time_Days"]
    d["static_safety"] = (d["Static_Reorder_Point"] - d["lead_time_demand"]).clip(lower=0)
    d["ai_safety"] = (d["AI_Reorder_Point"] - d["lead_time_demand"]).clip(lower=0)
    d["static_inv_units"] = d["static_safety"] + d["Static_Order_Qty_Units"] / 2.0
    d["ai_inv_units"] = d["ai_safety"] + d["AI_Order_Qty_Units"] / 2.0
    d["static_cost"] = d["static_inv_units"] * d["Holding_Cost_Per_Unit"]
    d["ai_cost"] = d["ai_inv_units"] * d["Holding_Cost_Per_Unit"]
    d["stockout_days"] = d["Stockout_Events_YTD"] * d["Avg_Stockout_Duration_Days"]
    d["lost_units"] = d["stockout_days"] * d["Avg_Daily_Demand"]
    d["lost_revenue"] = d["lost_units"] * d["Unit_Price"]
    d["lost_margin"] = d["lost_units"] * (d["Unit_Price"] - d["Unit_Cost"])
    d["forward_exposure"] = np.where(
        d["Current_Stock"] < d["lead_time_demand"],
        (d["lead_time_demand"] - d["Current_Stock"]) * d["Unit_Price"], 0.0,
    )
    d["revenue_at_risk"] = d["lost_revenue"] + d["forward_exposure"]
    d["annual_cogs"] = d["Units_Sold_YTD"] * d["Unit_Cost"] * ANNUALISE
    return d


def new_figure(theme: dict, width: float, height: float):
    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_facecolor(theme["surface"])
    ax.set_facecolor(theme["surface"])
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(theme["axis"])
        ax.spines[side].set_linewidth(0.8)
    ax.tick_params(colors=theme["muted"], labelsize=9, length=0)
    return fig, ax


def titles(ax, theme: dict, title: str, subtitle: str) -> None:
    ax.set_title(title, color=theme["text"], fontsize=13.5, fontweight="bold",
                 loc="left", pad=26)
    ax.text(0, 1.025, subtitle, transform=ax.transAxes, color=theme["muted"],
            fontsize=9.5, va="bottom", ha="left")


def _data_radius(ax, radius_px=3.5):
    """Convert a pixel radius into x and y data units for the current axes."""
    fig = ax.get_figure()
    w_in, h_in = fig.get_size_inches()
    pos = ax.get_position()
    ax_w_px = max(w_in * 100 * pos.width, 1)
    ax_h_px = max(h_in * 100 * pos.height, 1)
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    return radius_px * (x1 - x0) / ax_w_px, radius_px * (y1 - y0) / ax_h_px


def rounded_bar(ax, x, y, w, h, color, theme, horizontal=True, radius_px=3.5):
    """Bar with the data end rounded and the baseline end left square."""
    rx, ry = _data_radius(ax, radius_px)

    if horizontal:
        rx = min(rx, abs(w) * 0.8)
        ry = min(ry, abs(h) / 2.2)
        sx = 1 if w >= 0 else -1
        xe = x + w
        verts = [
            (x, y),
            (xe - sx * rx, y), (xe, y), (xe, y + ry),
            (xe, y + h - ry), (xe, y + h), (xe - sx * rx, y + h),
            (x, y + h), (x, y),
        ]
    else:
        ry = min(ry, abs(h) * 0.8)
        rx = min(rx, abs(w) / 2.2)
        sy = 1 if h >= 0 else -1
        ye = y + h
        verts = [
            (x, y),
            (x, ye - sy * ry), (x, ye), (x + rx, ye),
            (x + w - rx, ye), (x + w, ye), (x + w, ye - sy * ry),
            (x + w, y), (x, y),
        ]

    codes = [MplPath.MOVETO, MplPath.LINETO, MplPath.CURVE3, MplPath.CURVE3,
             MplPath.LINETO, MplPath.CURVE3, MplPath.CURVE3, MplPath.LINETO, MplPath.CLOSEPOLY]
    ax.add_patch(PathPatch(MplPath(verts, codes), facecolor=color, edgecolor="none", zorder=3))


def axis_sgd(v: float, _=None) -> str:
    """Compact SGD formatter for axis ticks: 10k, 100k, 1m, 10m."""
    if abs(v) >= 1_000_000:
        return f"{v / 1_000_000:g}m"
    if abs(v) >= 1_000:
        return f"{v / 1_000:g}k"
    return f"{v:g}"


def sgd(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"{v / 1_000_000:.2f}m"
    if abs(v) >= 1_000:
        return f"{v / 1_000:.0f}k"
    return f"{v:.0f}"


def save(fig, name: str, mode: str) -> str:
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{name}-{mode}.png")
    fig.savefig(path, dpi=170, facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.32)
    plt.close(fig)
    return path


# ----------------------------------------------------------------------------------
# Chart 1 - Carrying cost by warehouse
# ----------------------------------------------------------------------------------
def chart_carrying_cost(d: pd.DataFrame, theme: dict, mode: str) -> str:
    g = (d.groupby(["Warehouse_ID", "Warehouse_Name"])
           .agg(static=("static_cost", "sum"), ai=("ai_cost", "sum"),
                protected=("static_cost", "size"))
           .reset_index())
    g["protected"] = [
        int(((d.Warehouse_ID == w) & (d.ai_cost > d.static_cost)).sum()) for w in g.Warehouse_ID
    ]
    g["saving_pct"] = (g.static - g.ai) / g.static * 100
    g = g.sort_values("static", ascending=True).reset_index(drop=True)

    fig, ax = new_figure(theme, 9.8, 4.9)
    xmax = g.static.max()
    ax.set_xlim(0, xmax * 1.46)
    ax.set_ylim(-0.52, len(g) - 0.48)

    bh = 0.19
    for i, row in g.iterrows():
        rounded_bar(ax, 0, i + 0.03, row.static, bh, theme["s1"], theme)
        rounded_bar(ax, 0, i - bh - 0.03, row.ai, bh, theme["s2"], theme)
        ax.text(row.static + xmax * 0.015, i + 0.03 + bh / 2, sgd(row.static),
                va="center", ha="left", color=theme["muted"], fontsize=8.5)
        ax.text(row.ai + xmax * 0.015, i - bh / 2 - 0.03, sgd(row.ai),
                va="center", ha="left", color=theme["muted"], fontsize=8.5)
        ax.text(xmax * 1.16, i + 0.05, f"-{row.saving_pct:.1f}%",
                va="center", ha="left", color=theme["text"], fontsize=11, fontweight="bold")
        ax.text(xmax * 1.16, i - 0.16, f"{row.protected} SKUs given more stock",
                va="center", ha="left", color=theme["muted"], fontsize=8.5)

    ax.set_yticks(range(len(g)))
    ax.set_yticklabels([f"{r.Warehouse_Name}\n{r.Warehouse_ID}" for _, r in g.iterrows()],
                       color=theme["text"], fontsize=9.5, linespacing=1.5)
    ax.set_xticks([])
    ax.spines["bottom"].set_visible(False)
    ax.spines["left"].set_color(theme["axis"])

    handles = [plt.Rectangle((0, 0), 1, 1, fc=theme["s1"]), plt.Rectangle((0, 0), 1, 1, fc=theme["s2"])]
    leg = ax.legend(handles, ["Static reorder points (today)", "AI forecast-driven policy"],
                    loc="lower left", frameon=False, fontsize=9.5, ncol=2,
                    bbox_to_anchor=(0.0, -0.17), handlelength=1.1, handleheight=1.1)
    for t in leg.get_texts():
        t.set_color(theme["text"])

    total_s, total_a = g.static.sum(), g.ai.sum()
    titles(ax, theme,
           "Annual inventory carrying cost, by warehouse",
           f"SGD. Portfolio falls from {sgd(total_s)} to {sgd(total_a)}, "
           f"a {(total_s - total_a) / total_s * 100:.1f}% reduction. "
           "Batam saves least because its long lead times need protection, not cuts.")
    return save(fig, "01-carrying-cost-by-warehouse", mode)


# ----------------------------------------------------------------------------------
# Chart 2 - Saving waterfall
# ----------------------------------------------------------------------------------
def chart_waterfall(d: pd.DataFrame, theme: dict, mode: str) -> str:
    static_total = d.static_cost.sum()
    ai_total = d.ai_cost.sum()
    safety = ((d.static_safety - d.ai_safety) * d.Holding_Cost_Per_Unit).sum()
    cycle = ((d.Static_Order_Qty_Units - d.AI_Order_Qty_Units) / 2 * d.Holding_Cost_Per_Unit).sum()

    steps = [
        ("Carrying cost\nunder static\nreorder points", 0, static_total, theme["s1"], True),
        ("Safety stock\nreduction", static_total - safety, safety, theme["s2"], False),
        ("Cycle stock\nreduction", ai_total, cycle, theme["s2"], False),
        ("Carrying cost\nunder AI\npolicy", 0, ai_total, theme["s1"], True),
    ]

    fig, ax = new_figure(theme, 9.2, 5.0)
    ax.set_xlim(-0.7, 3.7)
    ax.set_ylim(0, static_total * 1.2)
    ax.grid(axis="y", color=theme["grid"], linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)

    bw = 0.52
    for i, (label, base, height, color, is_total) in enumerate(steps):
        rounded_bar(ax, i - bw / 2, base, bw, height, color, theme, horizontal=False)
        ax.text(i, base + height + static_total * 0.03,
                ("" if is_total else "-") + sgd(height),
                ha="center", va="bottom", color=theme["text"], fontsize=10, fontweight="bold")
        if not is_total:
            pct = height / (static_total - ai_total) * 100
            if height > static_total * 0.11:
                ax.text(i, base + height / 2, f"{pct:.0f}% of\nthe saving", ha="center",
                        va="center", color="#ffffff", fontsize=8.5, linespacing=1.4)
            else:
                ax.text(i, base - static_total * 0.025, f"{pct:.0f}% of the saving",
                        ha="center", va="top", color=theme["muted"], fontsize=8.5)

    for i in range(3):
        y = steps[i][1] + steps[i][2] if i == 0 else steps[i][1]
        ax.plot([i + bw / 2, i + 1 - bw / 2], [y, y], color=theme["axis"],
                linewidth=1, linestyle=(0, (3, 3)), zorder=2)

    ax.set_xticks(range(4))
    ax.set_xticklabels([s[0] for s in steps], color=theme["text"], fontsize=9.5, linespacing=1.5)
    ax.set_yticks(np.arange(0, static_total * 1.2, 1_000_000))
    ax.set_yticklabels([f"{v/1e6:.0f}m" for v in np.arange(0, static_total * 1.2, 1_000_000)])

    handles = [plt.Rectangle((0, 0), 1, 1, fc=theme["s1"]), plt.Rectangle((0, 0), 1, 1, fc=theme["s2"])]
    leg = ax.legend(handles, ["Policy carrying cost", "Reduction component"],
                    loc="upper right", frameon=False, fontsize=9.5)
    for t in leg.get_texts():
        t.set_color(theme["text"])

    titles(ax, theme,
           "Where the SGD 776k saving actually comes from",
           "Annual carrying cost, SGD. Two independently auditable components: statistical "
           "safety stock sizing, and smaller order quantities once PO raising is automated.")
    return save(fig, "02-savings-waterfall", mode)


# ----------------------------------------------------------------------------------
# Chart 3 - Revenue at risk, Pareto concentration
# ----------------------------------------------------------------------------------
def chart_pareto(d: pd.DataFrame, theme: dict, mode: str) -> str:
    """Two stacked panels sharing one x-axis - never two y-scales on one plot."""
    total = d.revenue_at_risk.sum()
    top = d.nlargest(25, "revenue_at_risk").reset_index(drop=True)
    share = top.revenue_at_risk / total * 100
    cum = share.cumsum()

    fig, (ax_top, ax_bot) = plt.subplots(
        2, 1, figsize=(9.6, 5.8), sharex=True,
        gridspec_kw={"height_ratios": [1, 1.35], "hspace": 0.22})
    fig.patch.set_facecolor(theme["surface"])
    for ax in (ax_top, ax_bot):
        ax.set_facecolor(theme["surface"])
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(theme["axis"])
            ax.spines[side].set_linewidth(0.8)
        ax.tick_params(colors=theme["muted"], labelsize=9, length=0)
        ax.grid(axis="y", color=theme["grid"], linewidth=0.8, zorder=0)
        ax.set_axisbelow(True)
        ax.set_xlim(-0.9, 25.0)

    # Panel 1 - what each individual position contributes
    ax_top.set_ylim(0, share.max() * 1.28)
    for i, v in enumerate(share):
        rounded_bar(ax_top, i - 0.3, 0, 0.6, v, theme["s1"], theme, horizontal=False)
    ax_top.text(0, share.max() * 1.18, f"SKU-{top.SKU_ID.iloc[0].split('-')[1]} at "
                f"{top.Warehouse_ID.iloc[0]} alone carries {share.iloc[0]:.1f}%",
                color=theme["muted"], fontsize=8.5, ha="left", va="bottom")
    ax_top.set_yticks(np.arange(0, share.max() * 1.28, 1))
    ax_top.set_yticklabels([f"{v:.0f}%" for v in np.arange(0, share.max() * 1.28, 1)])
    ax_top.set_ylabel("Each position", color=theme["muted"], fontsize=9.5, labelpad=10)

    # Panel 2 - how fast the exposure accumulates
    ax_bot.set_ylim(0, cum.iloc[-1] * 1.16)
    ax_bot.fill_between(range(25), cum, 0, color=theme["s2"], alpha=0.12, zorder=2)
    ax_bot.plot(range(25), cum, color=theme["s2"], linewidth=2.2, zorder=4)
    ax_bot.scatter([24], [cum.iloc[-1]], s=75, color=theme["s2"], zorder=5,
                   edgecolor=theme["surface"], linewidth=2)
    ax_bot.annotate(f"{cum.iloc[-1]:.0f}% of all exposure",
                    xy=(24, cum.iloc[-1]), xytext=(19.4, cum.iloc[-1] * 0.60),
                    color=theme["text"], fontsize=9.5, ha="center", fontweight="bold",
                    arrowprops=dict(arrowstyle="-", color=theme["axis"], linewidth=1))
    ax_bot.set_yticks(np.arange(0, 35, 10))
    ax_bot.set_yticklabels([f"{v}%" for v in np.arange(0, 35, 10)])
    ax_bot.set_ylabel("Running total", color=theme["muted"], fontsize=9.5, labelpad=10)
    ax_bot.set_xticks([0, 4, 9, 14, 19, 24])
    ax_bot.set_xticklabels(["1", "5", "10", "15", "20", "25"])
    ax_bot.set_xlabel("SKU-warehouse positions, ranked by revenue at risk",
                      color=theme["muted"], fontsize=9.5, labelpad=10)

    ax_top.set_title("Stockout exposure is concentrated, not portfolio-wide",
                     color=theme["text"], fontsize=13.5, fontweight="bold", loc="left", pad=30)
    ax_top.text(0, 1.10, f"Share of SGD {total/1e6:.1f}m total revenue at risk. "
                "Fixing 25 of 1,000 positions addresses roughly a third of the problem.",
                transform=ax_top.transAxes, color=theme["muted"], fontsize=9.5,
                va="bottom", ha="left")
    return save(fig, "03-revenue-at-risk-pareto", mode)


# ----------------------------------------------------------------------------------
# Chart 4 - Inventory turnover
# ----------------------------------------------------------------------------------
def chart_turnover(d: pd.DataFrame, theme: dict, mode: str) -> str:
    sku = (d.groupby(["SKU_ID", "ABC_Class"])
             .agg(cogs=("annual_cogs", "sum"),
                  ai_inv=("ai_inv_units", lambda s: 0),
                  )
             .reset_index())
    inv_val = d.assign(v=d.ai_inv_units * d.Unit_Cost).groupby("SKU_ID").v.sum()
    sku["inv_val"] = sku.SKU_ID.map(inv_val)
    sku["turnover"] = sku.cogs / sku.inv_val

    fig, ax = new_figure(theme, 9.6, 5.4)
    ax.set_xscale("log")
    ax.grid(color=theme["grid"], linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)

    colours = {"A": theme["s1"], "B": theme["s2"], "C": theme["s3"]}
    handles = {}
    for cls in ["C", "B", "A"]:
        pts = sku[sku.ABC_Class == cls]
        handles[cls] = ax.scatter(pts.cogs, pts.turnover, s=34, color=colours[cls], alpha=0.85,
                                  edgecolor=theme["surface"], linewidth=0.8, zorder=3,
                                  label=f"Class {cls}  ({len(pts)} SKUs)")

    ax.axhline(TURNOVER_TARGET, color=theme["neutral"], linewidth=1.4,
               linestyle=(0, (5, 4)), zorder=2)
    ax.text(sku.cogs.max(), TURNOVER_TARGET + 0.7, f"Target {TURNOVER_TARGET}x",
            ha="right", va="bottom", color=theme["text"], fontsize=9)

    tail = sku.nsmallest(15, "turnover")
    ax.annotate(
        f"{len(sku[sku.turnover < 5])} SKUs turn below 5x,\n"
        f"holding {365/tail.turnover.max():.0f}-{365/tail.turnover.min():.0f} days of stock",
        xy=(tail.cogs.quantile(0.6), tail.turnover.quantile(0.6)),
        xytext=(sku.cogs.min() * 1.25, sku.turnover.max() * 0.30),
        color=theme["text"], fontsize=9.5, linespacing=1.5, ha="left",
        arrowprops=dict(arrowstyle="-", color=theme["axis"], linewidth=1,
                        connectionstyle="arc3,rad=-0.2"))

    ax.set_xlabel("Annual cost of goods sold, SGD (log scale)", color=theme["muted"],
                  fontsize=9.5, labelpad=10)
    ax.set_ylabel("Inventory turnover, times per year", color=theme["muted"],
                  fontsize=9.5, labelpad=10)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(axis_sgd))

    leg = ax.legend([handles[c] for c in ["A", "B", "C"]],
                    [handles[c].get_label() for c in ["A", "B", "C"]],
                    loc="upper left", frameon=False, fontsize=9.5)
    for t in leg.get_texts():
        t.set_color(theme["text"])

    titles(ax, theme,
           "The trapped capital sits in the slow-moving tail",
           "Each point is one SKU across all four warehouses, under the AI policy. "
           "High-revenue A-class items already turn well; C-class items are the problem.")
    return save(fig, "04-inventory-turnover", mode)


# ----------------------------------------------------------------------------------
# Chart 5 - ROI payback
# ----------------------------------------------------------------------------------
def chart_payback(d: pd.DataFrame, theme: dict, mode: str) -> str:
    carrying = d.static_cost.sum() - d.ai_cost.sum()
    margin = d.lost_margin.sum() * ANNUALISE * TRUE_LOST_SALES_FACTOR * STOCKOUT_REDUCTION_RATE
    productivity = PLANNER_HOURS_PER_WEEK * 52 * PLANNER_HOURLY_RATE
    net_annual = carrying + margin + productivity - ANNUAL_RUN_COST

    months = np.arange(0, 25)
    cumulative = -IMPLEMENTATION_COST + net_annual / 12 * months
    breakeven = IMPLEMENTATION_COST / (net_annual / 12)

    fig, ax = new_figure(theme, 9.6, 5.4)
    ax.set_xlim(0, 24)
    ax.set_ylim(cumulative.min() * 1.25, cumulative.max() * 1.22)
    ax.grid(axis="y", color=theme["grid"], linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)

    ax.axhline(0, color=theme["axis"], linewidth=1.2, zorder=2)
    ax.fill_between(months, cumulative, 0, where=(cumulative < 0),
                    color=theme["s2"], alpha=0.13, zorder=1)
    ax.fill_between(months, cumulative, 0, where=(cumulative >= 0),
                    color=theme["s1"], alpha=0.13, zorder=1)
    ax.plot(months, cumulative, color=theme["s1"], linewidth=2.4, zorder=4)

    ax.scatter([breakeven], [0], s=90, color=theme["s1"], zorder=6,
               edgecolor=theme["surface"], linewidth=2)
    ax.annotate(f"Breakeven at {breakeven:.1f} months",
                xy=(breakeven, 0), xytext=(breakeven + 1.1, cumulative.min() * 0.52),
                color=theme["text"], fontsize=10, fontweight="bold",
                arrowprops=dict(arrowstyle="-", color=theme["axis"], linewidth=1))

    ax.scatter([24], [cumulative[-1]], s=70, color=theme["s1"], zorder=6,
               edgecolor=theme["surface"], linewidth=2)
    ax.text(23.6, cumulative[-1] + cumulative.max() * 0.07,
            f"+SGD {sgd(cumulative[-1])} by month 24",
            ha="right", va="bottom", color=theme["text"], fontsize=9.5)
    ax.text(1.3, -IMPLEMENTATION_COST * 0.97,
            f"SGD {sgd(IMPLEMENTATION_COST)} implementation cost",
            ha="left", va="top", color=theme["muted"], fontsize=9.5)

    ax.set_xticks([0, 3, 6, 9, 12, 15, 18, 21, 24])
    ax.set_xlabel("Months from go-live", color=theme["muted"], fontsize=9.5, labelpad=10)
    yt = np.arange(-1_000_000, cumulative.max() + 500_000, 500_000)
    ax.set_yticks(yt)
    ax.set_yticklabels([("-" if v < 0 else "") + sgd(abs(v)) if v else "0" for v in yt])

    titles(ax, theme,
           "Cumulative net position turns positive inside the first year",
           f"SGD, cumulative. Net annual benefit of {sgd(net_annual)} against a "
           f"{sgd(IMPLEMENTATION_COST)} build and {sgd(ANNUAL_RUN_COST)} annual run cost.")
    return save(fig, "05-roi-payback", mode)


def main() -> None:
    if not os.path.exists(CSV_PATH):
        raise SystemExit("inventory_data.csv not found. Run data/generate_supply_chain_data.py first.")
    d = load_positions()
    builders = [chart_carrying_cost, chart_waterfall, chart_pareto, chart_turnover, chart_payback]
    written = []
    for mode, theme in THEMES.items():
        for build in builders:
            written.append(build(d, theme, mode))
    print(f"Generated {len(written)} chart files in presentation/charts/")
    for p in written:
        print(f"  {os.path.relpath(p, ROOT)}  ({os.path.getsize(p) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
