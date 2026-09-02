"""
SQL Analysis Runner
===================

Loads data/inventory_data.csv into an in-memory SQLite database, executes every
statement in sql/analysis_queries.sql, and prints the results. This lets a reviewer
reproduce the full analysis with no database server to install.

Usage:
    python3 sql/run_analysis.py            # print results to the console
    python3 sql/run_analysis.py --csv      # also write each result set to sql/output/
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_PATH = os.path.join(ROOT, "data", "inventory_data.csv")
SQL_PATH = os.path.join(ROOT, "sql", "analysis_queries.sql")
OUT_DIR = os.path.join(ROOT, "sql", "output")

QUERY_TITLES = [
    "QUERY 1 - TOTAL REVENUE AT RISK DUE TO STOCKOUTS",
    "QUERY 2 - CARRYING COST SAVINGS PER WAREHOUSE: AI vs STATIC",
    "QUERY 3 - INVENTORY TURNOVER RATIO ACROSS TOP SKUs",
]


def strip_comments(sql: str) -> str:
    """Remove block and line comments so statements can be split reliably."""
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    sql = re.sub(r"^\s*--.*$", "", sql, flags=re.MULTILINE)
    return sql


def load_statements() -> list[str]:
    with open(SQL_PATH, "r", encoding="utf-8") as fh:
        raw = fh.read()
    cleaned = strip_comments(raw)
    return [s.strip() for s in cleaned.split(";") if s.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the inventory analysis SQL suite.")
    parser.add_argument("--csv", action="store_true", help="write each result set to sql/output/")
    parser.add_argument("--rows", type=int, default=12, help="rows to print per query (default 12)")
    args = parser.parse_args()

    if not os.path.exists(CSV_PATH):
        print("inventory_data.csv not found. Run: python3 data/generate_supply_chain_data.py")
        return 1

    df = pd.read_csv(CSV_PATH)
    conn = sqlite3.connect(":memory:")
    df.to_sql("inventory_data", conn, index=False)
    print(f"Loaded {len(df):,} rows into in-memory SQLite (sqlite {sqlite3.sqlite_version})")

    statements = load_statements()
    if args.csv:
        os.makedirs(OUT_DIR, exist_ok=True)

    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 40)

    for i, stmt in enumerate(statements):
        title = QUERY_TITLES[i] if i < len(QUERY_TITLES) else f"STATEMENT {i + 1}"
        print("\n" + "=" * 118)
        print(f"  {title}")
        print("=" * 118)
        result = pd.read_sql_query(stmt, conn)
        print(result.head(args.rows).to_string(index=False))
        print(f"  [{len(result)} rows returned, {len(result.columns)} columns]")
        if args.csv:
            path = os.path.join(OUT_DIR, f"query_{i + 1}_results.csv")
            result.to_csv(path, index=False)
            print(f"  -> written to {path}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
