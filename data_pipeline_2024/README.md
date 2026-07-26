# HTW Summer School 2024 data pipeline

This folder builds the teaching dataset for the retail electricity portfolio
project. It deliberately separates observed source data from the synthetic
forward-market snapshot.

## Data design

| Dataset | Status | Source / method |
| --- | --- | --- |
| Berlin HB, GB and LB profiles | Observed | Stromnetz Berlin 2024 SLP workbooks |
| Day-Ahead prices | Observed | Bundesnetzagentur SMARD, DE/LU |
| Imbalance price | Observed | Netztransparenz, quality-assured reBAP |
| Shape factors | Derived | Robust hourly pattern from 2019-2022 SMARD prices |
| Futures prices and market activity | Synthetic | Calibrated teaching snapshot dated 2023-09-29 |

The futures snapshot is designed so that a long hedge earns a small ex-post
gain of approximately EUR 1.25/MWh against the observed 2024 Day-Ahead block
averages. The generated prices are not historical EEX observations.

The exercise offers three alternative product sets:

- coarse: CAL 2024;
- intended granular: M01-M03 plus Q2-Q4, covering the year without overlap;
- optional extension: Q1-Q4.

These are alternative hedges. Students should not combine overlapping annual,
quarterly and monthly contracts in the same full-volume hedge.

The one-column `market_activity` indicator is intentionally simple:

- values above 100 indicate clearly usable teaching products;
- values from 1 to 10 indicate deliberately illiquid monthly products;
- it is a synthetic teaching proxy, not an exchange liquidity statistic.

## Folder structure

```text
data_pipeline_2024/
  raw/          downloaded source files
  processed/    student-ready CSV files
  inspection/   validation summaries and charts
  outputs/      final inspection workbook
  scripts/      reproducible fetch, build and inspection scripts
```

## Run

From the repository root:

```bash
uv sync
uv run python data_pipeline_2024/scripts/fetch_sources.py
uv run python data_pipeline_2024/scripts/build_dataset.py
uv run python data_pipeline_2024/scripts/inspect_dataset.py
```

The first command needs internet access. The other two run entirely from the
downloaded source files. If the raw files are already present, start with the
build command.

The inspection script fails on validation errors and writes:

- a compact JSON status and detailed check CSV;
- comparisons of forwards with realized Day-Ahead block averages;
- plots for the three SLPs, monthly market prices, the historical shape factor
  and futures-market activity.

## Important conventions

- Student-ready time series use UTC timestamps for unambiguous joins.
- A second ISO timestamp shows Europe/Berlin local time and its UTC offset.
- The 2024 SLP files contain 35,136 quarter-hours, including the daylight
  saving time transitions.
- Day-Ahead prices are hourly observations repeated across the four
  constituent quarter-hours for alignment with SLP and reBAP.
- Peak is simplified to Monday-Friday, 08:00-20:00 Europe/Berlin.
