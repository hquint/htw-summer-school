# HTW Summer School 2024 portfolio hedge

This folder contains the ex-ante portfolio and hedge layer of the teaching
project. It builds a forecast customer portfolio, optimizes two futures hedges
and settles the forecast position against observed 2024 Day-Ahead prices.

Imbalance settlement is deliberately excluded. It will be added later using
actual-load deviations from the forecast.

## Customer portfolio

The editable assumptions are in `inputs/portfolio_assumptions.csv`:

| Profile | Customers | MWh/customer/year | Portfolio energy |
| --- | ---: | ---: | ---: |
| HB | 10,000 | 3.5 | 35,000 MWh |
| GB | 200 | 30 | 6,000 MWh |
| LB | 20 | 100 | 2,000 MWh |
| **Total** | **10,220** |  | **43,000 MWh** |

The published Berlin SLPs each represent 1,000 MWh, not one individual
customer. The build script scales each normalized SLP to the annual energy
implied by customer count and consumption per customer.

## Hedge strategies

- `COARSE_CAL`: CAL Base and CAL Peak.
- `GRANULAR`: M01-M03 and Q2-Q4, with Base and Peak for every period.

Only products with `market_activity > 100` are eligible. Contract volumes are
continuous MW; lot sizes, transaction costs and bid-ask spreads remain outside
the teaching model.

## Value-neutral hedge optimization

The HPFC is treated as an arbitrage-/contract-consistent hourly price curve.
For each non-overlapping optimization period, the hedge is value-neutral when
valued on that curve:

```text
sum(hedge_energy_t * HPFC_t) = sum(forecast_load_t * HPFC_t)
```

Among all Base/Peak combinations satisfying this neutrality condition, the
model minimizes the quarter-hour shape mismatch:

```text
minimize sum((forecast_load_t - hedge_energy_t)^2)
```

This is solved as an equality-constrained least-squares problem. A
non-negativity check prevents short futures positions in the teaching case.

Value neutrality does not imply volume neutrality. The optimized hedge can
slightly overhedge low-value hours and underhedge high-value hours while its
net residual has zero HPFC value.

## Day-Ahead settlement

The effective procurement cost is shown in two equivalent forms:

```text
fixed futures cost + residual forecast shape at Day-Ahead
```

and:

```text
full forecast load at Day-Ahead - financial futures payoff
```

The build validates that both calculations are equal. A negative Day-Ahead
residual represents selling an overhedged forecast position back to the
Day-Ahead market.

## Run

From the repository root:

```bash
uv sync
uv run python portfolio_hedge_2024/scripts/build_portfolio_hedge.py
uv run python portfolio_hedge_2024/scripts/inspect_portfolio_hedge.py
```

No internet access is required once `data_pipeline_2024/processed` and
`hpfc_2024/processed` exist.

## Next module

The later `imbalance_backtest_2024` module will create actual-load deviations,
settle only the deviation against observed reBAP and compare final cost and
risk across the unhedged, coarse and granular strategies.
