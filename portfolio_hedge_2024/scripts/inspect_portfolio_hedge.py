"""Validate and visualize the 2024 portfolio hedge and Day-Ahead layer."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

MODEL_DIR = Path(__file__).resolve().parents[1]
PROCESSED_DIR = MODEL_DIR / "processed"
INSPECTION_DIR = MODEL_DIR / "inspection"

EXPECTED_QUARTER_HOURS = 35_136
EXPECTED_CUSTOMERS = 10_220
EXPECTED_ENERGY_MWH = 43_000
VALUE_TOLERANCE_EUR = 0.01
SETTLEMENT_TOLERANCE_EUR = 0.01

COLORS = {
    "UNHEDGED": "#64748B",
    "COARSE_CAL": "#2563EB",
    "GRANULAR": "#0F766E",
    "HB": "#2563EB",
    "GB": "#EA580C",
    "LB": "#16A34A",
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
        "assumptions": pd.read_csv(
            PROCESSED_DIR / "portfolio_assumptions_resolved.csv"
        ),
        "forecast": pd.read_csv(PROCESSED_DIR / "portfolio_forecast_2024.csv"),
        "positions": pd.read_csv(PROCESSED_DIR / "hedge_positions.csv"),
        "diagnostics": pd.read_csv(
            PROCESSED_DIR / "optimizer_diagnostics.csv"
        ),
        "timeseries": pd.read_csv(
            PROCESSED_DIR / "hedge_day_ahead_timeseries.csv"
        ),
        "summary": pd.read_csv(PROCESSED_DIR / "strategy_summary.csv"),
    }


def summary_value(
    summary: pd.DataFrame,
    strategy: str,
    column: str,
) -> float:
    match = summary.loc[summary["strategy"].eq(strategy), column]
    if len(match) != 1:
        raise ValueError(f"Expected one summary row for {strategy}")
    return float(match.iloc[0])


def run_checks(data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    assumptions = data["assumptions"]
    forecast = data["forecast"]
    positions = data["positions"]
    diagnostics = data["diagnostics"]
    summary = data["summary"]
    checks: list[dict[str, object]] = []

    checks.append(
        check_row(
            "Portfolio customer count",
            int(assumptions["customer_count"].sum()),
            EXPECTED_CUSTOMERS,
            0,
            int(assumptions["customer_count"].sum()) == EXPECTED_CUSTOMERS,
            "HB must strongly dominate customer count.",
        )
    )
    checks.append(
        check_row(
            "Forecast annual energy (MWh)",
            float(forecast["total_forecast_mwh"].sum()),
            EXPECTED_ENERGY_MWH,
            1e-6,
            np.isclose(
                forecast["total_forecast_mwh"].sum(),
                EXPECTED_ENERGY_MWH,
                atol=1e-6,
            ),
            "Portfolio assumptions imply 43 GWh.",
        )
    )
    checks.append(
        check_row(
            "Forecast row count",
            len(forecast),
            EXPECTED_QUARTER_HOURS,
            0,
            len(forecast) == EXPECTED_QUARTER_HOURS,
            "Full leap-year quarter-hour coverage.",
        )
    )
    missing = sum(
        int(frame.isna().sum().sum())
        for frame in (
            forecast,
            positions,
            diagnostics,
            data["timeseries"],
            summary,
        )
    )
    checks.append(
        check_row(
            "Missing cells in model outputs",
            missing,
            0,
            0,
            missing == 0,
            "All output tables must be complete.",
        )
    )

    hedged = summary["strategy"].isin(["COARSE_CAL", "GRANULAR"])
    value_error = float(
        summary.loc[hedged, "value_neutral_difference_eur"].abs().max()
    )
    checks.append(
        check_row(
            "Maximum hedge value-neutrality error (EUR)",
            value_error,
            0.0,
            VALUE_TOLERANCE_EUR,
            value_error <= VALUE_TOLERANCE_EUR,
            "Hedge and forecast load have equal HPFC value.",
        )
    )

    solver_failures = int(diagnostics["status"].ne("OK").sum())
    checks.append(
        check_row(
            "Failed optimization blocks",
            solver_failures,
            0,
            0,
            solver_failures == 0,
            "Every non-overlapping period solved successfully.",
        )
    )
    minimum_volume = float(positions["volume_mw"].min())
    checks.append(
        check_row(
            "Minimum futures volume (MW)",
            minimum_volume,
            ">= 0",
            None,
            minimum_volume >= 0,
            "The teaching hedge uses long positions only.",
        )
    )
    minimum_activity = int(positions["market_activity"].min())
    checks.append(
        check_row(
            "Minimum selected market activity",
            minimum_activity,
            "> 100",
            None,
            minimum_activity > 100,
            "No deliberately illiquid product may be selected.",
        )
    )

    coarse_rmse = summary_value(summary, "COARSE_CAL", "residual_load_rmse_mw")
    granular_rmse = summary_value(summary, "GRANULAR", "residual_load_rmse_mw")
    checks.append(
        check_row(
            "Granular residual RMSE improvement (MW)",
            coarse_rmse - granular_rmse,
            "> 0",
            None,
            granular_rmse < coarse_rmse,
            "The granular hedge must fit the forecast shape better.",
        )
    )

    settlement_error = float(
        summary.loc[hedged, "settlement_equivalence_error_eur"].abs().max()
    )
    checks.append(
        check_row(
            "Maximum settlement equivalence error (EUR)",
            settlement_error,
            0.0,
            SETTLEMENT_TOLERANCE_EUR,
            settlement_error <= SETTLEMENT_TOLERANCE_EUR,
            "Physical-residual and financial-payoff views must agree.",
        )
    )

    minimum_saving = float(
        summary.loc[hedged, "saving_vs_unhedged_eur"].min()
    )
    checks.append(
        check_row(
            "Minimum hedge saving versus unhedged (EUR)",
            minimum_saving,
            "> 0",
            None,
            minimum_saving > 0,
            "Synthetic futures should produce a small positive saving.",
        )
    )
    return pd.DataFrame(checks)


def create_portfolio_plot(assumptions: pd.DataFrame) -> pd.DataFrame:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    codes = assumptions["profile_code"]
    colors = [COLORS[code] for code in codes]
    axes[0].bar(codes, assumptions["customer_count"], color=colors)
    axes[0].set(
        title="Customers by profile",
        ylabel="Customer count (log scale)",
        yscale="log",
    )
    axes[1].bar(codes, assumptions["annual_portfolio_mwh"], color=colors)
    axes[1].set(
        title="Annual portfolio energy by profile",
        ylabel="MWh",
    )
    for ax in axes:
        ax.grid(axis="y", alpha=0.2)
    fig.suptitle("Teaching portfolio composition")
    fig.tight_layout()
    fig.savefig(INSPECTION_DIR / "01_portfolio_composition.png", dpi=160)
    plt.close(fig)
    return assumptions.copy()


def create_sample_week_plot(timeseries: pd.DataFrame) -> pd.DataFrame:
    frame = timeseries.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
    start = pd.Timestamp("2024-01-15", tz="Europe/Berlin").tz_convert("UTC")
    end = start + pd.Timedelta(days=7)
    sample = frame.loc[
        frame["timestamp"].ge(start) & frame["timestamp"].lt(end)
    ].copy()
    sample["timestamp_local_plot"] = sample["timestamp"].dt.tz_convert(
        "Europe/Berlin"
    )

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(
        sample["timestamp_local_plot"],
        sample["forecast_load_mw"],
        color="#0F172A",
        linewidth=2,
        label="Forecast load",
    )
    ax.plot(
        sample["timestamp_local_plot"],
        sample["coarse_cal_hedge_energy_mwh"] * 4,
        color=COLORS["COARSE_CAL"],
        label="CAL hedge",
    )
    ax.plot(
        sample["timestamp_local_plot"],
        sample["granular_hedge_energy_mwh"] * 4,
        color=COLORS["GRANULAR"],
        label="Granular hedge",
    )
    ax.set(
        title="Forecast and optimized hedge shapes — sample week",
        xlabel="Europe/Berlin local time",
        ylabel="MW",
    )
    ax.grid(alpha=0.2)
    ax.legend(frameon=False, ncol=3)
    ax.tick_params(axis="x", rotation=25)
    fig.tight_layout()
    fig.savefig(INSPECTION_DIR / "02_sample_week_hedge_shape.png", dpi=160)
    plt.close(fig)
    return sample


def create_residual_duration_plot(timeseries: pd.DataFrame) -> pd.DataFrame:
    residuals = pd.DataFrame(
        {
            "rank": np.arange(1, len(timeseries) + 1),
            "coarse_absolute_residual_mw": np.sort(
                np.abs(timeseries["coarse_cal_residual_da_mwh"].to_numpy() * 4)
            )[::-1],
            "granular_absolute_residual_mw": np.sort(
                np.abs(timeseries["granular_residual_da_mwh"].to_numpy() * 4)
            )[::-1],
        }
    )
    residuals["exceedance_share"] = residuals["rank"] / len(residuals)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(
        residuals["exceedance_share"],
        residuals["coarse_absolute_residual_mw"],
        color=COLORS["COARSE_CAL"],
        label="CAL hedge",
    )
    ax.plot(
        residuals["exceedance_share"],
        residuals["granular_absolute_residual_mw"],
        color=COLORS["GRANULAR"],
        label="Granular hedge",
    )
    ax.set(
        title="Absolute Day-Ahead shaping residual duration curve",
        xlabel="Share of quarter-hours exceeded",
        ylabel="Absolute residual (MW)",
    )
    ax.grid(alpha=0.2)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(INSPECTION_DIR / "03_residual_duration_curve.png", dpi=160)
    plt.close(fig)
    return residuals


def create_cost_plot(summary: pd.DataFrame) -> pd.DataFrame:
    ordered = summary.set_index("strategy").loc[
        ["UNHEDGED", "COARSE_CAL", "GRANULAR"]
    ].reset_index()
    labels = ["Unhedged", "CAL hedge", "Granular hedge"]
    values = ordered["average_procurement_price_eur_mwh"]
    colors = [COLORS[strategy] for strategy in ordered["strategy"]]

    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(labels, values, color=colors)
    ax.bar_label(bars, fmt="€%.2f/MWh", padding=4)
    ax.set(
        title="Forecast procurement cost before imbalance",
        ylabel="EUR/MWh",
        ylim=(0, values.max() * 1.12),
    )
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    fig.savefig(INSPECTION_DIR / "04_procurement_cost_comparison.png", dpi=160)
    plt.close(fig)
    return ordered


def write_outputs(
    data: dict[str, pd.DataFrame],
    checks: pd.DataFrame,
    portfolio_plot_data: pd.DataFrame,
    sample_week: pd.DataFrame,
    residual_duration: pd.DataFrame,
    cost_summary: pd.DataFrame,
) -> None:
    checks.to_csv(INSPECTION_DIR / "portfolio_hedge_checks.csv", index=False)
    portfolio_plot_data.to_csv(
        INSPECTION_DIR / "portfolio_composition_summary.csv",
        index=False,
    )
    sample_week.to_csv(
        INSPECTION_DIR / "sample_week_hedge_shape.csv",
        index=False,
    )
    residual_duration.to_csv(
        INSPECTION_DIR / "residual_duration_curve.csv",
        index=False,
    )
    cost_summary.to_csv(
        INSPECTION_DIR / "cost_comparison_summary.csv",
        index=False,
    )

    summary = data["summary"]
    payload = {
        "status": "OK" if checks["status"].eq("OK").all() else "FAIL",
        "checks_ok": int(checks["status"].eq("OK").sum()),
        "checks_total": len(checks),
        "portfolio_customers": int(
            data["assumptions"]["customer_count"].sum()
        ),
        "portfolio_energy_mwh": round(
            float(data["forecast"]["total_forecast_mwh"].sum()),
            4,
        ),
        "coarse_saving_eur": round(
            summary_value(
                summary,
                "COARSE_CAL",
                "saving_vs_unhedged_eur",
            ),
            2,
        ),
        "granular_saving_eur": round(
            summary_value(
                summary,
                "GRANULAR",
                "saving_vs_unhedged_eur",
            ),
            2,
        ),
        "coarse_residual_rmse_mw": round(
            summary_value(
                summary,
                "COARSE_CAL",
                "residual_load_rmse_mw",
            ),
            6,
        ),
        "granular_residual_rmse_mw": round(
            summary_value(
                summary,
                "GRANULAR",
                "residual_load_rmse_mw",
            ),
            6,
        ),
    }
    (INSPECTION_DIR / "portfolio_hedge_validation_summary.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )

    workbook_payload = {
        "summary": payload,
        "checks": checks.fillna("").to_dict(orient="records"),
        "assumptions": data["assumptions"].fillna("").to_dict(
            orient="records"
        ),
        "positions": data["positions"].fillna("").to_dict(orient="records"),
        "diagnostics": data["diagnostics"].fillna("").to_dict(orient="records"),
        "strategies": summary.fillna("").to_dict(orient="records"),
    }
    (INSPECTION_DIR / "portfolio_hedge_workbook_data.json").write_text(
        json.dumps(workbook_payload, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    INSPECTION_DIR.mkdir(parents=True, exist_ok=True)
    data = load_data()
    checks = run_checks(data)
    portfolio_plot_data = create_portfolio_plot(data["assumptions"])
    sample_week = create_sample_week_plot(data["timeseries"])
    residual_duration = create_residual_duration_plot(data["timeseries"])
    cost_summary = create_cost_plot(data["summary"])
    write_outputs(
        data,
        checks,
        portfolio_plot_data,
        sample_week,
        residual_duration,
        cost_summary,
    )

    print(checks.to_string(index=False))
    if not checks["status"].eq("OK").all():
        raise SystemExit("Portfolio hedge validation failed.")
    print(
        f"\nPortfolio hedge validation passed. Inspection files: "
        f"{INSPECTION_DIR}"
    )


if __name__ == "__main__":
    main()

