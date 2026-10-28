use anyhow::{anyhow, Result};
use chrono::{NaiveDate, TimeZone, Utc};
use clap::Parser;
use plotters::prelude::*;
use reqwest::blocking::Client;
use serde::Deserialize;

#[derive(Parser)]
#[command(name = "stock-chart", about = "Fetches stock data from Yahoo Finance and plots a daily candlestick chart with SMAs")]
struct Args {
    ticker: String,
}

#[derive(Debug, Deserialize)]
struct YahooResponse {
    chart: ChartData,
}

#[derive(Debug, Deserialize)]
struct ChartData {
    result: Option<Vec<ChartResult>>,
    error: Option<serde_json::Value>,
}

#[derive(Debug, Deserialize)]
struct ChartResult {
    timestamp: Vec<i64>,
    indicators: Indicators,
}

#[derive(Debug, Deserialize)]
struct Indicators {
    quote: Vec<Quote>,
}

#[derive(Debug, Deserialize)]
struct Quote {
    open: Vec<Option<f64>>,
    high: Vec<Option<f64>>,
    low: Vec<Option<f64>>,
    close: Vec<Option<f64>>,
    volume: Vec<Option<u64>>,
}

#[derive(Debug, Clone)]
struct Candle {
    date: NaiveDate,
    open: f64,
    high: f64,
    low: f64,
    close: f64,
    volume: u64,
}

#[derive(Debug, Clone, Copy, PartialEq)]
enum ZoneBias {
    Accumulation,
    Distribution,
}

#[derive(Debug, Clone)]
struct AdZone {
    start: usize,
    end: usize,
    bias: ZoneBias,
    #[allow(dead_code)]
    ongoing: bool,
}

fn detect_ad_zones(candles: &[Candle]) -> Vec<AdZone> {
    let n = candles.len();
    if n < 40 {
        return Vec::new();
    }

    let mut raw_zones = Vec::new();
    let threshold = 0.25;

    for end in (39..n).step_by(10) {
        let start = end - 39;

        let prices: Vec<f64> = (start..=end).map(|i| candles[i].close).collect();
        let sum_p: f64 = prices.iter().sum();
        let sum_t2 = 20540.0f64;
        let sum_t = 780.0f64;
        let n_f = 40.0f64;

        let sum_tp: f64 = prices.iter().enumerate().map(|(j, &p)| j as f64 * p).sum();

        let slope_num = n_f * sum_tp - sum_t * sum_p;
        let slope_den = n_f * sum_t2 - sum_t * sum_t;
        if slope_den == 0.0 {
            continue;
        }
        let a = slope_num / slope_den;
        let b = (sum_p - a * sum_t) / n_f;

        let residuals: f64 = prices.iter().enumerate()
            .map(|(j, &p)| {
                let expected = a * j as f64 + b;
                (p - expected).powi(2)
            })
            .sum();
        let se = (residuals / 38.0).sqrt();

        let window_highs: f64 = (start..=end).map(|i| candles[i].high).fold(f64::NEG_INFINITY, f64::max);
        let window_lows: f64 = (start..=end).map(|i| candles[i].low).fold(f64::INFINITY, f64::min);
        let range = window_highs - window_lows;

        if range <= 0.0 || se / range >= threshold {
            continue;
        }

        let window_vol_norm: f64 = (start..=end)
            .map(|i| candles[i].volume as f64 / candles[i].close)
            .sum::<f64>() / n_f;

        let prior_start = start.saturating_sub(40);
        let prior_end = start;
        let prior_vol: f64 = (prior_start..prior_end)
            .map(|i| candles[i].volume as f64 / candles[i].close)
            .sum::<f64>() / (prior_end - prior_start).max(1) as f64;
        if window_vol_norm <= prior_vol {
            continue;
        }

        let opens_in_window: f64 = (start..=end).map(|i| candles[i].open).sum();
        let closes_in_window: f64 = (start..=end).map(|i| candles[i].close).sum();
        let rel_close = closes_in_window / opens_in_window - 1.0;

        let bias = if rel_close > 0.0 { ZoneBias::Accumulation } else { ZoneBias::Distribution };

        let ongoing = end == n - 1 || end + 20 >= n - 1;
        raw_zones.push(AdZone { start, end, bias, ongoing });
    }

    // Merge same-bias zones (only if they overlap, no merge across gaps)
    let mut merged: Vec<AdZone> = Vec::new();
    for raw in &raw_zones {
        let mergeable = merged.last_mut()
            .map(|last| last.bias == raw.bias && raw.start <= last.end);
        if mergeable == Some(true) {
            merged.last_mut().unwrap().end = raw.end;
            merged.last_mut().unwrap().ongoing = raw.ongoing;
        } else {
            merged.push(raw.clone());
        }
    }

    // Resolve opposite-bias overlap by trimming later zone, minimum 20 bars
    let mut zones: Vec<AdZone> = Vec::new();
    for zone in merged {
        if let Some(last) = zones.last() {
            if last.bias != zone.bias && zone.start < last.end {
                let trimmed_start = last.end;
                if zone.end.saturating_sub(trimmed_start) >= 20 {
                    zones.push(AdZone { start: trimmed_start, ..zone });
                }
                continue;
            }
        }
        zones.push(zone);
    }

    // Post-merge adjacent same-bias zones that were separated by discarded intermediate zones
    let mut final_zones: Vec<AdZone> = Vec::new();
    for zone in zones {
        if let Some(last) = final_zones.last_mut() {
            if last.bias == zone.bias && last.end >= zone.start {
                last.end = last.end.max(zone.end);
                continue;
            }
        }
        final_zones.push(zone);
    }

    final_zones
}

