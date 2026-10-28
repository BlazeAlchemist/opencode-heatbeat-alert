import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from dataclasses import dataclass
from enum import Enum
import sys


class ZoneBias(Enum):
    ACCUMULATION = 1
    DISTRIBUTION = -1


@dataclass
class AdZone:
    start: int
    end: int
    bias: ZoneBias


def fetch_data(ticker: str, period: str = "5y") -> np.ndarray:
    df = yf.download(ticker, period=period, progress=False)
    arr = np.column_stack([
        df["Open"].values,
        df["High"].values,
        df["Low"].values,
        df["Close"].values,
        df["Volume"].values,
    ])
    return arr.astype(np.float64)


def compute_initial_states(data: np.ndarray, vol_sma: int = 50):
    closes = data[:, 3]
    volumes = data[:, 4]
    n = len(data)

    delta_p = np.zeros(n)
    v_rel = np.ones(n)
    delta_p[1:] = np.diff(closes)

    vol_sma_vals = np.full(n, np.nan)
    cum_sum = np.cumsum(volumes)
    for i in range(vol_sma - 1, n):
        vol_sma_vals[i] = (cum_sum[i] - cum_sum[i - vol_sma]) / vol_sma if i >= vol_sma else cum_sum[i] / (i + 1)

    for i in range(n):
        if vol_sma_vals[i] > 0 and not np.isnan(vol_sma_vals[i]):
            v_rel[i] = volumes[i] / vol_sma_vals[i]
    v_rel[:vol_sma] = 1.0

    return delta_p, v_rel


def kalman_filter_ad(data: np.ndarray, v_rel: np.ndarray,
                     phi: float = 0.95, psi: float = 0.85,
                     q_diag: tuple = (0.005, 0.005),
                     r_diag: tuple = (0.02, 0.01)) -> tuple:
    n = data.shape[0]

    highs = data[:, 2]
    lows = data[:, 1]
    closes = data[:, 3]

    range_pos = np.full(n, 0.5)
    for i in range(40, n):
        r_high = np.max(highs[i-39:i+1])
        r_low = np.min(lows[i-39:i+1])
        rng = r_high - r_low
        if rng > 0:
            range_pos[i] = (closes[i] - r_low) / rng

    F = np.array([
        [phi, 0.0],
        [0.0, psi],
    ])
    H = np.eye(2)
    Q = np.diag(q_diag)
    R = np.diag(r_diag)
    I2 = np.eye(2)

    x_hat = np.array([0.5, 1.0])
    P = np.eye(2) * 5.0

    bias_raw = np.zeros(n)
    vr_smooth = np.ones(n)

    for t in range(n):
        y_t = np.array([range_pos[t], v_rel[t]])

        x_pred = F @ x_hat
        P_pred = F @ P @ F.T + Q

        innovation = y_t - H @ x_pred
        S = H @ P_pred @ H.T + R
        K = P_pred @ H.T @ np.linalg.inv(S)

        x_hat = x_pred + K @ innovation
        P = (I2 - K @ H) @ P_pred

        pos = x_hat[0]
        vr_smooth[t] = x_hat[1]

        bias_raw[t] = (0.5 - pos) * 2.0

    gamma_ema = 0.94
    bias_smooth = np.zeros(n)
    bias_smooth[0] = 0.0
    for t in range(1, n):
        bias_smooth[t] = gamma_ema * bias_smooth[t-1] + (1 - gamma_ema) * bias_raw[t]

    return bias_smooth, vr_smooth

    gamma_ema = 0.94
    bias_smooth = np.zeros(n)
    bias_smooth[0] = 0.0
    for t in range(1, n):
        bias_smooth[t] = gamma_ema * bias_smooth[t-1] + (1 - gamma_ema) * bias_raw[t]

    return bias_smooth

    gamma_ema = 0.94
    bias_smooth = np.zeros(n)
    bias_smooth[0] = 0.0
    for t in range(1, n):
        bias_smooth[t] = gamma_ema * bias_smooth[t-1] + (1 - gamma_ema) * bias_raw[t]

    return bias_smooth


