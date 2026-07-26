#!/usr/bin/env python3
"""Build the student-only data archive for the 2024 Power Markets project."""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "output" / "student_data"
ARCHIVE = OUTPUT_DIR / "Power_Markets_Student_Data_2024.zip"

COPY_FILES = {
    "slp_profiles.csv": ROOT / "data_pipeline_2024" / "processed" / "slp_profiles.csv",
    "futures_prices.csv": ROOT / "data_pipeline_2024" / "processed" / "futures_prices.csv",
    "shape_factors.csv": ROOT / "data_pipeline_2024" / "processed" / "shape_factors.csv",
    "day_ahead_prices.csv": ROOT
    / "data_pipeline_2024"
    / "processed"
    / "day_ahead_prices.csv",
    "imbalance_prices.csv": ROOT
    / "data_pipeline_2024"
    / "processed"
    / "imbalance_prices.csv",
}

ACTUAL_SOURCE = (
    ROOT / "imbalance_backtest_2024" / "processed" / "actual_portfolio_2024.csv"
)
ACTUAL_COLUMNS = [
    "timestamp_utc",
    "timestamp_local",
    "hb_actual_mwh",
    "gb_actual_mwh",
    "lb_actual_mwh",
    "total_actual_mwh",
]

DATA_DICTIONARY = [
    ("slp_profiles.csv", "timestamp_utc", "Quarter-hour start in UTC; primary join key.", "observed/preprocessed"),
    ("slp_profiles.csv", "timestamp_local", "Quarter-hour start in Europe/Berlin with UTC offset.", "observed/preprocessed"),
    ("slp_profiles.csv", "hb_normalized_kwh", "Berlin household SLP energy; annual sum is 1,000,000 kWh.", "observed"),
    ("slp_profiles.csv", "gb_normalized_kwh", "Berlin general-commercial SLP energy; annual sum is 1,000,000 kWh.", "observed"),
    ("slp_profiles.csv", "lb_normalized_kwh", "Berlin agricultural SLP energy; annual sum is 1,000,000 kWh.", "observed"),
    ("futures_prices.csv", "quote_date", "Date of the teaching futures snapshot.", "synthetic"),
    ("futures_prices.csv", "delivery_year", "Calendar year in which the product delivers.", "synthetic"),
    ("futures_prices.csv", "load_type", "BASE delivers in all intervals; PEAK only in the defined Peak intervals.", "synthetic"),
    ("futures_prices.csv", "product_type", "YEAR, QUARTER, or MONTH delivery product.", "synthetic"),
    ("futures_prices.csv", "delivery_period", "Product delivery label such as CAL, Q1, or M01.", "synthetic"),
    ("futures_prices.csv", "delivery_start", "Inclusive delivery-period start date.", "synthetic"),
    ("futures_prices.csv", "delivery_end_exclusive", "Exclusive delivery-period end date.", "synthetic"),
    ("futures_prices.csv", "price_eur_mwh", "Teaching forward price in EUR/MWh.", "synthetic"),
    ("futures_prices.csv", "market_activity", "Teaching tradability indicator; higher values indicate more active products.", "synthetic"),
    ("shape_factors.csv", "timestamp_utc", "Quarter-hour start in UTC; primary join key.", "derived"),
    ("shape_factors.csv", "timestamp_local", "Quarter-hour start in Europe/Berlin with UTC offset.", "derived"),
    ("shape_factors.csv", "month", "Local calendar month, from 1 to 12.", "derived"),
    ("shape_factors.csv", "hour", "Local delivery hour, from 0 to 23.", "derived"),
    ("shape_factors.csv", "weekday", "Local weekday using Monday = 0 and Sunday = 6.", "derived"),
    ("shape_factors.csv", "is_peak", "Peak flag: Monday-Friday, 08:00-20:00 Europe/Berlin.", "derived"),
    ("shape_factors.csv", "historical_shape_factor", "Robust 2019-2022 Day-Ahead price shape normalized to annual mean 1.", "derived"),
    ("day_ahead_prices.csv", "timestamp_utc", "Quarter-hour start in UTC; primary join key.", "observed/preprocessed"),
    ("day_ahead_prices.csv", "timestamp_local", "Quarter-hour start in Europe/Berlin with UTC offset.", "observed/preprocessed"),
    ("day_ahead_prices.csv", "day_ahead_price_eur_mwh", "Observed hourly DE/LU Day-Ahead price repeated across its four quarter-hours.", "observed/preprocessed"),
    ("actual_portfolio_load.csv", "timestamp_utc", "Quarter-hour start in UTC; primary join key.", "synthetic"),
    ("actual_portfolio_load.csv", "timestamp_local", "Quarter-hour start in Europe/Berlin with UTC offset.", "synthetic"),
    ("actual_portfolio_load.csv", "hb_actual_mwh", "Realised household-profile portfolio energy in the quarter-hour.", "synthetic"),
    ("actual_portfolio_load.csv", "gb_actual_mwh", "Realised general-commercial-profile portfolio energy in the quarter-hour.", "synthetic"),
    ("actual_portfolio_load.csv", "lb_actual_mwh", "Realised agricultural-profile portfolio energy in the quarter-hour.", "synthetic"),
    ("actual_portfolio_load.csv", "total_actual_mwh", "Total realised portfolio energy in the quarter-hour.", "synthetic"),
    ("imbalance_prices.csv", "timestamp_utc", "Quarter-hour start in UTC; primary join key.", "observed"),
    ("imbalance_prices.csv", "timestamp_local", "Quarter-hour start in Europe/Berlin with UTC offset.", "observed"),
    ("imbalance_prices.csv", "imbalance_price_eur_mwh", "Observed quality-assured symmetric German reBAP in EUR/MWh.", "observed"),
]


