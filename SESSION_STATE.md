# Resume checkpoint

Saved: 2026-10-28 (local timezone +08:00).

## User intent and stopping point

- The advanced A/D detection research is **PAUSED** at the user's request. Do not resume experiments, change algorithms, or port prototypes without a new request.
- Latest request: "push to https://github.com/BlazeAlchemist/opencode-heatbeat-alert"
- Git initialized on branch `chore/save-session-state`, with `origin` set to `https://github.com/BlazeAlchemist/opencode-heatbeat-alert.git`. Remote inspection returned no refs. Initial snapshot commit: `b8d3d56` (`chore: save chart implementation and paused research state`).
- **Push blocked by authentication**: `git push --set-upstream origin chore/save-session-state` failed with `could not read Username for 'https://github.com': terminal prompts disabled`. No successful publication has been confirmed. No credentials were available in this session; external home-directory credential stores were not inspected.
- Commits use the explicit agent identity `OpenCode <opencode@localhost>`; no user identity was guessed and no global Git settings were changed. This checkpoint/status update is saved in a follow-up local commit.
- `.gitignore` excludes virtual environments, build output, scratch data, caches, credential files, machine-local `opencode.json`, and the local `session.txt` pointer. Sources, docs, role definitions, logs, and saved chart images are retained. A heuristic secret scan of candidate text files returned no findings; this is not a guarantee of complete secret detection.

## Read first

1. `RULES.md` and `users-prompts-create-team.md` — workspace, logging, review, and testing requirements.
2. This file — current status and known limitations.
3. `BACKLOG_AD_RESEARCH.md` — paused research summary and historical comparisons.
4. `advance_plan.md` — research proposals, not validated mathematical specifications.
5. `logs/session_log.md` — historical interactions; older success claims must not override the caveats below.

Stay within this workspace, including for caches and temporary files. Do not access external networks without authorization. Git publication authorization does not authorize new Yahoo downloads or package installation.

## Saved implementation and artifacts

- Rust CLI: `src/rust/src/main.rs`; manifest/lockfile: `src/rust/Cargo.toml`, `src/rust/Cargo.lock`; runtime font configuration: `src/rust/.cargo/config.toml`.
- Existing Rust PNGs: `src/rust/results/{AAPL,AVGO,IREN,NOK}.png`.
- Python prototypes: `src/python/kalman_ad.py`, `src/python/chebyshev_ad.py`.
- Comparison scripts: `src/python/compare_zones.py`, `src/python/run_summary.py`.
- Python dependency declarations: `src/python/requirements.txt`; local environment: `venv/` (do not commit).
- Saved comparison PNGs: `src/python/results/AAPL_kalman_vs_ols.png`, `src/python/results/AVGO_kalman_vs_ols.png`, `src/python/results/IREN_kalman_vs_ols.png`. No Chebyshev comparison PNG is saved.
- `implementation_plan.md` and `walkthrough.md` document earlier Rust work. Some introductory parameters are stale (e.g. gap-tolerant merging); verify against source and later change notes before relying on them.

## Rust baseline (historical implementation summary)

Daily Yahoo OHLCV, candlesticks, SMA50/100/150/200, volume and volume-spike markers. Candle bodies use three one-pixel columns centered on a one-pixel wick on an f64 x-axis; output is 6000×2160.

A/D: 40-bar OLS windows, step 10, sum(t)=780, sum(t²)=20540, residual degrees of freedom 38, SE/range <0.25, average(volume/close) versus the preceding 40 bars. Direction uses sum(close)/sum(open)-1. Same-bias overlapping zones merge; opposite-bias overlaps are trimmed and zones shorter than 20 bars dropped, followed by same-bias post-merging. Prior sessions reported successful review/build/lint; these checks were **not rerun** while saving this checkpoint.

## Prototype status — exploratory, not accepted

Historical counts and directional overlap percentages are retained in the backlog for reference, **not accuracy estimates**. There are no ground-truth labels or established precision/recall/F1 results. No winning method is established. Python OLS is not a verified equivalent of Rust OLS. No Python test/lint/review/beta signoff is established.

Confirmed by source inspection during checkpointing; left unchanged because research is paused:

- `kalman_ad.py` reads high/low columns backwards in both Kalman range calculation and Python OLS. Loader order is `[open, high, low, close, volume]`, but these functions use column 2 for high and 1 for low.
- Kalman transitions shrink uncentered position and relative volume toward zero; this is not mean-reversion toward position 0.5 / relative volume 1.0. Bias is derived from smoothed range position, not validated institutional accumulation/distribution.
- Duplicate unreachable EMA blocks remain after `kalman_filter_ad` returns.
- Kalman summary uses volume threshold 0.80, while PNG generation uses 0.95. Saved images therefore must not be assumed to match summary results. Label placement also needs review.
- Python OLS and Chebyshev lack the Rust opposite-bias overlap trimming. Zone boundary/merge semantics need parity tests.
- Chebyshev `rho_low` / `rho_high` arguments are ignored in favor of hardcoded 0.30/0.80. Its coefficient-based ratio is a heuristic: the basis is not orthogonal on the equally spaced sample grid, so omitted cross terms prevent interpreting it as exact variation energy.
- Scripts repeatedly fetch live data, without a persisted source-data snapshot. Old results are not guaranteed reproducible. Do not rerun merely to restore the session; request network authorization and enforce the project's request spacing first.

`advance_plan.md` also needs mathematical re-review before implementation: the proposed 3D Kalman bias is unobservable under its stated observation/transition matrices; discrete Chebyshev orthogonality assumptions and PID damping-to-A/D claims are not established; forward response windows introduce look-ahead unless detection time is tracked.

## When research is explicitly resumed

1. Correct/test data-column indexing and Rust/Python baseline parity before interpreting comparisons.
2. Align chart/table settings; add deterministic fixture data, tests, and causal detection-time semantics.
3. Re-review model assumptions with the Mathematician/TA Analyst; obtain independent code review and beta validation as required.
4. Annotate ground truth, define evaluation units and one-to-one matching, then measure held-out performance. Tune parameters without leakage.
5. Consider an ensemble or Rust port only after evidence supports it.

## Suggested next-session prompt

"Read RULES.md, SESSION_STATE.md, and BACKLOG_AD_RESEARCH.md. Keep A/D research paused. Check Git status and the latest session log for publication status before doing further work."

## Finish publication

From this project directory, authenticate using your normal GitHub workflow, then run:

```sh
git push -u origin chore/save-session-state
```

If GitHub CLI is already installed, an interactive terminal can use `gh auth login` followed by `gh auth setup-git` before pushing. Do not paste credentials into chat or embed them in the remote URL. No force push is authorized or needed.
