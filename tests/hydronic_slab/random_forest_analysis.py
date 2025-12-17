"""Random forest analysis of melt time per snow depth from CSV exports.

Usage example:
    python -m tests.hydronic_slab.random_forest_analysis \
        --csv path/to/combined_runs.csv \
        --target melt_time_per_mm_s

The dataset is expected to contain environmental readings from the Excel
export (air temperature, humidity, wind speed and direction), an angle column
for sloped vs non-sloped runs, and either a precomputed melt_time_per_mm_s
column or melt_time_s and snow_depth_cleared_mm columns that can be used to
derive the target.
"""

import argparse
import json
from pathlib import Path
from typing import Iterable, List, Tuple

import pandas as pd

try:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_absolute_error, r2_score
    from sklearn.model_selection import train_test_split
except Exception as exc:  # pragma: no cover - dependency hint
    raise SystemExit(
        "scikit-learn is required for this analysis. Install it with 'pip install scikit-learn'."
    ) from exc


DEFAULT_FEATURE_COLUMNS = [
    "air_temp_C",
    "humidity_pct",
    "wind_speed_mps",
    "wind_dir_deg",
    "angle_deg",
    "is_sloped",
]


def _ensure_target(df: pd.DataFrame, target_column: str | None) -> Tuple[pd.Series, str]:
    """Return the melt time per mm series, deriving it when needed."""

    if target_column and target_column in df:
        return df[target_column], target_column

    if {"melt_time_s", "snow_depth_cleared_mm"}.issubset(df.columns):
        derived = df["melt_time_s"] / df["snow_depth_cleared_mm"].replace(0, pd.NA)
        derived.name = "melt_time_per_mm_s"
        return derived, derived.name

    raise ValueError(
        "Target column not found. Provide --target or ensure melt_time_s and snow_depth_cleared_mm columns exist."
    )


def _ensure_features(df: pd.DataFrame, feature_columns: Iterable[str]) -> pd.DataFrame:
    """Create a feature frame with sloped indicator derived when absent."""

    feature_df = df.copy()
    if "is_sloped" not in feature_df.columns:
        angle_col = None
        for candidate in ("angle_deg", "tilt_angle_deg"):
            if candidate in feature_df.columns:
                angle_col = candidate
                break
        if angle_col:
            feature_df["is_sloped"] = (feature_df[angle_col].fillna(0) > 0).astype(int)
        else:
            feature_df["is_sloped"] = 0

    # Keep only requested columns and coerce to numeric for modeling stability
    trimmed = feature_df[list(feature_columns)].apply(pd.to_numeric, errors="coerce").fillna(0)
    return trimmed


def train_random_forest(
    csv_path: Path,
    target_column: str | None = None,
    feature_columns: List[str] | None = None,
    n_estimators: int = 300,
    test_size: float = 0.25,
    random_state: int = 42,
):
    """Train a random forest regressor and print feature importances."""

    df = pd.read_csv(csv_path)
    y, target_name = _ensure_target(df, target_column)
    X = _ensure_features(df, feature_columns or DEFAULT_FEATURE_COLUMNS)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state
    )

    model = RandomForestRegressor(
        n_estimators=n_estimators,
        random_state=random_state,
        n_jobs=-1,
        oob_score=False,
    )
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    r2 = r2_score(y_test, preds)
    mae = mean_absolute_error(y_test, preds)

    importances = sorted(
        zip(X.columns, model.feature_importances_), key=lambda pair: pair[1], reverse=True
    )

    print("\n=== Random forest melt-time-per-depth analysis ===")
    print(f"Samples: {len(df)} | Train: {len(X_train)} | Test: {len(X_test)}")
    print(f"Target: {target_name}")
    print(f"R^2: {r2:.3f} | MAE: {mae:.3f} seconds/mm")
    print("Feature importances (higher = more influence):")
    for name, weight in importances:
        print(f"  {name}: {weight:.4f}")

    return {
        "model": model,
        "r2": r2,
        "mae": mae,
        "feature_importances": importances,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Train a random forest to identify key drivers of melt time per snow depth."
    )
    parser.add_argument("--csv", required=True, type=Path, help="Path to the combined CSV dataset")
    parser.add_argument(
        "--target",
        help="Optional target column. If omitted, melt_time_per_mm_s is derived from melt_time_s/snow_depth_cleared_mm.",
    )
    parser.add_argument(
        "--features",
        nargs="+",
        default=DEFAULT_FEATURE_COLUMNS,
        help="Feature columns to include in the model (defaults match Excel export columns).",
    )
    parser.add_argument("--n-estimators", type=int, default=300, help="Number of trees in the forest")
    parser.add_argument("--test-size", type=float, default=0.25, help="Fraction of data for the test split")
    parser.add_argument("--random-state", type=int, default=42, help="Random seed for repeatability")
    parser.add_argument(
        "--save-report",
        type=Path,
        help="Optional path to save a JSON report with metrics and feature importances.",
    )
    args = parser.parse_args()

    result = train_random_forest(
        csv_path=args.csv,
        target_column=args.target,
        feature_columns=args.features,
        n_estimators=args.n_estimators,
        test_size=args.test_size,
        random_state=args.random_state,
    )

    if args.save_report:
        args.save_report.parent.mkdir(parents=True, exist_ok=True)
        with open(args.save_report, "w") as f:
            json.dump(
                {
                    "r2": result["r2"],
                    "mae": result["mae"],
                    "feature_importances": result["feature_importances"],
                },
                f,
                indent=2,
            )
        print(f"Saved report to {args.save_report}")


if __name__ == "__main__":
    main()
