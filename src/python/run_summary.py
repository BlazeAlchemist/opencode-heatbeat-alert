#!/usr/bin/env python3
"""Run side-by-side comparison and produce formatted summary."""
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


def match_rate(zone_list_a, zone_list_b, threshold=0.3):
    matched = 0
    for za in zone_list_a:
        best_j = max((jaccard(za, zb) for zb in zone_list_b if za.bias == zb.bias), default=0.0)
        if best_j >= threshold:
            matched += 1
    return matched / len(zone_list_a) if zone_list_a else 0.0


def run_all():
    tickers = ["AAPL", "AVGO", "IREN"]

    headers = ["Ticker", "Method", "A", "D", "Total", "AvgLen", "Match%"]
    col_w = [8, 10, 5, 5, 6, 8, 8]
    sep = "  ".join(h.center(w) for h, w in zip(headers, col_w))
    print(sep)
    print("-" * len(sep))

    for ticker in tickers:
        data = fetch_data(ticker)
        n = data.shape[0]

        _, v_rel = compute_initial_states(data)
        bias, vr_smooth = kalman_filter_ad(data, v_rel)

        kf_zones = extract_zones(bias, threshold=0.10, min_bars=20,
                                 merge_gap=10, vr=vr_smooth, vol_min=0.80)
        ols_zones = compute_ols_ad_zones(data)
        cheb_raw = detect_ad_chebyshev(data, window=40, step=10,
                                       rho_low=0.30, rho_high=0.80)
        cheb_zones = to_zone_list(cheb_raw)

        def avg_len(zones):
            return np.mean([z.end - z.start + 1 for z in zones]) if zones else 0.0

        def fmt(tkr, name, zones, match_ref=None):
            a = sum(1 for z in zones if z.bias == ZoneBias.ACCUMULATION)
            d = sum(1 for z in zones if z.bias == ZoneBias.DISTRIBUTION)
            al = avg_len(zones)
            mr = match_rate(zones, match_ref) * 100 if match_ref else 0.0
            row = [tkr, name, str(a), str(d), str(len(zones)), f"{al:.0f}", f"{mr:.0f}%"]
            return "  ".join(cell.rjust(w) for cell, w in zip(row, col_w))

        print(fmt(ticker, "OLS", ols_zones))
        print(fmt(ticker, "Kalman", kf_zones, ols_zones))
        print(fmt(ticker, "Chebyshev", cheb_zones, ols_zones))
        print()


if __name__ == "__main__":
    run_all()
