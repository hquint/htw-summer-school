"""Build an arbitrage-consistent 2024 HPFC from selected liquid futures."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

HPFC_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = HPFC_DIR.parent
INPUT_DIR = REPO_DIR / "data_pipeline_2024" / "processed"
OUTPUT_DIR = HPFC_DIR / "processed"

EXPECTED_QUARTER_HOURS = 35_136
ACTIVITY_THRESHOLD = 100
CALIBRATION_PRODUCTS = {
    "M01": [1],
    "M02": [2],
    "M03": [3],
    "Q2": [4, 5, 6],
    "Q3": [7, 8, 9],
    "Q4": [10, 11, 12],
}


def months_for_period(period: str) -> list[int]:
    if period == "CAL":
        return list(range(1, 13))
    if period.startswith("Q"):
        start = (int(period[1]) - 1) * 3 + 1
        return [start, start + 1, start + 2]
    if period.startswith("M"):
        return [int(period[1:])]
    raise ValueError(f"Unknown delivery period: {period}")


def quote_price(
    futures: pd.DataFrame,
    delivery_period: str,
    load_type: str,
) -> float:
    match = futures.loc[
        futures["delivery_period"].eq(delivery_period)
        & futures["load_type"].eq(load_type),
        "price_eur_mwh",
    ]
    if len(match) != 1:
        raise ValueError(
            f"Expected one {delivery_period} {load_type} quote, found {len(match)}"
        )
    return float(match.iloc[0])


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    shape = pd.read_csv(INPUT_DIR / "shape_factors.csv")
    futures = pd.read_csv(INPUT_DIR / "futures_prices.csv")

    required_shape = {
        "timestamp_utc",
        "timestamp_local",
        "is_peak",
        "historical_shape_factor",
    }
    required_futures = {
        "quote_date",
        "load_type",
        "delivery_period",
        "price_eur_mwh",
        "market_activity",
    }
    if not required_shape.issubset(shape.columns):
        raise ValueError("shape_factors.csv is missing required columns")
    if not required_futures.issubset(futures.columns):
        raise ValueError("futures_prices.csv is missing required columns")
    if len(shape) != EXPECTED_QUARTER_HOURS:
        raise ValueError(
            f"Expected {EXPECTED_QUARTER_HOURS:,} shape rows, got {len(shape):,}"
        )
    if shape["timestamp_utc"].nunique() != EXPECTED_QUARTER_HOURS:
        raise ValueError("Shape timestamps are not unique")
    if shape[list(required_shape)].isna().any().any():
        raise ValueError("Shape inputs contain missing values")
    if (shape["historical_shape_factor"] <= 0).any():
        raise ValueError("Historical shape factors must be strictly positive")

    return shape, futures


def build_curve(
    shape: pd.DataFrame,
    futures: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    timestamps = pd.to_datetime(shape["timestamp_utc"], utc=True)
    local_month = timestamps.dt.tz_convert("Europe/Berlin").dt.month
    peak_flag = shape["is_peak"].astype(bool)
    raw_shape = shape["historical_shape_factor"].astype(float)

    hpfc = np.full(len(shape), np.nan)
    assigned_period = np.full(len(shape), "", dtype=object)
    assigned_slice = np.full(len(shape), "", dtype=object)
    slice_target = np.full(len(shape), np.nan)
    parameter_rows: list[dict[str, object]] = []

    for period, months in CALIBRATION_PRODUCTS.items():
        period_mask = local_month.isin(months).to_numpy()
        peak_mask = period_mask & peak_flag.to_numpy()
        offpeak_mask = period_mask & ~peak_flag.to_numpy()

        count_all = int(period_mask.sum())
        count_peak = int(peak_mask.sum())
        count_offpeak = int(offpeak_mask.sum())
        if min(count_all, count_peak, count_offpeak) <= 0:
            raise ValueError(f"{period}: empty calibration block")

        base_target = quote_price(futures, period, "BASE")
        peak_target = quote_price(futures, period, "PEAK")
        offpeak_target = (
            base_target * count_all - peak_target * count_peak
        ) / count_offpeak

        peak_shape_mean = float(raw_shape.loc[peak_mask].mean())
        offpeak_shape_mean = float(raw_shape.loc[offpeak_mask].mean())
        hpfc[peak_mask] = (
            peak_target
            * raw_shape.loc[peak_mask].to_numpy()
            / peak_shape_mean
        )
        hpfc[offpeak_mask] = (
            offpeak_target
            * raw_shape.loc[offpeak_mask].to_numpy()
            / offpeak_shape_mean
        )
        assigned_period[period_mask] = period
        assigned_slice[peak_mask] = "PEAK"
        assigned_slice[offpeak_mask] = "OFFPEAK"
        slice_target[peak_mask] = peak_target
        slice_target[offpeak_mask] = offpeak_target

        parameter_rows.append(
            {
                "delivery_period": period,
                "base_target_eur_mwh": base_target,
                "peak_target_eur_mwh": peak_target,
                "implied_offpeak_target_eur_mwh": offpeak_target,
                "quarter_hours_all": count_all,
                "quarter_hours_peak": count_peak,
                "quarter_hours_offpeak": count_offpeak,
                "peak_shape_mean": peak_shape_mean,
                "offpeak_shape_mean": offpeak_shape_mean,
            }
        )

    if np.isnan(hpfc).any() or (assigned_period == "").any():
        raise ValueError("Calibration products did not cover every quarter-hour")

    curve = pd.DataFrame(
        {
            "timestamp_utc": shape["timestamp_utc"],
            "timestamp_local": shape["timestamp_local"],
            "calibration_product": assigned_period,
            "calibration_slice": assigned_slice,
            "is_peak": peak_flag.astype(int),
            "historical_shape_factor": raw_shape,
            "slice_target_price_eur_mwh": slice_target,
            "hpfc_price_eur_mwh": hpfc,
        }
    )
    curve["slice_target_price_eur_mwh"] = curve[
        "slice_target_price_eur_mwh"
    ].round(6)
    curve["hpfc_price_eur_mwh"] = curve["hpfc_price_eur_mwh"].round(6)

    parameters = pd.DataFrame(parameter_rows)
    numeric_columns = parameters.select_dtypes(include="number").columns
    parameters[numeric_columns] = parameters[numeric_columns].round(8)
    return curve, parameters


def build_reconciliation(
    curve: pd.DataFrame,
    futures: pd.DataFrame,
) -> pd.DataFrame:
    timestamps = pd.to_datetime(curve["timestamp_utc"], utc=True)
    local_month = timestamps.dt.tz_convert("Europe/Berlin").dt.month
    is_peak = curve["is_peak"].astype(bool)
    hpfc = curve["hpfc_price_eur_mwh"]

    rows: list[dict[str, object]] = []
    for quote in futures.itertuples(index=False):
        months = months_for_period(quote.delivery_period)
        delivery_mask = local_month.isin(months)
        mask = (
            delivery_mask
            if quote.load_type == "BASE"
            else delivery_mask & is_peak
        )
        curve_average = float(hpfc.loc[mask].mean())
        difference = curve_average - quote.price_eur_mwh
        calibration_product = quote.delivery_period in CALIBRATION_PRODUCTS
        is_usable = quote.market_activity > ACTIVITY_THRESHOLD

        if calibration_product:
            status = "OK_CALIBRATED" if abs(difference) <= 1e-6 else "FAIL"
        elif is_usable:
            status = "OK_CROSS_CHECK" if abs(difference) <= 0.01 else "FAIL"
        elif quote.market_activity <= 10:
            status = "NOT_USED_ILLIQUID"
        else:
            status = "REVIEW"

        rows.append(
            {
                "load_type": quote.load_type,
                "delivery_period": quote.delivery_period,
                "is_calibration_product": int(calibration_product),
                "market_activity": quote.market_activity,
                "futures_price_eur_mwh": quote.price_eur_mwh,
                "hpfc_block_average_eur_mwh": curve_average,
                "difference_eur_mwh": difference,
                "status": status,
            }
        )

    reconciliation = pd.DataFrame(rows)
    price_columns = [
        "futures_price_eur_mwh",
        "hpfc_block_average_eur_mwh",
        "difference_eur_mwh",
    ]
    reconciliation[price_columns] = reconciliation[price_columns].round(8)
    return reconciliation


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    shape, futures = load_inputs()
    curve, parameters = build_curve(shape, futures)
    reconciliation = build_reconciliation(curve, futures)

    curve.to_csv(OUTPUT_DIR / "hpfc_granular_2024.csv", index=False)
    parameters.to_csv(OUTPUT_DIR / "hpfc_calibration_parameters.csv", index=False)
    reconciliation.to_csv(
        OUTPUT_DIR / "hpfc_contract_reconciliation.csv",
        index=False,
    )

    metadata = {
        "delivery_year": 2024,
        "quote_date": str(futures["quote_date"].iloc[0]),
        "curve_rows": len(curve),
        "calibration_products": list(CALIBRATION_PRODUCTS),
        "activity_threshold": ACTIVITY_THRESHOLD,
        "shape_source": (
            "data_pipeline_2024/processed/shape_factors.csv; "
            "derived from observed 2019-2022 SMARD prices"
        ),
        "futures_source": (
            "data_pipeline_2024/processed/futures_prices.csv; synthetic teaching quotes"
        ),
    }
    (OUTPUT_DIR / "hpfc_metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    print(f"Built HPFC: {OUTPUT_DIR / 'hpfc_granular_2024.csv'}")
    print(f"Quarter-hours: {len(curve):,}")
    print(
        "HPFC range: "
        f"{curve['hpfc_price_eur_mwh'].min():.2f} to "
        f"{curve['hpfc_price_eur_mwh'].max():.2f} EUR/MWh"
    )


if __name__ == "__main__":
    main()
