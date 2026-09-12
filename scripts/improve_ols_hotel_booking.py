"""
scripts/improve_ols_hotel_booking.py
-------------------------------------

Adds hotel reservation features to the Node B (Fukui Station East) OLS
model, node-specifically — Node A (Tojinbo) is run unchanged as a
control to confirm it is unaffected.

Hotel features (from code4fukui/fukui-station-kanko-reservation
latest_rsv_sum.csv):
  hotel_reserve_lag1   — reservations, 1-day lag
  hotel_reserve_lag2   — reservations, 2-day lag
  hotel_reserve_roll7  — reservations, 7-day rolling average
  hotel_rooms_lag1     — rooms booked, 1-day lag
  hotel_people_lag1    — guests, 1-day lag

Validation: 5-fold Time-Series Cross-Validation across the full date
range (not a single 80/20 holdout — an earlier single-holdout check
happened to land entirely in one winter window and gave a misleading
picture, so this walks forward through several chronological folds
instead). Multicollinearity is checked via VIF (src.models.robustness_suite).

This script does NOT modify src/spatial.py, src/data_loader.py, or
src/models.py. It only imports and reuses their existing functions.
"""

from __future__ import annotations

import io
import urllib.request

import pandas as pd
import statsmodels.api as sm
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import TimeSeriesSplit

from src.config import load_config
from src.report import Reporter
from src.data_loader import load_all_data
from src.spatial import _load_peopleflow_daily, _load_node_weather_daily
from src.models import fit_ols, robustness_suite

HOTEL_RESERVATION_URL = (
    "https://code4fukui.github.io/fukui-station-kanko-reservation/latest_rsv_sum.csv"
)

BASE_FEATURES_TEMPLATE = ["temp", "precip", "wind", "snow_depth"]
HOTEL_FEATURES = [
    "hotel_reserve_lag1", "hotel_reserve_lag2", "hotel_reserve_roll7",
    "hotel_rooms_lag1", "hotel_people_lag1",
]

N_CV_SPLITS = 5


