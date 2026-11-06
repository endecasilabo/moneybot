"""Image entrypoint. Usage: python /app/entrypoint.py trade|snapshot"""

import sys

from src.jobs import guarded, take_snapshot, trade_window

JOBS = {"trade": trade_window, "snapshot": take_snapshot}

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) == 2 else ""
    if name not in JOBS:
        raise SystemExit("usage: entrypoint.py trade|snapshot")
    guarded(name, JOBS[name])
