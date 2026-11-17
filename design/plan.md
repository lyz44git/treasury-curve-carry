# Carry and roll-down on the U.S. Treasury curve: plan written 2026-11-17, before the yield data were downloaded or read

## Question

Two parts, kept separate because only the second is a test.

- **Part A (description).** How much of the monthly movement of the 1- to 10-year zero-coupon curve do level,
  slope and curvature factors explain, and what do standard positions (a bullet, a barbell, a butterfly) gain
  or lose under shocks to each factor?
- **Part B (test).** Does the carry and roll-down of a level- and slope-neutral 2-5-10 butterfly predict its
  excess return over the next month, out of sample, better than its historical mean?

## What is and is not known when this is written

No yield file has been downloaded or opened. Only an HTTP header request confirmed that the source file exists
(16.7 MB). The feature definitions, the sample, the primary estimand and the reading rule are fixed here; any
later change is logged in `design/deviations.md`.

The published evidence is known in general terms. The slope of the curve predicts bond excess returns in
sample (Fama and Bliss 1987; Campbell and Shiller 1991). Carry predicts returns across asset classes,
bonds included (Koijen, Moskowitz, Pedersen and Vrugt 2018). Out-of-sample evidence for bond return
predictability is weaker, in particular after 2008. A result that does not beat the historical mean is a
plausible outcome and will be reported as such.

## Data

| Series | Source | Use |
|---|---|---|
| Zero-coupon yields and Svensson parameters, daily | Federal Reserve, Gürkaynak, Sack and Wright nominal yield curve (`feds200628.csv`) | Yields at any maturity from the fitted curve |
| One-month Treasury bill return, monthly | Kenneth French data library (`RF`) | Financing rate for excess returns |

Both are public and free. Raw files are git-ignored.

- Frequency: last business day of each month with a fitted curve.
- Maturities: 1, 2, ..., 10 years, and each of them less one month (for the return of a zero held one month),
  all evaluated from the Svensson parameters of that day.
- Sample: starts at the first month-end at which the 10-year yield is available in the file and ends at the
  last complete month. The start date is read from the file at step 0 and recorded; it is not chosen.

**Step 0, before any return is computed:** read the source's documentation and confirm (i) that each day's
curve is fitted to that day's prices only, so a month-end curve uses no later information; (ii) the units and
compounding of the yields; (iii) which maturities the authors consider reliable, in particular the short end.
If the one-year point or the "less one month" points are flagged as unreliable, the shortest maturity is moved
out to two years and the change is logged. Tabulate coverage by year.

## Definitions (fixed)

With continuously compounded zero yield y(n) for maturity n in years and h = 1/12:

- Log price of an n-year zero: p(n) = -n y(n).
- One-month log return: r(n) = p_next(n - h) - p(n).
- Excess return: rx(n) = r(n) - rf, with rf the one-month bill return of that month in logs.
- Carry and roll-down (the return if the curve does not move): c(n) = n y(n) - (n - h) y(n - h) - rf_known, where
  rf_known is the one-month rate observable at the month-end. If the bill return for the coming month is not
  observable at the month-end in the source, the prior month's bill return is used and this is stated.
- Modified duration of a zero held to the next month-end: n - h.

**Factors (Part A).** Principal components of the monthly changes of the ten yields, estimated on the full
sample for the description, and on expanding windows (first window 240 months) for the stability check.

**Butterfly (Parts A and B).** Long the 5-year zero, short the 2-year and 10-year zeros, with weights chosen
each month so that the position has zero exposure to the first two principal components estimated on data up
to that month, and a 5-year leg of one unit of duration. Weights use only past data.

## Part A outputs

1. Variance explained by the first three components; their loadings.
2. Expanding-window loadings at five-year intervals, to show how stable they are.
3. A scenario table: profit or loss, per 100 of notional in the 5-year leg, of a 5-year bullet, a
   duration-matched 2-10 barbell and the butterfly, under a one-standard-deviation monthly move of each of the
   first three components and under a parallel 25 basis point shift.
4. Realized monthly volatility of each position and the share explained by each component.

Part A makes no claim that needs a test. It is reported whatever Part B finds.

## Part B: test

| Element | Choice |
|---|---|
| Target | Excess return of the butterfly over the next month |
| Predictor | The butterfly's carry and roll-down at the month-end (weighted sum of c(n) over its legs) |
| Forecast | Expanding-window ordinary least squares of target on predictor; first forecast after 240 months |
| Benchmark | Expanding-window mean of the target (the "historical mean" forecast) |
| Frequency | Monthly, non-overlapping |

**Primary estimand:** out-of-sample R-squared, 1 - (sum of squared forecast errors of the model) / (sum of
squared forecast errors of the benchmark), over all forecast months, with a 95% interval from a stationary
bootstrap of the paired squared-error series (mean block 12 months, 2,000 draws; blocks 6 and 24 as a check).

**Secondary:**

1. The same statistic with the forecast restricted to have the sign of the predictor's coefficient implied by
   theory (a positive slope on carry), following Campbell and Thompson (2008).
2. In-sample regression with Newey-West errors (12 lags), for comparison with the literature.
3. A timing rule: hold the butterfly when the forecast is positive and the reverse position when negative.
   Annualized return, volatility, Sharpe ratio and maximum drawdown before costs, and under a cost scenario of
   0.5 basis points of yield per unit of duration traded on each leg. **The cost figure is an assumed scenario,
   not an estimate from transaction data.**
4. Sub-periods: before and after December 2008; and before and after the end of the first half of the forecast
   sample.
5. A cross-maturity check: each month, a duration-neutral position long the three maturities with the highest
   carry per unit of duration and short the three with the lowest, among 1 to 10 years. Sharpe ratio with
   interval.
6. Placebo: the predictor shifted forward by 12 months relative to the target (so that it cannot carry
   information about the next month beyond persistence). The out-of-sample R-squared should not be above that
   of the real predictor.
7. The level position (the 5-year bullet) predicted by the 10-year minus 1-year slope, the classic
   specification, reported for reference only.

**Reading rule (fixed in advance).**

- "Carry and roll-down predict the butterfly's return out of sample" only if the primary interval is above
  zero.
- "The prediction is usable" additionally requires the timing rule's Sharpe ratio interval under the cost
  scenario to be above zero.
- Otherwise the result is reported as no detectable predictability, with the secondary numbers shown as they
  are.
- No predictor, position or sample choice is changed after results are seen. A second round would be a new
  plan with its own date.

## Known limits

- The yields are a fitted curve of off-the-run securities, not traded prices. Returns computed from it are the
  returns of hypothetical zero-coupon bonds; the fitting error at the 2-, 5- and 10-year points enters the
  butterfly directly.
- The file is the current vintage. Step 0 checks whether past curves are re-estimated.
- No financing spread, no repo specialness, no margin: the excess return uses the bill rate.
- One country, one curve, about 650 months at most; the forecast sample is shorter by 240 months.

## Not in this plan

Individual securities, on-the-run versus off-the-run spreads, futures, swaps, inflation-indexed bonds,
macroeconomic predictors (Cochrane-Piazzesi forward-rate factors, survey data) and intraday data.
