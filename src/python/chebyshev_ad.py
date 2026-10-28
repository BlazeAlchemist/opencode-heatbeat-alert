import numpy as np
import yfinance as yf
import sys


def fetch_data(ticker: str, period: str = "5y"):
    df = yf.download(ticker, period=period, progress=False)
    arr = np.column_stack([
        df["Open"].values,
        df["High"].values,
        df["Low"].values,
        df["Close"].values,
        df["Volume"].values,
    ])
    return arr.astype(np.float64)


def build_chebyshev_design(n: int, degree: int) -> np.ndarray:
    x = 2.0 * np.arange(n) / (n - 1) - 1.0
    X = np.column_stack([
        np.ones(n),
        x,
        2.0 * x**2 - 1.0,
        4.0 * x**3 - 3.0 * x,
    ])
    return X[:, :degree + 1]


def chebyshev_fit(closes: np.ndarray, X: np.ndarray) -> np.ndarray:
    return np.linalg.lstsq(X, closes, rcond=None)[0]


def compute_spectral_ratio(coeffs: np.ndarray, X: np.ndarray) -> float:
    n = X.shape[0]
    T1 = X[:, 1]
    E_trend = abs(coeffs[1]) * np.sqrt(np.sum(T1**2) / n)
    E_variation = 0.0
    for k in range(1, len(coeffs)):
        Tk = X[:, k]
        E_variation += coeffs[k]**2 * np.sum(Tk**2) / n
    E_variation = np.sqrt(max(E_variation, 1e-12))
    return E_trend / E_variation if E_variation > 0 else 0.0


def detect_ad_chebyshev(data: np.ndarray, window: int = 40, step: int = 10,
                        rho_low: float = 0.30, rho_high: float = 0.80,
                        debug: bool = False) -> list:
    n = data.shape[0]
    X = build_chebyshev_design(window, degree=3)

    results = []
    counts = {'total': 0, 'rho_pass': 0, 'vol_pass': 0}

    for end in range(window - 1, n, step):
        start = end - window + 1
        counts['total'] += 1
        closes = data[start:end + 1, 3]
        vols = data[start:end + 1, 4]

        coeffs = chebyshev_fit(closes, X)
        rho = compute_spectral_ratio(coeffs, X)

        if rho < 0.30 or rho > 0.80:
            continue
        counts['rho_pass'] += 1

        if coeffs[1] > 0:
            bias = 'A'
        else:
            bias = 'D'

        window_norm_vol = np.mean(vols / closes)
        if start >= window:
            prior_closes = data[start - window:start, 3]
            prior_vol = np.mean(data[start - window:start, 4] / prior_closes)
            if prior_vol > 0 and window_norm_vol <= prior_vol:
                if debug:
                    print(f"    skip vol: start={start}, w_vol={window_norm_vol:.4f}, p_vol={prior_vol:.4f}")
                continue
        counts['vol_pass'] += 1

        results.append({
            'start': start,
            'end': end,
            'bias': bias,
            'rho': rho,
            'c1': coeffs[1],
            'c2': coeffs[2],
            'c3': coeffs[3],
            'vol_ratio': window_norm_vol / (prior_vol if start >= window and prior_vol > 0 else 1.0),
        })

    if debug:
        rhos_debug = []
        for end in range(window - 1, n, step):
            start = end - window + 1
            c = data[start:end + 1, 3]
            coeffs_d = chebyshev_fit(c, X)
            rhos_debug.append(compute_spectral_ratio(coeffs_d, X))
        rhos_debug = np.array(rhos_debug)
        print(f"  ρ stats: min={rhos_debug.min():.4f}, max={rhos_debug.max():.4f}, "
              f"mean={rhos_debug.mean():.4f}, median={np.median(rhos_debug):.4f}")
        print(f"  ρ 0.30–0.80: {np.sum((rhos_debug >= 0.30) & (rhos_debug <= 0.80))}/{len(rhos_debug)}")
        print(f"  ρ < 0.30: {np.sum(rhos_debug < 0.30)}/{len(rhos_debug)} ({np.sum(rhos_debug < 0.30)/len(rhos_debug)*100:.1f}%)")
        print(f"  ρ > 0.80: {np.sum(rhos_debug > 0.80)}/{len(rhos_debug)} ({np.sum(rhos_debug > 0.80)/len(rhos_debug)*100:.1f}%)")
        print(f"  Filter counts: total={counts['total']}, ρ_pass={counts['rho_pass']}, "
              f"vol_pass={counts['vol_pass']}")
        print(f"  Raw windows before merge: {len(results)}")

    merged = []
    for r in results:
        if merged and r['bias'] == merged[-1]['bias'] and r['start'] <= merged[-1]['end']:
            merged[-1]['end'] = max(merged[-1]['end'], r['end'])
            merged[-1]['rho'] = (merged[-1]['rho'] + r['rho']) / 2
        else:
            merged.append(r)

    if debug:
        print(f"  After merge: {len(merged)}")

    final = [z for z in merged if (z['end'] - z['start'] + 1) >= 20]

    if debug:
        print(f"  After min_duration: {len(final)}")

    changed = True
    while changed:
        changed = False
        new_zones = []
        for z in final:
            if new_zones and z['bias'] == new_zones[-1]['bias'] and new_zones[-1]['end'] >= z['start']:
                new_zones[-1]['end'] = max(new_zones[-1]['end'], z['end'])
                changed = True
            else:
                new_zones.append(z)
        final = new_zones

    if debug:
        print(f"  After post-merge: {len(final)}")

    return final


def report(ticker, zones):
    n_a = sum(1 for z in zones if z['bias'] == 'A')
    n_d = sum(1 for z in zones if z['bias'] == 'D')
    lengths = [z['end'] - z['start'] + 1 for z in zones]
    avg_len = np.mean(lengths) if lengths else 0
    print(f"\n  Chebyshev A/D: {n_a}A / {n_d}D ({len(zones)} total zones)")
    print(f"  Avg zone length: {avg_len:.1f} bars")
    for z in zones:
        print(f"    {z['bias']}({z['start']:4d},{z['end']:4d})  [{z['end'] - z['start'] + 1:3d}b]"
              f"  ρ={z['rho']:.2f}  c₁={z['c1']:.2f}")


def main():
    tickers = sys.argv[1:] if len(sys.argv) > 1 else ["AAPL", "AVGO", "IREN"]

    for ticker in tickers:
        print(f"\n{'='*60}")
        print(f"  {ticker}")
        print(f"{'='*60}")

        data = fetch_data(ticker)
        print(f"  Bars: {data.shape[0]}")

        zones = detect_ad_chebyshev(data, window=40, step=10,
                                    rho_low=0.30, rho_high=0.80, debug=False)
        report(ticker, zones)


if __name__ == "__main__":
    main()
