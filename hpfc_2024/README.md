# HTW Summer School 2024 HPFC

This folder constructs the default hourly price forward curve (HPFC) for the
2024 teaching project. The curve is arbitrage-consistent with the selected
tradable futures and preserves their quoted Base and Peak block values. It
consumes the curated inputs in `data_pipeline_2024/processed`; it does not
download or modify source data.

## Calibration set

The default curve uses the non-overlapping liquid products:

- Base and Peak M01, M02 and M03;
- Base and Peak Q2, Q3 and Q4.

Together these products cover the full year exactly once. CAL and Q1 remain
independent reconciliation checks. The deliberately illiquid M04-M12 quotes
are not used to construct the curve.

## Contract-consistent construction

For each calibration period, the Peak target is the quoted Peak future. The
implied Off-Peak target is:

```text
P_off = (P_base * N_all - P_peak * N_peak) / N_off
```

where `N` is the number of quarter-hours in the applicable block.

Within Peak and Off-Peak separately, the historical shape is rescaled:

```text
HPFC_t = P_slice * shape_t / mean(shape_slice)
```

This preserves the relative historical pattern while guaranteeing contract
consistency:

- the average Peak HPFC equals the Peak future;
- the average full-period HPFC equals the Base future.

The historical shape comes from real 2019-2022 SMARD Day-Ahead prices. Futures
prices remain the synthetic teaching quotes created by the data pipeline.

## Folder structure

```text
hpfc_2024/
  processed/    final quarter-hour HPFC and calibration parameters
  inspection/   reconciliation checks and charts
  outputs/      formatted inspection workbook
  scripts/      reproducible build and inspection scripts
```

## Run

From the repository root:

```bash
uv sync
uv run python hpfc_2024/scripts/build_hpfc.py
uv run python hpfc_2024/scripts/inspect_hpfc.py
```

The build is deterministic and needs no internet access once
`data_pipeline_2024/processed` exists.

## Interpretation

- The HPFC is an arbitrage-consistent forward-valuation curve, not a prediction
  of realized 2024 Day-Ahead prices and not itself a hedge.
- “Value-neutral” is reserved for the subsequent hedge constraint: the hedge
  and forecast load must have equal value when measured with this HPFC.
- CAL and Q1 reconcile within half a cent per MWh. Their tiny residuals are
  caused by the synthetic quotes being rounded independently to cents.
- Illiquid monthly products intentionally do not reconcile and are reported as
  `NOT_USED_ILLIQUID`.
- The next modelling step is to combine this curve with a customer portfolio,
  hedge optimization, residual Day-Ahead shaping and imbalance settlement.
