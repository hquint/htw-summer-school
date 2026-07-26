"""Validate and visualize the final 2024 procurement-cost backtest."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/htw-matplotlib")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

MODEL_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = MODEL_DIR.parent
INPUT_DIR = MODEL_DIR / "inputs"
PROCESSED_DIR = MODEL_DIR / "processed"
INSPECTION_DIR = MODEL_DIR / "inspection"
DATA_DIR = REPO_DIR / "data_pipeline_2024" / "processed"
HEDGE_DIR = REPO_DIR / "portfolio_hedge_2024" / "processed"

EXPECTED_QUARTER_HOURS = 35_136
STRATEGIES = ("UNHEDGED", "COARSE_CAL", "GRANULAR")
TOLERANCE_MWH = 1e-6
TOLERANCE_EUR = 0.01

COLORS = {
    "UNHEDGED": "#64748B",
    "COARSE_CAL": "#2563EB",
    "GRANULAR": "#0F766E",
    "FORECAST": "#64748B",
    "ACTUAL": "#DC2626",
    "IMBALANCE": "#EA580C",
    "PREMIUM": "#7C3AED",
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


def load_data() -> dict[str, object]:
    return {
        "parameters": pd.read_csv(
            INPUT_DIR / "simulation_parameters.csv"
        ),
        "profile_assumptions": pd.read_csv(
            INPUT_DIR / "profile_error_assumptions.csv"
        ),
        "actual": pd.read_csv(
            PROCESSED_DIR / "actual_portfolio_2024.csv"
        ),
        "profiles": pd.read_csv(
            PROCESSED_DIR / "actual_profile_summary.csv"
        ),
        "settlement": pd.read_csv(
            PROCESSED_DIR / "imbalance_settlement_timeseries.csv"
        ),
        "monthly": pd.read_csv(
            PROCESSED_DIR / "monthly_procurement_comparison.csv"
        ),
        "annual": pd.read_csv(
            PROCESSED_DIR / "annual_procurement_comparison.csv"
        ),
        "components": pd.read_csv(
            PROCESSED_DIR / "procurement_cost_components.csv"
        ),
        "procurement_pnl": pd.read_csv(
            PROCESSED_DIR / "procurement_cost_pnl.csv"
        ),
        "metadata": json.loads(
            (
                PROCESSED_DIR / "imbalance_backtest_metadata.json"
            ).read_text(encoding="utf-8")
        ),
        "seed_candidates": pd.read_csv(
            INSPECTION_DIR / "seed_selection_candidates.csv"
        ),
        "seed_audit": json.loads(
            (
                INSPECTION_DIR / "seed_selection_audit.json"
            ).read_text(encoding="utf-8")
        ),
        "source_rebap": pd.read_csv(
            DATA_DIR / "imbalance_prices.csv"
        ),
        "source_hedge_summary": pd.read_csv(
            HEDGE_DIR / "strategy_summary.csv"
        ),
    }


def strategy_value(
    annual: pd.DataFrame,
    strategy: str,
    column: str,
) -> float:
    match = annual.loc[annual["strategy"].eq(strategy), column]
    if len(match) != 1:
        raise ValueError(f"Expected one annual row for {strategy}")
    return float(match.iloc[0])


def run_checks(data: dict[str, object]) -> pd.DataFrame:
    parameters = data["parameters"]
    profile_assumptions = data["profile_assumptions"]
    actual = data["actual"]
    profiles = data["profiles"]
    settlement = data["settlement"]
    monthly = data["monthly"]
    annual = data["annual"]
    metadata = data["metadata"]
    seed_candidates = data["seed_candidates"]
    source_rebap = data["source_rebap"]
    source_hedge_summary = data["source_hedge_summary"]
    procurement_pnl = data["procurement_pnl"]
    frames = (
        parameters,
        profile_assumptions,
        actual,
        profiles,
        settlement,
        monthly,
        annual,
        seed_candidates,
        source_rebap,
        source_hedge_summary,
        procurement_pnl,
    )
    if not all(isinstance(frame, pd.DataFrame) for frame in frames):
        raise TypeError("Inspection table input is not a DataFrame")
    if not isinstance(metadata, dict):
        raise TypeError("Inspection metadata is not a dictionary")

    checks: list[dict[str, object]] = []
    parameter_values = parameters.set_index("parameter")["value"]
    locked_seed = int(float(parameter_values["locked_seed"]))
    checks.append(
        check_row(
            "Locked seed matches metadata",
            int(metadata["locked_seed"]),
            locked_seed,
            0,
            int(metadata["locked_seed"]) == locked_seed,
            "The production build must use the documented deterministic seed.",
        )
    )
    checks.append(
        check_row(
            "Quarter-hour row count",
            len(settlement),
            EXPECTED_QUARTER_HOURS,
            0,
            len(settlement) == EXPECTED_QUARTER_HOURS,
            "Complete leap-year quarter-hour coverage.",
        )
    )
    missing = sum(
        int(frame.isna().sum().sum())
        for frame in (
            actual,
            profiles,
            settlement,
            monthly,
            annual,
        )
    )
    checks.append(
        check_row(
            "Missing cells in model outputs",
            missing,
            0,
            0,
            missing == 0,
            "All final output tables must be complete.",
        )
    )

    assumptions_by_profile = profile_assumptions.set_index("profile_code")
    expected_actual_energy = sum(
        float(row.forecast_energy_mwh)
        * (
            1.0
            + float(
                assumptions_by_profile.loc[row.profile_code, "annual_bias"]
            )
        )
        for row in profiles.itertuples(index=False)
    )
    actual_energy = float(actual["total_actual_mwh"].sum())
    checks.append(
        check_row(
            "Actual annual energy matches profile biases (MWh)",
            actual_energy,
            expected_actual_energy,
            TOLERANCE_MWH,
            np.isclose(
                actual_energy,
                expected_actual_energy,
                atol=TOLERANCE_MWH,
                rtol=0.0,
            ),
            "Energy-weighted random shocks are centered by profile.",
        )
    )
    profile_energy_difference = abs(
        float(profiles["actual_energy_mwh"].sum()) - actual_energy
    )
    checks.append(
        check_row(
            "Profile actual energy reconciles to portfolio (MWh)",
            profile_energy_difference,
            0.0,
            TOLERANCE_MWH,
            profile_energy_difference <= TOLERANCE_MWH,
            "HB, GB and LB actual energy must sum to portfolio actual energy.",
        )
    )
    clipped = int(profiles["clipped_quarter_hours"].sum())
    checks.append(
        check_row(
            "Clipped profile quarter-hours",
            clipped,
            0,
            0,
            clipped == 0,
            "Selected seed remains inside the configured factor bounds.",
        )
    )
    nmae = float(
        settlement["imbalance_volume_mwh"].abs().sum()
        / settlement["total_forecast_mwh"].sum()
    )
    checks.append(
        check_row(
            "Portfolio normalized mean absolute error",
            nmae,
            "1.5% to 3.0%",
            None,
            0.015 <= nmae <= 0.03,
            "Aggregate forecast error should be visible but plausible.",
        )
    )
    rebap_error = float(
        (
            settlement["imbalance_price_eur_mwh"]
            - source_rebap["imbalance_price_eur_mwh"]
        )
        .abs()
        .max()
    )
    checks.append(
        check_row(
            "Observed reBAP source alignment (EUR/MWh)",
            rebap_error,
            0.0,
            0.0,
            rebap_error == 0.0,
            "The backtest must not modify the observed imbalance prices.",
        )
    )
    volume_error = float(
        (
            settlement["imbalance_volume_mwh"]
            - (
                settlement["total_actual_mwh"]
                - settlement["total_forecast_mwh"]
            )
        )
        .abs()
        .max()
    )
    checks.append(
        check_row(
            "Maximum imbalance-volume identity error (MWh)",
            volume_error,
            0.0,
            TOLERANCE_MWH,
            volume_error <= TOLERANCE_MWH,
            "Imbalance volume equals actual minus forecast schedule.",
        )
    )
    settlement_error = float(
        (
            settlement["imbalance_settlement_eur"]
            - settlement["imbalance_volume_mwh"]
            * settlement["imbalance_price_eur_mwh"]
        )
        .abs()
        .max()
    )
    checks.append(
        check_row(
            "Maximum reBAP settlement identity error (EUR)",
            settlement_error,
            0.0,
            TOLERANCE_EUR,
            settlement_error <= TOLERANCE_EUR,
            "Signed imbalance volume is settled at observed reBAP.",
        )
    )
    premium_error = float(
        (
            settlement["imbalance_premium_eur"]
            - settlement["imbalance_volume_mwh"]
            * (
                settlement["imbalance_price_eur_mwh"]
                - settlement["day_ahead_price_eur_mwh"]
            )
        )
        .abs()
        .max()
    )
    checks.append(
        check_row(
            "Maximum imbalance-premium identity error (EUR)",
            premium_error,
            0.0,
            TOLERANCE_EUR,
            premium_error <= TOLERANCE_EUR,
            "Premium isolates reBAP versus Day-Ahead pricing of the deviation.",
        )
    )
    final_identity_error = max(
        float(
            (
                settlement[f"{strategy.lower()}_final_procurement_cost_eur"]
                - settlement[
                    f"{strategy.lower()}_forecast_procurement_cost_eur"
                ]
                - settlement["imbalance_settlement_eur"]
            )
            .abs()
            .max()
        )
        for strategy in STRATEGIES
    )
    checks.append(
        check_row(
            "Maximum final-cost identity error (EUR)",
            final_identity_error,
            0.0,
            TOLERANCE_EUR,
            final_identity_error <= TOLERANCE_EUR,
            "Final cost equals forecast procurement plus imbalance settlement.",
        )
    )
    annual_component_error = float(
        (
            annual["final_procurement_cost_eur"]
            - annual["forecast_procurement_cost_eur"]
            - annual["imbalance_settlement_eur"]
        )
        .abs()
        .max()
    )
    checks.append(
        check_row(
            "Maximum annual cost-component error (EUR)",
            annual_component_error,
            0.0,
            TOLERANCE_EUR,
            annual_component_error <= TOLERANCE_EUR,
            "Annual cost bridge must reconcile for every strategy.",
        )
    )
    component_lines = procurement_pnl.loc[
        procurement_pnl["classification"].eq("COST_COMPONENT")
    ]
    subtotal_lines = procurement_pnl.loc[
        procurement_pnl["classification"].eq("SUBTOTAL")
    ].set_index("strategy")
    pnl_reconciliation_error = max(
        abs(
            float(
                component_lines.loc[
                    component_lines["strategy"].eq(strategy),
                    "amount_eur",
                ].sum()
            )
            - float(subtotal_lines.loc[strategy, "amount_eur"])
        )
        for strategy in STRATEGIES
    )
    checks.append(
        check_row(
            "Maximum procurement P&L reconciliation error (EUR)",
            pnl_reconciliation_error,
            0.0,
            TOLERANCE_EUR,
            pnl_reconciliation_error <= TOLERANCE_EUR,
            "Cost-component lines must sum to final procurement cost.",
        )
    )

    monthly_rollup_error = max(
        abs(
            float(
                monthly.loc[
                    monthly["strategy"].eq(strategy),
                    "final_procurement_cost_eur",
                ].sum()
            )
            - strategy_value(
                annual,
                strategy,
                "final_procurement_cost_eur",
            )
        )
        for strategy in STRATEGIES
    )
    checks.append(
        check_row(
            "Maximum monthly-to-annual rollup error (EUR)",
            monthly_rollup_error,
            0.0,
            TOLERANCE_EUR,
            monthly_rollup_error <= TOLERANCE_EUR,
            "Twelve monthly costs must sum to each annual result.",
        )
    )
    minimum_saving = min(
        strategy_value(annual, strategy, "saving_vs_unhedged_eur")
        for strategy in ("COARSE_CAL", "GRANULAR")
    )
    checks.append(
        check_row(
            "Minimum realized hedge saving (EUR)",
            minimum_saving,
            "> 0",
            None,
            minimum_saving > 0,
            "Both teaching hedges remain slightly cheaper after imbalance.",
        )
    )
    hedge_summary = source_hedge_summary.set_index("strategy")
    saving_tie_error = max(
        abs(
            strategy_value(annual, strategy, "saving_vs_unhedged_eur")
            - float(
                hedge_summary.loc[strategy, "saving_vs_unhedged_eur"]
            )
        )
        for strategy in ("COARSE_CAL", "GRANULAR")
    )
    checks.append(
        check_row(
            "Maximum hedge-saving tie error before/after imbalance (EUR)",
            saving_tie_error,
            0.0,
            TOLERANCE_EUR,
            saving_tie_error <= TOLERANCE_EUR,
            "Identical load forecast error must not change hedge savings.",
        )
    )
    premium_per_mwh = float(
        annual["imbalance_premium_eur"].iloc[0]
        / annual["actual_energy_mwh"].iloc[0]
    )
    checks.append(
        check_row(
            "Imbalance premium (EUR/MWh actual)",
            premium_per_mwh,
            "0.10 to 1.50",
            None,
            0.10 <= premium_per_mwh <= 1.50,
            "Selected seed gives a moderate positive cost of forecast error.",
        )
    )
    unhedged_std = strategy_value(
        annual,
        "UNHEDGED",
        "monthly_average_price_std_eur_mwh",
    )
    maximum_hedged_std = max(
        strategy_value(
            annual,
            strategy,
            "monthly_average_price_std_eur_mwh",
        )
        for strategy in ("COARSE_CAL", "GRANULAR")
    )
    checks.append(
        check_row(
            "Maximum hedged monthly volatility versus unhedged",
            maximum_hedged_std,
            f"< {unhedged_std:.6f}",
            None,
            maximum_hedged_std < unhedged_std,
            "Both hedges should reduce monthly procurement-price variability.",
        )
    )
    coarse_open = strategy_value(
        annual,
        "COARSE_CAL",
        "absolute_open_day_ahead_volume_mwh",
    )
    granular_open = strategy_value(
        annual,
        "GRANULAR",
        "absolute_open_day_ahead_volume_mwh",
    )
    checks.append(
        check_row(
            "Granular reduction in absolute open DA volume (MWh)",
            coarse_open - granular_open,
            "> 0",
            None,
            granular_open < coarse_open,
            "Granular products should improve forecast-shape coverage.",
        )
    )
    return pd.DataFrame(checks)


def save_sample_week(settlement: pd.DataFrame) -> None:
    timestamp = pd.to_datetime(settlement["timestamp_utc"], utc=True)
    sample_start = pd.Timestamp("2024-01-15T00:00:00Z")
    sample_end = sample_start + pd.Timedelta(days=7)
    sample = settlement.loc[
        timestamp.between(sample_start, sample_end, inclusive="left"),
        [
            "timestamp_utc",
            "timestamp_local",
            "forecast_load_mw",
            "actual_load_mw",
            "forecast_error_mw",
            "imbalance_price_eur_mwh",
        ],
    ].copy()
    sample.to_csv(
        INSPECTION_DIR / "sample_week_actual_vs_forecast.csv",
        index=False,
    )

    plot_time = pd.to_datetime(sample["timestamp_utc"], utc=True)
    figure, axis = plt.subplots(figsize=(13, 5.5))
    axis.plot(
        plot_time,
        sample["forecast_load_mw"],
        color=COLORS["FORECAST"],
        linewidth=1.4,
        label="Forecast schedule",
    )
    axis.plot(
        plot_time,
        sample["actual_load_mw"],
        color=COLORS["ACTUAL"],
        linewidth=1.0,
        alpha=0.9,
        label="Synthetic actual",
    )
    axis.set_title("Portfolio forecast and synthetic actual load — sample week")
    axis.set_ylabel("MW")
    axis.grid(axis="y", alpha=0.25)
    axis.legend(frameon=False, ncol=2)
    figure.autofmt_xdate()
    figure.tight_layout()
    figure.savefig(
        INSPECTION_DIR / "01_sample_week_actual_vs_forecast.png",
        dpi=170,
    )
    plt.close(figure)


def plot_daily_forecast_error(settlement: pd.DataFrame) -> None:
    timestamp = pd.to_datetime(settlement["timestamp_utc"], utc=True)
    daily = (
        settlement.assign(
            date=timestamp.dt.tz_convert("Europe/Berlin").dt.strftime(
                "%Y-%m-%d"
            )
        )
        .groupby("date", as_index=False)
        .agg(
            forecast_mwh=("total_forecast_mwh", "sum"),
            actual_mwh=("total_actual_mwh", "sum"),
            imbalance_mwh=("imbalance_volume_mwh", "sum"),
        )
    )
    daily["absolute_imbalance_mwh"] = (
        settlement.assign(
            date=timestamp.dt.tz_convert("Europe/Berlin").dt.strftime(
                "%Y-%m-%d"
            )
        )
        .groupby("date")["imbalance_volume_mwh"]
        .apply(lambda series: float(series.abs().sum()))
        .to_numpy()
    )
    daily.to_csv(
        INSPECTION_DIR / "daily_forecast_error_summary.csv",
        index=False,
    )

    figure, axis = plt.subplots(figsize=(13, 5.2))
    dates = pd.to_datetime(daily["date"])
    axis.axhline(0, color="#334155", linewidth=0.8)
    axis.plot(
        dates,
        daily["imbalance_mwh"],
        color=COLORS["IMBALANCE"],
        linewidth=1.0,
    )
    axis.fill_between(
        dates,
        0,
        daily["imbalance_mwh"],
        color=COLORS["IMBALANCE"],
        alpha=0.18,
    )
    axis.set_title("Daily actual-minus-forecast energy")
    axis.set_ylabel("MWh")
    axis.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    figure.savefig(
        INSPECTION_DIR / "02_daily_forecast_error.png",
        dpi=170,
    )
    plt.close(figure)


def plot_monthly_imbalance(monthly: pd.DataFrame) -> None:
    unhedged = monthly.loc[monthly["strategy"].eq("UNHEDGED")].copy()
    unhedged.to_csv(
        INSPECTION_DIR / "monthly_imbalance_summary.csv",
        index=False,
    )
    positions = np.arange(len(unhedged))
    width = 0.38
    figure, axis = plt.subplots(figsize=(12, 5.4))
    axis.bar(
        positions - width / 2,
        unhedged["imbalance_settlement_eur"],
        width,
        color=COLORS["IMBALANCE"],
        label="reBAP settlement",
    )
    axis.bar(
        positions + width / 2,
        unhedged["imbalance_premium_eur"],
        width,
        color=COLORS["PREMIUM"],
        label="Premium vs Day-Ahead",
    )
    axis.axhline(0, color="#334155", linewidth=0.8)
    axis.set_xticks(positions, unhedged["month"].str[5:])
    axis.set_xlabel("2024 month")
    axis.set_ylabel("EUR")
    axis.set_title("Monthly imbalance settlement and price premium")
    axis.grid(axis="y", alpha=0.25)
    axis.legend(frameon=False, ncol=2)
    figure.tight_layout()
    figure.savefig(
        INSPECTION_DIR / "03_monthly_imbalance_cost.png",
        dpi=170,
    )
    plt.close(figure)


def plot_procurement_comparison(
    annual: pd.DataFrame,
    monthly: pd.DataFrame,
) -> None:
    annual.to_csv(
        INSPECTION_DIR / "final_procurement_summary.csv",
        index=False,
    )
    figure, axes = plt.subplots(1, 2, figsize=(13, 5.3))
    strategy_colors = [COLORS[strategy] for strategy in annual["strategy"]]
    axes[0].bar(
        annual["strategy"],
        annual["final_average_price_eur_mwh"],
        color=strategy_colors,
    )
    axes[0].set_ylim(
        0,
        float(annual["final_average_price_eur_mwh"].max()) * 1.15,
    )
    axes[0].set_title("Final actual procurement price")
    axes[0].set_ylabel("EUR/MWh actual")
    axes[0].grid(axis="y", alpha=0.25)
    for index, value in enumerate(annual["final_average_price_eur_mwh"]):
        axes[0].text(
            index,
            value + 1.5,
            f"{value:.2f}",
            ha="center",
            fontsize=9,
        )

    hedged = annual.loc[annual["strategy"].ne("UNHEDGED")]
    axes[1].bar(
        hedged["strategy"],
        hedged["saving_vs_unhedged_eur_mwh"],
        color=[COLORS[strategy] for strategy in hedged["strategy"]],
    )
    axes[1].set_title("Realized saving versus unhedged")
    axes[1].set_ylabel("EUR/MWh actual")
    axes[1].grid(axis="y", alpha=0.25)
    for index, value in enumerate(hedged["saving_vs_unhedged_eur_mwh"]):
        axes[1].text(
            index,
            value + 0.03,
            f"{value:.2f}",
            ha="center",
            fontsize=9,
        )
    figure.tight_layout()
    figure.savefig(
        INSPECTION_DIR / "04_final_procurement_comparison.png",
        dpi=170,
    )
    plt.close(figure)

    pivot = monthly.pivot(
        index="month",
        columns="strategy",
        values="final_average_price_eur_mwh",
    ).reset_index()
    pivot.to_csv(
        INSPECTION_DIR / "monthly_procurement_price_summary.csv",
        index=False,
    )
    figure, axis = plt.subplots(figsize=(12, 5.5))
    for strategy in STRATEGIES:
        axis.plot(
            pivot["month"].str[5:],
            pivot[strategy],
            marker="o",
            linewidth=1.8,
            color=COLORS[strategy],
            label=strategy,
        )
    axis.set_title("Monthly final procurement price")
    axis.set_xlabel("2024 month")
    axis.set_ylabel("EUR/MWh actual")
    axis.grid(axis="y", alpha=0.25)
    axis.legend(frameon=False, ncol=3)
    figure.tight_layout()
    figure.savefig(
        INSPECTION_DIR / "05_monthly_procurement_price.png",
        dpi=170,
    )
    plt.close(figure)


def create_workbook_data(
    data: dict[str, object],
    checks: pd.DataFrame,
) -> None:
    parameters = data["parameters"]
    profile_assumptions = data["profile_assumptions"]
    profiles = data["profiles"]
    monthly = data["monthly"]
    annual = data["annual"]
    metadata = data["metadata"]
    seed_candidates = data["seed_candidates"]
    if not all(
        isinstance(frame, pd.DataFrame)
        for frame in (
            parameters,
            profile_assumptions,
            profiles,
            monthly,
            annual,
            seed_candidates,
        )
    ):
        raise TypeError("Workbook table input is not a DataFrame")
    if not isinstance(metadata, dict):
        raise TypeError("Workbook metadata is not a dictionary")

    combined_profiles = profiles.merge(
        profile_assumptions,
        on="profile_code",
        how="left",
        validate="one_to_one",
    )
    sources = [
        {
            "item": "Day-Ahead prices",
            "source_type": "Observed",
            "source_name": "SMARD / Bundesnetzagentur",
            "reference": (
                "data_pipeline_2024/processed/day_ahead_prices.csv"
            ),
            "notes": "Observed German/Luxembourg 2024 Day-Ahead prices.",
        },
        {
            "item": "Imbalance prices",
            "source_type": "Observed",
            "source_name": "Netztransparenz / German TSOs",
            "reference": (
                "https://www.netztransparenz.de/Regelenergie/"
                "Ausgleichsenergiepreis/reBAP"
            ),
            "notes": "Quality-assured symmetric 2024 reBAP.",
        },
        {
            "item": "Forecast portfolio and hedge",
            "source_type": "Model output",
            "source_name": "portfolio_hedge_2024",
            "reference": (
                "portfolio_hedge_2024/processed/"
                "hedge_day_ahead_timeseries.csv"
            ),
            "notes": "Value-neutral hedge and forecast Day-Ahead schedule.",
        },
        {
            "item": "Actual customer load",
            "source_type": "Synthetic assumption",
            "source_name": "imbalance_backtest_2024",
            "reference": (
                "inputs/profile_error_assumptions.csv and "
                "inputs/simulation_parameters.csv"
            ),
            "notes": (
                "Seeded profile-level deviations; no observed price is changed."
            ),
        },
    ]
    workbook_data = {
        "metadata": metadata,
        "parameters": parameters.to_dict(orient="records"),
        "profiles": combined_profiles.to_dict(orient="records"),
        "annual": annual.to_dict(orient="records"),
        "monthly": monthly.to_dict(orient="records"),
        "seed_candidates": seed_candidates.head(20).to_dict(
            orient="records"
        ),
        "checks": checks.to_dict(orient="records"),
        "sources": sources,
    }
    (INSPECTION_DIR / "imbalance_workbook_data.json").write_text(
        json.dumps(workbook_data, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    INSPECTION_DIR.mkdir(parents=True, exist_ok=True)
    data = load_data()
    checks = run_checks(data)
    checks.to_csv(
        INSPECTION_DIR / "imbalance_backtest_checks.csv",
        index=False,
    )

    settlement = data["settlement"]
    monthly = data["monthly"]
    annual = data["annual"]
    if not all(
        isinstance(frame, pd.DataFrame)
        for frame in (settlement, monthly, annual)
    ):
        raise TypeError("Plot input is not a DataFrame")
    save_sample_week(settlement)
    plot_daily_forecast_error(settlement)
    plot_monthly_imbalance(monthly)
    plot_procurement_comparison(annual, monthly)
    create_workbook_data(data, checks)

    summary = {
        "status": "OK" if checks["status"].eq("OK").all() else "FAIL",
        "checks_ok": int(checks["status"].eq("OK").sum()),
        "checks_total": len(checks),
        "locked_seed": int(data["metadata"]["locked_seed"]),
        "actual_energy_mwh": round(
            float(annual["actual_energy_mwh"].iloc[0]),
            2,
        ),
        "portfolio_nmae": round(
            float(
                settlement["imbalance_volume_mwh"].abs().sum()
                / settlement["total_forecast_mwh"].sum()
            ),
            6,
        ),
        "imbalance_premium_eur": round(
            float(annual["imbalance_premium_eur"].iloc[0]),
            2,
        ),
        "coarse_final_eur_mwh": round(
            strategy_value(
                annual,
                "COARSE_CAL",
                "final_average_price_eur_mwh",
            ),
            6,
        ),
        "granular_final_eur_mwh": round(
            strategy_value(
                annual,
                "GRANULAR",
                "final_average_price_eur_mwh",
            ),
            6,
        ),
    }
    (INSPECTION_DIR / "imbalance_validation_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print(checks.to_string(index=False))
    if not checks["status"].eq("OK").all():
        failed = checks.loc[checks["status"].ne("OK"), "check"].tolist()
        raise SystemExit(f"Imbalance backtest validation failed: {failed}")
    print(
        "\nImbalance backtest validation passed. Inspection files: "
        f"{INSPECTION_DIR}"
    )


if __name__ == "__main__":
    main()
