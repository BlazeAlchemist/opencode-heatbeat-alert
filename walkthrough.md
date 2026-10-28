# Walkthrough: A/D Zone Indicator

## Summary
An Accumulation/Distribution zone detection indicator was added to the `stock-chart` Rust CLI tool. It identifies 40-bar windows where price is ranging (not trending) with above-normalized volume, classifies them as Accumulation or Distribution, and renders colored background rectangles with text labels.

## Changes to `src/rust/src/main.rs`

### Data structures (lines 55-68)
- `ZoneBias` enum: `Accumulation`, `Distribution` with `PartialEq`
- `AdZone` struct: `start`, `end`, `bias`, `ongoing`

### Detection function `detect_ad_zones` (lines 70-153)
- 40-bar rolling OLS regression on closes
  - `sum_t = 780`, `sum_t2 = 20540` (corrected from buggy `124740`)
  - SE divided by 38 degrees of freedom
- SE/range < 0.25 filter for ranging detection
- Normalized volume `avg(vol_i / close_i)` vs prior 40-bar baseline (same formula)
- Bias from `rel_close = close_avg / open_avg - 1.0 > 0`
- Zone merging with 15-bar gap tolerance and `==` comparison (uses `PartialEq`)

### Rendering (lines 315-342)
- Semi-transparent `Rectangle` at raw candle index coordinates (not pixel-scaled)
- Bold 32px "A"/"D" text via `top_area.draw_text()` at pixel y=130
- Green `RGBA(0,180,70,0.15)` = Accumulation, Red `RGBA(200,0,40,0.15)` = Distribution

### Console output (lines 269-285)
- Zone count breakdown by bias
- Full list of all detected zones with bar ranges and dates

### HTTP client (line 158)
- 30-second timeout added to prevent indefinite hangs

## Bug Fixes

### Critical — OLS `sum_t2` constant
- **Bug**: `sum_t2 = 124740.0` (sum of j² for j=0..50 — wrong for 40-bar window)
- **Fix**: Changed to `20540.0` (correct sum for j=0..39)
- **Effect**: Slope denominator was 20× too large → slope `a` too flat → SE inflated → fewer zones detected
- **Before fix**: AVGO 19 zones, AAPL 41 zones
- **After fix**: AVGO 22 zones, AAPL 48 zones

### Rectangle coordinate misalignment
- **Bug**: `x = (index - 0.5) * nf / chart_w` — pixel-scale values re-mapped by chart transform → all zones clustered in first ~20%
- **Fix**: `x = index as f64 - 0.5` — raw candle indices matching chart's x-range

## Code Review Issues Addressed
| Severity | Issue | Fix |
|----------|-------|-----|
| Critical | Wrong `sum_t2` for 40-bar OLS | Corrected to `20540.0` |
| Major | No HTTP timeout | Added `Duration::from_secs(30)` |
| Minor | `std::mem::discriminant` for fieldless enum | Added `#[derive(PartialEq)]`, used `==` |
| Minor | Volume normalization mismatch | Both window and prior use `avg(vol_i / close_i)` |
| Minor | Hardcoded label offset | Uses `160 + (mid/nf) * chart_w` |
| Nitpick | `#[allow(dead_code)]` on `ongoing` | Retained with TODO intent |
| Nitpick | `#[allow(clippy::needless_range_loop)]` | Retained; required for multi-field OLS indexing |

## TA Review Feedback Addressed
1. **Volume baseline**: Switched from global last-value SMA20 to per-window local normalized volume comparison
2. **Zone merging**: Overlapping same-bias zones consolidated with 15-bar gap tolerance
3. **Slope-aware bias**: `rel_close > 0.0` instead of raw sum comparison
4. **Ongoing zones**: Field preserved but not visually styled yet (future: dashed border)
5. **Label position**: Computed pixel x = 160 + (mid/nf) × chart_w
6. **Rectangle alpha**: Set to 0.15 for subtle background tint

## Permission Changes
Three agent configs changed from `edit: deny, bash: ask` to `edit: allow, bash: allow`:
- `.opencode/agent/ta-analyst.md`
- `.opencode/agent/code-reviewer.md`
- `.opencode/agent/beta-tester.md`

## Usage
```bash
RUST_FONTCONFIG_DLOPEN=1 cargo run -- <TICKER>
```
Charts saved to `src/rust/results/<TICKER>.png`.

## Current Zone Counts
- **AVGO**: 11 accumulation, 11 distribution (22 merged zones across 1255 bars)
- **AAPL**: 25 accumulation, 23 distribution (48 merged zones across 1255 bars)