def extract_zones(bias: np.ndarray, threshold: float = 0.1,
                  min_bars: int = 20, merge_gap: int = 10,
                  vr: np.ndarray | None = None,
                  vol_min: float = 0.0) -> list[AdZone]:
    n = len(bias)
    active = np.zeros(n, dtype=int)

    for i in range(n):
        if bias[i] > threshold:
            active[i] = 1
        elif bias[i] < -threshold:
            active[i] = -1
        else:
            active[i] = 0

    raw_zones = []
    i = 0
    while i < n:
        if active[i] != 0:
            bias_val = active[i]
            j = i
            while j < n and active[j] == bias_val:
                j += 1
            raw_zones.append(AdZone(i, j - 1, ZoneBias.ACCUMULATION if bias_val == 1 else ZoneBias.DISTRIBUTION))
            i = j
        else:
            i += 1

    raw_zones = [z for z in raw_zones if (z.end - z.start + 1) >= min_bars]

    if vr is not None and vol_min > 0:
        raw_zones = [
            z for z in raw_zones
            if np.mean(vr[z.start:z.end + 1]) >= vol_min
        ]

    merged = []
    for z in raw_zones:
        if merged and z.bias == merged[-1].bias and z.start <= merged[-1].end + merge_gap:
            merged[-1].end = max(merged[-1].end, z.end)
        else:
            merged.append(z)

    return merged


def compute_ols_ad_zones(data: np.ndarray, window: int = 40, step: int = 10,
                         se_range_thresh: float = 0.25) -> list[AdZone]:
    n = data.shape[0]
    sum_t = window * (window - 1) / 2.0
    sum_t2 = sum(j * j for j in range(window))
    denom = window * sum_t2 - sum_t * sum_t

    raw_windows = []

    for end in range(window - 1, n, step):
        start = end - window + 1
        window_data = data[start:end + 1]
        closes = window_data[:, 3]
        highs = window_data[:, 2]
        lows = window_data[:, 1]

        t = np.arange(window, dtype=np.float64)
        sum_close = closes.sum()
        sum_t_close = np.dot(t, closes)
        slope = (window * sum_t_close - sum_t * sum_close) / denom
        intercept = (sum_close - slope * sum_t) / window
        residuals = closes - (slope * t + intercept)
        se = np.sqrt(np.sum(residuals ** 2) / (window - 2))

        price_range = highs.max() - lows.min()
        if price_range == 0:
            continue
        se_ratio = se / price_range

        if se_ratio >= se_range_thresh:
            continue

        opens = window_data[:, 0]
        rel_close = closes.sum() / opens.sum() - 1.0

        vol = window_data[:, 4]
        window_norm_vol = np.mean(vol / closes)
        prior_vol = 0.0
        if start >= window:
            prior_data = data[start - window:start]
            prior_closes = prior_data[:, 3]
            prior_vol = np.mean(prior_data[:, 4] / prior_closes)
        if prior_vol > 0 and window_norm_vol <= prior_vol:
            continue

        bias = ZoneBias.ACCUMULATION if rel_close > 0 else ZoneBias.DISTRIBUTION
        raw_windows.append(AdZone(start, end, bias))

    merged = []
    for z in raw_windows:
        if merged and z.bias == merged[-1].bias and z.start <= merged[-1].end:
            merged[-1].end = max(merged[-1].end, z.end)
        else:
            merged.append(z)

    final = []
    for z in merged:
        if (z.end - z.start + 1) >= 20:
            final.append(z)

    changed = True
    while changed:
        changed = False
        new_zones = []
        for z in final:
            if new_zones and z.bias == new_zones[-1].bias and new_zones[-1].end >= z.start:
                new_zones[-1].end = max(new_zones[-1].end, z.end)
                changed = True
            else:
                new_zones.append(z)
        final = new_zones

    return final


