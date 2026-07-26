"""Build the student-ready 2024 teaching data from downloaded sources."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

PIPELINE_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = PIPELINE_DIR / "raw"
PROCESSED_DIR = PIPELINE_DIR / "processed"
BERLIN_TZ = "Europe/Berlin"
DELIVERY_YEAR = 2024
QUOTE_DATE = "2023-09-29"
TARGET_HEDGE_GAIN_EUR_MWH = 1.25

PROFILE_FILES = {
    "HB": ("slp_HB_2024.xlsx", "Household / Haushalt"),
    "GB": ("slp_GB_2024.xlsx", "General commercial / Gewerbe allgemein"),
    "LB": ("slp_LB_2024.xlsx", "Agriculture / Landwirtschaft"),
}

MONTH_STALE_OFFSETS = {
    4: 6.00,
    5: -5.00,
    6: 8.00,
    7: -7.00,
    8: 4.00,
    9: -4.00,
    10: 7.00,
    11: -6.00,
    12: 5.00,
}

BASE_ACTIVITY = {
    "CAL": 5000,
    "Q1": 3000,
    "Q2": 2200,
    "Q3": 1600,
    "Q4": 1400,
    "M01": 900,
    "M02": 800,
    "M03": 650,
    "M04": 10,
    "M05": 8,
    "M06": 7,
    "M07": 6,
    "M08": 5,
    "M09": 4,
    "M10": 3,
    "M11": 2,
    "M12": 1,
}


def utc_string(series: pd.Series | pd.DatetimeIndex) -> pd.Series:
    return pd.Series(series).dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def local_iso_strings(index: pd.DatetimeIndex) -> list[str]:
    return [timestamp.isoformat() for timestamp in index.tz_convert(BERLIN_TZ)]


def canonical_quarter_hours() -> pd.DatetimeIndex:
    local_index = pd.date_range(
        f"{DELIVERY_YEAR}-01-01",
        f"{DELIVERY_YEAR + 1}-01-01",
        freq="15min",
        inclusive="left",
        tz=BERLIN_TZ,
    )
    return local_index.tz_convert("UTC")


def load_slp_profiles(canonical_index: pd.DatetimeIndex) -> pd.DataFrame:
    result = pd.DataFrame(index=canonical_index)
    for profile_code, (filename, _) in PROFILE_FILES.items():
        path = RAW_DIR / "stromnetz_berlin" / filename
        source = pd.read_excel(path, header=0, skiprows=[1])
        values = pd.to_numeric(source.iloc[:, 2], errors="raise")
        if len(values) != len(canonical_index):
            raise ValueError(
                f"{profile_code}: expected {len(canonical_index)} rows, "
                f"received {len(values)}"
            )
        if not np.isclose(values.sum(), 1_000_000.0, atol=0.01):
            raise ValueError(f"{profile_code}: annual normalization is not 1,000 MWh")
        result[f"{profile_code.lower()}_normalized_kwh"] = values.to_numpy()

    result.insert(0, "timestamp_local", local_iso_strings(canonical_index))
    result.insert(0, "timestamp_utc", utc_string(canonical_index).to_numpy())
    return result.reset_index(drop=True)


def load_smard_hourly(year: int) -> pd.DataFrame:
    path = RAW_DIR / "smard" / f"day_ahead_{year}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    data = pd.DataFrame(payload["series"], columns=["timestamp_ms", "price"])
    data["timestamp"] = pd.to_datetime(data["timestamp_ms"], unit="ms", utc=True)
    data["price"] = pd.to_numeric(data["price"], errors="coerce")
    data = data.dropna(subset=["price"]).sort_values("timestamp")
    data = data.drop_duplicates("timestamp", keep="last")
    local_year = data["timestamp"].dt.tz_convert(BERLIN_TZ).dt.year
    return data.loc[local_year == year, ["timestamp", "price"]].reset_index(drop=True)


def build_day_ahead_quarter_hour(
    canonical_index: pd.DatetimeIndex,
) -> pd.DataFrame:
    hourly = load_smard_hourly(DELIVERY_YEAR)
    expected_hours = len(canonical_index) // 4
    if len(hourly) != expected_hours:
        raise ValueError(
            f"Day-Ahead: expected {expected_hours} hourly rows, got {len(hourly)}"
        )

    timestamps = np.repeat(hourly["timestamp"].array, 4)
    offsets = pd.to_timedelta(np.tile(np.arange(4) * 15, len(hourly)), unit="min")
    qh_index = pd.DatetimeIndex(timestamps + offsets)
    prices = np.repeat(hourly["price"].to_numpy(), 4)
    if not qh_index.equals(canonical_index):
        raise ValueError("Day-Ahead timestamps do not match the canonical 2024 index")

    return pd.DataFrame(
        {
            "timestamp_utc": utc_string(qh_index).to_numpy(),
            "timestamp_local": local_iso_strings(qh_index),
            "day_ahead_price_eur_mwh": np.round(prices, 2),
        }
    )


def build_imbalance_prices(canonical_index: pd.DatetimeIndex) -> pd.DataFrame:
    source_path = RAW_DIR / "netztransparenz" / "rebap_2024_utc.csv"
    source = pd.read_csv(
        source_path,
        sep=";",
        decimal=",",
        encoding="utf-8-sig",
    )
    source["timestamp"] = pd.to_datetime(
        source["Datum"].astype(str) + " " + source["von"].astype(str),
        format="%d.%m.%Y %H:%M",
        utc=True,
    )
    source = source.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    source = source.set_index("timestamp").reindex(canonical_index)

    short = pd.to_numeric(source["reBAP unterdeckt"], errors="coerce")
    long = pd.to_numeric(source["reBAP ueberdeckt"], errors="coerce")
    if short.isna().any() or long.isna().any():
        raise ValueError("reBAP contains missing observations after timestamp alignment")
    if not np.allclose(short, long):
        raise ValueError("2024 reBAP short and long prices are unexpectedly asymmetric")

    return pd.DataFrame(
        {
            "timestamp_utc": utc_string(canonical_index).to_numpy(),
            "timestamp_local": local_iso_strings(canonical_index),
            "imbalance_price_eur_mwh": np.round(short.to_numpy(), 2),
        }
    )


def build_shape_factors(canonical_index: pd.DatetimeIndex) -> pd.DataFrame:
    history = pd.concat(
        [load_smard_hourly(year) for year in (2019, 2020, 2021, 2022)],
        ignore_index=True,
    )
    history["local"] = history["timestamp"].dt.tz_convert(BERLIN_TZ)
    history["month"] = history["local"].dt.month
    history["hour"] = history["local"].dt.hour
    history["is_weekend"] = (history["local"].dt.weekday >= 5).astype(int)

    pattern = (
        history.groupby(["month", "is_weekend", "hour"], as_index=False)["price"]
        .median()
        .rename(columns={"price": "historical_median_price"})
    )
    if pattern["historical_median_price"].min() <= 0:
        shift = 1.0 - pattern["historical_median_price"].min()
        pattern["historical_median_price"] += shift

    local = canonical_index.tz_convert(BERLIN_TZ)
    calendar = pd.DataFrame(
        {
            "timestamp_utc": canonical_index,
            "month": local.month,
            "hour": local.hour,
            "weekday": local.weekday,
            "is_weekend": (local.weekday >= 5).astype(int),
        }
    )
    calendar = calendar.merge(
        pattern, on=["month", "is_weekend", "hour"], how="left", validate="many_to_one"
    )
    if calendar["historical_median_price"].isna().any():
        raise ValueError("Shape-factor mapping produced missing observations")

    raw = calendar["historical_median_price"].to_numpy()
    annual_factor = raw / raw.mean()
    is_peak = (
        (calendar["weekday"] < 5)
        & (calendar["hour"] >= 8)
        & (calendar["hour"] < 20)
    ).astype(int)

    return pd.DataFrame(
        {
            "timestamp_utc": utc_string(canonical_index).to_numpy(),
            "timestamp_local": local_iso_strings(canonical_index),
            "month": calendar["month"].to_numpy(),
            "hour": calendar["hour"].to_numpy(),
            "weekday": calendar["weekday"].to_numpy(),
            "is_peak": is_peak.to_numpy(),
            "historical_shape_factor": np.round(annual_factor, 8),
        }
    )


def months_for_period(period: str) -> list[int]:
    if period == "CAL":
        return list(range(1, 13))
    if period.startswith("Q"):
        quarter = int(period[1])
        start = (quarter - 1) * 3 + 1
        return [start, start + 1, start + 2]
    if period.startswith("M"):
        return [int(period[1:])]
    raise ValueError(f"Unknown period: {period}")


def activity_for(period: str, load_type: str) -> int:
    base = BASE_ACTIVITY[period]
    if load_type == "BASE":
        return base
    return max(1, round(base * 0.28))


def build_futures(
    canonical_index: pd.DatetimeIndex,
    day_ahead: pd.DataFrame,
    shape_factors: pd.DataFrame,
) -> pd.DataFrame:
    local = canonical_index.tz_convert(BERLIN_TZ)
    price = day_ahead["day_ahead_price_eur_mwh"].to_numpy()
    is_peak = shape_factors["is_peak"].to_numpy().astype(bool)
    periods = ["CAL", "Q1", "Q2", "Q3", "Q4"] + [
        f"M{month:02d}" for month in range(1, 13)
    ]

    rows: list[dict[str, object]] = []
    for period in periods:
        months = months_for_period(period)
        delivery_mask = np.isin(local.month, months)
        for load_type in ("BASE", "PEAK"):
            mask = delivery_mask if load_type == "BASE" else delivery_mask & is_peak
            realized_block_average = float(price[mask].mean())
            forward_price = realized_block_average - TARGET_HEDGE_GAIN_EUR_MWH

            if period.startswith("M") and int(period[1:]) >= 4:
                stale_offset = MONTH_STALE_OFFSETS[int(period[1:])]
                if load_type == "PEAK":
                    stale_offset *= 1.15
                forward_price += stale_offset

            start = pd.Timestamp(f"{DELIVERY_YEAR}-{months[0]:02d}-01")
            if months[-1] == 12:
                end = pd.Timestamp(f"{DELIVERY_YEAR + 1}-01-01")
            else:
                end = pd.Timestamp(f"{DELIVERY_YEAR}-{months[-1] + 1:02d}-01")

            rows.append(
                {
                    "quote_date": QUOTE_DATE,
                    "delivery_year": DELIVERY_YEAR,
                    "load_type": load_type,
                    "product_type": (
                        "YEAR"
                        if period == "CAL"
                        else "QUARTER"
                        if period.startswith("Q")
                        else "MONTH"
                    ),
                    "delivery_period": period,
                    "delivery_start": start.date().isoformat(),
                    "delivery_end_exclusive": end.date().isoformat(),
                    "price_eur_mwh": round(forward_price, 2),
                    "market_activity": activity_for(period, load_type),
                }
            )

    return pd.DataFrame(rows)


def write_data_dictionary() -> None:
    rows = [
        (
            "slp_profiles.csv",
            "timestamp_utc",
            "Quarter-hour start in UTC; primary join key.",
            "observed/preprocessed",
        ),
        (
            "slp_profiles.csv",
            "timestamp_local",
            "Quarter-hour start in Europe/Berlin with UTC offset.",
            "observed/preprocessed",
        ),
        (
            "slp_profiles.csv",
            "hb_normalized_kwh",
            "Berlin household SLP energy; annual sum is 1,000,000 kWh.",
            "observed",
        ),
        (
            "slp_profiles.csv",
            "gb_normalized_kwh",
            "Berlin general-commercial SLP; annual sum is 1,000,000 kWh.",
            "observed",
        ),
        (
            "slp_profiles.csv",
            "lb_normalized_kwh",
            "Berlin agriculture SLP; annual sum is 1,000,000 kWh.",
            "observed",
        ),
        (
            "day_ahead_prices.csv",
            "day_ahead_price_eur_mwh",
            "Observed hourly DE/LU DA price repeated over four quarter-hours.",
            "observed/preprocessed",
        ),
        (
            "imbalance_prices.csv",
            "imbalance_price_eur_mwh",
            "Observed quality-assured symmetric German reBAP.",
            "observed",
        ),
        (
            "shape_factors.csv",
            "historical_shape_factor",
            "Robust real-price shape from 2019-2022, normalized to annual mean 1.",
            "derived",
        ),
        (
            "shape_factors.csv",
            "is_peak",
            "Teaching peak flag: Mon-Fri 08:00-20:00 Europe/Berlin.",
            "derived",
        ),
        (
            "futures_prices.csv",
            "price_eur_mwh",
            "Synthetic teaching forward price; not historical EEX data.",
            "synthetic",
        ),
        (
            "futures_prices.csv",
            "market_activity",
            "Synthetic combined activity indicator; higher means easier to trade.",
            "synthetic",
        ),
    ]
    pd.DataFrame(
        rows, columns=["file", "column", "description", "data_status"]
    ).to_csv(PROCESSED_DIR / "data_dictionary.csv", index=False)


def write_sources() -> None:
    rows = [
        {
            "dataset": "Berlin SLP HB",
            "publisher": "Stromnetz Berlin GmbH",
            "status": "observed",
            "url": (
                "https://www.stromnetz.berlin/files/globalassets/dokumente/"
                "netz-nutzen/lastprofile/standardlastprofil-haushalte-2024.xlsx"
            ),
        },
        {
            "dataset": "Berlin SLP GB",
            "publisher": "Stromnetz Berlin GmbH",
            "status": "observed",
            "url": (
                "https://www.stromnetz.berlin/files/globalassets/dokumente/"
                "netz-nutzen/lastprofile/"
                "standardlastprofil-gewerbe-allgemein-2024.xlsx"
            ),
        },
        {
            "dataset": "Berlin SLP LB",
            "publisher": "Stromnetz Berlin GmbH",
            "status": "observed",
            "url": (
                "https://www.stromnetz.berlin/files/globalassets/dokumente/"
                "netz-nutzen/lastprofile/"
                "standardlastprofil-landwirtschaftsbetriebe-2024.xlsx"
            ),
        },
        {
            "dataset": "Day-Ahead price and historical shape inputs",
            "publisher": "Bundesnetzagentur | SMARD.de",
            "status": "observed",
            "url": (
                "https://www.smard.de/app/chart_data/4169/DE/index_hour.json"
            ),
        },
        {
            "dataset": "Quality-assured reBAP",
            "publisher": "Netztransparenz / German TSOs",
            "status": "observed",
            "url": (
                "https://www.netztransparenz.de/Regelenergie/"
                "Ausgleichsenergiepreis/reBAP"
            ),
        },
        {
            "dataset": "Teaching futures snapshot",
            "publisher": "HTW Summer School project",
            "status": "synthetic",
            "url": "",
        },
    ]
    pd.DataFrame(rows).to_csv(PROCESSED_DIR / "sources.csv", index=False)


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    canonical_index = canonical_quarter_hours()
    if len(canonical_index) != 35_136:
        raise ValueError(f"Unexpected 2024 quarter-hour count: {len(canonical_index)}")

    slp = load_slp_profiles(canonical_index)
    day_ahead = build_day_ahead_quarter_hour(canonical_index)
    imbalance = build_imbalance_prices(canonical_index)
    shape = build_shape_factors(canonical_index)
    futures = build_futures(canonical_index, day_ahead, shape)

    slp.to_csv(PROCESSED_DIR / "slp_profiles.csv", index=False)
    day_ahead.to_csv(PROCESSED_DIR / "day_ahead_prices.csv", index=False)
    imbalance.to_csv(PROCESSED_DIR / "imbalance_prices.csv", index=False)
    shape.to_csv(PROCESSED_DIR / "shape_factors.csv", index=False)
    futures.to_csv(PROCESSED_DIR / "futures_prices.csv", index=False)
    write_data_dictionary()
    write_sources()

    print(f"Built data in {PROCESSED_DIR}")
    print(f"Quarter-hours: {len(canonical_index):,}")
    print(f"Futures rows: {len(futures):,}")


if __name__ == "__main__":
    main()
