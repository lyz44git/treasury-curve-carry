# Part C, a forward record of the carry forecast: plan written 2026-11-19, before the first forward position (end of November 2026)

## Purpose

Parts A and B used one vintage of the curve, downloaded once, and every month they score existed when the
rule was chosen. Part C applies the Part B rule, unchanged, to each new month as it is published, and records
the forecast before the month it forecasts has ended. It checks that the rule keeps running as specified on
months that did not exist when it was fixed. It is not a new test of carry: section 5 explains why.

## 1. Rule (Part B, unchanged)

- Butterfly at month-end t: long the 5-year zero, short the 2- and 10-year zeros, with weights that have no
  exposure to the first two principal components of monthly yield changes observed up to t (expanding window
  from August 1971, first weights after 120 changes): `core.expanding_butterfly`.
- Forecast of the butterfly's excess return over month t + 1: intercept and slope of an ordinary least-squares
  regression of the return on carry and roll-down over all earlier positions, applied to the carry at t. Same
  arithmetic as `evaluate.expanding_forecast`.
- Benchmark: the mean of all earlier returns.
- No new predictor, no re-estimated choice, no change to the sample start.

## 2. Data

| Series | Source | Use |
|---|---|---|
| Zero-coupon yields and Svensson parameters, daily | Federal Reserve, Gürkaynak, Sack and Wright nominal yield curve (`feds200628.csv`), downloaded fresh on each run | As in Part B |
| 1-month Treasury constant-maturity yield, daily | Federal Reserve, H.15 Selected Interest Rates (series `RIFLGFCM01_N.B`), downloaded fresh on each run | Bill return |

- **Bill return.** Part B used the Kenneth French RF, which is published a month or more after the month it
  covers and so is not available at month-end. The bill return over month m is the 1-month yield (percent,
  investment basis) on the last day of month m − 1 with data, times the days in month m over 365. A month is
  used only once the file contains a later date.
- **Step 0** (`scripts/04_forward_step0.py`, `reports/forward_step0.json`), computed before this plan was
  written and involving no month after August 2026:
  - Over August 2001 to September 2026 (302 months), the two bill returns differ by 0.84 bp a month on
    average (largest 8.1 bp; correlation 0.996).
  - The butterfly's weights sum to −0.04 on average, so the swap moves its carry by 0.04 bp on average
    (largest 0.34 bp), against a carry standard deviation of 0.69 bp. It moves the return by the same amount,
    against a return standard deviation of 6.2 bp.
  - Run on the files of 2026-11-19 over the 301 positions from August 2001 to August 2026, the Part C pipeline
    reproduces the published butterfly weights exactly, and the published carry and return to within those
    0.34 bp.
- **History.** The published series in `reports/part_b_monthly.csv` (positions opened from August 1981 to
  August 2026) is used as it stands. Positions opened from September 2026 on are computed from the files of
  the day of the run.
- A month-end is complete when the curve file contains a later date.

## 3. Record

- The first forward position is the one opened at the end of November 2026, the first month-end after this
  plan is committed. Positions opened in September and October 2026 enter the regression history only.
- Each run appends a row for every complete forward position not yet in the record: run time (UTC), code
  commit, last dates of the two files, butterfly weights, carry, forecast, benchmark, slope, number of
  months in the regression, and the largest change in the published butterfly weights when they are
  recomputed from the day's curve file (a check for revisions of past curves).
- Once written, these fields are never changed. A later revision of the curve shows up in the revision column of
  later rows; earlier forecasts stay as they were.
- The realized return is added once the following month-end is complete, with the run time and the curve
  date used.
- A forecast written after the end of the month it forecasts (for example, after the schedule was down) stays in
  the record and is counted separately as late.
- Files: `forward/forecasts.csv` and `forward/summary.md`, the latter written from the record alone.

## 4. Schedule and checks

- GitHub Actions, weekly (Tuesday), and on demand. The run commits only when the record changes.
- The run fails, and writes nothing, if:
  - either download fails after three attempts;
  - the curve file lacks a parameter or a published 1- to 10-year yield column;
  - the curve file ends more than 21 days before the run, or the H.15 file more than 10 days before;
  - a month-end since August 1971 lacks a full set of parameters;
  - a month-end yield is not finite or lies outside (−5%, 25%);
  - the Svensson formula misses the published yields of the last 250 days by more than 0.001 percentage points;
  - a 1-month yield lies outside [−1%, 25%];
  - the plan file differs from the version whose hash is recorded in the code.

## 5. Statistic and reading

- Forward out-of-sample R² of the forecast against the benchmark over the scored forward positions, updated
  each month and reported whatever its value.
- No interval before 24 scored months; from 24 on, the stationary bootstrap of Part B (paired squared errors,
  mean block 12 months, 2,000 draws).
- No conclusion before 60 scored months. Part B's interval over 421 months is about three percentage points wide
  on each side, and 60 more months cannot narrow it much. The record therefore shows that the rule runs as
  written on new data; it does not overturn or confirm Part B.

## 6. Changes

Any change to the rule, the data, the checks or the record after this plan is committed is logged in
`design/deviations.md` with its date, and its hash is recorded again.