def plot_comparison(ticker: str, data: np.ndarray, ols_zones: list[AdZone],
                    kalman_zones: list[AdZone], bias: np.ndarray):
    closes = data[:, 3]
    n = len(closes)

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(18, 10),
                                         gridspec_kw={'height_ratios': [3, 1, 1]})
    fig.suptitle(f"{ticker} — Kalman Filter A/D vs OLS A/D", fontsize=14, fontweight='bold')

    for ax in (ax1, ax2):
        for z in kalman_zones:
            color = 'green' if z.bias == ZoneBias.ACCUMULATION else 'red'
            ax.axvspan(z.start, z.end, alpha=0.15, color=color)
            mid = (z.start + z.end) / 2
            label = 'A' if z.bias == ZoneBias.ACCUMULATION else 'D'
            ax.text(mid, ax.get_ylim()[1] * 0.95 if ax.get_ylim() else 0,
                    label, fontsize=10, fontweight='bold',
                    ha='center', va='top', color=color)

    for z in ols_zones:
        color = 'green' if z.bias == ZoneBias.ACCUMULATION else 'red'
        ax1.axvspan(z.start, z.end, alpha=0.08, color='blue' if z.bias == ZoneBias.ACCUMULATION else 'orange')
        mid = (z.start + z.end) / 2
        label = 'A*' if z.bias == ZoneBias.ACCUMULATION else 'D*'
        ax1.text(mid, ax1.get_ylim()[0] + ax1.get_ylim()[1] * 0.05,
                label, fontsize=8, fontweight='bold',
                ha='center', va='bottom', color='blue' if z.bias == ZoneBias.ACCUMULATION else 'orange')

    ax1.plot(closes, color='black', linewidth=0.8)
    ax1.set_ylabel('Price')
    ax1.set_title('Price with Kalman A/D (green=Acc, red=Dis) and OLS A/D (blue=Acc*, orange=Dis*)')
    ax1.legend(handles=[
        mpatches.Patch(color='green', alpha=0.3),
        mpatches.Patch(color='red', alpha=0.3),
        mpatches.Patch(color='blue', alpha=0.3),
        mpatches.Patch(color='orange', alpha=0.3),
    ], labels=['Kalman A', 'Kalman D', 'OLS A*', 'OLS D*'], loc='upper left')

    ax2.plot(closes, color='black', linewidth=0.8)
    ax2.set_ylabel('Price')
    ax2.set_title('Price with Kalman A/D zones only')

    ax3.plot(bias, color='purple', linewidth=0.6)
    ax3.axhline(y=0.1, color='green', linestyle='--', alpha=0.5, label='Acc threshold')
    ax3.axhline(y=-0.1, color='red', linestyle='--', alpha=0.5, label='Dis threshold')
    ax3.axhline(y=0, color='gray', linestyle='-', alpha=0.3)
    ax3.fill_between(range(n), 0, bias, where=bias > 0,
                      color='green', alpha=0.2)
    ax3.fill_between(range(n), 0, bias, where=bias < 0,
                      color='red', alpha=0.2)
    ax3.set_ylabel('Latent Bias b̂(t)')
    ax3.set_xlabel('Bar Index')
    ax3.set_title('Kalman Filter Latent Bias Estimate')
    ax3.legend(loc='upper right')

    plt.tight_layout()
    plt.savefig(f"src/python/results/{ticker}_kalman_vs_ols.png", dpi=150)
    print(f"  Chart saved to src/python/results/{ticker}_kalman_vs_ols.png")


def report_zone_stats(ticker: str, label: str, zones: list[AdZone]):
    n_acc = sum(1 for z in zones if z.bias == ZoneBias.ACCUMULATION)
    n_dis = sum(1 for z in zones if z.bias == ZoneBias.DISTRIBUTION)
    lengths = [z.end - z.start + 1 for z in zones]
    avg_len = np.mean(lengths) if lengths else 0
    print(f"\n  {label}: {n_acc}A / {n_dis}D ({len(zones)} total zones)")
    print(f"  Avg zone length: {avg_len:.1f} bars")
    for z in zones:
        label_c = 'A' if z.bias == ZoneBias.ACCUMULATION else 'D'
        print(f"    {label_c}({z.start:4d},{z.end:4d})  [{z.end - z.start + 1:3d} bars]")


def main():
    tickers = sys.argv[1:] if len(sys.argv) > 1 else ["AAPL", "AVGO", "IREN"]
    gen_charts = "--chart" in tickers
    tickers = [t for t in tickers if t != "--chart"]

    for ticker in tickers:
        print(f"\n{'='*60}")
        print(f"  {ticker}")
        print(f"{'='*60}")

        data = fetch_data(ticker)
        n = data.shape[0]
        print(f"  Bars: {n}")

        _, v_rel = compute_initial_states(data)

        bias, vr_smooth = kalman_filter_ad(data, v_rel)
        print(f"  Bias stats: min={bias.min():.6f}, max={bias.max():.6f}, "
              f"mean={bias.mean():.6f}, std={bias.std():.6f}")
        print(f"  vr_smooth stats: min={vr_smooth.min():.3f}, max={vr_smooth.max():.3f}, "
              f"mean={vr_smooth.mean():.3f}")

        for thresh in [0.05, 0.10, 0.15, 0.20]:
            kalman_zones = extract_zones(bias, threshold=thresh, min_bars=20,
                                         merge_gap=10, vr=vr_smooth, vol_min=0.80)
            n_a = sum(1 for z in kalman_zones if z.bias == ZoneBias.ACCUMULATION)
            n_d = sum(1 for z in kalman_zones if z.bias == ZoneBias.DISTRIBUTION)
            print(f"  threshold={thresh}: {n_a}A / {n_d}D ({len(kalman_zones)} zones)")

        ols_zones = compute_ols_ad_zones(data)
        report_zone_stats(ticker, "OLS A/D", ols_zones)

        if gen_charts:
            calib_thresh = 0.10
            kalman_zones = extract_zones(bias, threshold=calib_thresh, min_bars=20,
                                         merge_gap=10, vr=vr_smooth, vol_min=0.95)
            plot_comparison(ticker, data, ols_zones, kalman_zones, bias)

        plt.close('all')


if __name__ == "__main__":
    main()
