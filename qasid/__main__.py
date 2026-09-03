"""
Two ways in, on purpose.

    python -m qasid            opens the page — what a person does
    python -m qasid --run      posts what is due — what the schedule does

The scheduled run must never open the page, and the page must never be needed
for the scheduled run to work.
"""
import argparse
from datetime import date

def main():
    ap = argparse.ArgumentParser(prog="qasid")
    ap.add_argument("--run", action="store_true", help="post whatever is due now, then exit")
    ap.add_argument("--dry", action="store_true", help="show what would go out, send nothing")
    ap.add_argument("--force", action="store_true", help="ignore the time window")
    ap.add_argument("--limit", type=int, default=0, help="send at most N posts")
    ap.add_argument("--port", type=int, default=8770)
    a = ap.parse_args()

    if a.run or a.dry:
        from .engine import run
        run(dry=a.dry, force=a.force, limit=a.limit)
    else:
        from .app import main as serve
        serve(port=a.port)

if __name__ == "__main__":
    main()
