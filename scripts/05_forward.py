"""Part C (design/forward_plan.md): extend the forward record with today's published files.

Usage: python3 scripts/05_forward.py            fetch today's files, check them, update the record
       python3 scripts/05_forward.py --offline  reuse the files already in data/raw/forward

Writes forward/forecasts.csv (only when a row is added or scored) and forward/summary.md. A failed data check
stops the run before anything is written; on the schedule this fails the workflow, which notifies the owner.
"""
from pathlib import Path
import os
import subprocess
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tcurve import core, forward  # noqa: E402

RAW = ROOT / "data" / "raw" / "forward"
RECORD = ROOT / "forward" / "forecasts.csv"
SUMMARY = ROOT / "forward" / "summary.md"


def code_commit() -> str:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"][:12]
    try:
        out = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=ROOT, capture_output=True, text=True)
        return out.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def main(offline=False):
    if forward.plan_sha256() != forward.PLAN_SHA256:
        raise SystemExit("design/forward_plan.md differs from the version recorded in tcurve/forward.py")
    now = pd.Timestamp.now(tz="UTC")
    paths = ({name: RAW / name for name in forward.URLS} if offline else forward.download(RAW))
    raw = core.load_gsw(paths["feds200628.csv"])
    cm1 = forward.load_h15(paths["h15_treasury_constant_maturity.csv"])
    facts = forward.validate(raw, cm1, now.tz_localize(None).normalize())

    current = forward.build(raw, forward.bill_returns(cm1))
    archive = forward.load_archive()
    y, x = forward.series(archive, current)
    meta = {"made_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "code_commit": code_commit(),
            "curve_last_date": facts["curve_last_date"], "bill_last_date": facts["bill_last_date"],
            "weight_revision_max": forward.weight_revision(archive, current)}
    log = forward.read_log(RECORD)
    updated = forward.update(log, current, y, x, meta)

    RECORD.parent.mkdir(exist_ok=True)
    changed = len(updated) != len(log) or updated["realized_bp"].notna().sum() != log["realized_bp"].notna().sum()
    if changed or not RECORD.exists():
        updated.to_csv(RECORD, index=False)
    SUMMARY.write_text(forward.summary(updated))
    print(f"curve to {facts['curve_last_date']}, H.15 to {facts['bill_last_date']}; last complete month-end "
          f"{current.index[-1]}; record: {len(updated)} forecasts, {updated['realized_bp'].notna().sum()} scored"
          f"{' (updated)' if changed else ' (unchanged)'}; weight revision {meta['weight_revision_max']:.2e}")


if __name__ == "__main__":
    main(offline="--offline" in sys.argv[1:])
