"""Feature engineering for the tourism demand prediction pipeline.

All functions accept a ``daily`` DataFrame and return an augmented copy.
Calendar features, weather severity, rolling/lag features, interaction
terms, day-of-week mean encoding, and Node B hotel-reservation lag
features are computed here.
"""

from __future__ import annotations

from pathlib import Path

import jpholiday
import pandas as pd

from .report import Reporter

# The only node hotel-reservation features may attach to. Any node_key
# other than this is a no-op in add_hotel_lag_features / build_features —
# that is the isolation guarantee, enforced in code rather than by caller
# discipline, so the signal cannot leak into Nodes A, C, or D.
HOTEL_FEATURE_NODE = "fukui_station"

HOTEL_FEATURE_COLS = [
    "hotel_reserve_lag1", "hotel_reserve_lag7", "hotel_reserve_roll7",
    "hotel_checkin_lag1", "hotel_checkin_lag7", "hotel_checkin_roll7",
]


def add_calendar_features(daily: pd.DataFrame) -> pd.DataFrame:
    """Add day-of-week, weekend, holiday, and month columns.

    Args:
        daily: Master daily DataFrame (must have ``date``).

    Returns:
        DataFrame with new columns ``dow``, ``is_weekend``, ``is_holiday``,
        ``is_weekend_or_holiday``, ``month``.
    """
    daily = daily.copy()
    daily["dow"] = daily["date"].dt.dayofweek
    daily["is_weekend"] = daily["dow"].isin([5, 6]).astype(int)
    daily["is_holiday"] = daily["date"].apply(
        lambda d: jpholiday.is_holiday(d.date())
    ).astype(int)
    daily["is_weekend_or_holiday"] = (
        (daily["is_weekend"] == 1) | (daily["is_holiday"] == 1)
    ).astype(int)
    daily["month"] = daily["date"].dt.month
    return daily


def add_weather_severity(
    daily: pd.DataFrame,
    *,
    precip_light: float = 0,
    precip_heavy: float = 10,
    wind_strong: float = 8,
) -> pd.DataFrame:
    """Compute a weather severity score (0–3).

    Scoring:
        0 = fine, 1 = light rain, 2 = heavy rain, 3 = stormy (rain + wind).

    Args:
        daily: Must have ``precip`` and ``wind`` columns.
        precip_light: Threshold for score +1.
        precip_heavy: Threshold for score +2.
        wind_strong: Threshold for score +1.

    Returns:
        DataFrame with new column ``weather_severity``.
    """
    daily = daily.copy()

    daily["weather_severity"] = (
        (daily["precip"] > precip_light).astype(int)
        + (daily["precip"] > precip_heavy).astype(int)
        + (daily["wind"] > wind_strong).astype(int)
    ).clip(upper=3)
    return daily


def add_rolling_features(
    daily: pd.DataFrame,
    col: str,
    windows: list[int] | None = None,
) -> pd.DataFrame:
    """Add rolling-mean columns for the given intent column.

    Args:
        daily: Master daily DataFrame.
        col: Column name to compute rolling means on.
        windows: Window sizes (default ``[3, 7, 14]``).

    Returns:
        DataFrame with new columns ``{col}_roll{w}`` for each window.
    """
    daily = daily.copy()
    for w in (windows or [3, 7, 14]):
        daily[f"{col}_roll{w}"] = daily[col].rolling(w, min_periods=1).mean()
    return daily


def add_lag_features(
    daily: pd.DataFrame,
    col: str,
    max_lag: int = 7,
) -> pd.DataFrame:
    """Add lagged columns for the intent column and weather.

    Args:
        daily: Must have ``col``, ``precip``, ``temp``.
        col: Column to lag.
        max_lag: Maximum lag in days (inclusive).

    Returns:
        DataFrame with ``{col}_lag0`` … ``{col}_lag{max_lag}`` plus
        ``precip_lag1`` and ``temp_lag1``.
    """
    daily = daily.copy()
    for lag in range(0, max_lag + 1):
        daily[f"{col}_lag{lag}"] = daily[col].shift(lag)
    daily["precip_lag1"] = daily["precip"].shift(1)
    daily["temp_lag1"] = daily["temp"].shift(1)
    return daily


