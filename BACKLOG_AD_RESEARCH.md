# Backlog — Advanced A/D Zone Detection Research

## Status: PAUSED (ready for revisit)

Resume checkpoint: `SESSION_STATE.md`. Research remains paused. Results below are historical exploratory outputs, not validated accuracy measurements; the checkpoint records known prototype defects and chart/summary setting differences.

## Objective
Explore mathematical approaches beyond the current OLS regression + step-window for A/D zone detection. Three methods prototyped and compared.

---

## Prototypes Built

### 1. OLS (Baseline — Rust `main.rs`)
- 40-bar rolling OLS, SE/range < 0.25, volume vs prior 40-bar
- Implemented in the Rust CLI; the Python reference is not yet verified equivalent

### 2. Kalman Filter (`src/python/kalman_ad.py`)
- **State**: 2D — `[range_pos, v_rel]`
  - `range_pos = (close - min_low[0:40]) / (max_high[0:40] - min_low[0:40])` ∈ [0, 1]
  - `v_rel = vol / SMA(vol, 50)`
- **Transition**: φ=0.95 (position persistence), ψ=0.85 (volume mean-reversion)
- **Bias**: `(0.5 - pos) × 2`, EMA-smoothed (γ=0.94)
- **Zone extraction**: threshold=0.10, min_bars=20, vol post-filter ≥ 0.80
- **Key insight**: Separate bias direction (position-in-range) from volume confirmation (post-filter)

### 3. Chebyshev Spectral Analysis (`src/python/chebyshev_ad.py`)
- Degree-3 Chebyshev polynomial fit on 40-bar windows (step=10)
- **Spectral ratio**: `ρ = |c₁|·RMS(T₁) / √(Σ_{k=1}^{3} cₖ²·RMS²(Tₖ))` — exploratory coefficient-based proxy, not exact variation energy
- **Classification**: 0.30 ≤ ρ ≤ 0.80 → potential A/D; c₁ > 0 → A, c₁ < 0 → D
- **Volume filter**: same as OLS (avg vol/close vs prior window)
- **Caveat**: Chebyshev polynomials are not discretely orthogonal on this equally spaced grid; coefficient fitting uses least squares, but the ratio omits cross terms

---

## Results Summary

| Ticker  | OLS        | Kalman     | Chebyshev  |
|---------|------------|------------|------------|
| AAPL    | 8A/4D (12) | 8A/6D (14) | 8A/8D (16) |
| AVGO    | 5A/7D (12) | 3A/6D (9)  | 9A/4D (13) |
| IREN    | 9A/10D(19) | 5A/6D (11) | 7A/9D (16) |

### Agreement Rates (Chebyshev vs OLS)
- IREN: 75% — best agreement
- AVGO: 46%
- AAPL: 19% — lowest agreement (Chebyshev→Kalman agreement was about 63%)

These are directional same-bias zone overlap rates (IoU ≥ 0.30), not precision/recall or proof of detector quality. Baseline defects may affect them.

---

## Files
| File | Description |
|------|-------------|
| `src/python/kalman_ad.py` | Kalman filter prototype + OLS reference (Python) |
| `src/python/chebyshev_ad.py` | Chebyshev spectral analysis prototype |
| `src/python/compare_zones.py` | Three-way comparison with zone overlap |
| `src/python/run_summary.py` | Formatted summary table |
| `src/python/results/AAPL_kalman_vs_ols.png` | AAPL chart: KF bias + zones vs OLS |
| `src/python/results/AVGO_kalman_vs_ols.png` | AVGO chart: KF bias + zones vs OLS |
| `src/python/results/IREN_kalman_vs_ols.png` | IREN chart: KF bias + zones vs OLS |
| `advance_plan.md` | Six research proposals requiring mathematical re-review |
| `src/python/requirements.txt` | Python dependencies (yfinance, numpy, matplotlib) |
| `SESSION_STATE.md` | Resume checkpoint, known limitations, and Git publication blocker |

---

## Unresolved Questions (to address on revisit)
1. **Ground truth annotation** — manually label Wyckoff Phase A–E on 3 tickers for Precision/Recall/F1
2. **Kalman tuning** — phi, psi, Q, R per ticker vs universal; impact of volume threshold
3. **Chebyshev ρ bounds** — 0.30/0.80 are preliminary; optimize via grid search
4. **Ensemble** — combine KF bias signal + Chebyshev spectral ratio for confidence scoring
5. **Wyckoff Phase C detection** — Spring (accumulation) and Upthrust (distribution) not explicitly detected
6. **Port to Rust** — winning approach (or ensemble) needs Rust port for production use
