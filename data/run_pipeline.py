"""
Run the full data pipeline end to end.

    python3 data/run_pipeline.py

Equivalent to running, in order:
    data/01_generate_demand_history.py     two years of daily demand
    data/02_forecast_demand.py             backtest, select, forecast
    data/03_build_inventory_snapshot.py    replay the legacy policy, size both policies

Each step depends on the output of the one before it, so the order is not optional.
Every step is seeded, so the whole pipeline is byte-for-byte reproducible.
"""

from __future__ import annotations

import os
import subprocess
import sys

STEPS = [
    "01_generate_demand_history.py",
    "02_forecast_demand.py",
    "03_build_inventory_snapshot.py",
]

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    for i, step in enumerate(STEPS, 1):
        print(f"\n{'=' * 72}\n  STEP {i} of {len(STEPS)}: {step}\n{'=' * 72}")
        result = subprocess.run([sys.executable, os.path.join(HERE, step)])
        if result.returncode != 0:
            print(f"\n{step} failed. Stopping.")
            return result.returncode
    print("\nPipeline complete. Next: python3 sql/run_analysis.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
