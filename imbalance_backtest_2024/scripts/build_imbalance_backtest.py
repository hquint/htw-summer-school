"""Build synthetic actual load, observed-reBAP settlement and final costs."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import lfilter

MODEL_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = MODEL_DIR.parent
INPUT_DIR = MODEL_DIR / "inputs"
OUTPUT_DIR = MODEL_DIR / "processed"
DATA_DIR = REPO_DIR / "data_pipeline_2024" / "processed"
HEDGE_DIR = REPO_DIR / "portfolio_hedge_2024" / "processed"

EXPECTED_QUARTER_HOURS = 35_136
QUARTER_HOURS_PER_HOUR = 4
PROFILE_CODES = ("HB", "GB", "LB")
STRATEGIES = ("UNHEDGED", "COARSE_CAL", "GRANULAR")

FORECAST_COLUMNS = {
    "HB": "hb_forecast_mwh",
    "GB": "gb_forecast_mwh",
    "LB": "lb_forecast_mwh",
}
BASE_COST_COLUMNS = {
    "UNHEDGED": "unhedged_day_ahead_cost_eur",
    "COARSE_CAL": "coarse_cal_effective_total_cost_eur",
    "GRANULAR": "granular_effective_total_cost_eur",
}
FIXED_COST_COLUMNS = {
    "UNHEDGED": None,
    "COARSE_CAL": "coarse_cal_fixed_hedge_cost_eur",
    "GRANULAR": "granular_fixed_hedge_cost_eur",
}
DAY_AHEAD_COST_COLUMNS = {
    "UNHEDGED": "unhedged_day_ahead_cost_eur",
    "COARSE_CAL": "coarse_cal_da_shaping_cost_eur",
    "GRANULAR": "granular_da_shaping_cost_eur",
}
FUTURES_PAYOFF_COLUMNS = {
    "UNHEDGED": None,
    "COARSE_CAL": "coarse_cal_futures_payoff_eur",
    "GRANULAR": "granular_futures_payoff_eur",
}
OPEN_VOLUME_COLUMNS = {
    "UNHEDGED": "total_forecast_mwh",
    "COARSE_CAL": "coarse_cal_residual_da_mwh",
    "GRANULAR": "granular_residual_da_mwh",
}


def read_parameters() -> dict[str, float]:
    parameters = pd.read_csv(INPUT_DIR / "simulation_parameters.csv")
    if parameters["parameter"].duplicated().any():
        raise ValueError("Simulation parameters contain duplicate names")
    values = dict(zip(parameters["parameter"], parameters["value"], strict=True))
    required = {
        "locked_seed",
        "daily_common_sigma",
        "daily_common_ar",
        "quarter_hour_common_sigma",
        "quarter_hour_common_ar",
        "minimum_load_factor",
        "maximum_load_factor",
        "seed_target_nmae",
        "seed_target_imbalance_premium",
    }
    if set(values) != required:
        missing = sorted(required - set(values))
        extra = sorted(set(values) - required)
        raise ValueError(f"Parameter mismatch; missing={missing}, extra={extra}")
    return {name: float(value) for name, value in values.items()}


def load_inputs() -> dict[str, pd.DataFrame | dict[str, float]]:
    data: dict[str, pd.DataFrame | dict[str, float]] = {
        "parameters": read_parameters(),
        "profile_assumptions": pd.read_csv(
            INPUT_DIR / "profile_error_assumptions.csv"
        ),
        "forecast": pd.read_csv(
            HEDGE_DIR / "portfolio_forecast_2024.csv"
        ),
        "hedge_timeseries": pd.read_csv(
            HEDGE_DIR / "hedge_day_ahead_timeseries.csv"
        ),
        "hedge_summary": pd.read_csv(HEDGE_DIR / "strategy_summary.csv"),
        "imbalance_prices": pd.read_csv(DATA_DIR / "imbalance_prices.csv"),
    }
    frames = {
        name: frame
        for name, frame in data.items()
        if isinstance(frame, pd.DataFrame)
        and name not in {"profile_assumptions", "hedge_summary"}
    }
    for name, frame in frames.items():
        if len(frame) != EXPECTED_QUARTER_HOURS:
            raise ValueError(
                f"{name}: expected {EXPECTED_QUARTER_HOURS:,} rows, "
                f"got {len(frame):,}"
            )

    timestamp_source = data["forecast"]["timestamp_utc"]  # type: ignore[index]
    for name in ("hedge_timeseries", "imbalance_prices"):
        frame = data[name]
        if not isinstance(frame, pd.DataFrame):
            raise TypeError(f"{name} is not a DataFrame")
        if not timestamp_source.equals(frame["timestamp_utc"]):
            raise ValueError(f"{name}: timestamps do not align with forecast")

    assumptions = data["profile_assumptions"]
    if not isinstance(assumptions, pd.DataFrame):
        raise TypeError("profile_assumptions is not a DataFrame")
    if assumptions["profile_code"].duplicated().any():
        raise ValueError("Profile error assumptions contain duplicates")
    if set(assumptions["profile_code"]) != set(PROFILE_CODES):
        raise ValueError("Profile error assumptions must contain HB, GB and LB")
    numeric = assumptions[
        ["annual_bias", "idiosyncratic_sigma", "idiosyncratic_ar"]
    ]
    if numeric.isna().any().any():
        raise ValueError("Profile error assumptions contain missing values")
    if not assumptions["idiosyncratic_ar"].between(0, 0.999).all():
        raise ValueError("Profile AR coefficients must be in [0, 0.999]")
    if (assumptions["idiosyncratic_sigma"] <= 0).any():
        raise ValueError("Profile idiosyncratic sigmas must be positive")
    return data


def ar1_standardized(
    length: int,
    persistence: float,
    rng: np.random.Generator,
) -> np.ndarray:
    innovations = rng.standard_normal(length)
    stationary_scale = np.sqrt(1.0 - persistence**2)
    series = lfilter([stationary_scale], [1.0, -persistence], innovations)
    series -= series.mean()
    standard_deviation = series.std(ddof=0)
    if standard_deviation == 0:
        raise ValueError("AR(1) process unexpectedly has zero variance")
    return series / standard_deviation


def simulate_actual_load(
    seed: int,
    forecast: pd.DataFrame,
    profile_assumptions: pd.DataFrame,
    parameters: dict[str, float],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    utc = pd.to_datetime(forecast["timestamp_utc"], utc=True)
    local = utc.dt.tz_convert("Europe/Berlin")
    day_codes, local_days = pd.factorize(local.dt.strftime("%Y-%m-%d"))

    daily_common = (
        parameters["daily_common_sigma"]
        * ar1_standardized(
            len(local_days),
            parameters["daily_common_ar"],
            rng,
        )[day_codes]
    )
    quarter_hour_common = (
        parameters["quarter_hour_common_sigma"]
        * ar1_standardized(
            len(forecast),
            parameters["quarter_hour_common_ar"],
            rng,
        )
    )
    common_shock = daily_common + quarter_hour_common

    actual = forecast[["timestamp_utc", "timestamp_local"]].copy()
    profile_rows: list[dict[str, object]] = []
    actual_columns: list[str] = []
    deviation_columns: list[str] = []

    indexed_assumptions = profile_assumptions.set_index("profile_code")
    for profile_code in PROFILE_CODES:
        assumption = indexed_assumptions.loc[profile_code]
        forecast_column = FORECAST_COLUMNS[profile_code]
        forecast_energy = forecast[forecast_column].to_numpy(dtype=float)
        idiosyncratic = (
            float(assumption["idiosyncratic_sigma"])
            * ar1_standardized(
                len(forecast),
                float(assumption["idiosyncratic_ar"]),
                rng,
            )
        )
        combined_shock = common_shock + idiosyncratic
        combined_shock -= np.average(
            combined_shock,
            weights=forecast_energy,
        )
        factor = (
            1.0
            + float(assumption["annual_bias"])
            + combined_shock
        )
        unclipped_factor = factor.copy()
        factor = np.clip(
            factor,
            parameters["minimum_load_factor"],
            parameters["maximum_load_factor"],
        )
        actual_energy = forecast_energy * factor
        deviation = actual_energy - forecast_energy

        prefix = profile_code.lower()
        actual[f"{prefix}_forecast_mwh"] = forecast_energy
        actual[f"{prefix}_actual_factor"] = factor
        actual[f"{prefix}_actual_mwh"] = actual_energy
        actual[f"{prefix}_deviation_mwh"] = deviation
        actual_columns.append(f"{prefix}_actual_mwh")
        deviation_columns.append(f"{prefix}_deviation_mwh")

        profile_rows.append(
            {
                "profile_code": profile_code,
                "forecast_energy_mwh": float(forecast_energy.sum()),
                "actual_energy_mwh": float(actual_energy.sum()),
                "annual_bias": (
                    float(actual_energy.sum() / forecast_energy.sum()) - 1.0
                ),
                "absolute_error_mwh": float(np.abs(deviation).sum()),
                "normalized_mean_absolute_error": float(
                    np.abs(deviation).sum() / forecast_energy.sum()
                ),
                "minimum_actual_factor": float(factor.min()),
                "maximum_actual_factor": float(factor.max()),
                "clipped_quarter_hours": int(
                    np.count_nonzero(factor != unclipped_factor)
                ),
            }
        )

    actual["total_forecast_mwh"] = forecast["total_forecast_mwh"]
    actual["total_actual_mwh"] = actual[actual_columns].sum(axis=1)
    actual["imbalance_volume_mwh"] = actual[deviation_columns].sum(axis=1)
    actual["forecast_load_mw"] = (
        actual["total_forecast_mwh"] * QUARTER_HOURS_PER_HOUR
    )
    actual["actual_load_mw"] = (
        actual["total_actual_mwh"] * QUARTER_HOURS_PER_HOUR
    )
    actual["forecast_error_mw"] = (
        actual["imbalance_volume_mwh"] * QUARTER_HOURS_PER_HOUR
    )
    return actual, pd.DataFrame(profile_rows)


def add_market_settlement(
    actual: pd.DataFrame,
    hedge_timeseries: pd.DataFrame,
    imbalance_prices: pd.DataFrame,
) -> pd.DataFrame:
    settlement = actual.copy()
    settlement["day_ahead_price_eur_mwh"] = hedge_timeseries[
        "day_ahead_price_eur_mwh"
    ]
    settlement["imbalance_price_eur_mwh"] = imbalance_prices[
        "imbalance_price_eur_mwh"
    ]
    settlement["imbalance_settlement_eur"] = (
        settlement["imbalance_volume_mwh"]
        * settlement["imbalance_price_eur_mwh"]
    )
    settlement["deviation_day_ahead_value_eur"] = (
        settlement["imbalance_volume_mwh"]
        * settlement["day_ahead_price_eur_mwh"]
    )
    settlement["imbalance_premium_eur"] = (
        settlement["imbalance_volume_mwh"]
        * (
            settlement["imbalance_price_eur_mwh"]
            - settlement["day_ahead_price_eur_mwh"]
        )
    )

    for strategy in STRATEGIES:
        prefix = strategy.lower()
        base_cost_column = BASE_COST_COLUMNS[strategy]
        open_volume_column = OPEN_VOLUME_COLUMNS[strategy]
        settlement[f"{prefix}_forecast_procurement_cost_eur"] = (
            hedge_timeseries[base_cost_column]
        )
        settlement[f"{prefix}_open_day_ahead_volume_mwh"] = (
            hedge_timeseries[open_volume_column]
        )
        settlement[f"{prefix}_final_procurement_cost_eur"] = (
            settlement[f"{prefix}_forecast_procurement_cost_eur"]
            + settlement["imbalance_settlement_eur"]
        )
    return settlement


def monthly_summary(
    settlement: pd.DataFrame,
    hedge_timeseries: pd.DataFrame,
) -> pd.DataFrame:
    utc = pd.to_datetime(settlement["timestamp_utc"], utc=True)
    month = utc.dt.tz_convert("Europe/Berlin").dt.strftime("%Y-%m")
    rows: list[dict[str, object]] = []

    for month_label in sorted(month.unique()):
        mask = month.eq(month_label).to_numpy()
        actual_energy = float(settlement.loc[mask, "total_actual_mwh"].sum())
        forecast_energy = float(
            settlement.loc[mask, "total_forecast_mwh"].sum()
        )
        imbalance_volume = float(
            settlement.loc[mask, "imbalance_volume_mwh"].sum()
        )
        imbalance_cost = float(
            settlement.loc[mask, "imbalance_settlement_eur"].sum()
        )
        imbalance_premium = float(
            settlement.loc[mask, "imbalance_premium_eur"].sum()
        )
        unhedged_final_cost = float(
            settlement.loc[
                mask,
                "unhedged_final_procurement_cost_eur",
            ].sum()
        )

        for strategy in STRATEGIES:
            prefix = strategy.lower()
            fixed_column = FIXED_COST_COLUMNS[strategy]
            payoff_column = FUTURES_PAYOFF_COLUMNS[strategy]
            fixed_cost = (
                0.0
                if fixed_column is None
                else float(hedge_timeseries.loc[mask, fixed_column].sum())
            )
            futures_payoff = (
                0.0
                if payoff_column is None
                else float(hedge_timeseries.loc[mask, payoff_column].sum())
            )
            day_ahead_cost = float(
                hedge_timeseries.loc[
                    mask,
                    DAY_AHEAD_COST_COLUMNS[strategy],
                ].sum()
            )
            forecast_procurement_cost = float(
                settlement.loc[
                    mask,
                    f"{prefix}_forecast_procurement_cost_eur",
                ].sum()
            )
            final_cost = float(
                settlement.loc[
                    mask,
                    f"{prefix}_final_procurement_cost_eur",
                ].sum()
            )
            open_volume = float(
                settlement.loc[
                    mask,
                    f"{prefix}_open_day_ahead_volume_mwh",
                ].abs().sum()
            )
            rows.append(
                {
                    "month": month_label,
                    "strategy": strategy,
                    "forecast_energy_mwh": forecast_energy,
                    "actual_energy_mwh": actual_energy,
                    "imbalance_volume_mwh": imbalance_volume,
                    "fixed_futures_cost_eur": fixed_cost,
                    "day_ahead_scheduled_cost_eur": day_ahead_cost,
                    "futures_payoff_eur": futures_payoff,
                    "forecast_procurement_cost_eur": forecast_procurement_cost,
                    "imbalance_settlement_eur": imbalance_cost,
                    "imbalance_premium_eur": imbalance_premium,
                    "final_procurement_cost_eur": final_cost,
                    "final_average_price_eur_mwh": final_cost / actual_energy,
                    "saving_vs_unhedged_eur": (
                        unhedged_final_cost - final_cost
                    ),
                    "saving_vs_unhedged_eur_mwh": (
                        (unhedged_final_cost - final_cost) / actual_energy
                    ),
                    "absolute_open_day_ahead_volume_mwh": open_volume,
                }
            )
    return pd.DataFrame(rows)


def annual_summary(
    settlement: pd.DataFrame,
    hedge_timeseries: pd.DataFrame,
    monthly: pd.DataFrame,
) -> pd.DataFrame:
    actual_energy = float(settlement["total_actual_mwh"].sum())
    forecast_energy = float(settlement["total_forecast_mwh"].sum())
    imbalance_volume = float(settlement["imbalance_volume_mwh"].sum())
    imbalance_cost = float(settlement["imbalance_settlement_eur"].sum())
    imbalance_premium = float(settlement["imbalance_premium_eur"].sum())
    unhedged_final_cost = float(
        settlement["unhedged_final_procurement_cost_eur"].sum()
    )
    rows: list[dict[str, object]] = []

    for strategy in STRATEGIES:
        prefix = strategy.lower()
        fixed_column = FIXED_COST_COLUMNS[strategy]
        payoff_column = FUTURES_PAYOFF_COLUMNS[strategy]
        fixed_cost = (
            0.0
            if fixed_column is None
            else float(hedge_timeseries[fixed_column].sum())
        )
        futures_payoff = (
            0.0
            if payoff_column is None
            else float(hedge_timeseries[payoff_column].sum())
        )
        day_ahead_cost = float(
            hedge_timeseries[DAY_AHEAD_COST_COLUMNS[strategy]].sum()
        )
        forecast_cost = float(
            settlement[
                f"{prefix}_forecast_procurement_cost_eur"
            ].sum()
        )
        final_cost = float(
            settlement[f"{prefix}_final_procurement_cost_eur"].sum()
        )
        absolute_open_volume = float(
            settlement[
                f"{prefix}_open_day_ahead_volume_mwh"
            ].abs().sum()
        )
        strategy_monthly = monthly.loc[monthly["strategy"].eq(strategy)]

        rows.append(
            {
                "strategy": strategy,
                "forecast_energy_mwh": forecast_energy,
                "actual_energy_mwh": actual_energy,
                "actual_minus_forecast_mwh": imbalance_volume,
                "fixed_futures_cost_eur": fixed_cost,
                "day_ahead_scheduled_cost_eur": day_ahead_cost,
                "futures_payoff_eur": futures_payoff,
                "forecast_procurement_cost_eur": forecast_cost,
                "imbalance_settlement_eur": imbalance_cost,
                "imbalance_premium_eur": imbalance_premium,
                "final_procurement_cost_eur": final_cost,
                "final_average_price_eur_mwh": final_cost / actual_energy,
                "saving_vs_unhedged_eur": unhedged_final_cost - final_cost,
                "saving_vs_unhedged_eur_mwh": (
                    (unhedged_final_cost - final_cost) / actual_energy
                ),
                "absolute_open_day_ahead_volume_mwh": absolute_open_volume,
                "forecast_shaping_coverage": (
                    1.0 - absolute_open_volume / forecast_energy
                ),
                "monthly_average_price_std_eur_mwh": float(
                    strategy_monthly[
                        "final_average_price_eur_mwh"
                    ].std(ddof=1)
                ),
                "monthly_average_price_range_eur_mwh": float(
                    strategy_monthly[
                        "final_average_price_eur_mwh"
                    ].max()
                    - strategy_monthly[
                        "final_average_price_eur_mwh"
                    ].min()
                ),
            }
        )
    return pd.DataFrame(rows)


def build_procurement_pnl(annual: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for result in annual.itertuples(index=False):
        cost_lines = (
            ("Fixed futures cost", result.fixed_futures_cost_eur),
            (
                "Day-Ahead scheduled cost",
                result.day_ahead_scheduled_cost_eur,
            ),
            ("reBAP imbalance settlement", result.imbalance_settlement_eur),
        )
        for line_item, amount in cost_lines:
            rows.append(
                {
                    "strategy": result.strategy,
                    "line_item": line_item,
                    "classification": "COST_COMPONENT",
                    "amount_eur": amount,
                    "notes": (
                        "Positive is procurement cost; negative is sale revenue."
                    ),
                }
            )
        rows.extend(
            [
                {
                    "strategy": result.strategy,
                    "line_item": "Final procurement cost",
                    "classification": "SUBTOTAL",
                    "amount_eur": result.final_procurement_cost_eur,
                    "notes": "Sum of the three procurement cost components.",
                },
                {
                    "strategy": result.strategy,
                    "line_item": "Saving versus unhedged",
                    "classification": "INFORMATIONAL",
                    "amount_eur": result.saving_vs_unhedged_eur,
                    "notes": (
                        "Realized procurement-cost difference, not trading profit."
                    ),
                },
                {
                    "strategy": result.strategy,
                    "line_item": "Futures payoff versus Day-Ahead",
                    "classification": "INFORMATIONAL",
                    "amount_eur": result.futures_payoff_eur,
                    "notes": (
                        "Financial hedge payoff already reflected in final cost."
                    ),
                },
                {
                    "strategy": result.strategy,
                    "line_item": "Imbalance premium versus Day-Ahead",
                    "classification": "INFORMATIONAL",
                    "amount_eur": result.imbalance_premium_eur,
                    "notes": "Price effect of reBAP rather than Day-Ahead.",
                },
            ]
        )
    return pd.DataFrame(rows)


def prepare_seed_evaluation(
    data: dict[str, pd.DataFrame | dict[str, float]],
) -> dict[str, object]:
    parameters = data["parameters"]
    profile_assumptions = data["profile_assumptions"]
    forecast = data["forecast"]
    hedge_timeseries = data["hedge_timeseries"]
    imbalance_prices = data["imbalance_prices"]
    if not isinstance(parameters, dict):
        raise TypeError("parameters is not a dictionary")
    if not all(
        isinstance(frame, pd.DataFrame)
        for frame in (
            profile_assumptions,
            forecast,
            hedge_timeseries,
            imbalance_prices,
        )
    ):
        raise TypeError("Seed evaluation inputs must be DataFrames")

    utc = pd.to_datetime(forecast["timestamp_utc"], utc=True)
    local = utc.dt.tz_convert("Europe/Berlin")
    day_codes, local_days = pd.factorize(local.dt.strftime("%Y-%m-%d"))
    month_codes, month_labels = pd.factorize(
        local.dt.strftime("%Y-%m"),
        sort=True,
    )
    indexed_assumptions = profile_assumptions.set_index("profile_code")
    profiles = [
        {
            "profile_code": profile_code,
            "forecast_energy": forecast[
                FORECAST_COLUMNS[profile_code]
            ].to_numpy(dtype=float),
            "annual_bias": float(
                indexed_assumptions.loc[profile_code, "annual_bias"]
            ),
            "idiosyncratic_sigma": float(
                indexed_assumptions.loc[
                    profile_code,
                    "idiosyncratic_sigma",
                ]
            ),
            "idiosyncratic_ar": float(
                indexed_assumptions.loc[
                    profile_code,
                    "idiosyncratic_ar",
                ]
            ),
        }
        for profile_code in PROFILE_CODES
    ]
    return {
        "parameters": parameters,
        "day_codes": day_codes,
        "day_count": len(local_days),
        "month_codes": month_codes,
        "month_count": len(month_labels),
        "profiles": profiles,
        "forecast_total": forecast["total_forecast_mwh"].to_numpy(
            dtype=float
        ),
        "day_ahead_price": hedge_timeseries[
            "day_ahead_price_eur_mwh"
        ].to_numpy(dtype=float),
        "imbalance_price": imbalance_prices[
            "imbalance_price_eur_mwh"
        ].to_numpy(dtype=float),
        "base_costs": {
            strategy: hedge_timeseries[
                BASE_COST_COLUMNS[strategy]
            ].to_numpy(dtype=float)
            for strategy in STRATEGIES
        },
    }


def evaluate_seed(
    seed: int,
    data: dict[str, pd.DataFrame | dict[str, float]],
    context: dict[str, object] | None = None,
) -> dict[str, float | int]:
    evaluation = context or prepare_seed_evaluation(data)
    parameters = evaluation["parameters"]
    if not isinstance(parameters, dict):
        raise TypeError("Seed parameters are not a dictionary")
    day_codes = np.asarray(evaluation["day_codes"])
    month_codes = np.asarray(evaluation["month_codes"])
    profiles = evaluation["profiles"]
    base_costs = evaluation["base_costs"]
    if not isinstance(profiles, list) or not isinstance(base_costs, dict):
        raise TypeError("Seed evaluation context is malformed")

    rng = np.random.default_rng(seed)
    daily_common = (
        parameters["daily_common_sigma"]
        * ar1_standardized(
            int(evaluation["day_count"]),
            parameters["daily_common_ar"],
            rng,
        )[day_codes]
    )
    quarter_hour_common = (
        parameters["quarter_hour_common_sigma"]
        * ar1_standardized(
            len(day_codes),
            parameters["quarter_hour_common_ar"],
            rng,
        )
    )
    common_shock = daily_common + quarter_hour_common
    total_actual = np.zeros(len(day_codes))
    minimum_factor = np.inf
    maximum_factor = -np.inf
    clipped_quarter_hours = 0

    for profile in profiles:
        if not isinstance(profile, dict):
            raise TypeError("Profile seed context is malformed")
        profile_forecast = np.asarray(
            profile["forecast_energy"],
            dtype=float,
        )
        idiosyncratic = (
            float(profile["idiosyncratic_sigma"])
            * ar1_standardized(
                len(day_codes),
                float(profile["idiosyncratic_ar"]),
                rng,
            )
        )
        shock = common_shock + idiosyncratic
        shock -= np.average(shock, weights=profile_forecast)
        factor = 1.0 + float(profile["annual_bias"]) + shock
        clipped = np.clip(
            factor,
            parameters["minimum_load_factor"],
            parameters["maximum_load_factor"],
        )
        clipped_quarter_hours += int(np.count_nonzero(clipped != factor))
        minimum_factor = min(minimum_factor, float(clipped.min()))
        maximum_factor = max(maximum_factor, float(clipped.max()))
        total_actual += profile_forecast * clipped

    forecast_total = np.asarray(evaluation["forecast_total"], dtype=float)
    imbalance_price = np.asarray(
        evaluation["imbalance_price"],
        dtype=float,
    )
    day_ahead_price = np.asarray(
        evaluation["day_ahead_price"],
        dtype=float,
    )
    deviation = total_actual - forecast_total
    imbalance_settlement = deviation * imbalance_price
    imbalance_premium = deviation * (
        imbalance_price - day_ahead_price
    )
    forecast_energy = float(forecast_total.sum())
    actual_energy = float(total_actual.sum())
    nmae = float(np.abs(deviation).sum() / forecast_energy)
    premium_per_mwh = float(imbalance_premium.sum() / actual_energy)

    monthly_energy = np.bincount(
        month_codes,
        weights=total_actual,
        minlength=int(evaluation["month_count"]),
    )
    monthly_std: dict[str, float] = {}
    for strategy in STRATEGIES:
        strategy_base_cost = np.asarray(base_costs[strategy], dtype=float)
        monthly_cost = np.bincount(
            month_codes,
            weights=strategy_base_cost + imbalance_settlement,
            minlength=int(evaluation["month_count"]),
        )
        monthly_std[strategy] = float(
            np.std(monthly_cost / monthly_energy, ddof=1)
        )

    target_nmae = parameters["seed_target_nmae"]
    target_premium = parameters["seed_target_imbalance_premium"]
    score = (
        abs(nmae - target_nmae) / 0.005
        + abs(premium_per_mwh - target_premium) / 0.35
    )
    if premium_per_mwh < 0.10:
        score += 20.0 + 20.0 * abs(premium_per_mwh - 0.10)
    if premium_per_mwh > 1.50:
        score += 10.0 * (premium_per_mwh - 1.50)
    for strategy in ("COARSE_CAL", "GRANULAR"):
        volatility_ratio = (
            monthly_std[strategy] / monthly_std["UNHEDGED"]
        )
        if volatility_ratio >= 1.0:
            score += 20.0 * (volatility_ratio - 1.0 + 0.05)

    return {
        "seed": seed,
        "score": score,
        "portfolio_nmae": nmae,
        "annual_actual_energy_mwh": actual_energy,
        "annual_energy_bias": actual_energy / forecast_energy - 1.0,
        "imbalance_settlement_eur": float(
            imbalance_settlement.sum()
        ),
        "imbalance_settlement_eur_mwh": float(
            imbalance_settlement.sum() / actual_energy
        ),
        "imbalance_premium_eur": float(imbalance_premium.sum()),
        "imbalance_premium_eur_mwh": premium_per_mwh,
        "minimum_actual_factor": minimum_factor,
        "maximum_actual_factor": maximum_factor,
        "clipped_quarter_hours": clipped_quarter_hours,
        "unhedged_monthly_price_std": float(monthly_std["UNHEDGED"]),
        "coarse_monthly_price_std": float(monthly_std["COARSE_CAL"]),
        "granular_monthly_price_std": float(monthly_std["GRANULAR"]),
    }


def build_metadata(
    seed: int,
    parameters: dict[str, float],
    settlement: pd.DataFrame,
    annual: pd.DataFrame,
) -> dict[str, object]:
    return {
        "delivery_year": 2024,
        "locked_seed": seed,
        "forecast_energy_mwh": float(
            settlement["total_forecast_mwh"].sum()
        ),
        "actual_energy_mwh": float(settlement["total_actual_mwh"].sum()),
        "portfolio_nmae": float(
            settlement["imbalance_volume_mwh"].abs().sum()
            / settlement["total_forecast_mwh"].sum()
        ),
        "imbalance_price_source": (
            "Observed quality-assured 2024 reBAP from Netztransparenz"
        ),
        "actual_load_source": (
            "Synthetic profile-level deviations from published Berlin SLP "
            "forecast portfolio"
        ),
        "settlement_convention": (
            "Positive actual-minus-forecast volume is bought at reBAP; "
            "negative volume is sold at reBAP."
        ),
        "identical_imbalance_across_strategies": True,
        "hedging_purpose": (
            "Procurement price risk management, not speculative profit."
        ),
        "parameters": parameters,
        "strategies": annual["strategy"].tolist(),
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data = load_inputs()
    parameters = data["parameters"]
    profile_assumptions = data["profile_assumptions"]
    forecast = data["forecast"]
    hedge_timeseries = data["hedge_timeseries"]
    imbalance_prices = data["imbalance_prices"]
    if not isinstance(parameters, dict):
        raise TypeError("parameters is not a dictionary")
    if not all(
        isinstance(frame, pd.DataFrame)
        for frame in (
            profile_assumptions,
            forecast,
            hedge_timeseries,
            imbalance_prices,
        )
    ):
        raise TypeError("Build inputs must be DataFrames")

    seed = int(parameters["locked_seed"])
    actual, profile_summary = simulate_actual_load(
        seed,
        forecast,
        profile_assumptions,
        parameters,
    )
    settlement = add_market_settlement(
        actual,
        hedge_timeseries,
        imbalance_prices,
    )
    monthly = monthly_summary(settlement, hedge_timeseries)
    annual = annual_summary(settlement, hedge_timeseries, monthly)
    cost_components = annual[
        [
            "strategy",
            "fixed_futures_cost_eur",
            "day_ahead_scheduled_cost_eur",
            "imbalance_settlement_eur",
            "final_procurement_cost_eur",
        ]
    ].copy()
    procurement_pnl = build_procurement_pnl(annual)

    for frame in (
        actual,
        profile_summary,
        settlement,
        monthly,
        annual,
        cost_components,
        procurement_pnl,
    ):
        numeric_columns = frame.select_dtypes(include="number").columns
        frame[numeric_columns] = frame[numeric_columns].round(8)

    actual.to_csv(OUTPUT_DIR / "actual_portfolio_2024.csv", index=False)
    profile_summary.to_csv(
        OUTPUT_DIR / "actual_profile_summary.csv",
        index=False,
    )
    settlement.to_csv(
        OUTPUT_DIR / "imbalance_settlement_timeseries.csv",
        index=False,
    )
    monthly.to_csv(
        OUTPUT_DIR / "monthly_procurement_comparison.csv",
        index=False,
    )
    annual.to_csv(
        OUTPUT_DIR / "annual_procurement_comparison.csv",
        index=False,
    )
    cost_components.to_csv(
        OUTPUT_DIR / "procurement_cost_components.csv",
        index=False,
    )
    procurement_pnl.to_csv(
        OUTPUT_DIR / "procurement_cost_pnl.csv",
        index=False,
    )
    metadata = build_metadata(seed, parameters, settlement, annual)
    (OUTPUT_DIR / "imbalance_backtest_metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    seed_metrics = evaluate_seed(seed, data)
    print(f"Built imbalance backtest outputs in {OUTPUT_DIR}")
    print(f"Locked seed: {seed}")
    print(
        "Actual energy: "
        f"{metadata['actual_energy_mwh']:,.2f} MWh; "
        f"NMAE: {metadata['portfolio_nmae']:.2%}"
    )
    print(
        "Imbalance premium: "
        f"{seed_metrics['imbalance_premium_eur']:,.2f} EUR "
        f"({seed_metrics['imbalance_premium_eur_mwh']:.3f} EUR/MWh)"
    )
    print(
        annual[
            [
                "strategy",
                "final_average_price_eur_mwh",
                "saving_vs_unhedged_eur",
                "monthly_average_price_std_eur_mwh",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
