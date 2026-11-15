"""Image entrypoint. Usage: python /app/entrypoint.py snapshot|bars"""

import sys

from src.jobs import guarded, store_bars, take_snapshot

JOBS = {"snapshot": take_snapshot, "bars": store_bars}

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) == 2 else ""
    if name not in JOBS:
        raise SystemExit("usage: entrypoint.py snapshot|bars")
    guarded(name, JOBS[name])