def fetch_hotel_reservations() -> pd.DataFrame:
    """Fetch Fukui Station hotel reservation telemetry (read-only)."""
    req = urllib.request.Request(
        HOTEL_RESERVATION_URL, headers={"User-Agent": "FTAS-OLS-Improve/1.0"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        csv_text = resp.read().decode("utf-8")
    df = pd.read_csv(io.StringIO(csv_text))
    date_col = next(
        (c for c in df.columns if any(t in str(c).lower() for t in ["date", "visit", "日付", "年月"])),
        df.columns[0],
    )
    df["date"] = pd.to_datetime(df[date_col]).dt.normalize()
    df = df.sort_values("date").reset_index(drop=True)

    df["hotel_reserve_lag1"] = df["n_reserve"].shift(1)
    df["hotel_reserve_lag2"] = df["n_reserve"].shift(2)
    df["hotel_reserve_roll7"] = df["n_reserve"].shift(1).rolling(7, min_periods=1).mean()
    df["hotel_rooms_lag1"] = df["n_room"].shift(1)
    df["hotel_people_lag1"] = df["n_people"].shift(1)
    return df


def build_node_model_df(
    count_df: pd.DataFrame,
    weather_df: pd.DataFrame,
    rsi: pd.DataFrame,
    route_col: str,
    hotel_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Assemble the modelling DataFrame for one node (optionally + hotel)."""
    model_df = count_df.merge(weather_df, on="date", how="inner")
    model_df = model_df.merge(rsi[["date", route_col]], on="date", how="inner")

    model_df["snow_depth"] = pd.to_numeric(
        model_df.get("snow_depth", pd.Series(dtype=float)), errors="coerce"
    ).fillna(0.0)

    if hotel_df is not None:
        model_df = model_df.merge(hotel_df[["date"] + HOTEL_FEATURES], on="date", how="left")
        model_df[HOTEL_FEATURES] = model_df[HOTEL_FEATURES].fillna(0.0)

    required = [route_col, "temp", "precip", "wind", "snow_depth"]
    model_df = model_df.dropna(subset=["count"] + required).reset_index(drop=True)
    return model_df.sort_values("date").reset_index(drop=True)


def time_series_cv(model_df: pd.DataFrame, feature_cols: list[str], label: str, n_splits: int = N_CV_SPLITS) -> pd.DataFrame:
    """Chronological k-fold cross-validation across the full date range."""
    X = model_df[feature_cols].values
    y = model_df["count"].values

    tscv = TimeSeriesSplit(n_splits=n_splits)
    rows = []
    for fold, (train_idx, test_idx) in enumerate(tscv.split(X), start=1):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        model = sm.OLS(y_train, sm.add_constant(X_train, has_constant="add")).fit()
        y_pred = model.predict(sm.add_constant(X_test, has_constant="add"))

        rows.append({
            "fold": fold,
            "r2": r2_score(y_test, y_pred),
            "mae": mean_absolute_error(y_test, y_pred),
        })

    cv_df = pd.DataFrame(rows)
    print(f"{label}: CV avg R² = {cv_df['r2'].mean():+.4f} (std={cv_df['r2'].std():.4f})  "
          f"CV avg MAE = {cv_df['mae'].mean():.1f}")
    return cv_df


def main():
    cfg = load_config()
    reporter = Reporter(cfg)
    paths = cfg["paths"]
    ws = cfg["_resolved"]["workspace_root"]
    repo = cfg["_resolved"]["repo_dir"]

    data = load_all_data(cfg, reporter)
    rsi, route_col = data["rsi"], data["route_col"]
    feature_cols_base = [route_col] + BASE_FEATURES_TEMPLATE

    # ── Node A (Tojinbo) — control, must stay unaffected ────────────────────
    node_a_counts = _load_peopleflow_daily(str(ws / paths["camera"]["tojinbo"]))
    node_a_weather = _load_node_weather_daily(str(repo / paths["weather"]["mikuni"]))
    node_a_df = build_node_model_df(node_a_counts, node_a_weather, rsi, route_col)
    node_a_ols = fit_ols(node_a_df, feature_cols_base, reporter)

    # ── Node B (Fukui Station) — baseline ────────────────────────────────────
    node_b_counts = _load_peopleflow_daily(str(ws / paths["camera"]["fukui_station"]))
    node_b_weather = _load_node_weather_daily(str(repo / paths["weather"]["fukui"]))
    node_b_baseline_df = build_node_model_df(node_b_counts, node_b_weather, rsi, route_col)
    node_b_baseline_ols = fit_ols(node_b_baseline_df, feature_cols_base, reporter)
    baseline_cv = time_series_cv(node_b_baseline_df, feature_cols_base, "Node B baseline")

    # ── Node B (Fukui Station) — hotel-augmented ────────────────────────────
    hotel_df = fetch_hotel_reservations()
    node_b_aug_df = build_node_model_df(node_b_counts, node_b_weather, rsi, route_col, hotel_df=hotel_df)
    feature_cols_aug = feature_cols_base + HOTEL_FEATURES

    node_b_aug_ols = fit_ols(node_b_aug_df, feature_cols_aug, reporter)
    node_b_aug_robust = robustness_suite(node_b_aug_df, node_b_aug_ols, feature_cols_aug, reporter)
    max_vif = node_b_aug_robust.vif["vif"].max() if node_b_aug_robust.vif is not None else None

    aug_cv = time_series_cv(node_b_aug_df, feature_cols_aug, "Node B + hotel")

    # ── Summary ───────────────────────────────────────────────────────────
    print("\n" + "=" * 66)
    print("SUMMARY — OLS IMPROVEMENT WITH HOTEL BOOKING (Node-Specific)")
    print("=" * 66)
    print(f"{'Metric':<26} | {'Node A':<10} | {'Node B base':<12} | {'Node B +hotel':<14}")
    print("-" * 66)
    print(f"{'In-sample R²':<26} | {node_a_ols.r2:<10.4f} | {node_b_baseline_ols.r2:<12.4f} | {node_b_aug_ols.r2:<14.4f}")
    print(f"{'CV avg R² (5 periods)':<26} | {'—':<10} | {baseline_cv['r2'].mean():<12.4f} | {aug_cv['r2'].mean():<14.4f}")
    print(f"{'CV avg MAE (5 periods)':<26} | {'—':<10} | {baseline_cv['mae'].mean():<12.1f} | {aug_cv['mae'].mean():<14.1f}")
    if max_vif is not None:
        flag = " (>10, some collinearity)" if max_vif > 10 else ""
        print(f"{'Max VIF (+hotel model)':<26} | {'—':<10} | {'—':<12} | {max_vif:<14.1f}{flag}")
    print("-" * 66)
    print(f"Δ CV avg R² = {aug_cv['r2'].mean() - baseline_cv['r2'].mean():+.4f}")
    print(f"Node A unaffected: R² stayed at {node_a_ols.r2:.4f} (no hotel features applied)")
    print("=" * 66)


if __name__ == "__main__":
    main()