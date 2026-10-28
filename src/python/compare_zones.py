import numpy as np
import sys
sys.path.insert(0, "src/python")
from kalman_ad import (fetch_data, compute_initial_states, kalman_filter_ad,
                       extract_zones, compute_ols_ad_zones, ZoneBias)
from chebyshev_ad import detect_ad_chebyshev


def to_zone_list(cheb_zones):
    result = []
    for z in cheb_zones:
        bias = ZoneBias.ACCUMULATION if z['bias'] == 'A' else ZoneBias.DISTRIBUTION
        result.append(type('Zone', (), {'start': z['start'], 'end': z['end'], 'bias': bias})())
    return result


def jaccard(z1, z2):
    overlap = max(0, min(z1.end, z2.end) - max(z1.start, z2.start) + 1)
    union = (z1.end - z1.start + 1) + (z2.end - z2.start + 1) - overlap
    return overlap / union if union > 0 else 0.0


def match_rate(zones_a, zones_b):
    matched = 0
    for za in zones_a:
        best_j = 0.0
        for zb in zones_b:
            if za.bias == zb.bias:
                best_j = max(best_j, jaccard(za, zb))
        if best_j >= 0.3:
            matched += 1
    return matched, len(zones_a)


def run_comparison(ticker):
    print(f"\n{'='*70}")
    print(f"  {ticker} — Three-Way Comparison")
    print(f"{'='*70}")

    data = fetch_data(ticker)
    n = data.shape[0]
    print(f"  Bars: {n}")
    print()

    _, v_rel = compute_initial_states(data)
    bias, vr_smooth = kalman_filter_ad(data, v_rel)
    kf_zones = extract_zones(bias, threshold=0.10, min_bars=20,
                             merge_gap=10, vr=vr_smooth, vol_min=0.80)
    ols_zones = compute_ols_ad_zones(data)
    cheb_raw = detect_ad_chebyshev(data, window=40, step=10,
                                   rho_low=0.30, rho_high=0.80)
    cheb_zones = to_zone_list(cheb_raw)

    kf_a = sum(1 for z in kf_zones if z.bias == ZoneBias.ACCUMULATION)
    kf_d = sum(1 for z in kf_zones if z.bias == ZoneBias.DISTRIBUTION)
    ols_a = sum(1 for z in ols_zones if z.bias == ZoneBias.ACCUMULATION)
    ols_d = sum(1 for z in ols_zones if z.bias == ZoneBias.DISTRIBUTION)
    ch_a = sum(1 for z in cheb_zones if z.bias == ZoneBias.ACCUMULATION)
    ch_d = sum(1 for z in cheb_zones if z.bias == ZoneBias.DISTRIBUTION)

    print(f"  {'Method':<12} {'A':>4} {'D':>4} {'Total':>6} {'AvgLen':>8}")
    print(f"  {'-'*34}")
    print(f"  {'OLS':<12} {ols_a:>4d} {ols_d:>4d} {len(ols_zones):>6d} {np.mean([z.end-z.start+1 for z in ols_zones]):>7.1f}")
    print(f"  {'Kalman':<12} {kf_a:>4d} {kf_d:>4d} {len(kf_zones):>6d} {np.mean([z.end-z.start+1 for z in kf_zones]):>7.1f}")
    print(f"  {'Chebyshev':<12} {ch_a:>4d} {ch_d:>4d} {len(cheb_zones):>6d} {np.mean([z.end-z.start+1 for z in cheb_zones]):>7.1f}")

    def overlap(a, b, name):
        m_a, t_a = match_rate(a, b)
        m_b, t_b = match_rate(b, a)
        print(f"  {name}: {m_a}/{t_a} of Method1 ↔ {m_b}/{t_b} of Method2")

    print()
    overlap(kf_zones, ols_zones, "KF↔OLS  ")
    overlap(cheb_zones, kf_zones, "Chb↔KF  ")
    overlap(cheb_zones, ols_zones, "Chb↔OLS ")

    print(f"\n  Bias distribution (Kalman):")
    print(f"    A: {np.sum(bias > 0.10):5d} bars ({np.sum(bias > 0.10)/n*100:.1f}%)")
    print(f"    D: {np.sum(bias < -0.10):5d} bars ({np.sum(bias < -0.10)/n*100:.1f}%)")
    print(f"    N: {np.sum(np.abs(bias) <= 0.10):5d} bars ({np.sum(np.abs(bias) <= 0.10)/n*100:.1f}%)")


if __name__ == "__main__":
    tickers = sys.argv[1:] if len(sys.argv) > 1 else ["AAPL", "AVGO", "IREN"]
    for t in tickers:
        run_comparison(t)
