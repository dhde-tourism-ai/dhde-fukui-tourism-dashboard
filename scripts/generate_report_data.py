"""
generate_report_data.py
------------------------
Builds public/data/dashboard_data.json for the FTAS Executive Dashboard.
- Iterates the full 4-node DHDE spatial network (Tojinbo, Fukui Station,
  Katsuyama, Rainbow Line) instead of Tojinbo alone.
- Ingests Fukui Station hotel reservation telemetry from the local
  ``latest_rsv_sum.csv`` snapshot and attaches lag/rolling features to
  Node B ('fukui_station') only.
- Robust weather column mapper and safe imputation (prevents 0-row dropna drops).
- Fast time-series data loader bypassing heavy survey NLP text scrubbing,
  with Node C's survey-proxy fallback when camera counts are unavailable.
- Full live JMA Bosai API fallback when local weather data is stale.
"""
 
from __future__ import annotations
 
import json
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
 
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
 
from src.config import load_config, resolve_repo_path
from src.report import Reporter
from src.feature_engineering import build_features, load_hotel_reservations, HOTEL_FEATURE_NODE
from src.spatial import _load_peopleflow_daily, _load_node_weather_daily, build_node_metrics
 
JMA_AREA_CODE = "180000"
JMA_ENDPOINT = f"https://www.jma.go.jp/bosai/forecast/data/forecast/{JMA_AREA_CODE}.json"
 
WEATHER_FRESHNESS_THRESHOLD_DAYS = 3
 
RF_PARAMS = dict(
    n_estimators=300, max_depth=10, min_samples_leaf=5,
    random_state=42, n_jobs=-1,
)
 
