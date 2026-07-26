"""Validate and visualize the generated 2024 teaching dataset."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PIPELINE_DIR = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PIPELINE_DIR / "processed"
INSPECTION_DIR = PIPELINE_DIR / "inspection"
EXPECTED_QUARTER_HOURS = 35_136
ACTIVITY_THRESHOLD = 100
TARGET_GAIN = 1.25

COLORS = {
    "HB": "#2563EB",
    "GB": "#EA580C",
    "LB": "#16A34A",
    "DA": "#334155",
    "IMB": "#DC2626",
    "FORWARD": "#0F766E",
}


def load_data() -> dict[str, pd.DataFrame]:
    return {
        "slp": pd.read_csv(PROCESSED_DIR / "slp_profiles.csv"),
        "da": pd.read_csv(PROCESSED_DIR / "day_ahead_prices.csv"),
        "imb": pd.read_csv(PROCESSED_DIR / "imbalance_prices.csv"),
        "shape": pd.read_csv(PROCESSED_DIR / "shape_factors.csv"),
        "futures": pd.read_csv(PROCESSED_DIR / "futures_prices.csv"),
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
        "tolerance": "" if tolerance is None else tolerance,
        "status": "OK" if ok else "FAIL",
        "notes": notes,
    }


def period_months(period: str) -> list[int]:
    if period == "CAL":
        return list(range(1, 13))
    if period.startswith("Q"):
        start = (int(period[1]) - 1) * 3 + 1
        return [start, start + 1, start + 2]
    return [int(period[1:])]


def run_checks(data: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    checks: list[dict[str, object]] = []
    for name in ("slp", "da", "imb", "shape"):
        frame = data[name]
        checks.append(
            check_row(
                f"{name}: row count",
                len(frame),
                EXPECTED_QUARTER_HOURS,
                0,
                len(frame) == EXPECTED_QUARTER_HOURS,
                "Full leap-year quarter-hour coverage.",
            )
        )
        checks.append(
            check_row(
                f"{name}: missing cells",
                int(frame.isna().sum().sum()),
                0,
                0,
                not frame.isna().any().any(),
                "No missing values allowed in teaching files.",
            )
        )
        checks.append(
            check_row(
                f"{name}: unique timestamps",
                frame["timestamp_utc"].nunique(),
                EXPECTED_QUARTER_HOURS,
                0,
                frame["timestamp_utc"].nunique() == EXPECTED_QUARTER_HOURS,
                "UTC is the unambiguous primary key.",
            )
        )

    slp = data["slp"]
    for profile in ("hb", "gb", "lb"):
        total = float(slp[f"{profile}_normalized_kwh"].sum())
        checks.append(
            check_row(
                f"{profile.upper()} annual normalization (kWh)",
                round(total, 6),
                1_000_000,
                0.01,
                abs(total - 1_000_000) <= 0.01,
                "Each official SLP represents 1,000 MWh per year.",
            )
        )

    shape_mean = float(data["shape"]["historical_shape_factor"].mean())
    checks.append(
        check_row(
            "Shape-factor annual mean",
            round(shape_mean, 8),
            1.0,
            1e-6,
            abs(shape_mean - 1.0) <= 1e-6,
            "Derived historical factor is normalized to 1.",
        )
    )

    timestamps = pd.to_datetime(data["da"]["timestamp_utc"], utc=True)
    local_month = timestamps.dt.tz_convert("Europe/Berlin").dt.month
    is_peak = data["shape"]["is_peak"].astype(bool)
    da_price = data["da"]["day_ahead_price_eur_mwh"]
    futures = data["futures"].copy()

    realized_rows = []
    for row in futures.itertuples(index=False):
        months = period_months(row.delivery_period)
        mask = local_month.isin(months)
        if row.load_type == "PEAK":
            mask &= is_peak
        realized = float(da_price[mask].mean())
        realized_rows.append(
            {
                "load_type": row.load_type,
                "delivery_period": row.delivery_period,
                "price_eur_mwh": row.price_eur_mwh,
                "market_activity": row.market_activity,
                "realized_da_average_eur_mwh": realized,
                "realized_gain_eur_mwh": realized - row.price_eur_mwh,
            }
        )

    realized = pd.DataFrame(realized_rows)
    liquid = realized["market_activity"] >= ACTIVITY_THRESHOLD
    liquid_gain = float(realized.loc[liquid, "realized_gain_eur_mwh"].mean())
    max_liquid_gain_error = float(
        (realized.loc[liquid, "realized_gain_eur_mwh"] - TARGET_GAIN).abs().max()
    )
    checks.append(
        check_row(
            "Liquid-product mean ex-post gain (EUR/MWh)",
            round(liquid_gain, 4),
            TARGET_GAIN,
            0.02,
            max_liquid_gain_error <= 0.02,
            "Synthetic quotes target a small positive teaching-case gain.",
        )
    )

    intended = realized["delivery_period"].isin(
        ["M01", "M02", "M03", "Q2", "Q3", "Q4"]
    )
    intended &= liquid
    intended_min = float(realized.loc[intended, "realized_gain_eur_mwh"].min())
    checks.append(
        check_row(
            "Mixed granular set: minimum gain (EUR/MWh)",
            round(intended_min, 4),
            "> 0",
            None,
            intended_min > 0,
            "M01-M03 and Q2-Q4 all deliver positive ex-post payoff.",
        )
    )

    return pd.DataFrame(checks), realized


def create_plot_slp(slp: pd.DataFrame) -> pd.DataFrame:
    local = pd.to_datetime(slp["timestamp_utc"], utc=True).dt.tz_convert(
        "Europe/Berlin"
    )
    quarter = local.dt.hour * 4 + local.dt.minute // 15
    profile = pd.DataFrame(
        {
            "quarter": quarter,
            "HB": slp["hb_normalized_kwh"],
            "GB": slp["gb_normalized_kwh"],
            "LB": slp["lb_normalized_kwh"],
        }
    ).groupby("quarter", as_index=False).mean()
    profile["hour"] = profile["quarter"] / 4

    fig, ax = plt.subplots(figsize=(10, 5))
    for code in ("HB", "GB", "LB"):
        ax.plot(profile["hour"], profile[code], label=code, color=COLORS[code])
    ax.set(
        title="Average official Berlin SLP shape by time of day",
        xlabel="Local hour",
        ylabel="Normalized quarter-hour energy (kWh)",
        xlim=(0, 23.75),
    )
    ax.grid(alpha=0.2)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(INSPECTION_DIR / "01_slp_daily_profiles.png", dpi=160)
    plt.close(fig)
    return profile


def create_plot_prices(
    da: pd.DataFrame, imbalance: pd.DataFrame
) -> pd.DataFrame:
    local = pd.to_datetime(da["timestamp_utc"], utc=True).dt.tz_convert(
        "Europe/Berlin"
    )
    monthly = pd.DataFrame(
        {
            "month": local.dt.month,
            "day_ahead_eur_mwh": da["day_ahead_price_eur_mwh"],
            "imbalance_eur_mwh": imbalance["imbalance_price_eur_mwh"],
        }
    ).groupby("month", as_index=False).mean()

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(
        monthly["month"],
        monthly["day_ahead_eur_mwh"],
        marker="o",
        label="Day-Ahead",
        color=COLORS["DA"],
    )
    ax.plot(
        monthly["month"],
        monthly["imbalance_eur_mwh"],
        marker="o",
        label="reBAP",
        color=COLORS["IMB"],
    )
    ax.set(
        title="Observed 2024 monthly average market prices",
        xlabel="Month",
        ylabel="EUR/MWh",
        xticks=range(1, 13),
    )
    ax.grid(alpha=0.2)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(INSPECTION_DIR / "02_monthly_market_prices.png", dpi=160)
    plt.close(fig)
    return monthly


def create_plot_shape(shape: pd.DataFrame) -> pd.DataFrame:
    weekday = (
        shape.loc[shape["weekday"] < 5]
        .groupby(["month", "hour"], as_index=False)["historical_shape_factor"]
        .mean()
    )
    matrix = weekday.pivot(
        index="month", columns="hour", values="historical_shape_factor"
    )

    fig, ax = plt.subplots(figsize=(11, 5))
    image = ax.imshow(matrix, aspect="auto", cmap="viridis", origin="lower")
    ax.set(
        title="Historical weekday shape factor used for the 2024 HPFC",
        xlabel="Local hour",
        ylabel="Month",
        xticks=range(0, 24, 2),
        yticks=range(12),
        yticklabels=range(1, 13),
    )
    fig.colorbar(image, ax=ax, label="Shape factor")
    fig.tight_layout()
    fig.savefig(INSPECTION_DIR / "03_shape_factor_heatmap.png", dpi=160)
    plt.close(fig)
    return weekday


def create_plot_futures(realized: pd.DataFrame) -> pd.DataFrame:
    order = ["CAL", "Q1", "Q2", "Q3", "Q4"] + [
        f"M{month:02d}" for month in range(1, 13)
    ]
    base = realized.loc[realized["load_type"] == "BASE"].copy()
    base["order"] = base["delivery_period"].map({name: i for i, name in enumerate(order)})
    base = base.sort_values("order")

    fig, left = plt.subplots(figsize=(13, 5))
    x = np.arange(len(base))
    left.plot(
        x,
        base["price_eur_mwh"],
        marker="o",
        color=COLORS["FORWARD"],
        label="Synthetic forward",
    )
    left.plot(
        x,
        base["realized_da_average_eur_mwh"],
        marker=".",
        linestyle="--",
        color=COLORS["DA"],
        label="Realized DA block average",
    )
    left.set(
        title="Base products: teaching forward prices, realized prices and activity",
        ylabel="EUR/MWh",
        xticks=x,
        xticklabels=base["delivery_period"],
    )
    right = left.twinx()
    right.bar(
        x,
        base["market_activity"],
        alpha=0.16,
        color="#7C3AED",
        label="Market activity",
    )
    right.set_ylabel("Synthetic market activity")
    left.grid(axis="y", alpha=0.2)
    handles_left, labels_left = left.get_legend_handles_labels()
    handles_right, labels_right = right.get_legend_handles_labels()
    left.legend(
        handles_left + handles_right,
        labels_left + labels_right,
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.13),
        ncol=3,
    )
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(INSPECTION_DIR / "04_futures_and_activity.png", dpi=160)
    plt.close(fig)
    return base.drop(columns=["order"])


def write_summary(
    checks: pd.DataFrame,
    realized: pd.DataFrame,
    daily_profiles: pd.DataFrame,
    monthly_prices: pd.DataFrame,
    shape_summary: pd.DataFrame,
    futures_summary: pd.DataFrame,
) -> None:
    checks.to_csv(INSPECTION_DIR / "validation_checks.csv", index=False)
    realized.to_csv(INSPECTION_DIR / "futures_realized_comparison.csv", index=False)
    daily_profiles.to_csv(INSPECTION_DIR / "slp_daily_profile_summary.csv", index=False)
    monthly_prices.to_csv(INSPECTION_DIR / "monthly_price_summary.csv", index=False)
    shape_summary.to_csv(INSPECTION_DIR / "shape_factor_summary.csv", index=False)
    futures_summary.to_csv(INSPECTION_DIR / "futures_base_summary.csv", index=False)

    payload = {
        "status": "OK" if (checks["status"] == "OK").all() else "FAIL",
        "checks_ok": int((checks["status"] == "OK").sum()),
        "checks_total": len(checks),
        "failed_checks": checks.loc[
            checks["status"] != "OK", "check"
        ].tolist(),
        "liquid_product_gain_eur_mwh": round(
            float(
                realized.loc[
                    realized["market_activity"] >= ACTIVITY_THRESHOLD,
                    "realized_gain_eur_mwh",
                ].mean()
            ),
            4,
        ),
    }
    (INSPECTION_DIR / "validation_summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    workbook_payload = {
        "summary": payload,
        "checks": checks.to_dict(orient="records"),
        "futures": realized.round(6).to_dict(orient="records"),
        "daily_profiles": daily_profiles.round(6).to_dict(orient="records"),
        "monthly_prices": monthly_prices.round(6).to_dict(orient="records"),
        "sources": pd.read_csv(PROCESSED_DIR / "sources.csv")
        .fillna("")
        .to_dict(orient="records"),
    }
    (INSPECTION_DIR / "workbook_data.json").write_text(
        json.dumps(workbook_payload, indent=2), encoding="utf-8"
    )


def main() -> None:
    INSPECTION_DIR.mkdir(parents=True, exist_ok=True)
    data = load_data()
    checks, realized = run_checks(data)
    daily_profiles = create_plot_slp(data["slp"])
    monthly_prices = create_plot_prices(data["da"], data["imb"])
    shape_summary = create_plot_shape(data["shape"])
    futures_summary = create_plot_futures(realized)
    write_summary(
        checks,
        realized,
        daily_profiles,
        monthly_prices,
        shape_summary,
        futures_summary,
    )

    print(checks.to_string(index=False))
    if not (checks["status"] == "OK").all():
        raise SystemExit("Dataset validation failed.")
    print(f"\nValidation passed. Inspection files: {INSPECTION_DIR}")


if __name__ == "__main__":
    main()
