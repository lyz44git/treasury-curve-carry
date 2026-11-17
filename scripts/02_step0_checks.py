"""Step 0 of design/plan.md: conventions and coverage, before any return is computed.

Outputs: reports/step0.json
"""
from pathlib import Path
import json
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tcurve import core  # noqa: E402

raw = core.load_gsw()
header = (ROOT / "data" / "raw" / "gsw" / "feds200628.csv").read_text().splitlines()[:9]
pub = [f"SVENY{n:02d}" for n in core.MATURITIES]
both = raw.dropna(subset=core.PARAMS[:3] + ["TAU1"] + pub)
rebuilt = np.vstack([core.svensson(core.MATURITIES, *row) for row in both[core.PARAMS].to_numpy()])
gap = np.abs(rebuilt - both[pub].to_numpy())
monthly = core.month_end(raw)
ten = monthly["SVENY10"].dropna()
rf = core.load_rf()
out = {
    "header": header,
    "daily_rows": int(len(raw)), "first_day": str(raw.index[0].date()), "last_day": str(raw.index[-1].date()),
    "first_day_with_each_maturity": {c: str(raw[c].first_valid_index().date()) for c in pub},
    "first_month_with_10y": str(ten.index[0]), "last_month": str(monthly.index[-1]),
    "months_with_10y": int(len(ten)),
    "svensson_vs_published_max_abs_gap_percent": float(gap.max()),
    "days_with_nelson_siegel_only": int((raw["BETA3"].fillna(0) == 0).sum()),
    "last_day_with_nelson_siegel_only": str(raw.index[raw["BETA3"].fillna(0) == 0][-1].date()),
    "rf_first_month": str(rf.index[0]), "rf_last_month": str(rf.index[-1]),
    "months_per_year_min": int(monthly.loc[ten.index[0]:].groupby(lambda p: p.year).size().iloc[1:-1].min()),
}
(ROOT / "reports").mkdir(exist_ok=True)
(ROOT / "reports" / "step0.json").write_text(json.dumps(out, indent=2))
print(json.dumps({k: v for k, v in out.items() if k != "header"}, indent=1))
