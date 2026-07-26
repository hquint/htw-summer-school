"""Build the 2024 portfolio, value-neutral hedges and Day-Ahead settlement."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

MODEL_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = MODEL_DIR.parent
INPUT_DIR = MODEL_DIR / "inputs"
OUTPUT_DIR = MODEL_DIR / "processed"
DATA_DIR = REPO_DIR / "data_pipeline_2024" / "processed"
HPFC_DIR = REPO_DIR / "hpfc_2024" / "processed"

EXPECTED_QUARTER_HOURS = 35_136
QUARTER_HOURS_PER_HOUR = 4
ACTIVITY_THRESHOLD = 100
VALUE_TOLERANCE_EUR = 0.01

PROFILE_COLUMNS = {
    "HB": "hb_normalized_kwh",
    "GB": "gb_normalized_kwh",
    "LB": "lb_normalized_kwh",
}

STRATEGIES = {
    "COARSE_CAL": ["CAL"],
    "GRANULAR": ["M01", "M02", "M03", "Q2", "Q3", "Q4"],
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


def load_inputs() -> dict[str, pd.DataFrame]:
    data = {
        "assumptions": pd.read_csv(INPUT_DIR / "portfolio_assumptions.csv"),
        "slp": pd.read_csv(DATA_DIR / "slp_profiles.csv"),
        "futures": pd.read_csv(DATA_DIR / "futures_prices.csv"),
        "day_ahead": pd.read_csv(DATA_DIR / "day_ahead_prices.csv"),
        "hpfc": pd.read_csv(HPFC_DIR / "hpfc_granular_2024.csv"),
    }
    for name in ("slp", "day_ahead", "hpfc"):
        if len(data[name]) != EXPECTED_QUARTER_HOURS:
            raise ValueError(
                f"{name}: expected {EXPECTED_QUARTER_HOURS:,} rows, "
                f"got {len(data[name]):,}"
            )

    timestamps = data["slp"]["timestamp_utc"]
    for name in ("day_ahead", "hpfc"):
        if not timestamps.equals(data[name]["timestamp_utc"]):
            raise ValueError(f"{name}: timestamps do not align with SLP data")
    if data["assumptions"]["profile_code"].duplicated().any():
        raise ValueError("Portfolio assumptions contain duplicate profile codes")
    if set(data["assumptions"]["profile_code"]) != set(PROFILE_COLUMNS):
        raise ValueError("Portfolio assumptions must contain HB, GB and LB")
    numeric = data["assumptions"][
        ["customer_count", "annual_mwh_per_customer"]
    ]
    if numeric.isna().any().any() or (numeric <= 0).any().any():
        raise ValueError("Portfolio counts and annual consumption must be positive")
    return data


def build_portfolio(
    assumptions: pd.DataFrame,
    slp: pd.DataFrame,
    hpfc: pd.DataFrame,
    day_ahead: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    resolved = assumptions.copy()
    resolved["annual_portfolio_mwh"] = (
        resolved["customer_count"] * resolved["annual_mwh_per_customer"]
    )
    resolved["customer_share"] = (
        resolved["customer_count"] / resolved["customer_count"].sum()
    )
    resolved["energy_share"] = (
        resolved["annual_portfolio_mwh"]
        / resolved["annual_portfolio_mwh"].sum()
    )

    forecast = pd.DataFrame(
        {
            "timestamp_utc": slp["timestamp_utc"],
            "timestamp_local": slp["timestamp_local"],
        }
    )
    component_columns: list[str] = []
    for assumption in resolved.itertuples(index=False):
        source_column = PROFILE_COLUMNS[assumption.profile_code]
        output_column = f"{assumption.profile_code.lower()}_forecast_mwh"
        scale = assumption.annual_portfolio_mwh / 1_000.0
        forecast[output_column] = (
            slp[source_column].to_numpy() * scale / 1_000.0
        )
        component_columns.append(output_column)

    forecast["total_forecast_mwh"] = forecast[component_columns].sum(axis=1)
    forecast["forecast_load_mw"] = (
        forecast["total_forecast_mwh"] * QUARTER_HOURS_PER_HOUR
    )
    forecast["hpfc_price_eur_mwh"] = hpfc["hpfc_price_eur_mwh"]
    forecast["day_ahead_price_eur_mwh"] = day_ahead[
        "day_ahead_price_eur_mwh"
    ]
    forecast["forecast_hpfc_value_eur"] = (
        forecast["total_forecast_mwh"] * forecast["hpfc_price_eur_mwh"]
    )
    forecast["unhedged_day_ahead_cost_eur"] = (
        forecast["total_forecast_mwh"]
        * forecast["day_ahead_price_eur_mwh"]
    )

    expected_energy = float(resolved["annual_portfolio_mwh"].sum())
    actual_energy = float(forecast["total_forecast_mwh"].sum())
    if not np.isclose(actual_energy, expected_energy, atol=1e-6):
        raise ValueError(
            f"Portfolio energy {actual_energy} does not equal {expected_energy}"
        )
    return resolved, forecast


def quote_row(
    futures: pd.DataFrame,
    period: str,
    load_type: str,
) -> pd.Series:
    matches = futures.loc[
        futures["delivery_period"].eq(period)
        & futures["load_type"].eq(load_type)
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected one {period} {load_type} quote, found {len(matches)}"
        )
    quote = matches.iloc[0]
    if quote["market_activity"] <= ACTIVITY_THRESHOLD:
        raise ValueError(
            f"{period} {load_type} is not eligible: "
            f"market_activity={quote['market_activity']}"
        )
    return quote


def solve_period(
    period: str,
    forecast_load_mwh: np.ndarray,
    hpfc_price: np.ndarray,
    local_month: np.ndarray,
    is_peak: np.ndarray,
) -> tuple[np.ndarray, dict[str, object]]:
    period_mask = np.isin(local_month, months_for_period(period))
    peak_mask = period_mask & is_peak
    design = np.column_stack(
        [
            period_mask.astype(float) / QUARTER_HOURS_PER_HOUR,
            peak_mask.astype(float) / QUARTER_HOURS_PER_HOUR,
        ]
    )
    block_design = design[period_mask]
    block_load = forecast_load_mwh[period_mask]
    block_hpfc = hpfc_price[period_mask]

    shape_matrix = block_design.T @ block_design
    shape_vector = block_design.T @ block_load
    value_per_mw = block_design.T @ block_hpfc
    target_value = float(block_load @ block_hpfc)

    kkt = np.block(
        [
            [shape_matrix, value_per_mw[:, None]],
            [value_per_mw[None, :], np.zeros((1, 1))],
        ]
    )
    rhs = np.r_[shape_vector, target_value]
    solution = np.linalg.solve(kkt, rhs)
    volumes = solution[:2]
    if (volumes < -1e-9).any():
        raise ValueError(
            f"{period}: value-neutral optimum requires a short position: {volumes}"
        )
    volumes = np.maximum(volumes, 0.0)
    residual = block_load - block_design @ volumes
    achieved_value = float(value_per_mw @ volumes)

    diagnostics = {
        "optimization_period": period,
        "solver": "ANALYTIC_KKT",
        "condition_number": float(np.linalg.cond(kkt)),
        "objective_sum_squared_mwh": float(residual @ residual),
        "target_hpfc_value_eur": target_value,
        "achieved_hpfc_value_eur": achieved_value,
        "value_difference_eur": achieved_value - target_value,
        "minimum_volume_mw": float(volumes.min()),
        "status": (
            "OK"
            if abs(achieved_value - target_value) <= VALUE_TOLERANCE_EUR
            else "FAIL"
        ),
    }
    return volumes, diagnostics


def optimize_strategy(
    strategy: str,
    periods: list[str],
    forecast: pd.DataFrame,
    futures: pd.DataFrame,
    local_month: np.ndarray,
    is_peak: np.ndarray,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, np.ndarray]]:
    load = forecast["total_forecast_mwh"].to_numpy()
    hpfc = forecast["hpfc_price_eur_mwh"].to_numpy()
    day_ahead = forecast["day_ahead_price_eur_mwh"].to_numpy()

    hedge_energy = np.zeros(len(forecast))
    fixed_cost = np.zeros(len(forecast))
    position_rows: list[dict[str, object]] = []
    diagnostic_rows: list[dict[str, object]] = []

    for period in periods:
        volumes, diagnostics = solve_period(
            period,
            load,
            hpfc,
            local_month,
            is_peak,
        )
        diagnostics["strategy"] = strategy
        diagnostic_rows.append(diagnostics)
        period_mask = np.isin(local_month, months_for_period(period))
        peak_mask = period_mask & is_peak

        for load_type, volume, delivery_mask in (
            ("BASE", volumes[0], period_mask),
            ("PEAK", volumes[1], peak_mask),
        ):
            quote = quote_row(futures, period, load_type)
            energy_profile = (
                delivery_mask.astype(float)
                * volume
                / QUARTER_HOURS_PER_HOUR
            )
            delivery_hours = float(delivery_mask.sum()) / QUARTER_HOURS_PER_HOUR
            contract_cost_profile = energy_profile * quote["price_eur_mwh"]
            hedge_energy += energy_profile
            fixed_cost += contract_cost_profile

            position_rows.append(
                {
                    "strategy": strategy,
                    "optimization_period": period,
                    "load_type": load_type,
                    "delivery_period": period,
                    "volume_mw": volume,
                    "delivery_hours": delivery_hours,
                    "hedged_energy_mwh": float(energy_profile.sum()),
                    "futures_price_eur_mwh": quote["price_eur_mwh"],
                    "market_activity": quote["market_activity"],
                    "contract_cost_eur": float(contract_cost_profile.sum()),
                    "hpfc_value_eur": float(energy_profile @ hpfc),
                    "quote_date": quote["quote_date"],
                }
            )

    residual = load - hedge_energy
    da_shaping_cost = residual * day_ahead
    futures_payoff = hedge_energy * day_ahead - fixed_cost
    effective_total_cost = fixed_cost + da_shaping_cost
    financial_total_cost = (
        forecast["unhedged_day_ahead_cost_eur"].to_numpy() - futures_payoff
    )

    arrays = {
        "hedge_energy_mwh": hedge_energy,
        "residual_da_mwh": residual,
        "fixed_hedge_cost_eur": fixed_cost,
        "da_shaping_cost_eur": da_shaping_cost,
        "futures_payoff_eur": futures_payoff,
        "effective_total_cost_eur": effective_total_cost,
        "financial_total_cost_eur": financial_total_cost,
    }
    return (
        pd.DataFrame(position_rows),
        pd.DataFrame(diagnostic_rows),
        arrays,
    )


def build_strategy_summary(
    forecast: pd.DataFrame,
    positions: pd.DataFrame,
    strategy_arrays: dict[str, dict[str, np.ndarray]],
) -> pd.DataFrame:
    load = forecast["total_forecast_mwh"].to_numpy()
    hpfc = forecast["hpfc_price_eur_mwh"].to_numpy()
    unhedged_qh = forecast["unhedged_day_ahead_cost_eur"].to_numpy()
    annual_energy = float(load.sum())
    portfolio_hpfc_value = float(load @ hpfc)
    unhedged_cost = float(unhedged_qh.sum())

    rows = [
        {
            "strategy": "UNHEDGED",
            "forecast_energy_mwh": annual_energy,
            "portfolio_hpfc_value_eur": portfolio_hpfc_value,
            "hedge_notional_energy_mwh": 0.0,
            "hedge_hpfc_value_eur": 0.0,
            "value_neutral_difference_eur": -portfolio_hpfc_value,
            "residual_hpfc_value_eur": portfolio_hpfc_value,
            "fixed_hedge_cost_eur": 0.0,
            "day_ahead_shaping_cost_eur": unhedged_cost,
            "financial_futures_payoff_eur": 0.0,
            "total_procurement_cost_eur": unhedged_cost,
            "average_procurement_price_eur_mwh": unhedged_cost / annual_energy,
            "saving_vs_unhedged_eur": 0.0,
            "saving_vs_unhedged_eur_mwh": 0.0,
            "residual_energy_mwh": annual_energy,
            "residual_absolute_energy_mwh": float(np.abs(load).sum()),
            "residual_load_rmse_mw": float(
                np.sqrt(np.mean((load * QUARTER_HOURS_PER_HOUR) ** 2))
            ),
            "overhedged_quarter_hour_share": 0.0,
            "settlement_equivalence_error_eur": 0.0,
            "position_count": 0,
        }
    ]

    for strategy, arrays in strategy_arrays.items():
        strategy_positions = positions.loc[positions["strategy"].eq(strategy)]
        hedge = arrays["hedge_energy_mwh"]
        residual = arrays["residual_da_mwh"]
        fixed_cost = float(arrays["fixed_hedge_cost_eur"].sum())
        da_shaping_cost = float(arrays["da_shaping_cost_eur"].sum())
        effective_cost = float(arrays["effective_total_cost_eur"].sum())
        financial_cost = float(arrays["financial_total_cost_eur"].sum())
        hedge_hpfc_value = float(hedge @ hpfc)
        total_payoff = float(arrays["futures_payoff_eur"].sum())

        rows.append(
            {
                "strategy": strategy,
                "forecast_energy_mwh": annual_energy,
                "portfolio_hpfc_value_eur": portfolio_hpfc_value,
                "hedge_notional_energy_mwh": float(hedge.sum()),
                "hedge_hpfc_value_eur": hedge_hpfc_value,
                "value_neutral_difference_eur": (
                    hedge_hpfc_value - portfolio_hpfc_value
                ),
                "residual_hpfc_value_eur": float(residual @ hpfc),
                "fixed_hedge_cost_eur": fixed_cost,
                "day_ahead_shaping_cost_eur": da_shaping_cost,
                "financial_futures_payoff_eur": total_payoff,
                "total_procurement_cost_eur": effective_cost,
                "average_procurement_price_eur_mwh": (
                    effective_cost / annual_energy
                ),
                "saving_vs_unhedged_eur": unhedged_cost - effective_cost,
                "saving_vs_unhedged_eur_mwh": (
                    (unhedged_cost - effective_cost) / annual_energy
                ),
                "residual_energy_mwh": float(residual.sum()),
                "residual_absolute_energy_mwh": float(np.abs(residual).sum()),
                "residual_load_rmse_mw": float(
                    np.sqrt(
                        np.mean(
                            (residual * QUARTER_HOURS_PER_HOUR) ** 2
                        )
                    )
                ),
                "overhedged_quarter_hour_share": float(
                    np.mean(residual < 0)
                ),
                "settlement_equivalence_error_eur": (
                    effective_cost - financial_cost
                ),
                "position_count": len(strategy_positions),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data = load_inputs()
    assumptions, forecast = build_portfolio(
        data["assumptions"],
        data["slp"],
        data["hpfc"],
        data["day_ahead"],
    )

    timestamps = pd.to_datetime(forecast["timestamp_utc"], utc=True)
    local = timestamps.dt.tz_convert("Europe/Berlin")
    local_month = local.dt.month.to_numpy()
    is_peak = data["hpfc"]["is_peak"].astype(bool).to_numpy()

    all_positions: list[pd.DataFrame] = []
    all_diagnostics: list[pd.DataFrame] = []
    strategy_arrays: dict[str, dict[str, np.ndarray]] = {}
    time_series = forecast[
        [
            "timestamp_utc",
            "timestamp_local",
            "total_forecast_mwh",
            "forecast_load_mw",
            "hpfc_price_eur_mwh",
            "day_ahead_price_eur_mwh",
            "unhedged_day_ahead_cost_eur",
        ]
    ].copy()

    for strategy, periods in STRATEGIES.items():
        positions, diagnostics, arrays = optimize_strategy(
            strategy,
            periods,
            forecast,
            data["futures"],
            local_month,
            is_peak,
        )
        all_positions.append(positions)
        all_diagnostics.append(diagnostics)
        strategy_arrays[strategy] = arrays
        prefix = strategy.lower()
        for name, values in arrays.items():
            time_series[f"{prefix}_{name}"] = values

    positions = pd.concat(all_positions, ignore_index=True)
    diagnostics = pd.concat(all_diagnostics, ignore_index=True)
    summary = build_strategy_summary(forecast, positions, strategy_arrays)

    numeric_position_columns = positions.select_dtypes(include="number").columns
    positions[numeric_position_columns] = positions[
        numeric_position_columns
    ].round(8)
    numeric_diagnostic_columns = diagnostics.select_dtypes(
        include="number"
    ).columns
    diagnostics[numeric_diagnostic_columns] = diagnostics[
        numeric_diagnostic_columns
    ].round(8)
    numeric_summary_columns = summary.select_dtypes(include="number").columns
    summary[numeric_summary_columns] = summary[numeric_summary_columns].round(8)

    assumptions.to_csv(
        OUTPUT_DIR / "portfolio_assumptions_resolved.csv",
        index=False,
    )
    forecast.to_csv(OUTPUT_DIR / "portfolio_forecast_2024.csv", index=False)
    positions.to_csv(OUTPUT_DIR / "hedge_positions.csv", index=False)
    diagnostics.to_csv(OUTPUT_DIR / "optimizer_diagnostics.csv", index=False)
    time_series.to_csv(
        OUTPUT_DIR / "hedge_day_ahead_timeseries.csv",
        index=False,
    )
    summary.to_csv(OUTPUT_DIR / "strategy_summary.csv", index=False)

    metadata = {
        "delivery_year": 2024,
        "quote_date": str(data["futures"]["quote_date"].iloc[0]),
        "portfolio_customers": int(assumptions["customer_count"].sum()),
        "portfolio_energy_mwh": float(
            assumptions["annual_portfolio_mwh"].sum()
        ),
        "strategies": STRATEGIES,
        "value_neutrality": (
            "Hedge and forecast load have equal HPFC value within each "
            "non-overlapping optimization period."
        ),
        "imbalance_included": False,
    }
    (OUTPUT_DIR / "portfolio_hedge_metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    print(f"Built portfolio hedge outputs in {OUTPUT_DIR}")
    print(f"Customers: {metadata['portfolio_customers']:,}")
    print(f"Forecast energy: {metadata['portfolio_energy_mwh']:,.0f} MWh")
    print(
        summary[
            [
                "strategy",
                "average_procurement_price_eur_mwh",
                "saving_vs_unhedged_eur",
                "residual_load_rmse_mw",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