fn fetch_data(ticker: &str) -> Result<Vec<Candle>> {
    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        .build()?;

    let now = Utc::now();
    let start = (now - chrono::Duration::days(365 * 5)).timestamp();
    let end = now.timestamp();

    let url = format!(
        "https://query1.finance.yahoo.com/v8/finance/chart/{}?period1={}&period2={}&interval=1d",
        ticker, start, end
    );

    let resp = client.get(&url).send()?;
    let yahoo: YahooResponse = resp.json()?;

    if let Some(e) = &yahoo.chart.error {
        return Err(anyhow!("Yahoo Finance API error: {:?}", e));
    }

    let result = yahoo.chart.result.and_then(|mut r| r.pop())
        .ok_or_else(|| anyhow!("No chart result for {}", ticker))?;

    let quote = result.indicators.quote.into_iter().next()
        .ok_or_else(|| anyhow!("No quote data"))?;

    let candles: Vec<Candle> = result.timestamp.iter()
        .zip(quote.open.iter())
        .zip(quote.high.iter())
        .zip(quote.low.iter())
        .zip(quote.close.iter())
        .zip(quote.volume.iter())
        .filter_map(|(((((ts, o), h), l), c), v)| {
            let ts = *ts;
            let o = (*o)?;
            let h = (*h)?;
            let l = (*l)?;
            let c = (*c)?;
            let v = (*v)?;
            let date = Utc.timestamp_opt(ts, 0).single()?.date_naive();
            Some(Candle { date, open: o, high: h, low: l, close: c, volume: v })
        })
        .collect();

    if candles.is_empty() {
        Err(anyhow!("No candle data parsed for {}", ticker))
    } else {
        Ok(candles)
    }
}

fn calculate_sma(data: &[f64], period: usize) -> Vec<Option<f64>> {
    if data.len() < period {
        return vec![None; data.len()];
    }
    let mut sma = vec![None; data.len()];
    let mut sum: f64 = data[..period].iter().sum();
    sma[period - 1] = Some(sum / period as f64);
    for i in period..data.len() {
        sum += data[i] - data[i - period];
        sma[i] = Some(sum / period as f64);
    }
    sma
}

