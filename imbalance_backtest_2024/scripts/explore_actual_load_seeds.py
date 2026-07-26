"""Rank deterministic actual-load seeds against documented teaching criteria."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from build_imbalance_backtest import (
    evaluate_seed,
    load_inputs,
    prepare_seed_evaluation,
)

MODEL_DIR = Path(__file__).resolve().parents[1]
INSPECTION_DIR = MODEL_DIR / "inspection"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--stop", type=int, default=500)
    parser.add_argument("--top", type=int, default=20)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.start < 0 or args.stop < args.start:
        raise ValueError("Seed range must satisfy 0 <= start <= stop")
    if args.top <= 0:
        raise ValueError("--top must be positive")

    INSPECTION_DIR.mkdir(parents=True, exist_ok=True)
    data = load_inputs()
    context = prepare_seed_evaluation(data)
    rows = [
        evaluate_seed(seed, data, context)
        for seed in range(args.start, args.stop + 1)
    ]
    ranking = pd.DataFrame(rows).sort_values(
        ["score", "seed"],
        ignore_index=True,
    )
    numeric_columns = ranking.select_dtypes(include="number").columns
    ranking[numeric_columns] = ranking[numeric_columns].round(8)
    ranking.to_csv(
        INSPECTION_DIR / "seed_selection_candidates.csv",
        index=False,
    )

    selected = ranking.iloc[0].to_dict()
    audit = {
        "candidate_seed_start": args.start,
        "candidate_seed_stop": args.stop,
        "candidate_count": len(ranking),
        "selection_rule": (
            "Minimum documented score: proximity to 2% portfolio NMAE and "
            "0.35 EUR/MWh positive imbalance premium, with penalties for "
            "negative/excessive premium or hedged monthly volatility not "
            "below unhedged."
        ),
        "recommended_seed": int(selected["seed"]),
        "recommended_seed_metrics": selected,
    }
    (INSPECTION_DIR / "seed_selection_audit.json").write_text(
        json.dumps(audit, indent=2),
        encoding="utf-8",
    )
    print(ranking.head(args.top).to_string(index=False))
    print(
        f"\nRecommended seed: {int(selected['seed'])}. "
        "Update inputs/simulation_parameters.csv to lock it."
    )


if __name__ == "__main__":
    main()
