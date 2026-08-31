"""
Rollup Worker — Database size optimizer and downsampler.
Compresses snapshots older than 30 days into daily averages (daily_rollups),
and purges raw 15-minute rows to keep total database size under ~50-70 MB forever.
"""

import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.database import execute_rollup_cleanup


def run_rollup_job(days_to_keep: int = 30):
    print(f"[Rollup Worker] Starting database rollup cleanup (keeping {days_to_keep} days detailed)...")
    res = execute_rollup_cleanup(days_to_keep=days_to_keep)
    print(f"[Rollup Worker] Completed: {res['rollups_created']} rollups stored, {res['snapshots_purged']} old raw snapshots purged.")
    return res


if __name__ == "__main__":
    run_rollup_job(days_to_keep=30)
