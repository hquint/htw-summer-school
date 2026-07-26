
"""
Synthetic data generator for the HTW Summer School project:
Power Markets in Practice: Building and Hedging a Retail Electricity Portfolio

Creates:
- data/futures_prices.csv
- data/shape_factors.csv
- data/slp_portfolio.csv
- data/day_ahead_prices.csv
- data/project_data_dictionary.csv

The data is synthetic but designed to be plausible for a German retail electricity portfolio.
"""

from pathlib import Path
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

RNG = np.random.default_rng(42)

def make_hourly_index(start="2027-01-01", end="2028-12-31 23:00", tz=None):
    return pd.date_range(start=start, end=end, freq="h", tz=tz)

def peak_flag(idx):
    # Simplified EEX-style peak: Mon-Fri, 08:00-19:59.
    # In practice conventions may differ; here it is intentionally simplified.
    return ((idx.weekday < 5) & (idx.hour >= 8) & (idx.hour < 20)).astype(int)

def month_seasonality(idx):
    month = idx.month.values
    # Higher in winter, lower in summer.
    return 1.0 + 0.18 * np.cos(2 * np.pi * (month - 1) / 12)

def evening_load_shape(idx):
    hour = idx.hour.values
    morning = 0.10 * np.exp(-0.5 * ((hour - 7) / 2.2) ** 2)
    evening = 0.28 * np.exp(-0.5 * ((hour - 19) / 3.0) ** 2)
    night_dip = -0.10 * np.exp(-0.5 * ((hour - 3) / 2.5) ** 2)
    return 1.0 + morning + evening + night_dip

def weekend_adjustment(idx):
    # Residential demand slightly higher during the day on weekends.
    is_weekend = (idx.weekday >= 5).astype(float)
    hour = idx.hour.values
    daytime = np.exp(-0.5 * ((hour - 14) / 5.0) ** 2)
    return 1.0 + is_weekend * 0.08 * daytime

def price_shape(idx):
    hour = idx.hour.values
    month = idx.month.values
    winter = 1.0 + 0.16 * np.cos(2 * np.pi * (month - 1) / 12)
    solar_midday_discount = -0.16 * np.exp(-0.5 * ((hour - 13) / 3.0) ** 2)
    evening_peak = 0.24 * np.exp(-0.5 * ((hour - 19) / 2.5) ** 2)
    morning_peak = 0.08 * np.exp(-0.5 * ((hour - 8) / 2.0) ** 2)
    weekend = np.where(idx.weekday >= 5, -0.05, 0.0)
    raw = winter * (1.0 + solar_midday_discount + evening_peak + morning_peak + weekend)
    return raw

def build_futures():
    # Synthetic futures quotes. Some data is deliberately "too much" for the task.
    # 2027 has annual, quarterly and monthly quotes. 2028 has annual and quarterly,
    # but quarterly products are flagged as illiquid to force a market-judgement decision.
    rows = []

    def add(year, product, period, base_price, peak_price, liquid=True):
        rows.append({
            "delivery_year": year, "product_type": "BASE", "delivery_period": period,
            "price_eur_mwh": round(base_price, 2), "is_liquid": liquid
        })
        rows.append({
            "delivery_year": year, "product_type": "PEAK", "delivery_period": period,
            "price_eur_mwh": round(peak_price, 2), "is_liquid": liquid
        })

    # Annual quotes
    add(2027, "CAL", "CAL", 86.0, 108.0, True)
    add(2028, "CAL", "CAL", 83.0, 103.0, True)

    # Quarterly 2027 liquid
    quarters_2027 = {
        "Q1": (97, 124), "Q2": (78, 96), "Q3": (72, 88), "Q4": (100, 131)
    }
    for q, (b, p) in quarters_2027.items():
        add(2027, "QUARTER", q, b, p, True)

    # Quarterly 2028 included but illiquid / indicative
    quarters_2028 = {
        "Q1": (91, 116), "Q2": (77, 94), "Q3": (70, 86), "Q4": (94, 121)
    }
    for q, (b, p) in quarters_2028.items():
        add(2028, "QUARTER", q, b, p, False)

    # Monthly 2027 liquid
    monthly_base = [101, 98, 92, 82, 75, 72, 68, 70, 77, 91, 101, 108]
    monthly_peak = [132, 126, 115, 101, 91, 87, 82, 84, 94, 119, 133, 140]
    for m, (b, p) in enumerate(zip(monthly_base, monthly_peak), start=1):
        add(2027, "MONTH", f"M{m:02d}", b, p, True)

    # Monthly 2028 intentionally absent

    futures = pd.DataFrame(rows)
    futures["quote_date"] = "2026-06-08"
    futures.to_csv(DATA_DIR / "futures_prices.csv", index=False)

