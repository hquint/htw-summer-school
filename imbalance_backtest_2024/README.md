# HTW Summer School 2024 imbalance backtest

This folder completes the procurement-cost backtest. It takes the forecast
portfolio, futures hedges and Day-Ahead settlement from
`portfolio_hedge_2024`, creates a reproducible synthetic actual-load path and
settles the forecast deviation against observed 2024 reBAP.

Hedging is treated as risk management, not as a profit-seeking activity. Its
purpose is to make the procurement price more predictable. A realized saving
can occur when the futures price is favorable relative to the later spot
market, but that is an outcome of the backtest rather than the definition of a
successful hedge.

## Settlement boundary

The Day-Ahead schedule is the forecast portfolio for all three strategies:

```text
imbalance volume = actual load - forecast Day-Ahead schedule
imbalance settlement = imbalance volume * reBAP
```

Positive imbalance means the supplier consumed more than scheduled and buys
the shortfall at reBAP. Negative imbalance means the supplier consumed less
than scheduled and sells the surplus at reBAP. The observed German reBAP is
symmetric, so one price is used for both directions.

Because the Day-Ahead schedule is identical, the imbalance settlement is also
identical for `UNHEDGED`, `COARSE_CAL` and `GRANULAR`. The futures hedge
changes the price paid for the forecast volume; it does not remove load
forecast risk.

## Synthetic actual load

Actual load is generated separately for HB, GB and LB using:

- a persistent daily portfolio shock;
- a smaller persistent quarter-hour portfolio shock;
- profile-specific idiosyncratic shocks;
- a small documented annual consumption bias by profile.

The random shocks are centered using forecast-energy weights, which keeps the
annual profile bias auditable. All random parameters are in `inputs`, and the
final seed is locked for reproducibility.

The seed-selection script tests candidate seeds without altering observed
Day-Ahead or reBAP prices. Candidates are ranked against teaching criteria:

- plausible portfolio normalized absolute forecast error;
- a moderate positive imbalance premium versus Day-Ahead;
- lower monthly procurement-price volatility for the hedged strategies.

The complete candidate ranking is retained in the inspection output.

## Procurement cost

For each strategy:

```text
final procurement cost
    = fixed futures cost
    + forecast residual settled Day-Ahead
    + actual-minus-forecast deviation settled at reBAP
```

The annual and monthly outputs show the cost bridge, realized EUR/MWh, saving
versus unhedged procurement, open Day-Ahead volume and monthly price
volatility.

The reported volatility is the standard deviation of the twelve realized
monthly procurement prices. It is a transparent descriptive teaching metric,
not a probabilistic risk forecast or Value-at-Risk measure.

The imbalance premium is also shown separately:

```text
imbalance premium
    = imbalance volume * (reBAP - Day-Ahead price)
```

This separates the price consequence of being imbalanced from the ordinary
cost of serving more or less energy.

## Run

From the repository root:

```bash
uv run python imbalance_backtest_2024/scripts/explore_actual_load_seeds.py
uv run python imbalance_backtest_2024/scripts/build_imbalance_backtest.py
uv run python imbalance_backtest_2024/scripts/inspect_imbalance_backtest.py
```

The exploration step is only needed when deliberately reconsidering the
locked seed. The normal reproducible build starts with
`build_imbalance_backtest.py`.

The locked teaching case uses seed 173. It produces 43,138 MWh of actual
energy, 1.97% portfolio normalized mean absolute forecast error and a
€13,589 imbalance premium versus Day-Ahead.
