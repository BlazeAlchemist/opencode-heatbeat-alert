# Advance Plan: Mathematical Approaches for A/D Zone Detection

## Objective
Identify new mathematical frameworks for detecting accumulation and distribution zones beyond the current OLS regression + step-window approach. Explore control system theory, polynomial fitting, and other statistical methods without bias toward the existing implementation.

---

## Approach 1: Piecewise Polynomial Regression (Segmented Fits)

### Concept
Instead of sliding a fixed 40-bar window, fit piecewise polynomials with variable segment boundaries (knots). Accumulation and distribution are characterized by different polynomial orders and coefficients within each segment.

### Mathematical Formulation
Fit a piecewise polynomial of degree `d` with `k` knots:
```
Price(t) = Σᵢ βᵢ·tⁱ + Σⱼ γⱼ·(t - tⱼ)₊ᵈ + ε(t)
```
where `(t - tⱼ)₊ = max(0, t - tⱼ)` are truncated power basis functions.

**Detection logic:**
- Accumulation: degree 1 (linear drift up) with negative autocorrelation of residuals (mean-reversion around drift)
- Distribution: degree 1 (linear drift down) with positive autocorrelation of residuals (trending)
- Neutral/ranging: degree 0 (flat) with low variance

**Optimal knot placement:** Use Bayesian Information Criterion (BIC) or cross-validation to determine the number and position of knots. Each knot represents a phase transition (A→D or D→A).

### Pros
- Natural phase transition detection (knots = regime changes)
- No sliding window artifacts
- Variable segment lengths adapt to market conditions

### Cons
- Computationally expensive (optimization over knot positions)
- Requires choosing polynomial degree and knot penalty

---

## Approach 2: Kalman Filter with State-Space Model

### Concept
Model the market as a dynamical system with hidden states (accumulation, distribution, trending). Volume and price are noisy observations of these hidden states. The Kalman filter estimates the probability of being in each state in real-time.

### Mathematical Formulation
**State vector:** x(t) = [Δp(t), v_rel(t), b(t)]ᵀ
- Δp(t) = close(t) − close(t−1) (price change, observable)
- v_rel(t) = vol(t) / SMA(vol, 50) (volume relative to baseline, observable)
- b(t) = latent bias (accumulation > 0, distribution < 0, unobservable — estimated by filter)

**State transition (control system dynamics):**
```
x(t+1) = F·x(t) + w(t),    w(t) ~ N(0, Q)
```
where F is a 3×3 matrix:
```
F = [  φ    0    0  ]    ← price change is autoregressive (φ ≈ 0.1–0.3)
    [  0    ψ    0  ]    ← volume regime is mean-reverting (ψ ≈ 0.7–0.9)
    [  α    β    γ  ]    ← bias evolves from price change + volume interaction
```
- φ: price change persistence (low for mean-reverting, high for trending)
- ψ: volume mean-reversion speed (high = volume quickly returns to baseline)
- α: how much price change affects bias (positive Δp → positive bias)
- β: how much elevated volume affects bias (high volume + positive Δp → accumulation)
- γ: bias persistence (γ ≈ 0.95–0.99, slow decay)

**Observation model:**
```
y(t) = H·x(t) + v(t),    v(t) ~ N(0, R)
```
where y(t) = [Δp(t), v_rel(t)]ᵀ (only observable states) and:
```
H = [ 1  0  0 ]    ← Δp maps directly to first state
    [ 0  1  0 ]    ← v_rel maps directly to second state
```

**Covariance matrices:**
- Q = diag(σ²_Δp, σ²_v, σ²_b) — process noise (tune from training data residuals)
- R = diag(σ²_obs_Δp, σ²_obs_v) — measurement noise (typically small, price/volume are observed accurately)

**Kalman Filter Steps:**
1. **Predict:** x̂(t|t−1) = F·x̂(t−1|t−1), P(t|t−1) = F·P(t−1|t−1)·Fᵀ + Q
2. **Update:** K(t) = P(t|t−1)·Hᵀ·(H·P(t|t−1)·Hᵀ + R)⁻¹
3. **Correct:** x̂(t|t) = x̂(t|t−1) + K(t)·(y(t) − H·x̂(t|t−1))
4. **Covariance:** P(t|t) = (I − K(t)·H)·P(t|t−1)

