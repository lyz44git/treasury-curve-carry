"""Step 0 of Part C (design/forward_plan.md): checks of the bill return and of the forward pipeline.

Run once, before the first forward position. Needs the Part B downloads (scripts/01_download.py) and fetches
today's curve and H.15 files into data/raw/forward (git-ignored).

1. Bill return: H.15 1-month yield (as defined in the plan) against the Kenneth French RF used in Part B.
2. Its effect on the butterfly's carry and return, through the sum of the published butterfly weights.
3. The pipeline of Part C, run on today's files, against the published Part B series over the months where
   both bill returns exist.

Writes reports/forward_step0.json.
"""
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tcurve import core, forward  # noqa: E402


def main():
    paths = forward.download(ROOT / "data" / "raw" / "forward")
    raw = core.load_gsw(paths["feds200628.csv"])
    cm1 = forward.load_h15(paths["h15_treasury_constant_maturity.csv"])
    facts = forward.validate(raw, cm1, pd.Timestamp.now(tz="UTC").tz_localize(None).normalize())

    rf_h15 = forward.bill_returns(cm1)
    rf_french = core.load_rf()
    both = pd.concat([rf_french.rename("french"), rf_h15.rename("h15")], axis=1).dropna()
    diff_bp = (both["h15"] - both["french"]) * forward.BP

    archive = forward.load_archive()
    weight_sum = archive[[f"w_{n}y" for n in forward.LEGS]].sum(axis=1)
    log_gap = np.log1p(both["h15"]) - np.log1p(both["french"])
    carry_effect = (-weight_sum * log_gap.reindex(archive.index)).dropna() * forward.BP
    return_effect = (-weight_sum * log_gap.shift(-1).reindex(archive.index)).dropna() * forward.BP

    current = forward.build(raw, rf_h15)
    common = archive.index.intersection(current.dropna(subset=["x", "y"]).index)
    pipeline = {
        "positions_compared": len(common), "first": str(common[0]), "last": str(common[-1]),
        "max_abs_diff_carry_bp": float((current.loc[common, "x"] - archive.loc[common, "carry"]).abs().max() * forward.BP),
        "max_abs_diff_return_bp": float((current.loc[common, "y"] - archive.loc[common, "butterfly_rx"]).abs().max() * forward.BP),
        "max_abs_diff_weights_all_published_months": forward.weight_revision(archive, current),
    }
    result = {
        "files": facts,
        "bill_return": {"months": len(both), "first": str(both.index[0]), "last": str(both.index[-1]),
                        "mean_diff_bp": float(diff_bp.mean()), "mean_abs_diff_bp": float(diff_bp.abs().mean()),
                        "max_abs_diff_bp": float(diff_bp.abs().max()),
                        "correlation": float(both.corr().iloc[0, 1])},
        "butterfly_weight_sum": {"mean": float(weight_sum.mean()), "min": float(weight_sum.min()),
                                 "max": float(weight_sum.max())},
        "effect_on_carry_bp": {"mean_abs": float(carry_effect.abs().mean()), "max_abs": float(carry_effect.abs().max()),
                               "carry_sd": float(archive["carry"].std() * forward.BP)},
        "effect_on_return_bp": {"mean_abs": float(return_effect.abs().mean()),
                                "max_abs": float(return_effect.abs().max()),
                                "return_sd": float(archive["butterfly_rx"].std() * forward.BP)},
        "pipeline_against_published": pipeline,
    }
    (ROOT / "reports" / "forward_step0.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