def add_interaction_features(
    daily: pd.DataFrame,
    route_col: str,
) -> pd.DataFrame:
    """Add interaction terms.

    Args:
        daily: Must have ``is_weekend_or_holiday``, ``weather_severity``,
            and ``route_col``.
        route_col: Name of the RSI intent column.

    Returns:
        DataFrame with ``weekend_x_severity`` and ``weekend_x_intent``.
    """
    daily = daily.copy()
    daily["weekend_x_severity"] = (
        daily["is_weekend_or_holiday"] * daily["weather_severity"]
    )
    daily["weekend_x_intent"] = (
        daily["is_weekend_or_holiday"] * daily[route_col].fillna(0)
    )
    return daily


def add_dow_mean_encoding(daily: pd.DataFrame) -> pd.DataFrame:
    """Add day-of-week mean-encoded count.

    Args:
        daily: Must have ``dow`` and ``count``.

    Returns:
        DataFrame with ``dow_mean_count``.
    """
    daily = daily.copy()
    dow_means = daily.groupby("dow")["count"].mean()
    daily["dow_mean_count"] = daily["dow"].map(dow_means)
    return daily


# ── Node B hotel reservation features ────────────────────────────────────────

def load_hotel_reservations(csv_path: str | Path) -> pd.DataFrame:
    """Load Fukui Station hotel reservation telemetry from a local CSV.

    Args:
        csv_path: Path to ``latest_rsv_sum.csv``. Expected columns:
            ``date_visit``, ``n_stay``, ``n_people``, ``n_room``,
            ``amount_fee``, ``n_reserve``.

    Returns:
        DataFrame with a normalized ``date`` column plus the numeric
        reservation columns, de-duplicated by date and sorted ascending.
        Returns an empty (but correctly-shaped) DataFrame if the file is
        missing, unreadable, or has no parseable rows — callers should
        treat that the same as "no hotel signal available" rather than
        special-casing it.
    """
    csv_path = Path(csv_path)
    numeric_cols = ["n_stay", "n_people", "n_room", "amount_fee", "n_reserve"]
    empty = pd.DataFrame(columns=["date", *numeric_cols])

    if not csv_path.exists():
        return empty

    try:
        df = pd.read_csv(csv_path)
    except Exception:
        return empty

    if df.empty or len(df.columns) == 0:
        return empty

    date_col = next(
        (c for c in df.columns if any(t in str(c).lower() for t in ("date", "visit"))),
        df.columns[0],
    )
    df["date"] = pd.to_datetime(df[date_col], errors="coerce").dt.normalize()
    df = df.dropna(subset=["date"])
    if df.empty:
        return empty

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
        else:
            df[col] = 0.0

    return (
        df[["date", *numeric_cols]]
        .groupby("date", as_index=False)
        .sum()
        .sort_values("date")
        .reset_index(drop=True)
    )


def add_hotel_lag_features(
    daily: pd.DataFrame,
    hotel: pd.DataFrame | None,
    *,
    node_key: str,
) -> tuple[pd.DataFrame, list[str]]:
    """Add hotel booking/check-in lag + rolling features — Node B only.

    Adds t-1, t-7, and a 7-day rolling average for both reservation volume
    (``n_reserve``, i.e. bookings) and stay volume (``n_stay``, i.e.
    check-ins).

    Args:
        daily: Node daily DataFrame with a ``date`` column.
        hotel: Output of ``load_hotel_reservations``, or ``None``.
        node_key: The node this call is being run for. This is the
            isolation guard: any value other than ``HOTEL_FEATURE_NODE``
            (``"fukui_station"``) returns ``daily`` completely unchanged and
            an empty feature-column list, regardless of what ``hotel``
            contains — so passing hotel data for Node A/C/D is harmless.

    Returns:
        Tuple of ``(daily_with_hotel_features, hotel_feature_col_names)``.
    """
    if node_key != HOTEL_FEATURE_NODE:
        return daily, []

    daily = daily.copy()

    if hotel is None or hotel.empty:
        for col in HOTEL_FEATURE_COLS:
            daily[col] = 0.0
        return daily, HOTEL_FEATURE_COLS

    hotel = hotel.sort_values("date").copy()
    hotel["hotel_reserve_lag1"] = hotel["n_reserve"].shift(1)
    hotel["hotel_reserve_lag7"] = hotel["n_reserve"].shift(7)
    hotel["hotel_reserve_roll7"] = (
        hotel["n_reserve"].shift(1).rolling(7, min_periods=1).mean()
    )
    hotel["hotel_checkin_lag1"] = hotel["n_stay"].shift(1)
    hotel["hotel_checkin_lag7"] = hotel["n_stay"].shift(7)
    hotel["hotel_checkin_roll7"] = (
        hotel["n_stay"].shift(1).rolling(7, min_periods=1).mean()
    )

    daily = pd.merge(
        daily, hotel[["date", *HOTEL_FEATURE_COLS]], on="date", how="left"
    )
    daily[HOTEL_FEATURE_COLS] = daily[HOTEL_FEATURE_COLS].fillna(0.0)
    return daily, HOTEL_FEATURE_COLS