**Detection:**
- Accumulation: b̂(t|t) > τ (e.g., τ = 0.1) AND v_rel(t) > 1.0
- Distribution: b̂(t|t) < −τ AND v_rel(t) > 1.0
- The Kalman gain K(t) measures how much new information is incorporated — low gain = ranging/consolidation, high gain = trending/breakout

### Zone Extraction
The Kalman filter produces a continuous bias estimate b̂(t). To extract discrete zones:
1. **Thresholding:** Mark bars where |b̂(t)| > τ as "active" (A or D based on sign)
2. **Minimum duration:** Merge consecutive active bars into segments, discard segments < 20 bars
3. **Gap merging:** If two same-bias segments are separated by ≤ 10 inactive bars, merge them
4. **Overlap resolution:** Apply same trim-to-boundary logic as current implementation

### Pros
- Real-time detection (no look-ahead bias)
- Naturally handles noise via measurement error covariance R
- State-space framework is extensible (add features, regimes)
- Connection to control theory (system identification)
- Explicit matrix structure allows parameter tuning per ticker

### Cons
- Requires tuning Q and R covariance matrices
- Linear Gaussian assumption may miss nonlinear effects
- More complex implementation than sliding window
- Threshold τ still needs calibration (though less sensitive than OLS SE/range)

---

## Approach 3: Chebyshev Polynomial Approximation + Spectral Analysis

### Concept
Project price and volume onto Chebyshev polynomial basis functions. The coefficients of different polynomial orders capture different frequencies of market behavior. Accumulation/distribution manifests in specific spectral signatures.

### Mathematical Formulation
For a window of `n` bars, map bar indices to the Chebyshev domain xᵢ ∈ [−1, 1]:
```
xᵢ = 2·(i − i₀) / (n − 1) − 1,   i = 0, ..., n−1
```

Approximate price as a sum of Chebyshev polynomials Tₖ(x):
```
Price(x) = Σₖ cₖ·Tₖ(x),   k = 0, ..., d
```
where Tₖ(cos θ) = cos(k·θ) and **discrete orthogonality** coefficients are:
```
c₀ = (1/n) · Σᵢ Price(xᵢ)·T₀(xᵢ)
cₖ = (2/n) · Σᵢ Price(xᵢ)·Tₖ(xᵢ) / (Σᵢ Tₖ²(xᵢ) / n),   k ≥ 1
```

**Note:** For uniform bar spacing (not Chebyshev nodes), the denominator Σᵢ Tₖ²(xᵢ)/n ≠ 1 and must be computed explicitly. For n = 40, d = 3:
```
Σᵢ T₁²(xᵢ)/n ≈ 0.333,   Σᵢ T₂²(xᵢ)/n ≈ 0.125,   Σᵢ T₃²(xᵢ)/n ≈ 0.0625
```

**Detection logic based on coefficient patterns:**
- c₀ (mean): baseline price level
- c₁ (linear): overall trend direction (+ = accumulation, − = distribution)
- c₂ (quadratic): acceleration/deceleration — high |c₂| indicates phase transition
- c₃ (cubic): asymmetry — large c₃ with opposite sign to c₁ suggests distribution within uptrend

**Spectral ratio signature for A/D:**
```
E_trend = |c₁| · √(Σᵢ T₁²(xᵢ)/n)     (energy in linear component)
E_total = √(Σₖ cₖ² · Σᵢ Tₖ²(xᵢ)/n)  (total energy in polynomial fit)
ρ = E_trend / E_total                  (spectral ratio, ∈ [0, 1])
```

**Detection thresholds (two-band classification):**
- **Ranging/consolidation:** ρ < 0.30 (weak trend, energy spread across multiple frequencies)
- **Accumulation:** 0.30 ≤ ρ ≤ 0.70 AND c₁ > 0 (moderate trend up, controlled buying)
- **Distribution:** 0.30 ≤ ρ ≤ 0.70 AND c₁ < 0 (moderate trend down, controlled selling)
- **Strong trend (not A/D):** ρ > 0.70 (energy concentrated in linear term — breakout, not accumulation)

**Rationale:** Accumulation and distribution are *moderate* trends — not flat (ρ too low) and not explosive (ρ too high). The "Goldilocks zone" 0.30–0.70 captures controlled institutional buying/selling.