def build_shape_factors(idx):
    raw = price_shape(idx)
    df = pd.DataFrame({
        "timestamp": idx,
        "shape_factor_raw": raw,
        "month": idx.month,
        "hour": idx.hour,
        "weekday": idx.weekday,
        "is_peak": peak_flag(idx),
    })
    # Normalize raw shape to mean 1 at annual level per year.
    df["year"] = idx.year
    df["shape_factor_annual_norm"] = df["shape_factor_raw"] / df.groupby("year")["shape_factor_raw"].transform("mean")
    df.to_csv(DATA_DIR / "shape_factors.csv", index=False)

def build_slp(idx):
    raw = month_seasonality(idx) * evening_load_shape(idx) * weekend_adjustment(idx)
    noise = RNG.normal(0, 0.025, size=len(idx))
    raw = np.maximum(0.15, raw * (1 + noise))

    df = pd.DataFrame({"timestamp": idx, "raw_profile": raw})
    df["year"] = idx.year

    # Scale to annual consumption: 2027 = 120 GWh, 2028 = 128 GWh.
    annual_targets = {2027: 120_000.0, 2028: 128_000.0}  # MWh/year
    df["load_mwh"] = 0.0
    for y, target in annual_targets.items():
        mask = df["year"] == y
        df.loc[mask, "load_mwh"] = df.loc[mask, "raw_profile"] / df.loc[mask, "raw_profile"].sum() * target

    df["portfolio_id"] = "Residential_SLP_Portfolio_A"
    df[["timestamp", "portfolio_id", "load_mwh"]].to_csv(DATA_DIR / "slp_portfolio.csv", index=False)

def build_day_ahead(idx):
    # Realized DA price = forward-like shape + market noise + occasional spikes.
    base_level_by_year = np.where(idx.year == 2027, 84.0, 82.0)
    raw_shape = price_shape(idx)
    seasonal = raw_shape / pd.Series(raw_shape).groupby(idx.year).transform("mean").to_numpy()
    price = base_level_by_year * seasonal

    daily_noise = RNG.normal(0, 8, size=len(idx))
    # Some autocorrelation-ish smoothing
    daily_noise = pd.Series(daily_noise).rolling(6, min_periods=1).mean().to_numpy()
    price = price + daily_noise

    # Add scarcity spikes mostly winter evenings
    is_winter = np.isin(idx.month, [1,2,12])
    is_evening = (idx.hour >= 17) & (idx.hour <= 21)
    spike_candidates = np.where(is_winter & is_evening)[0]
    spike_idx = RNG.choice(spike_candidates, size=35, replace=False)
    price[spike_idx] += RNG.uniform(80, 220, size=len(spike_idx))

    # Negative-ish / low price solar events in summer midday
    is_summer = np.isin(idx.month, [5,6,7,8])
    is_midday = (idx.hour >= 11) & (idx.hour <= 15)
    low_candidates = np.where(is_summer & is_midday)[0]
    low_idx = RNG.choice(low_candidates, size=45, replace=False)
    price[low_idx] -= RNG.uniform(30, 75, size=len(low_idx))

    price = np.clip(price, -30, 350)

    df = pd.DataFrame({
        "timestamp": idx,
        "day_ahead_price_eur_mwh": np.round(price, 2)
    })
    df.to_csv(DATA_DIR / "day_ahead_prices.csv", index=False)

def build_dictionary():
    rows = [
        ("futures_prices.csv", "delivery_year", "Delivery year of the futures product."),
        ("futures_prices.csv", "product_type", "BASE or PEAK."),
        ("futures_prices.csv", "delivery_period", "CAL, Q1-Q4, or M01-M12."),
        ("futures_prices.csv", "price_eur_mwh", "Forward/futures price in EUR/MWh."),
        ("futures_prices.csv", "is_liquid", "Whether the product should be treated as liquid for the base exercise."),
        ("shape_factors.csv", "shape_factor_annual_norm", "Hourly shape factor normalized to annual average 1."),
        ("slp_portfolio.csv", "load_mwh", "Expected hourly portfolio load in MWh."),
        ("day_ahead_prices.csv", "day_ahead_price_eur_mwh", "Realized hourly Day-Ahead price in EUR/MWh."),
    ]
    pd.DataFrame(rows, columns=["file", "column", "description"]).to_csv(DATA_DIR / "project_data_dictionary.csv", index=False)

def main():
    idx = make_hourly_index()
    build_futures()
    build_shape_factors(idx)
    build_slp(idx)
    build_day_ahead(idx)
    build_dictionary()
    print(f"Data generated in: {DATA_DIR}")

if __name__ == "__main__":
    main()