# ── 4-node DHDE network config ───────────────────────────────────────────────
# camera_key / weather_key map onto cfg["paths"]["camera"][...] and
# cfg["paths"]["weather"][...] — the same keys spatial.py's multi_node_analysis
# already uses, so both modules stay in sync with one config schema.
NODE_CONFIG: dict[str, dict] = {
    "tojinbo": {
        "label": "Tojinbo",
        "description": "Coastal / Mikuni weather",
        "camera_key": "tojinbo",
        "weather_key": "mikuni",
    },
    "fukui_station": {
        "label": "Fukui Station East",
        "description": "Urban transit hub / Fukui City weather + Hotel reservation lags",
        "camera_key": "fukui_station",
        "weather_key": "fukui",
    },
    "katsuyama": {
        "label": "Katsuyama",
        "description": "Mountainous / Katsuyama weather / Survey-proxy count",
        "camera_key": "katsuyama",
        "weather_key": "katsuyama",
        "survey_proxy_fallback": True,
    },
    "rainbow_line": {
        "label": "Rainbow Line",
        "description": "Scenic corridor / Mihama weather / Gate detections",
        "camera_key": "rainbow_line",
        "weather_key": "rainbow_line",
    },
}
 
 
def fetch_weather_forecast() -> list[dict]:
    """Fetch the 14-day weather forecast from the JMA Bosai API for Fukui.
 
    A single prefecture-wide forecast (area code 180000) is shared across
    all 4 nodes — JMA does not publish node-level granularity.
    """
    req = urllib.request.Request(JMA_ENDPOINT, headers={"User-Agent": "FTAS-Dashboard/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[WARN] JMA fetch failed: {e}")
        return []
 
    forecast_days = []
    try:
        short_term = data[0]["timeSeries"][0]
        time_defines = short_term["timeDefines"]
        weather_area = short_term["areas"][0]
        weathers = weather_area.get("weathers", [])
        winds = weather_area.get("winds", [])
        pops_series = data[0]["timeSeries"][1] if len(data[0]["timeSeries"]) > 1 else None
        pops_defines = pops_series["timeDefines"] if pops_series else []
        pops_area = pops_series["areas"][0] if pops_series else {}
        pops = pops_area.get("pops", [])
 
        for i, date_str in enumerate(time_defines):
            date = date_str[:10]
            pop_value = None
            for j, pdate in enumerate(pops_defines):
                if pdate[:10] == date and j < len(pops) and pops[j]:
                    pop_value = int(pops[j])
                    break
            forecast_days.append({
                "date": date,
                "weather": weathers[i] if i < len(weathers) else None,
                "wind": winds[i] if i < len(winds) else None,
                "precipitation_pct": pop_value,
                "rain_risk": bool(pop_value is not None and pop_value >= 40),
            })
    except Exception as e:
        print(f"[WARN] Unexpected JMA response format: {e}")
 
    return forecast_days
 
 
def find_date_column(df: pd.DataFrame) -> str:
    """Detects the datetime column safely across varying datasets."""
    for c in df.columns:
        c_low = str(c).lower()
        if any(t in c_low for t in ["date", "日付", "年月", "time", "day", "jst", "datetime"]):
            if not any(neg in c_low for neg in ["name", "id", "node", "place", "location"]):
                return c
    return df.columns[0]
 
 
def standardize_weather_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Maps varied weather column names to standard keys and guarantees defaults."""
    df_clean = pd.DataFrame(index=df.index)
 
    col_mapping = {
        "precip": ["precip", "precipitation", "rain", "降水", "雨量"],
        "temp": ["temp", "temperature", "気温"],
        "sun": ["sun", "sunshine", "日照"],
        "wind": ["wind", "wind_speed", "風速"],
        "humidity": ["humidity", "humid", "湿度"],
    }
 
    defaults = {
        "precip": 0.0,
        "temp": 18.0,
        "sun": 5.0,
        "wind": 3.0,
        "humidity": 65.0,
    }
 
    for standard_name, aliases in col_mapping.items():
        found = False
        for c in df.columns:
            if any(alias in str(c).lower() for alias in aliases):
                df_clean[standard_name] = pd.to_numeric(df[c], errors="coerce")
                found = True
                break
        if not found:
            df_clean[standard_name] = defaults[standard_name]
 
    return df_clean
 
 
# ── Per-node loaders ──────────────────────────────────────────────────────────
 
RSI_ROUTE_COL = "directions"
RSI_EXTRA_COLS = ["search_views"]

# Maps a node to the trend-report's per-municipality file (area_<name>_*.csv)
# covering it, so its RSI signal reflects local search intent instead of a
# prefecture-wide average. Fukui Station has no matching municipality file
# in the trend-report dataset (Fukui City isn't one of the tracked areas),
# so it always falls back to the prefecture-wide total.
NODE_RSI_AREA = {
    "tojinbo": "坂井市",       # Sakai City — only tracked from 2026 onward; earlier
                                # dates fall back to the prefecture-wide total below.
    "katsuyama": "勝山市",     # Katsuyama City — full history available.
    "rainbow_line": "美浜町",  # Mihama Town — full history available.
}


def _rsi_year_dirs(rsi_dir: Path) -> list[Path]:
    return sorted(p for p in rsi_dir.iterdir() if p.is_dir() and p.name.isdigit())


def _load_total_rsi(rsi_dir: Path) -> pd.DataFrame:
    """Load the prefecture-wide RSI signal, concatenated across all years."""
    frames = []
    for year_dir in _rsi_year_dirs(rsi_dir):
        f = year_dir / "total_daily_metrics.csv"
        if f.exists():
            frames.append(pd.read_csv(f))
    if not frames:
        raise FileNotFoundError(f"No total_daily_metrics.csv found under {rsi_dir} (expected year subfolders).")
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    return df.dropna(subset=["date"]).drop_duplicates("date").sort_values("date").reset_index(drop=True)


def _load_area_rsi(rsi_dir: Path, area_name: str) -> pd.DataFrame:
    """Load one municipality's RSI signal, concatenated across whichever
    years it's tracked in (some areas were added later, e.g. 坂井市 in 2026)."""
    frames = []
    for year_dir in _rsi_year_dirs(rsi_dir):
        matches = list(year_dir.glob(f"area_{area_name}_*.csv"))
        if matches:
            frames.append(pd.read_csv(matches[0]))
    if not frames:
        return pd.DataFrame(columns=["date", RSI_ROUTE_COL, *RSI_EXTRA_COLS])
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    return df.dropna(subset=["date"]).drop_duplicates("date").sort_values("date").reset_index(drop=True)


def _load_node_rsi(cfg: dict, node_key: str) -> tuple[pd.DataFrame, str]:
    """Load per-node RSI (route/direction search-intent) signal.

    Reads directly from ``cfg["paths"]["rsi_data"]`` (the real,
    multi-year, per-municipality trend-report dataset) instead of an
    ad-hoc glob across the whole home directory — that glob previously
    matched a stale, 78-row leftover snapshot in an unrelated Downloads
    folder before ever reaching the real sibling repo, because the real
    data lives under year subfolders (``data/2024/``, ``data/2025/``,
    ...) one level deeper than the glob pattern accounted for. The
    result was a signal so sparse it was almost entirely a constant
    fill value — explaining why "directions" (the paper's #1 predictor,
    β=+0.456) showed near-zero correlation in the dashboard.

    Where the node has a matching municipality file (see
    ``NODE_RSI_AREA``), its local signal is used, falling back to the
    prefecture-wide total for any date the area file doesn't cover
    (rather than the previous behavior of silently filling gaps with a
    flat median).
    """
    ws = Path(cfg["_resolved"]["workspace_root"])
    rsi_dir = ws / cfg["paths"]["rsi_data"]
    total = _load_total_rsi(rsi_dir)[["date", RSI_ROUTE_COL, *RSI_EXTRA_COLS]]

    area_name = NODE_RSI_AREA.get(node_key)
    if not area_name:
        return total, RSI_ROUTE_COL

    area_df = _load_area_rsi(rsi_dir, area_name)
    if area_df.empty:
        return total, RSI_ROUTE_COL

    area_cols = {c: f"{c}__area" for c in (RSI_ROUTE_COL, *RSI_EXTRA_COLS)}
    merged = pd.merge(
        total, area_df[["date", *area_cols]].rename(columns=area_cols),
        on="date", how="left",
    )
    for col, area_col in area_cols.items():
        merged[col] = merged[area_col].fillna(merged[col])
        merged = merged.drop(columns=[area_col])
    return merged, RSI_ROUTE_COL
 
 
def _resolve_hotel_csv_path(cfg: dict) -> Path | None:
    """Locate the local Node B hotel-reservation CSV (latest_rsv_sum.csv)."""
    ws = Path(cfg["_resolved"]["workspace_root"])
    configured = cfg.get("paths", {}).get("hotel_reservations")
    if configured:
        p = ws / configured
        if p.exists():
            return p
 
    matches = list(ws.glob("**/latest_rsv_sum.csv"))
    return matches[0] if matches else None
 
 
def _load_node_counts(cfg: dict, node_key: str, reporter: Reporter) -> tuple[pd.DataFrame, str]:
    """Load daily camera counts for one node, with Node C's survey-proxy fallback."""
    ws = cfg["_resolved"]["workspace_root"]
    paths = cfg["paths"]
    node = NODE_CONFIG[node_key]
 
    counts = _load_peopleflow_daily(str(ws / paths["camera"][node["camera_key"]]))
    source = "camera"
 
    if counts.empty and node.get("survey_proxy_fallback"):
        source = "survey_proxy"
        survey_path = str(ws / paths["survey"]["raw_fukui"])
        try:
            s = pd.read_csv(survey_path, low_memory=False)
            s["date"] = pd.to_datetime(s.get("回答日時"), errors="coerce").dt.normalize()
            text_cols = [c for c in ["回答エリア", "回答エリア2", "市町村"] if c in s.columns]
            mask = pd.Series(False, index=s.index)
            for c in text_cols:
                mask = mask | s[c].astype(str).str.contains("勝山|恐竜|ダイナソー|博物館", na=False)
            s2 = s[mask & s["date"].notna()].copy()
            counts = s2.groupby("date").size().reset_index(name="count")
            reporter.log(f"[{node_key}] fallback: survey proxy (rows={len(counts)})")
        except Exception as e:
            reporter.log(f"[{node_key}] survey proxy fallback failed ({e})")
            counts = pd.DataFrame(columns=["date", "count"])
 
    return counts, source
 
 
def _load_node_weather(cfg: dict, node_key: str) -> pd.DataFrame:
    repo = cfg["_resolved"]["repo_dir"]
    node = NODE_CONFIG[node_key]
    return _load_node_weather_daily(str(repo / cfg["paths"]["weather"][node["weather_key"]]))
 
 
def _merge_node_daily(
    counts: pd.DataFrame,
    weather: pd.DataFrame,
    rsi_df: pd.DataFrame,
    route_col: str,
) -> pd.DataFrame:
    """Merge one node's camera counts + weather + its RSI intent signal."""
    daily = pd.merge(counts[["date", "count"]], weather, on="date", how="left")
    daily = pd.merge(daily, rsi_df, on="date", how="left")
    for col in [route_col, *RSI_EXTRA_COLS]:
        if col not in daily.columns:
            continue
        daily[col] = daily[col].fillna(
            daily[col].median() if not daily[col].dropna().empty else 0.0
        )
 
    # Guarantee all standard weather columns are present and filled. Node
    # weather CSVs (via spatial._load_node_weather_daily) carry temp/precip/
    # wind/snow_depth only — sun/humidity fall back to their defaults here.
    for col, default_val in [("precip", 0.0), ("temp", 18.0), ("sun", 5.0), ("wind", 3.0), ("humidity", 65.0)]:
        if col not in daily.columns:
            daily[col] = default_val
        else:
            daily[col] = daily[col].ffill().bfill().fillna(default_val)
 
    return daily.sort_values("date").reset_index(drop=True)
 
 
def is_local_weather_stale(daily: pd.DataFrame, threshold_days: int = WEATHER_FRESHNESS_THRESHOLD_DAYS) -> bool:
    if daily.empty:
        return True
    weather_cols = [c for c in ("temp", "precip", "wind") if c in daily.columns]
    if not weather_cols:
        return True
    has_weather = daily.dropna(subset=weather_cols, how="any")
    if has_weather.empty:
        return True
    last_weather_date = has_weather["date"].max()
    age_days = (pd.Timestamp(datetime.utcnow().date()) - last_weather_date).days
    return age_days > threshold_days
 
 
def compute_pacing_status(current_bookings: float, model_forecast: float) -> dict:
    rate = 0.0 if model_forecast == 0 else current_bookings / model_forecast
    if rate >= 1.20:
        badge, label = "HOT", "Superb"
    elif rate >= 0.80:
        badge, label = "OK", "Strong"
    elif rate >= 0.60:
        badge, label = "WARN", "Warning"
    else:
        badge, label = "CRIT", "Critical"
    return {"rate": round(rate, 4), "badge": badge, "label": label}
 
 
WALKFORWARD_MIN_TRAIN_FRAC = 0.50  # require this much history before the first backtest fold
WALKFORWARD_MIN_TRAIN_DAYS = 60
WALKFORWARD_REFIT_STEP = 30  # days per fold; re-fit on an expanding window each fold

DASHBOARD_ONLY_FEATURE_COLS = ["count_lag1", "count_lag7", "count_roll7", "search_views", "search_views_roll7"]


def add_dashboard_only_features(df: pd.DataFrame, feature_cols: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """Layer dashboard-only features on top of ``build_features``'s output.

    This deliberately does NOT touch ``src/feature_engineering.py`` —
    that module also backs the published academic pipeline
    (``src/run_analysis.py``), whose reported OLS/RF metrics must stay
    reproducible against the paper's methodology, and its ``models.py``
    LDV model already adds its own ``count_lag1`` on top of
    ``feature_cols`` (``ldv_feats = feature_cols + ["count_lag1"]``),
    which would collide with a duplicate column if added upstream.

    Adds:
    - ``count_lag1``/``count_lag7``/``count_roll7``: without an
      autoregressive feature on the target itself, the RF has no memory
      of recent actual traffic and a naive "yesterday's count" baseline
      reliably beat it on true held-out data (e.g. Fukui Station: naive
      MAE 1859 vs. RF MAE 2473 on the held-out 20%).
    - ``search_views``/``search_views_roll7``: the trend-report dataset
      (``_load_node_rsi``) carries this alongside ``directions`` but it
      was previously discarded entirely — same-day raw value plus a
      shifted 7-day rolling mean, mirroring how ``route_col`` itself is
      used same-day elsewhere in ``feature_cols``.
    """
    df = df.sort_values("date").reset_index(drop=True)
    df["count_lag1"] = df["count"].shift(1)
    df["count_lag7"] = df["count"].shift(7)
    df["count_roll7"] = df["count"].shift(1).rolling(7, min_periods=1).mean()
    if "search_views" in df.columns:
        df["search_views_roll7"] = df["search_views"].shift(1).rolling(7, min_periods=1).mean()
    extra = [c for c in DASHBOARD_ONLY_FEATURE_COLS if c not in feature_cols and c in df.columns]
    return df, feature_cols + extra


def train_and_predict(
    daily: pd.DataFrame,
    route_col: str,
    reporter: Reporter,
    *,
    node_key: str,
    hotel_df: pd.DataFrame | None = None,
):
    """Fit the per-node demand model and produce actual-vs-forecast history.

    Two different models are used on purpose, because a single static
    80/20 split was the root cause of the dashboard showing badly-wrong
    forecasts: the model was fit once on the first 80% of history and
    then asked to predict the *entire* series including months of data
    it never trained on — every point on the displayed chart was
    effectively a stale, months-old extrapolation with no way to tell.

    - A walk-forward backtest (expanding window, re-fit every
      ``WALKFORWARD_REFIT_STEP`` days) produces the ``forecast`` column
      used for the "Actual vs. Model Forecast" chart, so every displayed
      point is a genuine out-of-sample prediction from a model that had
      not yet seen that day.
    - ``final_model``, returned separately, is re-fit on *all* available
      history and is what actually powers the forward-looking outlook
      (see ``build_estimated_outlook``) — so near-term predictions are
      always informed by the most recent data, not by whatever the
      training cutoff happened to be months ago.
    """
    df, feature_cols = build_features(
        daily, route_col, reporter, node_key=node_key, hotel_reservations=hotel_df,
    )
    df, feature_cols = add_dashboard_only_features(df, feature_cols)
    clean_full = df[["date", "count"] + feature_cols].dropna().reset_index(drop=True)
    n = len(clean_full)
    min_train = max(int(n * WALKFORWARD_MIN_TRAIN_FRAC), WALKFORWARD_MIN_TRAIN_DAYS)

    if min_train >= n:
        # Not enough history for even one walk-forward fold (new/short-lived
        # node) — fall back to a plain 80/20 split so the dashboard still
        # renders something instead of an empty chart.
        reporter.log(f"[{node_key}] history too short ({n} rows) for walk-forward backtest; using a single 80/20 split")
        min_train = max(int(n * 0.80), 1)

    forecast = pd.Series(index=clean_full.index, dtype=float)
    abs_errors: list[float] = []
    cursor = min_train
    while cursor < n:
        end = min(cursor + WALKFORWARD_REFIT_STEP, n)
        train_slice = clean_full.iloc[:cursor]
        test_slice = clean_full.iloc[cursor:end]
        fold_model = RandomForestRegressor(**RF_PARAMS)
        fold_model.fit(train_slice[feature_cols], train_slice["count"])
        preds = fold_model.predict(test_slice[feature_cols])
        forecast.iloc[cursor:end] = preds
        abs_errors.extend(abs(test_slice["count"].to_numpy() - preds))
        cursor = end

    holdout_mae = float(sum(abs_errors) / len(abs_errors)) if abs_errors else None
    if holdout_mae is not None:
        reporter.log(f"[{node_key}] walk-forward held-out MAE = {holdout_mae:.1f}")
    else:
        reporter.log(f"[{node_key}] not enough history for a walk-forward backtest fold")

    # Rows before the first fold have no genuine out-of-sample forecast —
    # drop them from what's displayed rather than fabricate a number.
    clean = clean_full.iloc[min_train:].copy().reset_index(drop=True)
    clean["forecast"] = forecast.iloc[min_train:].reset_index(drop=True)

    final_model = RandomForestRegressor(**RF_PARAMS)
    final_model.fit(clean_full[feature_cols], clean_full["count"])

    return clean[["date", "count", "forecast"]], final_model, feature_cols, holdout_mae
 
 
def build_estimated_outlook(
    daily: pd.DataFrame,
    route_col: str,
    model,
    feature_cols: list[str],
    *,
    node_key: str,
    hotel_df: pd.DataFrame | None,
    weather_forecast: list[dict],
) -> list[dict]:
    if not weather_forecast or daily.empty:
        return []
 
    weather_cols = [c for c in ("temp", "precip", "wind") if c in daily.columns]
    with_weather = daily.dropna(subset=weather_cols, how="any") if weather_cols else daily
    recent = with_weather.sort_values("date").tail(7)
    if recent.empty:
        return []
 
    baseline_temp = recent["temp"].mean() if "temp" in recent else 20.0
    baseline_sun = recent["sun"].mean() if "sun" in recent else 5.0
    baseline_wind = recent["wind"].mean() if "wind" in recent else 3.0
    recent_route_values = daily.sort_values("date")[route_col].dropna().tail(7).tolist()
    recent_search_views = (
        daily.sort_values("date")["search_views"].dropna().tail(7).tolist()
        if "search_views" in daily.columns else []
    )
    # Seeds the recursive count_lag1/count_lag7/count_roll7 features below:
    # each predicted day's demand is appended so later days in this same
    # forecast horizon see it as history, the same way a walk-forward
    # multi-step forecast would.
    recent_counts = daily.sort_values("date")["count"].dropna().tail(7).tolist()

    # Hotel baseline only means anything for Node B — for every other node
    # feature_cols simply won't contain the hotel_* keys below, so these
    # values are computed but never selected into the model input.
    dow_means = daily.groupby(daily['date'].dt.weekday)['count'].mean().to_dict() if ('date' in daily.columns and 'count' in daily.columns) else {}
    overall_mean = float(daily['count'].mean()) if ('count' in daily.columns and not daily.empty) else 0.0
    base_hotel_reserve = base_hotel_checkin = 0.0
    if node_key == HOTEL_FEATURE_NODE and hotel_df is not None and not hotel_df.empty:
        recent_hotel = hotel_df.sort_values("date").tail(7)
        base_hotel_reserve = float(recent_hotel["n_reserve"].mean())
        base_hotel_checkin = float(recent_hotel["n_stay"].mean())
 
    rows = []
    import jpholiday
    for day in weather_forecast:
        date = pd.to_datetime(day["date"])
        precip_estimate = 8.0 if day.get("rain_risk") else 0.0
        is_weekend = int(date.dayofweek in (5, 6))
        is_holiday = int(jpholiday.is_holiday(date.date()))
        is_weekend_or_holiday = int(is_weekend or is_holiday)
        weather_severity = min(
            3,
            int(precip_estimate > 0) + int(precip_estimate > 10) + int((baseline_wind or 0) > 8),
        )
        route_roll7 = sum(recent_route_values) / len(recent_route_values) if recent_route_values else 0
        lag_values = (recent_route_values[-3:] if len(recent_route_values) >= 3
                      else recent_route_values + [route_roll7] * (3 - len(recent_route_values)))
 
        feature_row = {
            route_col: route_roll7,
            f"{route_col}_lag1": lag_values[-1],
            f"{route_col}_lag2": lag_values[-2],
            f"{route_col}_lag3": lag_values[-3],
            f"{route_col}_roll7": route_roll7,
            "precip": precip_estimate,
            "temp": baseline_temp,
            "sun": baseline_sun,
            "wind": baseline_wind,
            "precip_lag1": precip_estimate,
            "is_weekend_or_holiday": is_weekend_or_holiday,
            "weather_severity": weather_severity,
            "weekend_x_severity": is_weekend_or_holiday * weather_severity,
            "weekend_x_intent": is_weekend_or_holiday * route_roll7,
            "month": date.month,
            "dow_mean_count": dow_means.get(date.weekday(), overall_mean),
            "hotel_reserve_lag1": base_hotel_reserve,
            "hotel_reserve_lag7": base_hotel_reserve,
            "hotel_reserve_roll7": base_hotel_reserve,
            "hotel_checkin_lag1": base_hotel_checkin,
            "hotel_checkin_lag7": base_hotel_checkin,
            "hotel_checkin_roll7": base_hotel_checkin,
            "count_lag1": recent_counts[-1] if recent_counts else overall_mean,
            "count_lag7": recent_counts[-7] if len(recent_counts) >= 7 else (recent_counts[0] if recent_counts else overall_mean),
            "count_roll7": (sum(recent_counts[-7:]) / len(recent_counts[-7:])) if recent_counts else overall_mean,
            "search_views": recent_search_views[-1] if recent_search_views else 0.0,
            "search_views_roll7": (sum(recent_search_views) / len(recent_search_views)) if recent_search_views else 0.0,
        }
        X = pd.DataFrame([feature_row])[feature_cols]
        if X.isnull().any(axis=None):
            continue
        predicted = float(model.predict(X)[0])
        # Feed this prediction back in as history for the next iteration's
        # count_lag1/count_lag7/count_roll7 — a standard recursive
        # multi-step forecast, since real future counts don't exist yet.
        recent_counts.append(predicted)

        rows.append({
            "date": day["date"],
            "estimated_demand": round(predicted, 1),
            "weather": day.get("weather"),
            "precipitation_pct": day.get("precipitation_pct"),
            "rain_risk": day.get("rain_risk"),
            "is_estimated": True,
        })
    return rows
 
 
def build_summary(pred: pd.DataFrame) -> dict:
    last_date = pred["date"].max()
 
    def window_total(end_date, days):
        start = end_date - timedelta(days=days - 1)
        mask = (pred["date"] >= start) & (pred["date"] <= end_date)
        return pred.loc[mask, "count"].sum()
 
    current_30 = window_total(last_date, 30)
    prev_year_end = last_date - timedelta(days=365)
    previous_30 = window_total(prev_year_end, 30)
    diff = current_30 - previous_30
    yoy_pct = round((diff / previous_30 * 100), 2) if previous_30 else None
    this_week = pred[pred["date"] > last_date - timedelta(days=7)]
    this_week_pacing = compute_pacing_status(this_week["count"].sum(), this_week["forecast"].sum())
 
    return {
        "past_30_day": {
            "current_total": int(current_30),
            "previous_year_total": int(previous_30),
            "diff": int(diff),
            "yoy_pct": yoy_pct,
        },
        "this_week_pacing": this_week_pacing,
    }
 
 
def build_weekly_pacing(pred: pd.DataFrame) -> list[dict]:
    recent = pred.sort_values("date").tail(14)
    rows = []
    for _, r in recent.iterrows():
        status = compute_pacing_status(r["count"], r["forecast"])
        rows.append({
            "date": r["date"].strftime("%Y-%m-%d"),
            "actual": round(float(r["count"]), 1),
            "forecast": round(float(r["forecast"]), 1),
            **status,
        })
    return rows
 
 
def build_nudges(weather: list[dict], weekly_pacing: list[dict]) -> list[dict]:
    nudges = []
    for day in weather:
        if day.get("rain_risk"):
            nudges.append({
                "type": "weather", "date": day["date"],
                "message": "High rain probability — activate the indoor-activity plan and notify guests in advance.",
            })
    if weekly_pacing:
        last = weekly_pacing[-1]
        if last["badge"] in ("CRIT", "WARN"):
            nudges.append({
                "type": "demand", "date": last["date"],
                "message": "Below-expected pacing — activate an urgent 5-10% OTA discount.",
            })
        elif last["badge"] == "HOT":
            nudges.append({
                "type": "demand", "date": last["date"],
                "message": "Very high demand — raise rates and enable on-site upsell offers.",
            })
    return nudges
 
 
def build_dashboard_payload(cfg: dict, reporter: Reporter) -> dict:
    print("[1/5] Loading per-node RSI intent signal (per-municipality where available)...")

    print("[2/5] Loading Node B hotel reservation telemetry (latest_rsv_sum.csv)...")
    hotel_csv = _resolve_hotel_csv_path(cfg)
    hotel_df = load_hotel_reservations(hotel_csv) if hotel_csv else pd.DataFrame()
    if hotel_df.empty:
        print("      -> No local hotel reservation data found; Node B hotel features will default to 0.")
    else:
        print(f"      -> {len(hotel_df)} rows loaded from {hotel_csv}")
 
    print("[3/5] Fetching live 14-day weather forecast (shared across nodes)...")
    weather_forecast = fetch_weather_forecast()
 
    spending = cfg["economics"]["spending_per_visitor_yen"]
    nodes_payload: dict[str, dict] = {}
    node_metrics: dict[str, dict | None] = {}
 
    for node_key, node in NODE_CONFIG.items():
        print(f"[4/5] Building node '{node_key}' ({node['label']}) ...")
        counts, source = _load_node_counts(cfg, node_key, reporter)
        weather = _load_node_weather(cfg, node_key)
 
        if counts.empty:
            reporter.log(f"[{node_key}] Skipped — no usable count data ({node['label']}).")
            continue

        rsi_df, route_col = _load_node_rsi(cfg, node_key)
        daily = _merge_node_daily(counts, weather, rsi_df, route_col)

        node_hotel_df = hotel_df if node_key == HOTEL_FEATURE_NODE else None
        pred, model, feature_cols, holdout_mae = train_and_predict(
            daily, route_col, reporter, node_key=node_key, hotel_df=node_hotel_df,
        )

        weather_is_stale = is_local_weather_stale(daily)
        summary = build_summary(pred)
        mean_actual = float(pred["count"].mean()) if not pred.empty else 0.0
        summary["model_accuracy"] = {
            "walk_forward_mae": round(holdout_mae, 1) if holdout_mae is not None else None,
            "mean_actual": round(mean_actual, 1),
            "mae_pct_of_mean": (
                round(holdout_mae / mean_actual * 100, 1)
                if holdout_mae is not None and mean_actual
                else None
            ),
        }
        weekly_pacing = build_weekly_pacing(pred)
        nudges = build_nudges(weather_forecast, weekly_pacing)
 
        demand_forecast = [
            {
                "date": r["date"].strftime("%Y-%m-%d"),
                "actual": round(float(r["count"]), 1),
                "forecast": round(float(r["forecast"]), 1),
            }
            for _, r in pred.sort_values("date").tail(60).iterrows()
        ]
 
        estimated_outlook = []
        if weather_is_stale:
            estimated_outlook = build_estimated_outlook(
                daily, route_col, model, feature_cols,
                node_key=node_key, hotel_df=node_hotel_df, weather_forecast=weather_forecast,
            )
 
        nodes_payload[node_key] = {
            "label": node["label"],
            "description": node["description"],
            "data_source": source,
            "summary": summary,
            "weather_strip": weather_forecast,
            "demand_forecast": demand_forecast,
            "weekly_pacing": weekly_pacing,
            "nudges": nudges,
            "weather_data_is_stale": weather_is_stale,
            "feature_cols": feature_cols,
            "estimated_outlook": estimated_outlook,
        }
 
        print(f"[5/5] Computing opportunity-gap / weather-sensitivity metrics for '{node_key}'...")
        node_metrics[node_key] = build_node_metrics(
            node["label"], counts, weather, rsi_df, route_col, spending, reporter,
        )
 
    valid_metrics = {k: v for k, v in node_metrics.items() if v is not None}
    aggregate_lost_visitors = float(sum(v["lost_visitors"] for v in valid_metrics.values()))
    aggregate_yen = aggregate_lost_visitors * spending
 
    aggregate = {
        "node_count": len(valid_metrics),
        "opportunity_gap_visitors": int(round(aggregate_lost_visitors)),
        "opportunity_gap_yen": int(round(aggregate_yen)),
        "seasonal_weather_sensitivity_ratio": {
            k: round(v["weather_lift"], 4) for k, v in valid_metrics.items()
        },
    }
 
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "nodes": nodes_payload,
        "aggregate": aggregate,
    }
 
 
def export_json(payload: dict, cfg: dict) -> None:
    output_path = resolve_repo_path(cfg, "public", "data", "dashboard_data.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[OK] dashboard_data.json written to {output_path}")
 
 
def main():
    cfg = load_config()
    reporter = Reporter(cfg)
    payload = build_dashboard_payload(cfg, reporter)
    export_json(payload, cfg)
 
 
if __name__ == "__main__":
    main()
 