fn plot_chart(candles: &[Candle], ticker: &str) -> Result<()> {
    std::fs::create_dir_all("results")?;
    let path = format!("results/{}.png", ticker);

    let n = candles.len();
    if n == 0 {
        return Err(anyhow!("No candles to plot"));
    }

    let opens: Vec<f64> = candles.iter().map(|c| c.open).collect();
    let highs: Vec<f64> = candles.iter().map(|c| c.high).collect();
    let lows: Vec<f64> = candles.iter().map(|c| c.low).collect();
    let closes: Vec<f64> = candles.iter().map(|c| c.close).collect();
    let volumes: Vec<u64> = candles.iter().map(|c| c.volume).collect();

    let sma50 = calculate_sma(&closes, 50);
    let sma100 = calculate_sma(&closes, 100);
    let sma150 = calculate_sma(&closes, 150);
    let sma200 = calculate_sma(&closes, 200);

    let min_price = lows.iter().cloned().fold(f64::INFINITY, f64::min) * 0.98;
    let max_price = highs.iter().cloned().fold(f64::NEG_INFINITY, f64::max) * 1.02;
    let max_volume = *volumes.iter().max().unwrap_or(&1) as f64 * 1.05;

    let vol_sma = calculate_sma(
        &volumes.iter().map(|&v| v as f64).collect::<Vec<_>>(),
        20,
    );

    let mut buy_signals: Vec<usize> = Vec::new();
    let mut sell_signals: Vec<usize> = Vec::new();
    for i in 0..n {
        if let Some(baseline) = vol_sma[i] {
            let v = volumes[i] as f64;
            if v > baseline * 1.8 {
                if closes[i] >= opens[i] {
                    buy_signals.push(i);
                } else {
                    sell_signals.push(i);
                }
            }
        }
    }

    let breakouts_up: Vec<usize> = Vec::new();
    let breakouts_down: Vec<usize> = Vec::new();

    let ad_zones = detect_ad_zones(candles);
    if ad_zones.is_empty() {
        println!("  A/D zones: none detected (threshold may be too strict or volume filter too high)");
    } else {
        let acc = ad_zones.iter().filter(|z| matches!(z.bias, ZoneBias::Accumulation)).count();
        let dist = ad_zones.iter().filter(|z| matches!(z.bias, ZoneBias::Distribution)).count();
        println!("  A/D zones: {} accumulation, {} distribution",
            acc, dist);
        for (i, zone) in ad_zones.iter().enumerate() {
            let bias_str = if matches!(zone.bias, ZoneBias::Accumulation) { "A" } else { "D" };
            println!("    Zone {}: {} [{} bars] ({} to {})",
                i + 1, bias_str,
                zone.end - zone.start + 1,
                candles[zone.start].date,
                candles[zone.end.min(candles.len()-1)].date);
        }
    }

    let root = BitMapBackend::new(&path, (6000, 2160)).into_drawing_area();
    root.fill(&WHITE)?;

    let nf = n as f64;
    let x_range = 0.0..nf;

    let (top_area, bottom_area) = root.split_vertically(1720);

    // ---- Candlestick chart ----
    let mut chart = ChartBuilder::on(&top_area)
        .caption(format!("{} - Daily Candlestick", ticker), ("sans-serif", 72, &BLACK))
        .margin(40)
        .x_label_area_size(0)
        .y_label_area_size(120)
        .build_cartesian_2d(x_range.clone(), min_price..max_price)?;

    let (chart_w, chart_h) = {
        let dim = chart.plotting_area().dim_in_pixel();
        (dim.0 as f64, dim.1 as f64)
    };

    chart.configure_mesh()
        .x_labels(12)
        .x_label_style(("sans-serif", 0))
        .y_labels(10)
        .y_label_formatter(&|y| format!("${:.0}", y))
        .draw()?;

    // ---- A/D zone rectangles (background layer) ----
    for zone in &ad_zones {
        let x0 = zone.start as f64 - 0.5;
        let x1 = zone.end as f64 + 0.5;
        let color = match zone.bias {
            ZoneBias::Accumulation => RGBAColor(0, 180, 70, 0.15),
            ZoneBias::Distribution => RGBAColor(200, 0, 40, 0.15),
        };
        chart.draw_series(std::iter::once(
            Rectangle::new([(x0, min_price), (x1, max_price)], color.filled()),
        ))?;

        let label = match zone.bias {
            ZoneBias::Accumulation => "A",
            ZoneBias::Distribution => "D",
        };
        let mid = (zone.start + zone.end) as f64 / 2.0;
        let label_x = 160.0 + (mid / nf) * chart_w;
        let label_color = match zone.bias {
            ZoneBias::Accumulation => RGBAColor(0, 120, 50, 0.9),
            ZoneBias::Distribution => RGBAColor(180, 0, 25, 0.9),
        };
        let _ = top_area.draw_text(
            label,
            &("sans-serif", 32, FontStyle::Bold).into_font().color(&label_color),
            (label_x as i32, 130),
        );
    }

    // ---- Candlestick chart ----
    chart.draw_series(
        candles.iter().enumerate().map(|(i, c)| {
            let fi = i as f64;
            let color = if c.close >= c.open { GREEN } else { RED };
            PathElement::new(vec![(fi, c.low), (fi, c.high)], color)
        })
    )?;

    let delta = nf / chart_w;

    chart.draw_series(
        candles.iter().enumerate().flat_map(|(i, c)| {
            let fi = i as f64;
            let (top, bottom) = if c.open < c.close { (c.open, c.close) } else { (c.close, c.open) };
            let color = if c.close >= c.open { GREEN } else { RED };
            vec![
                PathElement::new(vec![(fi - delta, top), (fi - delta, bottom)], color),
                PathElement::new(vec![(fi + delta, top), (fi + delta, bottom)], color),
            ]
        })
    )?.label(ticker.to_string())
    .legend(|(x, y)| PathElement::new(vec![(x, y), (x + 20, y)], BLACK));

    let sma_points = |sma: &[Option<f64>]| -> Vec<(f64, f64)> {
        sma.iter().enumerate()
            .filter_map(|(i, v)| v.map(|v| (i as f64, v)))
            .collect()
    };

    let sp50 = sma_points(&sma50);
    let sp100 = sma_points(&sma100);
    let sp150 = sma_points(&sma150);
    let sp200 = sma_points(&sma200);

    if sp50.len() > 1 {
        chart.draw_series(LineSeries::new(sp50, BLUE))?
            .label("SMA 50")
            .legend(|(x, y)| PathElement::new(vec![(x, y), (x + 20, y)], BLUE));
    }
    if sp100.len() > 1 {
        chart.draw_series(LineSeries::new(sp100, RED))?
            .label("SMA 100")
            .legend(|(x, y)| PathElement::new(vec![(x, y), (x + 20, y)], RED));
    }
    if sp150.len() > 1 {
        chart.draw_series(LineSeries::new(sp150, GREEN))?
            .label("SMA 150")
            .legend(|(x, y)| PathElement::new(vec![(x, y), (x + 20, y)], GREEN));
    }
    if sp200.len() > 1 {
        chart.draw_series(LineSeries::new(sp200, MAGENTA))?
            .label("SMA 200")
            .legend(|(x, y)| PathElement::new(vec![(x, y), (x + 20, y)], MAGENTA));
    }

    // ---- Buy/Sell signals ----
    if !buy_signals.is_empty() || !sell_signals.is_empty() {
        println!("  Buy signals: {}, Sell signals: {}", buy_signals.len(), sell_signals.len());
        let px = 10f64;
        let ax = px * n as f64 / chart_w;
        let ay = px * (max_price - min_price) / chart_h;

        if !buy_signals.is_empty() {
            chart.draw_series(
                buy_signals.iter().map(|&i| {
                    let fi = i as f64;
                    let y = candles[i].low - ay * 1.5;
                    Polygon::new(
                        vec![
                            (fi, y + ay),
                            (fi - ax, y),
                            (fi + ax, y),
                        ],
                        GREEN.filled(),
                    )
                }),
            )?;
        }
        if !sell_signals.is_empty() {
            chart.draw_series(
                sell_signals.iter().map(|&i| {
                    let fi = i as f64;
                    let y = candles[i].high + ay * 1.5;
                    Polygon::new(
                        vec![
                            (fi, y - ay),
                            (fi - ax, y),
                            (fi + ax, y),
                        ],
                        RED.filled(),
                    )
                }),
            )?;
        }
    }

    // ---- Breakout signals ----
    if !breakouts_up.is_empty() || !breakouts_down.is_empty() {
        println!("  Breakouts up: {}, Breakouts down: {}", breakouts_up.len(), breakouts_down.len());
        let px = 12f64;
        let ax = px * n as f64 / chart_w;
        let ay = px * (max_price - min_price) / chart_h;
        let ax_i = ax * 0.4;
        let ay_i = ay * 0.4;

        let star = |cx: f64, cy: f64, orx: f64, irx: f64, ory: f64, iry: f64| -> Vec<(f64, f64)> {
            let mut pts = Vec::with_capacity(10);
            for k in 0..10 {
                let angle = -std::f64::consts::FRAC_PI_2 + std::f64::consts::PI * k as f64 / 5.0;
                let (rx, ry) = if k % 2 == 0 { (orx, ory) } else { (irx, iry) };
                pts.push((cx + rx * angle.cos(), cy + ry * angle.sin()));
            }
            pts
        };

        if !breakouts_up.is_empty() {
            chart.draw_series(
                breakouts_up.iter().map(|&i| {
                    let fi = i as f64;
                    let y = candles[i].high + ay * 1.8;
                    Polygon::new(star(fi, y, ax, ax_i, ay, ay_i), GREEN.filled())
                }),
            )?;
        }
        if !breakouts_down.is_empty() {
            chart.draw_series(
                breakouts_down.iter().map(|&i| {
                    let fi = i as f64;
                    let y = candles[i].low - ay * 1.8;
                    Polygon::new(star(fi, y, ax, ax_i, ay, ay_i), RED.filled())
                }),
            )?;
        }
    }

    chart.configure_series_labels()
        .background_style(WHITE.mix(0.85))
        .border_style(BLACK)
        .position(SeriesLabelPosition::UpperLeft)
        .draw()?;

    // ---- Volume chart ----
    let vol_delta = nf / (bottom_area.dim_in_pixel().0 as f64);

    let mut vol_chart = ChartBuilder::on(&bottom_area)
        .margin(10)
        .x_label_area_size(70)
        .y_label_area_size(120)
        .build_cartesian_2d(x_range, 0.0..max_volume)?;

    vol_chart.configure_mesh()
        .x_labels(12)
        .x_label_formatter(&|x| {
            let idx = *x as usize;
            if idx < n {
                candles[idx].date.format("%Y-%m").to_string()
            } else {
                String::new()
            }
        })
        .y_labels(5)
        .y_label_formatter(&|y| {
            if *y >= 1_000_000_000.0 { format!("{:.0}B", y / 1_000_000_000.0) }
            else if *y >= 1_000_000.0 { format!("{:.0}M", y / 1_000_000.0) }
            else if *y >= 1_000.0 { format!("{:.0}K", y / 1_000.0) }
            else { format!("{:.0}", y) }
        })
        .y_desc("Volume")
        .axis_desc_style(("sans-serif", 24))
        .draw()?;

    vol_chart.draw_series(
        candles.iter().enumerate().map(|(i, c)| {
            let fi = i as f64;
            let color = if c.close >= c.open { GREEN.filled() } else { RED.filled() };
            let v = c.volume as f64;
            Rectangle::new([(fi - vol_delta, 0.0), (fi + vol_delta, v)], color)
        })
    )?;

    root.present()?;
    Ok(())
}

fn main() -> Result<()> {
    let args = Args::parse();
    println!("Fetching data for {}...", args.ticker);
    let candles = fetch_data(&args.ticker)?;
    println!("Got {} daily candles", candles.len());
    println!("  Range: {} to {}", candles.first().unwrap().date, candles.last().unwrap().date);
    plot_chart(&candles, &args.ticker)?;
    println!("Chart saved to results/{}.png", args.ticker);
    Ok(())
}
