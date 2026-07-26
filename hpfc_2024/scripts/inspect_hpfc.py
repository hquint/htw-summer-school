"""Validate and visualize the value-neutral 2024 HPFC."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

HPFC_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = HPFC_DIR.parent
PROCESSED_DIR = HPFC_DIR / "processed"
INSPECTION_DIR = HPFC_DIR / "inspection"
DATA_DIR = REPO_DIR / "data_pipeline_2024" / "processed"

EXPECTED_QUARTER_HOURS = 35_136
CALIBRATION_TOLERANCE = 1e-6
CROSS_CHECK_TOLERANCE = 0.01

COLORS = {
    "HPFC": "#0F766E",
    "DA": "#334155",
    "BASE": "#2563EB",
    "PEAK": "#EA580C",
}


def check_row(
    check: str,
    actual: float | str,
    expected: float | str,
    tolerance: float | None,
    ok: bool,
    notes: str,
) -> dict[str, object]:
    return {
        "check": check,
        "actual": actual,
        "expected": expected,
        "difference": (
            ""
            if isinstance(actual, str)
            or isinstance(expected, str)
            or tolerance is None
            else actual - expected
        ),
        "tolerance": "" if tolerance is None else tolerance,
        "status": "OK" if ok else "FAIL",
        "notes": notes,
    }


def load_data() -> dict[str, pd.DataFrame]:
    return {
        "curve": pd.read_csv(PROCESSED_DIR / "hpfc_granular_2024.csv"),
        "parameters": pd.read_csv(
            PROCESSED_DIR / "hpfc_calibration_parameters.csv"
        ),
        "reconciliation": pd.read_csv(
            PROCESSED_DIR / "hpfc_contract_reconciliation.csv"
        ),
        "day_ahead": pd.read_csv(DATA_DIR / "day_ahead_prices.csv"),
    }


def run_checks(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    curve = data["curve"]
    reconciliation = data["reconciliation"]
    checks: list[dict[str, object]] = []

    checks.append(
        check_row(
            "HPFC row count",
            len(curve),
            EXPECTED_QUARTER_HOURS,
            0,
            len(curve) == EXPECTED_QUARTER_HOURS,
            "Full 2024 quarter-hour coverage.",
        )
    )
    checks.append(
        check_row(
            "Unique UTC timestamps",
            curve["timestamp_utc"].nunique(),
            EXPECTED_QUARTER_HOURS,
            0,
            curve["timestamp_utc"].nunique() == EXPECTED_QUARTER_HOURS,
            "UTC is the unambiguous primary key.",
        )
    )
    missing = int(curve.isna().sum().sum())
    checks.append(
        check_row(
            "Missing cells",
            missing,
            0,
            0,
            missing == 0,
            "No missing values in the final curve.",
        )
    )

    calibrated = reconciliation["is_calibration_product"].eq(1)
    calibration_error = float(
        reconciliation.loc[calibrated, "difference_eur_mwh"].abs().max()
    )
    checks.append(
        check_row(
            "Maximum calibration-product error (EUR/MWh)",
            calibration_error,
            0.0,
            CALIBRATION_TOLERANCE,
            calibration_error <= CALIBRATION_TOLERANCE,
            "M01-M03 and Q2-Q4 Base/Peak must tie exactly.",
        )
    )

    usable = reconciliation["market_activity"].gt(100)
    cross_check_error = float(
        reconciliation.loc[usable, "difference_eur_mwh"].abs().max()
    )
    checks.append(
        check_row(
            "Maximum usable-product error (EUR/MWh)",
            cross_check_error,
            0.0,
            CROSS_CHECK_TOLERANCE,
            cross_check_error <= CROSS_CHECK_TOLERANCE,
            "Includes CAL and Q1 consistency checks.",
        )
    )

    liquid_failures = int(
        reconciliation.loc[usable, "status"].eq("FAIL").sum()
    )
    checks.append(
        check_row(
            "Failed usable-product reconciliations",
            liquid_failures,
            0,
            0,
            liquid_failures == 0,
            "Every usable quote is calibrated or cross-checked.",
        )
    )

    uncovered = int(
        curve["calibration_product"]
        .isin(["M01", "M02", "M03", "Q2", "Q3", "Q4"])
        .eq(False)
        .sum()
    )
    checks.append(
        check_row(
            "Quarter-hours outside calibration coverage",
            uncovered,
            0,
            0,
            uncovered == 0,
            "The selected products cover the year without overlap or gaps.",
        )
    )

    minimum = float(curve["hpfc_price_eur_mwh"].min())
    checks.append(
        check_row(
            "Minimum HPFC price (EUR/MWh)",
            minimum,
            "> 0",
            None,
            minimum > 0,
            "Sanity check for this positive-price teaching curve.",
        )
    )
    return pd.DataFrame(checks)


def monthly_summary(
    curve: pd.DataFrame,
    day_ahead: pd.DataFrame,
) -> pd.DataFrame:
    timestamps = pd.to_datetime(curve["timestamp_utc"], utc=True)
    month = timestamps.dt.tz_convert("Europe/Berlin").dt.month
    summary = pd.DataFrame(
        {
            "month": month,
            "hpfc_eur_mwh": curve["hpfc_price_eur_mwh"],
            "realized_day_ahead_eur_mwh": day_ahead[
                "day_ahead_price_eur_mwh"
            ],
        }
    ).groupby("month", as_index=False).mean()

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(
        summary["month"],
        summary["hpfc_eur_mwh"],
        color=COLORS["HPFC"],
        marker="o",
        label="Value-neutral HPFC",
    )
    ax.plot(
        summary["month"],
        summary["realized_day_ahead_eur_mwh"],
        color=COLORS["DA"],
        marker="o",
        linestyle="--",
        label="Realized Day-Ahead",
    )
    ax.set(
        title="Monthly average HPFC versus realized 2024 Day-Ahead",
        xlabel="Month",
        ylabel="EUR/MWh",
        xticks=range(1, 13),
    )
    ax.grid(alpha=0.2)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(INSPECTION_DIR / "01_hpfc_monthly_average.png", dpi=160)
    plt.close(fig)
    return summary


def create_sample_weeks(curve: pd.DataFrame) -> pd.DataFrame:
    frame = curve.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
    frame["local"] = frame["timestamp"].dt.tz_convert("Europe/Berlin")
    frame["hour"] = frame["timestamp"].dt.floor("h")
    hourly = (
        frame.groupby("hour", as_index=False)
        .agg(
            hpfc_price_eur_mwh=("hpfc_price_eur_mwh", "mean"),
            is_peak=("is_peak", "max"),
        )
    )

    starts = [
        pd.Timestamp("2024-01-15", tz="Europe/Berlin").tz_convert("UTC"),
        pd.Timestamp("2024-04-15", tz="Europe/Berlin").tz_convert("UTC"),
        pd.Timestamp("2024-07-15", tz="Europe/Berlin").tz_convert("UTC"),
        pd.Timestamp("2024-10-14", tz="Europe/Berlin").tz_convert("UTC"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(12, 7), sharey=True)
    sample_rows: list[pd.DataFrame] = []
    for ax, start in zip(axes.flat, starts, strict=True):
        end = start + pd.Timedelta(days=7)
        sample = hourly.loc[
            hourly["hour"].ge(start) & hourly["hour"].lt(end)
        ].copy()
        sample["local"] = sample["hour"].dt.tz_convert("Europe/Berlin")
        sample_rows.append(sample)
        ax.plot(
            sample["local"],
            sample["hpfc_price_eur_mwh"],
            color=COLORS["HPFC"],
            linewidth=1.5,
        )
        peak_sample = sample.loc[sample["is_peak"].eq(1)]
        ax.scatter(
            peak_sample["local"],
            peak_sample["hpfc_price_eur_mwh"],
            color=COLORS["PEAK"],
            s=7,
            alpha=0.65,
            label="Peak hours",
        )
        ax.set_title(start.tz_convert("Europe/Berlin").strftime("Week of %d %b"))
        ax.grid(alpha=0.2)
        ax.tick_params(axis="x", rotation=25)

    axes[0, 0].legend(frameon=False, loc="upper left")
    fig.suptitle("Seasonal sample weeks of the value-neutral HPFC")
    fig.supxlabel("Europe/Berlin local time")
    fig.supylabel("EUR/MWh")
    fig.tight_layout()
    fig.savefig(INSPECTION_DIR / "02_hpfc_sample_weeks.png", dpi=160)
    plt.close(fig)
    return pd.concat(sample_rows, ignore_index=True)


def create_reconciliation_plot(reconciliation: pd.DataFrame) -> pd.DataFrame:
    usable = reconciliation.loc[
        reconciliation["market_activity"].gt(100)
    ].copy()
    order = ["CAL", "Q1", "Q2", "Q3", "Q4", "M01", "M02", "M03"]
    usable["order"] = usable["delivery_period"].map(
        {period: index for index, period in enumerate(order)}
    )
    usable = usable.sort_values(["order", "load_type"])
    labels = usable["delivery_period"] + " " + usable["load_type"].str.title()

    fig, ax = plt.subplots(figsize=(11, 5))
    colors = usable["load_type"].map(COLORS)
    ax.bar(labels, usable["difference_eur_mwh"], color=colors)
    ax.axhline(0, color="#0F172A", linewidth=0.8)
    ax.axhline(0.01, color="#94A3B8", linewidth=0.8, linestyle="--")
    ax.axhline(-0.01, color="#94A3B8", linewidth=0.8, linestyle="--")
    ax.set(
        title="HPFC minus futures quote for usable products",
        xlabel="Product",
        ylabel="Difference (EUR/MWh)",
        ylim=(-0.011, 0.011),
    )
    ax.tick_params(axis="x", rotation=45)
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    fig.savefig(INSPECTION_DIR / "03_contract_reconciliation.png", dpi=160)
    plt.close(fig)
    return usable.drop(columns=["order"])


def write_outputs(
    data: dict[str, pd.DataFrame],
    checks: pd.DataFrame,
    monthly: pd.DataFrame,
    sample_weeks: pd.DataFrame,
    usable_reconciliation: pd.DataFrame,
) -> None:
    checks.to_csv(INSPECTION_DIR / "hpfc_checks.csv", index=False)
    monthly.to_csv(INSPECTION_DIR / "hpfc_monthly_summary.csv", index=False)
    sample_weeks.to_csv(
        INSPECTION_DIR / "hpfc_sample_weeks_hourly.csv",
        index=False,
    )
    usable_reconciliation.to_csv(
        INSPECTION_DIR / "hpfc_usable_reconciliation.csv",
        index=False,
    )

    curve = data["curve"]
    reconciliation = data["reconciliation"]
    usable = reconciliation["market_activity"].gt(100)
    calibrated = reconciliation["is_calibration_product"].eq(1)
    payload = {
        "status": "OK" if checks["status"].eq("OK").all() else "FAIL",
        "checks_ok": int(checks["status"].eq("OK").sum()),
        "checks_total": len(checks),
        "curve_rows": len(curve),
        "hpfc_min_eur_mwh": round(
            float(curve["hpfc_price_eur_mwh"].min()), 4
        ),
        "hpfc_max_eur_mwh": round(
            float(curve["hpfc_price_eur_mwh"].max()), 4
        ),
        "maximum_calibration_error_eur_mwh": round(
            float(
                reconciliation.loc[
                    calibrated, "difference_eur_mwh"
                ].abs().max()
            ),
            8,
        ),
        "maximum_usable_product_error_eur_mwh": round(
            float(
                reconciliation.loc[usable, "difference_eur_mwh"].abs().max()
            ),
            8,
        ),
    }
    (INSPECTION_DIR / "hpfc_validation_summary.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )

    workbook_payload = {
        "summary": payload,
        "checks": checks.fillna("").to_dict(orient="records"),
        "parameters": data["parameters"].fillna("").to_dict(orient="records"),
        "reconciliation": reconciliation.fillna("").to_dict(orient="records"),
        "monthly": monthly.fillna("").to_dict(orient="records"),
    }
    (INSPECTION_DIR / "hpfc_workbook_data.json").write_text(
        json.dumps(workbook_payload, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    INSPECTION_DIR.mkdir(parents=True, exist_ok=True)
    data = load_data()
    checks = run_checks(data)
    monthly = monthly_summary(data["curve"], data["day_ahead"])
    sample_weeks = create_sample_weeks(data["curve"])
    usable_reconciliation = create_reconciliation_plot(
        data["reconciliation"]
    )
    write_outputs(
        data,
        checks,
        monthly,
        sample_weeks,
        usable_reconciliation,
    )

    print(checks.to_string(index=False))
    if not checks["status"].eq("OK").all():
        raise SystemExit("HPFC validation failed.")
    print(f"\nHPFC validation passed. Inspection files: {INSPECTION_DIR}")


if __name__ == "__main__":
    main()