### Zone Extraction
1. Compute Chebyshev coefficients for each 40-bar window (step = 10)
2. Classify each window: A, D, or neutral based on ρ and c₁
3. Merge consecutive same-bias windows into zones
4. Apply minimum duration filter (≥ 20 bars) and gap merging (≤ 10 bars)
5. Overlap resolution: trim later zone to previous zone's end

### Pros
- Numerically stable (Chebyshev are orthogonal, avoids multicollinearity of regular polynomials)
- Multi-scale analysis (different polynomial orders = different time scales)
- Spectral ratio provides a continuous A/D intensity metric (not just binary classification)
- Natural extension to Fourier analysis of market cycles
- Thresholds are interpretable (ρ = fraction of energy in trend component)

### Cons
- Polynomial order selection (how many coefficients to keep? d = 3 is reasonable)
- Less intuitive than linear regression for most traders
- Discrete orthogonality correction requires precomputing normalization constants

---

## Approach 4: Hidden Markov Model (HMM) with Switching Regimes

### Concept
Model the market as having discrete hidden states (Accumulation, Distribution, Trending Up, Trending Down, Quiet). Transitions between states follow a Markov chain. Observations (returns, volume) are emitted from state-specific probability distributions.

### Mathematical Formulation
**States:** S = {A, D, TU, TD, Q}
**Transition matrix:** P(S(t+1) | S(t)) — learned via Baum-Welch EM algorithm
**Observation model:** P(return(t), volume(t) | S(t)) — state-specific Gaussian

**Detection:** The Viterbi algorithm computes the most likely sequence of states. Accumulation and Distribution are directly inferred as hidden states.

**State-specific emission distributions:**
- Accumulation: return ~ N(+0.001, 0.02), volume ~ Gamma(α_A, β_A) — moderate positive drift, elevated volume
- Distribution: return ~ N(-0.001, 0.025), volume ~ Gamma(α_D, β_D) — moderate negative drift, elevated volume
- Trending Up: return ~ N(+0.003, 0.015), volume ~ Gamma(α_TU, β_TU) — strong positive drift, moderate volume
- Trending Down: return ~ N(-0.003, 0.02), volume ~ Gamma(α_TD, β_TD) — strong negative drift, moderate volume
- Quiet: return ~ N(0, 0.01), volume ~ Gamma(α_Q, β_Q) — no drift, low volume

### Pros
- Directly models A and D as distinct states
- Probabilistic output (confidence intervals)
- Transition matrix captures regime persistence
- Well-established theory, many libraries available

### Cons
- Number of states must be chosen a priori
- EM algorithm can converge to local optima
- Requires sufficient data for each state

---

## Approach 5: Feedback Control System — PID Detector

### Concept
Model price discovery as a control system where volume acts as the control input and price as the output. Accumulation/distribution are identified by analyzing the step response and transfer function of the price-volume system.

### Mathematical Formulation
Define the "error" signal as deviation from a low-pass filtered price (trend):
```
e(t) = Price(t) − EMA(Price, 200)
```

Volume acts as the "control effort":
```
u(t) = Volume(t) / Volume_SMA(50)   (normalized control input)
```

**PID-inspired A/D score:**
- Proportional term: P(t) = e(t) · u(t) — immediate price-volume interaction
- Integral term: I(t) = Σ_{j=t−19}^{t} e(j)·u(j) — accumulated effect over 20 bars
- Derivative term: D(t) = P(t) − P(t−1) — rate of change of interaction

**Control-theoretic signatures:**
- Accumulation: P(t) > 0 (price above trend, elevated volume absorbing supply), I(t) building positive
- Distribution: P(t) < 0 (price below trend, elevated volume distributing), I(t) building negative

**Step Response Analysis — Damping Ratio ζ:**

**Volume shock definition:** A bar t₀ where:
```
vol(t₀) > μ_vol + 2·σ_vol   (over 50-bar rolling window)
```
This identifies bars with statistically significant volume spikes (top ~5% of volume distribution).

**Overshoot measurement:** After a volume shock at t₀, track price deviation from pre-shock mean:
```
μ_pre = mean(price(t₀−10), ..., price(t₀−1))
peak = max(price(t₀), ..., price(t₀+10))
trough = min(price(t₀), ..., price(t₀+10))
OS = (peak − μ_pre) / μ_pre   (for positive shocks, price spikes up)
```

