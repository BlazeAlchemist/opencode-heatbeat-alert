# Implementation Plan: A/D Zone Detection Indicator

## Objective
Add an Accumulation/Distribution zone detection indicator to the Rust stock-chart CLI tool that identifies periods of accumulation (smart money buying) and distribution (smart money selling) on daily candlestick charts.

---

## Implemented (Current State)

### 1. Range Detection (40-bar rolling window, step=1)
- Slide a 40-bar window across the dataset (1-bar step)
- Fit OLS linear regression: `price = a*t + b` for t in 0..39
  - `sum_t = 780` (sum of 0..39)
  - `sum_t2 = 20540` (sum of squares of 0..39)
  - Slope denominator `n·Σt² - (Σt)² = 213200`
- Compute Standard Error (SE) of regression residuals (÷38 degrees of freedom)
- If `SE / (max_high - min_low) < 0.25` → window is ranging (not trending)

### 2. Volume Filter
- Compute normalized volume as `avg(volume_i / close_i)` for the window (average of per-bar ratios)
- Compare to prior 40-bar window's same normalized volume
- If current ≤ prior → skip (no institutional presence relative to local baseline)
- **Known issue**: When `start < 40`, `prior_vol` is computed from fewer bars (`.max(1)`). At `start = 0`, `prior_vol = 0`, so the first window always passes the volume filter.

### 3. Bias Classification
- Compare `sum(close) / sum(open) - 1.0` within the window
- If `rel_close > 0.0` → Accumulation
- If `rel_close < 0.0` → Distribution

### 4. Zone Merging
- Merge consecutive raw windows of same bias when gap ≤ 15 bars
- Merged zone spans from first window's start to last window's end

### 5. Visualization
- Semi-transparent green rectangle (`RGBA(0,180,70,0.15)`) full chart height for Accumulation
- Semi-transparent red rectangle (`RGBA(200,0,40,0.15)`) full chart height for Distribution
- Bold 32px "A" / "D" text labels at zone midpoint, drawn via `top_area.draw_text()` at pixel y=130
- Rectangle x-coordinates use raw candle indices (not pixel-scaled) to align with the chart's Cartesian2d x-range

### Current Parameters
| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Window size | 40 bars | ~2 months of daily data |
| Window step | 1 bar | Maximum detection granularity |
| SE/range threshold | 0.25 | Allows moderate trending with consolidation |
| Volume comparison | Prior 40-bar window | Local baseline adapts to changing volume |
| Merge gap | 15 bars | Bridges short gaps between same-bias zones |
| Rectangle alpha | 0.15 | Subtle background tint |
| Label font | sans-serif 32 Bold | Readable near chart caption |

### Current Zone Counts
- **AVGO**: 3 accumulation, 5 distribution (8 zones, no overlap)
- **AAPL**: 4 accumulation, 3 distribution (7 zones, no overlap)

---

## Changes Applied

### Step-Based Window (Rec B) — Applied (final: step=10)
- **Change**: Loop step from `1` → `10` (reduces consecutive window overlap from 97.5% to 75%)
- **Implementation**: `for end in (39..n).step_by(10)`
- **Effect**: ~120 raw zones instead of ~1200; structural overlap between consecutive windows reduced
- **Merge condition**: `raw.start <= last.end` — only merge zones that actually overlap. Prevents merging zones separated by gaps (zones that failed filters)

### Overlap Resolution — Trim Instead of Forced Gap
- **Change**: Trim later zone to start at the earlier zone's end boundary (no forced 5-bar gap)
- **Implementation**: If `zone.start < last.end`, trim zone start to `last.end`; discard if trimmed below 20 bars
- **Effect**: Short boundary zones survive (≥20 bars) vs being discarded by previous 5-bar gap requirement
- **Example**: AVGO Apr-May 2025 A zone (21 bars) now preserved

### Post-Merge — Rejoin Adjacent Same-Bias Zones (added Turn 41)
- **Why**: When an opposite-bias zone is discarded (<20 bars after trim), the same-bias zones on either side become adjacent in the final list but are NOT merged by the initial merge step (which ran before the discard)
- **Fix**: After overlap resolution, iterate zones again: if `last.bias == zone.bias && last.end >= zone.start`, merge via `last.end = last.end.max(zone.end)`
- **Effect**: Prevents silent dropping of zones that were separated by discarded short intermediate zones
- **Example**: IREN D(790,859) and A(859,909) were present in `final_zones` but would be skipped in output without post-merge; post-merge ensures they appear as zones 12 and 13

### Min Consecutive — Rejected
- Dropped isolated single-step zones too aggressively at phase boundaries and chart edges

### Volume-Weighted Bias (Rec D) — Rejected
- VWAP ratio too directional in strong uptrends (AAPL: 860-bar continuous A zone)
- Reverted to original `sum(close) / sum(open) - 1.0`

### Parameters (Final)

| Parameter | Before | After | Rationale |
|-----------|--------|-------|-----------|
| Window step | 1 bar | **10 bars** | 75% overlap; finer than step=20 |
| Merge condition | gap ≤ 15 bars | **raw.start ≤ last.end** | Only merge overlapping zones |
| Overlap resolution | 5-bar gap + discard | **trim to boundary** | Keeps short zones ≥20 bars |
| Bias signal | close/open ratio | close/open ratio | VWAP rejected |
| SE/range threshold | 0.25 | 0.25 | Unchanged |
| Volume comparison | Prior 40 bars | Prior 40 bars | Unchanged |

### Final Zone Counts
- **AVGO**: 6 accumulation, 10 distribution (16 zones, zero overlap)
- **AAPL**: 4 accumulation, 3 distribution (7 zones, zero overlap)

---

## Code Review Fixes Applied

| Issue | Severity | Fix |
|-------|----------|-----|
| `sum_t2 = 124740` (wrong for 40-bar window) | Critical | Corrected to `20540.0` |
| HTTP client no timeout, indefinite hang risk | Major | Added `.timeout(Duration::from_secs(30))` |
| `std::mem::discriminant` instead of `==` | Minor | Added `#[derive(PartialEq)]` on `ZoneBias`; used `==` |
| Volume normalization inconsistency (avg of ratios vs ratio of averages) | Minor | Both window and prior use `avg(vol_i / close_i)` |
| Hardcoded label x offset (160px) ignores chart margins | Minor | Computed as `160 + (mid/nf) * chart_w`; 160 maps to `margin + y_label_area_size` |
| `#[allow(dead_code)]` on `AdZone.ongoing` | Nitpick | Retained with `// TODO` for future dashed-border rendering |
| `#[allow(clippy::needless_range_loop)]` | Nitpick | Retained; absolute indices needed for OLS math across multiple candle fields |

---

## Files Modified
- `src/rust/src/main.rs` — All detection logic, rendering, and code review fixes
- `.opencode/agent/ta-analyst.md` — Permission changed to `edit: allow, bash: allow`
- `.opencode/agent/code-reviewer.md` — Permission changed to `edit: allow, bash: allow`
- `.opencode/agent/beta-tester.md` — Permission changed to `edit: allow, bash: allow`