# ── Convenience wrapper ──────────────────────────────────────────────────────

def build_features(
    daily: pd.DataFrame,
    route_col: str,
    reporter: Reporter,
    *,
    cfg: dict | None = None,
    node_key: str = "tojinbo",
    hotel_reservations: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Run the full feature-engineering pipeline for one node.

    Args:
        daily: Raw merged daily DataFrame for a single node.
        route_col: RSI intent column name.
        reporter: ``Reporter`` instance.
        cfg: Optional config for custom thresholds.
        node_key: Which of the 4 network nodes ``daily`` belongs to
            (``"tojinbo"``, ``"fukui_station"``, ``"katsuyama"``,
            ``"rainbow_line"``). Only ``"fukui_station"`` picks up hotel
            reservation features — see ``add_hotel_lag_features``. Defaults
            to ``"tojinbo"`` so existing callers are unaffected.
        hotel_reservations: Output of ``load_hotel_reservations``. Ignored
            for any node other than ``"fukui_station"``.

    Returns:
        Tuple of ``(daily_with_features, feature_col_names)``.
    """
    reporter.section(2, f"Feature Engineering — {node_key}")

    thresholds = (cfg or {}).get("thresholds", {}).get("weather_severity", {})

    daily = add_calendar_features(daily)
    reporter.log(f"Weekend/Holiday days: {daily['is_weekend_or_holiday'].sum()} / {len(daily)}")

    daily = add_weather_severity(
        daily,
        precip_light=thresholds.get("precip_light", 0),
        precip_heavy=thresholds.get("precip_heavy", 10),
        wind_strong=thresholds.get("wind_strong", 8),
    )
    reporter.log(f"Weather severity distribution:\n"
                 f"{daily['weather_severity'].value_counts().sort_index().to_string()}")

    daily = add_rolling_features(daily, route_col)
    daily = add_lag_features(daily, route_col)
    daily = add_interaction_features(daily, route_col)
    daily = add_dow_mean_encoding(daily)

    daily, hotel_feature_cols = add_hotel_lag_features(
        daily, hotel_reservations, node_key=node_key
    )
    if node_key == HOTEL_FEATURE_NODE:
        reporter.log(f"Hotel reservation features attached ({node_key}): {hotel_feature_cols}")

    # Log DOW averages
    reporter.log("\nDay-of-week average counts:")
    dow_means = daily.groupby("dow")["count"].mean()
    for dow, v in dow_means.items():
        name = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][int(dow)]
        reporter.log(f"  {name}: {v:.1f}")

    # Correlation matrix
    corr_cols = [
        "count", route_col, f"{route_col}_lag2", f"{route_col}_roll7",
        "precip", "temp", "sun", "wind",
        "is_weekend_or_holiday", "weather_severity", "dow_mean_count",
    ] + hotel_feature_cols
    corr_cols = [c for c in corr_cols if c in daily.columns]
    corr_matrix = daily[corr_cols].corr()
    reporter.log("\nCorrelation with 'count':")
    for col in corr_cols:
        if col != "count":
            r = corr_matrix.loc["count", col]
            reporter.log(f"  {col:35s}  r = {r:+.3f}")

    # Define modelling feature columns
    feature_cols = [
        route_col,
        f"{route_col}_lag1", f"{route_col}_lag2", f"{route_col}_lag3",
        f"{route_col}_roll7",
        "precip", "temp", "sun", "wind",
        "precip_lag1",
        "is_weekend_or_holiday", "weather_severity",
        "dow_mean_count",
        "weekend_x_severity", "weekend_x_intent",
        "month",
    ] + hotel_feature_cols
    feature_cols = [c for c in feature_cols if c in daily.columns]

    return daily, feature_cols