**Damping ratio from second-order system approximation:**
```
ζ = −ln(OS) / √(π² + ln²(OS))
```
- ζ > 1 (overdamped) = accumulation (price resists movement after volume shock — supply absorbed)
- ζ < 1 (underdamped) = distribution (price oscillates/trends after volume shock — supply not absorbed)
- ζ ≈ 1 (critically damped) = neutral (price returns to equilibrium without oscillation)

**Interpretation:** In accumulation, large volume doesn't move price much (high damping — institutional buyers absorb all supply). In distribution, large volume causes price to swing (low damping — institutional sellers are distributing into buying pressure).

### Zone Extraction
1. Detect volume shocks (vol > μ + 2σ over 50-bar window)
2. For each shock, compute ζ from the 10-bar post-shock price response
3. Classify: ζ > 1.2 → Accumulation zone, ζ < 0.8 → Distribution zone
4. Extend zones: from each shock bar, extend backward to previous shock (or 20 bars) and forward to next shock (or 20 bars)
5. Merge overlapping same-bias zones, apply minimum duration filter (≥ 20 bars)

### Pros
- Directly from control theory (transfer functions, step response)
- PID components are interpretable (P = immediate, I = accumulated, D = acceleration)
- Damping ratio provides a continuous A/D intensity metric
- Volume shock definition is statistically grounded (2σ threshold)

### Cons
- Requires careful definition of "volume shock" (2σ threshold may need per-ticker calibration)
- PID gains need tuning per ticker
- Step response analysis is approximate for financial data (no clean step inputs)
- May miss A/D zones without volume shocks (slow accumulation)

---

## Approach 6: Bayesian Change Point Detection (BCPD)

### Concept
Treat accumulation/distribution as change points in the joint distribution of returns and volume. Use Bayesian inference to estimate the posterior probability of a change point at each bar.

### Mathematical Formulation
Model parameters (mean return, volume intensity) are constant between change points. After a change point, new parameters are drawn from a prior distribution.

**Prior:** P(change at bar t) = 1/λ (exponential waiting time with mean λ)

**Likelihood:** P(data | parameters within segment)

**Posterior:** P(change point | data) ∝ P(data | change point) · P(change point)

**Detection:** Bars with high posterior probability of a change point are phase transitions. Between change points, the segment is classified as A or D based on posterior mean of return and volume.

### Pros
- Principled uncertainty quantification
- No sliding window — segments are data-driven
- Natural handling of multi-scale (λ controls expected segment length)

### Cons
- Computationally intensive (MCMC or particle filtering)
- Prior sensitivity (choice of λ and parameter priors)
- Requires careful model specification

---

## Wyckoff Phase Mapping

Each mathematical approach must be validated against Wyckoff's A/D phase signatures. Below is the mapping between Wyckoff phases and mathematical detection criteria:

### Accumulation Phases (Wyckoff)
| Phase | Wyckoff Description | Mathematical Signature |
|-------|---------------------|------------------------|
| **Phase A** | Selling climax, automatic rally, secondary test | High volume spike + price reversal (PID: volume shock with ζ > 1). Kalman: b̂(t) crosses from negative to positive. Chebyshev: c₁ changes sign from negative to positive. |
| **Phase B** | Building cause, trading range | Low spectral ratio (ρ < 0.30), low OLS SE/range. Kalman: |b̂(t)| < τ (latent bias near zero). Price oscillates within ±2σ channel. |
| **Phase C** | Spring/test of support — price breaks below range then recovers | Price dips below 20-bar low then closes back inside range within 5 bars. Kalman: brief negative b̂(t) spike followed by rapid recovery. Chebyshev: c₂ > 0 (convex — price bottoming). |
| **Phase D** | Markup begins, higher lows | c₁ > 0 AND ρ increasing (trend strengthening). Kalman: b̂(t) > τ and rising. Volume on up-bars > volume on down-bars. |
| **Phase E** | Breakout from accumulation | ρ > 0.70 (strong trend), price breaks above 20-bar high. This is the **exit** from accumulation zone. |