def csv_bytes(rows: list[list[str]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def build_actual_load() -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=ACTUAL_COLUMNS, lineterminator="\n")
    writer.writeheader()
    with ACTUAL_SOURCE.open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        missing = set(ACTUAL_COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Actual-load source is missing columns: {sorted(missing)}")
        for row in reader:
            writer.writerow({column: row[column] for column in ACTUAL_COLUMNS})
    return stream.getvalue().encode("utf-8")


def build_sources() -> bytes:
    source_path = ROOT / "data_pipeline_2024" / "processed" / "sources.csv"
    with source_path.open(newline="", encoding="utf-8") as source:
        rows = list(csv.reader(source))
    rows.append(
        [
            "Teaching actual portfolio load",
            "HTW Summer School project",
            "synthetic",
            "",
        ]
    )
    return csv_bytes(rows)


def parse_payload(payload: bytes) -> tuple[list[str], list[list[str]]]:
    rows = list(csv.reader(io.StringIO(payload.decode("utf-8"))))
    if not rows:
        raise ValueError("CSV payload is empty")
    return rows[0], rows[1:]


def validate_payloads(payloads: dict[str, bytes]) -> None:
    expected_names = {
        "slp_profiles.csv",
        "futures_prices.csv",
        "shape_factors.csv",
        "day_ahead_prices.csv",
        "actual_portfolio_load.csv",
        "imbalance_prices.csv",
        "data_dictionary.csv",
        "sources.csv",
    }
    if set(payloads) != expected_names:
        raise ValueError(f"Unexpected package contents: {sorted(payloads)}")

    time_series = [
        "slp_profiles.csv",
        "shape_factors.csv",
        "day_ahead_prices.csv",
        "actual_portfolio_load.csv",
        "imbalance_prices.csv",
    ]
    reference_timestamps: list[str] | None = None
    for name in time_series:
        header, rows = parse_payload(payloads[name])
        if len(rows) != 35_136:
            raise ValueError(f"{name} has {len(rows):,} rows; expected 35,136")
        timestamp_index = header.index("timestamp_utc")
        timestamps = [row[timestamp_index] for row in rows]
        if len(set(timestamps)) != len(timestamps):
            raise ValueError(f"{name} contains duplicate timestamp_utc values")
        if reference_timestamps is None:
            reference_timestamps = timestamps
        elif timestamps != reference_timestamps:
            raise ValueError(f"{name} does not use the common timestamp_utc grid")

    actual_header, actual_rows = parse_payload(payloads["actual_portfolio_load.csv"])
    forbidden = {"forecast", "deviation", "factor", "error", "hedge", "pnl"}
    if any(term in column.lower() for term in forbidden for column in actual_header):
        raise ValueError("Actual-load export contains a solution or simulation column")
    indices = {column: actual_header.index(column) for column in actual_header}
    for row_number, row in enumerate(actual_rows, start=2):
        component_total = sum(
            float(row[indices[column]])
            for column in ("hb_actual_mwh", "gb_actual_mwh", "lb_actual_mwh")
        )
        reported_total = float(row[indices["total_actual_mwh"]])
        if abs(component_total - reported_total) > 1e-6:
            raise ValueError(f"Actual-load total does not reconcile on CSV row {row_number}")

    dictionary_header, dictionary_rows = parse_payload(payloads["data_dictionary.csv"])
    if dictionary_header != ["file", "column", "description", "data_status"]:
        raise ValueError("Unexpected data_dictionary.csv header")
    dictionary_fields = {(row[0], row[1]) for row in dictionary_rows}
    for name in expected_names - {"data_dictionary.csv", "sources.csv"}:
        header, _ = parse_payload(payloads[name])
        missing = {(name, column) for column in header} - dictionary_fields
        if missing:
            raise ValueError(f"Data dictionary is missing: {sorted(missing)}")


def write_archive(payloads: dict[str, bytes]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ARCHIVE, "w") as archive:
        for name in sorted(payloads):
            info = zipfile.ZipInfo(name, date_time=(2024, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(
                info,
                payloads[name],
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )

    with zipfile.ZipFile(ARCHIVE) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP integrity test failed")
        if set(archive.namelist()) != set(payloads):
            raise ValueError("ZIP contents do not match the validated payloads")


def main() -> None:
    payloads = {name: path.read_bytes() for name, path in COPY_FILES.items()}
    payloads["actual_portfolio_load.csv"] = build_actual_load()
    payloads["data_dictionary.csv"] = csv_bytes(
        [["file", "column", "description", "data_status"], *DATA_DICTIONARY]
    )
    payloads["sources.csv"] = build_sources()
    validate_payloads(payloads)
    write_archive(payloads)

    print(ARCHIVE)
    print("files=8")
    print("quarter_hour_rows=35136")
    print(f"archive_bytes={ARCHIVE.stat().st_size}")


if __name__ == "__main__":
    main()
