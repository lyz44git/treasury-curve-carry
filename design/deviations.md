# Notes and changes against `design/plan.md`

## Settled at step 0, 2026-11-17, before any return was computed

1. **Conventions confirmed from the file itself.** The file header states that zero-coupon yields are
   continuously compounded. Evaluating the Svensson formula from the published parameters reproduces the
   published 1- to 10-year yields to within 0.0004 percentage points on every day (`reports/step0.json`), so
   yields at "maturity less one month" are computed from the same parameters.
2. **Each day's curve.** The method paper (Gürkaynak, Sack and Wright, 2007) describes a separate fit to each
   day's prices. This was taken from the paper and not checked independently. The file header warns that the
   series is a staff research product subject to revision; the file is the vintage downloaded on 2026-11-17.
3. **Sample.** The 10-year yield is first available on 1971-08-16, so the sample starts with the August 1971
   month-end. It ends with September 2026, the last month of the bill-return file; the last position is opened
   at the end of August 2026.
4. **Short end kept at one year.** The authors publish yields from one year and fit securities with more than
   three months to maturity; the eleven-month point is inside that range. The shortest maturity was not moved.
5. **Bill rate in the carry.** From June 2024 the bill return in the source is an index return, which is not
   known at the start of the month. The carry therefore uses the bill return of the month just ended in every
   month, as the plan allows.

## Details the plan left open, fixed before any return was computed

6. **Windows.** The plan gives 240 months before the first forecast but does not say how many months the
   butterfly weights need. Weights use components estimated on an expanding window with at least 120 monthly
   yield changes, so the butterfly series starts 120 months into the sample; the first forecast is made 240
   months into the sample, when the forecasting regression has 120 observations.
7. **Scenario table is first order.** Profit or loss under a shock is minus notional times duration times the
   yield change, without convexity.
8. **Timing-rule cost.** Duration traded is the absolute change, leg by leg, of signed notional times duration
   between consecutive month-ends, including changes in the weights. Ageing of the bonds within the month is
   ignored.
9. **Placebo.** "Shifted by 12 months" is implemented as the butterfly's carry observed 12 months earlier.