### Distribution Phases (Wyckoff)
| Phase | Wyckoff Description | Mathematical Signature |
|-------|---------------------|------------------------|
| **Phase A** | Buying climax, automatic reaction, secondary test | High volume spike + price reversal (PID: volume shock with ζ < 1). Kalman: b̂(t) crosses from positive to negative. Chebyshev: c₁ changes sign from positive to negative. |
| **Phase B** | Building cause, trading range | Low spectral ratio (ρ < 0.30), low OLS SE/range. Kalman: |b̂(t)| < τ. Price oscillates within ±2σ channel. |
| **Phase C** | Upthrust/test of resistance — price breaks above range then fails | Price rises above 20-bar high then closes back inside range within 5 bars. Kalman: brief positive b̂(t) spike followed by rapid decline. Chebyshev: c₂ < 0 (concave — price topping). |
| **Phase D** | Markdown begins, lower highs | c₁ < 0 AND |ρ| increasing (downtrend strengthening). Kalman: b̂(t) < −τ and falling. Volume on down-bars > volume on up-bars. |
| **Phase E** | Breakdown from distribution | ρ > 0.70 (strong downtrend), price breaks below 20-bar low. This is the **exit** from distribution zone. |

### Validation Criteria
A mathematical approach is considered valid for A/D detection if it:
1. **Detects Phase C reliably:** Spring (accumulation) and Upthrust (distribution) are the most important Wyckoff signals. The approach must identify these within 3 bars of occurrence.
2. **Distinguishes Phase B from Phase D:** Phase B is ranging (low ρ), Phase D is trending (increasing ρ). False classification here leads to premature entries.
3. **Does not confuse Phase E with accumulation/distribution:** Phase E is a breakout/breakdown — the A/D zone has ended. The approach must exit the zone at Phase E.

---

## Recommendation Priority Matrix

| Approach | Accuracy | Robustness | Complexity | Novelty | Big-O | Priority |
|----------|----------|------------|------------|---------|-------|----------|
| 1. Piecewise Polynomial | Medium | Medium | Low | Medium | O(n·k·d) | ★★★ |
| 2. Kalman Filter (Control) | High | High | Medium | **High** | O(n·d³) | ★★★★★ |
| 3. Chebyshev Spectral | Medium | High | Medium | **High** | O(n·W·d) | ★★★★ |
| 4. HMM Switching | High | Medium | Medium | Medium | O(n·S²) | ★★★ |
| 5. PID Detector (Control) | Medium | Low | Low | **High** | O(n) | ★★★ |
| 6. Bayesian Change Point | High | High | **High** | Medium | O(n²) | ★★ |

**Complexity notation:**
- n = total bars (~1250 for 5 years daily)
- W = window size (40)
- d = state dimension / polynomial degree (3)
- k = number of knots (piecewise polynomial)
- S = number of hidden states (5 for HMM)

**Current OLS baseline:** O(n·W) — simple, fast, but limited by fixed window and linear assumption.

**Kalman filter O(n·d³):** With d = 3, d³ = 27 — very fast. Matrix operations are constant-size (3×3). Dominated by O(n) loop over bars.

**Chebyshev O(n·W·d):** For each window (n/W windows), compute d coefficients over W bars. With W = 40, d = 3: ~375 × 40 × 3 = 45,000 operations.

**PID O(n):** Single pass, no windows. Fastest approach but may miss slow A/D zones.

### Top Recommendation: Kalman Filter + State-Space Model

**Why:** Control system theory maps directly to accumulation/distribution dynamics. The state-space framework naturally handles:
- **System identification** — learn the dynamics of price-volume interaction
- **Filtering** — separate signal from noise
- **Prediction** — forecast regime transitions

**Implementation path:**
1. Define state vector: [price_drift, volume_regime, bias]
2. Learn transition matrix F from training data
3. Run Kalman filter on test data
4. Classify: bias(t) > threshold → Accumulation, bias(t) < -threshold → Distribution

### Second Priority: Chebyshev Polynomial + Spectral Analysis

**Why:** Orthogonal polynomials avoid the multicollinearity issues of regular polynomial regression. The spectral ratio approach provides a threshold-agnostic A/D intensity metric.

**Implementation path:**
1. Compute Chebyshev coefficients for 40-bar windows
2. Compute spectral ratio = |c₁| / Σ|cₖ|
3. Classify: low spectral ratio + c₁ > 0 → Accumulation, low spectral ratio + c₁ < 0 → Distribution
4. Compare with current SE/range approach

---

## Testing Framework

To fairly compare new approaches against the current implementation:

### 1. Benchmark Dataset
- **AAPL** (~1250 bars, 5 years daily) — known for long accumulation phases
- **AVGO** (~1250 bars, 5 years daily) — multiple A/D cycles
- **IREN** (~1250 bars, 5 years daily) — volatile, tests robustness

### 2. Ground Truth Annotation
Manually annotate 3–5 known A/D periods per ticker using Wyckoff criteria:
- **Accumulation zones:** Phase A (selling climax) through Phase D (markup begins)
- **Distribution zones:** Phase A (buying climax) through Phase D (markdown begins)
- **Exclude Phase E** (breakout/breakdown) from ground truth — these are exits, not A/D

Annotation sources:
- Natenberg's "Option Volatility and Pricing" — volatility regime changes
- Wyckoff method chart analysis — known accumulation/distribution patterns
- Volume profile analysis — high-volume nodes (HVN) = accumulation, low-volume nodes (LVN) = distribution

### 3. Quantitative Metrics

| Metric | Formula | Target |
|--------|---------|--------|
| **Precision** | TP / (TP + FP) | > 0.70 |
| **Recall** | TP / (TP + FN) | > 0.60 |
| **F1 Score** | 2·P·R / (P + R) | > 0.65 |
| **Jaccard Similarity** | |A ∩ B| / |A ∪ B| (zone overlap) | > 0.50 |
| **False Positive Rate** | FP / (FP + TN) | < 0.15 |
| **Detection Latency** | Median bars from zone start to first detection | ≤ 10 bars |
| **Zone Count Stability** | StdDev(zone count across similar tickers) | < 3 |
| **Computation Time** | Wall-clock seconds per ticker | < 1.0s |

**True Positive (TP):** Detected zone overlaps ground truth zone by ≥ 50% (Jaccard ≥ 0.50)
**False Positive (FP):** Detected zone with no ground truth overlap (Jaccard < 0.10)
**False Negative (FN):** Ground truth zone with no detected overlap (Jaccard < 0.10)
**True Negative (TN):** Bars correctly classified as "not A/D"

### 4. Parameter Sensitivity Analysis
For each approach, vary key parameters and measure output stability:
- **Kalman filter:** Vary τ (0.05, 0.10, 0.15, 0.20), Q diagonal (0.5×, 1×, 2×), R diagonal (0.5×, 1×, 2×)
- **Chebyshev:** Vary ρ thresholds (0.25, 0.30, 0.35), polynomial degree (d = 2, 3, 4)
- **PID:** Vary volume shock threshold (1.5σ, 2.0σ, 2.5σ), ζ thresholds (0.8, 1.0, 1.2)
- **Current OLS:** Vary SE/range threshold (0.20, 0.25, 0.30), window size (30, 40, 50)

**Stability metric:** Coefficient of variation (CV = σ/μ) of zone count across parameter variations. Lower CV = more robust.

### 5. Cross-Ticker Validation
Train parameters on AAPL, test on AVGO and IREN (and vice versa). A robust approach should generalize across tickers without per-ticker recalibration.

**Generalization metric:** F1 score on out-of-sample tickers (trained on one, tested on others). Target: F1 > 0.55 on all 3 cross-ticker combinations.

## Next Steps

1. **Prototype Kalman filter in Python** for rapid iteration
   - Define state-space matrices F, H, Q, R explicitly
   - Run on AAPL data, compare b̂(t) trajectory with current OLS zones
   - Tune τ, Q, R to maximize F1 against ground truth

2. **Prototype Chebyshev spectral analysis in Python**
   - Compute discrete orthogonality coefficients for n = 40, d = 3
   - Compute spectral ratio ρ for each window
   - Compare ρ-based classification with current SE/range approach

3. **Manual ground truth annotation**
   - Annotate 3–5 A/D periods per ticker (AAPL, AVGO, IREN) using Wyckoff criteria
   - Document Phase A through Phase D boundaries

4. **Quantitative comparison**
   - Compute Precision, Recall, F1, Jaccard for each approach
   - Run parameter sensitivity analysis (CV of zone count)
   - Cross-ticker validation (train on one, test on others)

5. **Port winning approach to Rust** if F1 improves by > 10% over current OLS baseline

6. **Document mathematical derivations** in walkthrough.md (state-space equations, coefficient formulas, threshold justification)
