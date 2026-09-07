"""PAK -> JPN Visitor Arrivals Board + FTAS Executive Dashboard.

Two dashboards on one page:

1. PAK -> JPN - Visitor Arrivals Board, a replication of
   `pakistan_japan_visitor_dashboard (1).html`, built directly from the
   JNTO / Japan Ministry of Justice CSVs in ./JNTO_Pakistan. The
   `build_data()` output is verified byte-identical to the JSON payload
   embedded in that HTML dashboard.

2. FTAS Executive Dashboard, a replication of `public/index.html`, driven by
   `public/data/dashboard_data.json` -- the same file that page fetches.

Run with:  streamlit run streamlit_app_pk_jpn_ftas.py
"""

from __future__ import annotations

import datetime
import json
import math
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# Palette / typography -- mirrors the :root custom properties in the HTML.
# ---------------------------------------------------------------------------
BG = "#12161d"
BG_2 = "#0d1015"
PANEL = "#181d26"
PANEL_ALT = "#1d2330"
LINE = "#2b3242"
LINE_SOFT = "#232a37"
INK = "#eceef2"
MUTED = "#8b93a5"
MUTED_2 = "#5f6779"
AMBER = "#f2a93b"
AMBER_DIM = "#7a5b28"
TEAL = "#49b8ac"
TEAL_DIM = "#2a5854"
ROSE = "#e2685a"
ROSE_DIM = "#6e3a34"
GREY = "#5a6478"

FONT_BODY = "'IBM Plex Sans', sans-serif"
FONT_MONO = "'IBM Plex Mono', monospace"

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "JNTO_Pakistan")

MONTHS = ["Jan.", "Feb.", "Mar.", "Apr.", "May", "Jun.",
          "Jul.", "Aug.", "Sep.", "Oct.", "Nov.", "Dec."]

# The entries file carries two overlapping age schemes (5-year and 10-year
# bands) plus a "Total" row that double-counts them. Only these bands are used.
FINE_AGE_BANDS = ["0 - 4", "5 - 9", "10 - 14", "15 - 19", "20 - 24", "25 - 29",
                  "30 - 34", "35 - 39", "40 - 44", "45 - 49", "50 - 54",
                  "55 - 59", "60 - 64", "65 - 69", "70 -"]

PLOT_CONFIG = {"displayModeBar": False, "responsive": True}

# Pyramid geometry, mirroring the original SVG: a 34px centre gutter
# inside a chart that is the wider (1.3fr) half of a 1124px grid.
PYRAMID_W = 635
PYRAMID_MID = 34


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def _num(s):
    """Parse a JNTO cell ('1,234', '', 'Null') into a float or None."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return None if (isinstance(s, float) and math.isnan(s)) else float(s)
    s = str(s).strip().replace(",", "")
    if s in ("", "Null", "nan", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _read(name):
    return pd.read_csv(os.path.join(DATA_DIR, name), dtype=str,
                       encoding="utf-8-sig").fillna("")


@st.cache_data(show_spinner=False)
def build_data():
    D = {}

    # --- annual arrivals + YoY growth --------------------------------------
    a = _read("3_1_Visitor_arrivals_CSV_1__2_3_.csv")
    D["annual"] = [{"year": int(r["Year"]),
                    "arrivals": int(_num(r["Visitor Arrivals"])),
                    "growth": _num(r["Growth Rate(%)"]),
                    "term": r["Term"].strip()}
                   for _, r in a.iterrows()]

    # --- monthly seasonality, 2023-2026 ------------------------------------
    m = _read("3_1_Visitor_arrivals_CSV_1__2_3__1.csv")
    piv = {(r["Month (abbr)"].strip(), int(r["Year"])): _num(r["Visitor Arrivals"])
           for _, r in m.iterrows()}
    D["seasonality"] = [
        dict({"month": mo},
             **{str(y): (int(piv[(mo, y)]) if piv.get((mo, y)) is not None else None)
                for y in (2023, 2024, 2025, 2026)})
        for mo in MONTHS
    ]

    # --- purpose of visit, by year -----------------------------------------
    p = _read("3_1_Visitor_arrivals_CSV_5__2_3_.csv")
    rows = {}
    for _, r in p.iterrows():
        v = _num(r["Visitor Arrivals"])
        if v is None:
            continue
        yr = int(r["Year"])
        rows.setdefault(yr, {"year": yr})[r["Purpose_of_visit_to_Japan"].strip()] = int(v)
    D["purpose_by_year"] = [rows[y] for y in sorted(rows)]

    # --- purpose of visit by month (2022 snapshot) -------------------------
    pm = _read("3_1_Visitor_arrivals_CSV_5__3_2_.csv")
    rows = {}
    for _, r in pm.iterrows():
        v = _num(r["Visitor Arrivals"])
        if v is None:
            continue
        rows.setdefault(r["Month (abbr)"].strip(), {})[
            r["Purpose_of_visit_to_Japan"].strip()] = int(v)
    D["purpose_by_month_2022"] = [dict({"month": mo}, **rows[mo])
                                  for mo in MONTHS if mo in rows]

    # --- gender trend (entries, 2013-2024) ---------------------------------
    g = _read("3_5_Foreigners_Entries_CSV_3_1_1__1.csv")
    gt = g[g["Age"].str.strip().isin(FINE_AGE_BANDS)]
    rows = {}
    for _, r in gt.iterrows():
        v = _num(r["Foreigners Entries"])
        if v is None:
            continue
        yr = rows.setdefault(int(r["Year"]), {"year": int(r["Year"])})
        gk = r["Gender"].strip()
        yr[gk] = yr.get(gk, 0) + int(v)
    D["gender_trend"] = [rows[y] for y in sorted(rows)
                         if "Male" in rows[y] and "Female" in rows[y]]

    # --- age / gender snapshot, 2024 ---------------------------------------
    ag = _read("3_5_Foreigners_Entries_DB_3_Pakistan_2024_from-chart.csv")
    rows, order = {}, []
    for _, r in ag.iterrows():
        age = r["Age"]
        if age.strip().lower().startswith("total"):
            continue
        if age not in rows:
            rows[age] = {"age": age, "male": 0.0, "female": 0.0}
            order.append(age)
        f = _num(r["SUM(Foreigners Entries（Female）)"])
        mm = _num(r["SUM(Foreigners Entries（Male）)"])
        if f is not None:
            rows[age]["female"] = f
        if mm is not None:
            rows[age]["male"] = mm
    D["age_snapshot"] = [rows[k] for k in order]

    # --- ports of entry, 2024 ----------------------------------------------
    po = _read("3_5_Foreigners_Entries_CSV_1_1_1__3.csv")
    po = po[po["Year"].astype(int) == 2024]
    total, recs = None, []
    for _, r in po.iterrows():
        port = r["Port Name"].strip()
        v = _num(r["Foreigners Entries"])
        if v is None:
            continue
        if port == "Total":
            total = int(v)
            continue
        if not port:
            continue
        recs.append({"port": port, "type": r["Port Type"].strip(), "entries": int(v)})
    recs.sort(key=lambda x: -x["entries"])
    D["ports_2024"] = recs[:10]
    D["ports_total_2024"] = total

    # --- average length of stay --------------------------------------------
    st_ = _read("3_2_Facts_on_trips_to_Japan_CSV_5_2_2_.csv")
    st_.columns = [c.strip() for c in st_.columns]
    D["avg_stay"] = sorted(
        [{"year": int(r["Year"]), "days": float(r["SUM(Average length of stay)"])}
         for _, r in st_.iterrows()],
        key=lambda x: x["year"])

    # --- Pakistan's share of Japan's total inbound -------------------------
    jp = _read("3_1_Visitor_arrivals_CSV_2__2_3_.csv")
    jtot = {int(r["Year"]): _num(r["Visitor Arrivals to Japan"]) for _, r in jp.iterrows()}
    D["pak_share_of_japan_inbound"] = [
        {"year": r["year"], "share_pct": round(r["arrivals"] / jtot[r["year"]] * 100, 4)}
        for r in D["annual"] if jtot.get(r["year"])
    ]

    # --- KPI strip ----------------------------------------------------------
    ann = {r["year"]: r for r in D["annual"]}
    seas = {r["month"]: r for r in D["seasonality"]}
    ytd_term = ann[2026]["term"]
    last_m = ytd_term.split("-")[-1].strip().rstrip(".")
    idx = [i for i, mo in enumerate(MONTHS) if mo.rstrip(".").startswith(last_m)][0]
    prev = sum(seas[mo]["2025"] for mo in MONTHS[:idx + 1])
    gen24 = [r for r in D["gender_trend"] if r["year"] == 2024][0]
    tot24 = gen24["Male"] + gen24["Female"]
    peak = max(D["annual"],
               key=lambda r: r["arrivals"] if r["term"].endswith("Dec.") else -1)
    low = min([r for r in D["annual"]
               if r["year"] >= 2020 and r["term"].endswith("Dec.")],
              key=lambda r: r["arrivals"])
    D["kpi"] = {
        "2025_total": ann[2025]["arrivals"],
        "2025_growth": ann[2025]["growth"],
        "2026_ytd": ann[2026]["arrivals"],
        "2026_ytd_term": ytd_term,
        "2026_ytd_growth": round((ann[2026]["arrivals"] / prev - 1) * 100, 1),
        "gender_2024": {"male": gen24["Male"], "female": gen24["Female"],
                        "male_pct": round(gen24["Male"] / tot24 * 100, 1)},
        "avg_stay_2024": [r for r in D["avg_stay"] if r["year"] == 2024][0]["days"],
        "top_port": D["ports_2024"][0]["port"],
        "top_port_share": round(D["ports_2024"][0]["entries"] / D["ports_total_2024"] * 100, 1),
        "peak_arrivals_year": peak["year"],
        "covid_low_year": low["year"],
        "covid_low_value": low["arrivals"],
        "pak_share_2025": [r for r in D["pak_share_of_japan_inbound"]
                           if r["year"] == 2025][0]["share_pct"],
    }
    return D


# ---------------------------------------------------------------------------
# Formatting helpers (mirror fmt / fmt1 / pct in the HTML)
# ---------------------------------------------------------------------------
def fmt(n):
    if n is None or (isinstance(n, float) and math.isnan(n)):
        return "—"
    return f"{round(n):,}"


def fmt1(n):
    if n is None or (isinstance(n, float) and math.isnan(n)):
        return "—"
    return f"{n:.1f}"


def num(n):
    """Render a number the way JS string concatenation does: 54.0 -> '54'."""
    return f"{n:g}"


def pct(n, digits=1):
    if n is None or (isinstance(n, float) and math.isnan(n)):
        return "—"
    return ("+" if n >= 0 else "") + f"{n:.{digits}f}%"


# ---------------------------------------------------------------------------
# Chrome
# ---------------------------------------------------------------------------
st.set_page_config(page_title="PAK ⟶ JPN · Visitor Arrivals Board",
                   page_icon="✈️", layout="wide")

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500;600&display=swap');

:root{{
  --bg:{BG}; --bg-2:{BG_2}; --panel:{PANEL}; --panel-alt:{PANEL_ALT};
  --line:{LINE}; --line-soft:{LINE_SOFT}; --ink:{INK}; --muted:{MUTED};
  --muted-2:{MUTED_2}; --amber:{AMBER}; --amber-dim:{AMBER_DIM};
  --teal:{TEAL}; --teal-dim:{TEAL_DIM}; --rose:{ROSE}; --rose-dim:{ROSE_DIM};
  --font-display:'Space Grotesk', sans-serif;
  --font-body:'IBM Plex Sans', sans-serif;
  --font-mono:'IBM Plex Mono', monospace;
}}

html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"]{{
  background:var(--bg) !important;
}}
/* Streamlit's header is absolutely positioned (60px tall, z-index 999990), so
   it takes no space in the flow and would paint straight over the masthead
   title. Empty it, and clear its height in the container padding below. */
[data-testid="stHeader"]{{ box-shadow:none; border:none; }}
[data-testid="stToolbar"]{{ display:none; }}
#MainMenu, footer{{ visibility:hidden; }}

/* Set the family/colour once and let them inherit. Selectors like
   `.stApp div` would outrank the single-class rules below (.kpi-value,
   .legend, ...) and silently undo the mono numerals. */
.stApp, [data-testid="stMarkdownContainer"]{{
  color:var(--ink);
  font-family:var(--font-body);
  -webkit-font-smoothing:antialiased;
  line-height:1.45;
}}
::selection{{ background:var(--amber-dim); color:var(--ink); }}
a{{ color:var(--amber); }}

/* .wrap -- max-width:1180px; padding:60 28px 80px */
.block-container{{
  max-width:1180px;
  padding:60px 28px 0 !important;      /* 60px = height of Streamlit's header */
  margin:0 auto;
}}
[data-testid="stVerticalBlock"]{{ gap:0; }}
[data-testid="stElementContainer"]{{ margin:0; }}

/* Streamlit wraps every st.markdown in a fixed-height flex box and gives the
   markdown container a -16px bottom margin to cancel the vertical block's
   default 1rem gap. With gap:0 above, that negative margin would pull every
   following element 16px up and overlap the custom HTML blocks. Neutralise
   both so the margins written below are the margins that actually render. */
.stMarkdown, .stMarkdown > div, [data-testid="stMarkdownContainer"]{{
  height:auto !important; min-height:0 !important;
  margin:0 !important; display:block !important; width:100%;
}}
[data-testid="stElementContainer"]:has(> .stMarkdown){{ height:auto !important; }}

/* Chart rows: match the original .grid-2 gap of 32px. */
[data-testid="stHorizontalBlock"]{{ gap:32px !important; }}

/* ---------- Masthead ---------- */
.masthead{{
  padding:34px 0 22px;
  border-bottom:1px solid var(--line);
  display:flex; justify-content:space-between; align-items:flex-end;
  gap:24px; flex-wrap:wrap;
}}
.route{{ display:flex; align-items:baseline; gap:14px; font-family:var(--font-display); }}
.route .code{{ font-size:clamp(32px,5vw,52px); font-weight:700; letter-spacing:0.01em; }}
.route .code .arrow{{ color:var(--amber); padding:0 6px; font-weight:500; }}
.route .sub{{
  font-family:var(--font-body); color:var(--muted); font-size:13px;
  letter-spacing:0.06em; text-transform:uppercase; padding-bottom:6px;
}}
.masthead-right{{
  text-align:right; font-size:12px; color:var(--muted-2);
  letter-spacing:0.04em; padding-bottom:6px;
}}
.masthead-right div{{ color:var(--muted-2) !important; font-size:12px; }}
.masthead-right .status{{ color:var(--teal) !important; font-weight:600; }}
.masthead-right .dot{{
  display:inline-block; width:6px; height:6px; border-radius:50%;
  background:var(--teal); margin-right:6px; box-shadow:0 0 6px var(--teal);
}}

/* ---------- KPI board ---------- */
.kpi-strip{{
  display:grid; grid-template-columns:repeat(6,1fr);
  border:1px solid var(--line); border-top:none; margin-bottom:44px;
}}
.kpi{{ padding:20px 18px; border-right:1px solid var(--line); position:relative; }}
.kpi:last-child{{ border-right:none; }}
.kpi-label{{
  font-size:11px; letter-spacing:0.08em; text-transform:uppercase;
  color:var(--muted) !important; margin-bottom:10px;
}}
.kpi-value{{
  font-family:var(--font-mono); font-variant-numeric:tabular-nums;
  font-size:clamp(20px,2.4vw,28px); font-weight:600; letter-spacing:-0.01em;
}}
.kpi-delta{{ font-family:var(--font-mono); font-size:12.5px; margin-top:6px; font-weight:500; }}
.kpi-delta.up{{ color:var(--teal) !important; }}
.kpi-delta.down{{ color:var(--rose) !important; }}
.kpi-delta.flat{{ color:var(--muted) !important; }}
.kpi-note{{ font-size:11.5px; color:var(--muted-2) !important; margin-top:4px; }}

@media (max-width:900px){{
  .kpi-strip{{ grid-template-columns:repeat(3,1fr); }}
  .kpi{{ border-bottom:1px solid var(--line); }}
  .kpi:nth-child(3n){{ border-right:none; }}
}}
@media (max-width:560px){{
  .kpi-strip{{ grid-template-columns:repeat(2,1fr); }}
  .kpi:nth-child(3n){{ border-right:1px solid var(--line); }}
  .kpi:nth-child(2n){{ border-right:none; }}
}}

/* ---------- Section framework ---------- */
.panel-head{{
  display:flex; justify-content:space-between; align-items:baseline;
  border-bottom:1px solid var(--line); padding-bottom:10px; margin-bottom:18px;
  gap:16px; flex-wrap:wrap;
}}
.panel-head h2{{
  font-family:var(--font-display); font-size:16px; font-weight:600;
  margin:0; padding:0; line-height:1.45; letter-spacing:0.01em;
  color:var(--ink) !important;
}}
.panel-head .tick{{ color:var(--amber); margin-right:8px; }}
/* Split panel head: the title sits in one column, the toggle in the next,
   with the rule drawn underneath the whole row (matches .panel-head). */
.panel-head-title{{ padding-bottom:10px; }}
.panel-head-title h2{{
  font-family:var(--font-display); font-size:16px; font-weight:600;
  margin:0; padding:0; line-height:1.45; letter-spacing:0.01em;
  color:var(--ink) !important;
}}
.panel-head-title .tick{{ color:var(--amber); margin-right:8px; }}
.panel-rule{{ border-bottom:1px solid var(--line); margin-bottom:18px; }}
.panel-head .desc{{
  font-size:12.5px; color:var(--muted) !important;
  max-width:420px; text-align:right;
}}
.panel-spacer{{ height:40px; }}

.legend{{
  display:flex; gap:18px; flex-wrap:wrap; font-size:12px;
  color:var(--muted) !important; margin-top:10px;
}}
.legend-item{{ display:flex; align-items:center; gap:6px; color:var(--muted) !important; }}
.legend-swatch{{ width:10px; height:10px; display:inline-block; }}

.foot{{
  border-top:1px solid var(--line); margin-top:40px; padding-top:22px;
  font-size:12px; color:var(--muted-2) !important;
  display:flex; justify-content:space-between; flex-wrap:wrap; gap:10px;
}}
.foot span{{ color:var(--muted-2) !important; }}

.callout{{
  font-size:13px; color:var(--muted) !important; margin-top:14px;
  padding-top:12px; border-top:1px dashed var(--line-soft);
}}
.callout b{{ color:var(--ink) !important; font-weight:600; }}
.callout .amber{{ color:var(--amber) !important; font-weight:600; }}
.callout .teal{{ color:var(--teal) !important; font-weight:600; }}
.callout .rose{{ color:var(--rose) !important; font-weight:600; }}

/* ---------- ARRIVALS / YoY % toggle ---------- */
/* Streamlit renders st.segmented_control as a BaseWeb button group
   (data-testid="stButtonGroup"), whose buttons carry
   data-variant="segmented_control" and aria-checked for the active one. */
/* The head row that carries the toggle: title and buttons share a baseline,
   and the rule is drawn under the whole row (as .panel-head's border is). */
[data-testid="stHorizontalBlock"]:has([data-testid="stButtonGroup"]){{
  align-items:flex-end !important; padding-bottom:8px;
}}
[data-testid="stHorizontalBlock"]:has([data-testid="stButtonGroup"])
  [data-testid="stVerticalBlock"]{{ justify-content:flex-end; }}
[data-testid="stButtonGroup"]{{
  display:flex; justify-content:flex-end; width:100% !important;
  background:none !important;
}}
[data-testid="stButtonGroup"] > div{{ gap:2px !important; background:none !important; }}
[data-testid="stButtonGroup"] button[data-variant="segmented_control"]{{
  background:none !important; background-color:transparent !important;
  border:1px solid var(--line) !important; border-radius:0 !important;
  color:var(--muted) !important; fill:var(--muted) !important;
  padding:5px 12px !important; min-height:0 !important; height:auto !important;
  box-shadow:none !important;
  font-family:var(--font-mono) !important; font-size:11.5px !important;
  font-weight:500 !important; letter-spacing:0.03em; cursor:pointer;
}}
[data-testid="stButtonGroup"] button[data-variant="segmented_control"] *{{
  color:var(--muted) !important; fill:var(--muted) !important;
  font-family:var(--font-mono) !important; font-size:11.5px !important;
  background:none !important;
}}
[data-testid="stButtonGroup"] button[data-variant="segmented_control"]:hover{{
  background:none !important; background-color:transparent !important;
  border-color:var(--muted-2) !important; color:var(--ink) !important;
}}
[data-testid="stButtonGroup"] button[data-variant="segmented_control"]:hover *{{
  color:var(--ink) !important; fill:var(--ink) !important;
}}
[data-testid="stButtonGroup"] button[data-variant="segmented_control"][aria-checked="true"],
[data-testid="stButtonGroup"] button[data-variant="segmented_control"][aria-selected="true"],
[data-testid="stButtonGroup"] button[data-variant="segmented_control"][data-selected="true"]{{
  background:var(--amber) !important; background-color:var(--amber) !important;
  border-color:var(--amber) !important; color:var(--bg) !important;
}}
[data-testid="stButtonGroup"] button[data-variant="segmented_control"][aria-checked="true"] *,
[data-testid="stButtonGroup"] button[data-variant="segmented_control"][aria-selected="true"] *,
[data-testid="stButtonGroup"] button[data-variant="segmented_control"][data-selected="true"] *{{
  color:var(--bg) !important; fill:var(--bg) !important;
}}
[data-testid="stButtonGroup"] button:focus,
[data-testid="stButtonGroup"] button:focus-visible{{
  outline:2px solid var(--amber) !important; outline-offset:2px;
  box-shadow:none !important;
}}

/* flip-in animation for KPI values, single orchestrated moment */
@media (prefers-reduced-motion: no-preference){{
  .kpi-value, .route .code{{ animation:flipin 0.5s ease both; }}
}}
@keyframes flipin{{
  0%{{ opacity:0; transform:translateY(6px); filter:blur(2px); }}
  100%{{ opacity:1; transform:translateY(0); filter:blur(0); }}
}}

.js-plotly-plot .plotly .modebar{{ display:none !important; }}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def html(markup):
    st.markdown(markup, unsafe_allow_html=True)


def panel_head(title, desc=None):
    right = f'<div class="desc">{desc}</div>' if desc else ""
    html(f'<div class="panel-head"><h2><span class="tick">▍</span>{title}</h2>{right}</div>')


def legend(items):
    html('<div class="legend">' + "".join(
        f'<span class="legend-item"><span class="legend-swatch" '
        f'style="background:{c}"></span>{label}</span>' for label, c in items
    ) + "</div>")


def spacer():
    html('<div class="panel-spacer"></div>')


# The original charts are inline SVGs, which sit on the text baseline and leave
# ~6px of space under the box. Streamlit's chart box is a fixed-height border box
# (padding would eat into the plot), so the gap is built into the figure: 6px of
# extra height paid straight back into the bottom margin, leaving the plot area
# pixel-identical to the original's.
SVG_BASELINE_GAP = 6


def base_layout(height, margin, y_title=None):
    """Shared Plotly layout: transparent, muted axes, HTML-matching tooltip."""
    margin = dict(margin, b=margin["b"] + SVG_BASELINE_GAP)
    return dict(
        height=height + SVG_BASELINE_GAP,
        margin=margin,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT_BODY, size=11, color=MUTED),
        showlegend=False,
        hoverlabel=dict(bgcolor=PANEL_ALT, bordercolor=LINE,
                        font=dict(family=FONT_MONO, size=12, color=INK), align="left"),
        xaxis=dict(showgrid=False, zeroline=False, showline=False,
                   ticks="", color=MUTED, title=None),
        yaxis=dict(gridcolor=LINE_SOFT, zeroline=False, showline=False,
                   ticks="", color=MUTED, title=y_title),
        dragmode=False,
    )


def covid_band(fig, y0=0, y1=1):
    """The 2020-2021 shaded band + label used by the trend and share charts."""
    fig.add_vrect(x0=2019.9, x1=2021.6, fillcolor=ROSE_DIM, opacity=0.28,
                  layer="below", line_width=0)
    fig.add_annotation(x=(2019.9 + 2021.6) / 2, y=1, yref="paper", yshift=-8,
                       text="COVID-19", showarrow=False,
                       font=dict(family=FONT_BODY, size=10.5, color=ROSE))


DATA = build_data()
K = DATA["kpi"]

# ---------------------------------------------------------------------------
# BOARD 1 -- PAK -> JPN Visitor Arrivals
# ---------------------------------------------------------------------------
def render_pak_board():
    html("<style>.block-container{padding-bottom:80px !important;}</style>")

    # ---------------------------------------------------------------------------
    # Masthead
    # ---------------------------------------------------------------------------
    html("""
    <header class="masthead">
      <div class="route">
        <span class="code">PAK<span class="arrow">⟶</span>JPN</span>
        <span class="sub">Visitor Arrivals Board</span>
      </div>
      <div class="masthead-right">
        <div><span class="dot"></span><span class="status">Data through May 2026</span></div>
        <div>Source: JNTO / Japan Ministry of Justice, foreign national statistics</div>
      </div>
    </header>
    """)

    # ---------------------------------------------------------------------------
    # KPI strip
    # ---------------------------------------------------------------------------
    kpi_items = [
        dict(label="2025 Total Arrivals", value=fmt(K["2025_total"]),
             delta=pct(K["2025_growth"]),
             cls="up" if K["2025_growth"] >= 0 else "down", note="vs. 2024"),
        dict(label="2026 Year to Date", value=fmt(K["2026_ytd"]),
             delta=pct(K["2026_ytd_growth"]),
             cls=("up" if K["2026_ytd_growth"] > 0.5
                  else "down" if K["2026_ytd_growth"] < -0.5 else "flat"),
             note=K["2026_ytd_term"].replace("Jan. - ", "Jan–") + " vs same period '25"),
        dict(label="Avg. Length of Stay", value=fmt1(K["avg_stay_2024"]) + "d",
             delta="2024", cls="flat", note="down from 43d in 2021"),
        dict(label="Gender Split, 2024", value=num(K["gender_2024"]["male_pct"]) + "% M",
             delta=fmt(K["gender_2024"]["male"]) + " / " + fmt(K["gender_2024"]["female"]),
             cls="flat", note="male / female entries"),
        dict(label="Top Gateway", value=K["top_port"],
             delta=num(K["top_port_share"]) + "% share", cls="flat",
             note="of all 2024 entries"),
        dict(label="Share of Japan Inbound", value=fmt1(K["pak_share_2025"]) + "%",
             delta="2025", cls="flat", note="Pakistan vs. all countries"),
    ]
    html('<div class="kpi-strip">' + "".join(
        f'<div class="kpi"><div class="kpi-label">{i["label"]}</div>'
        f'<div class="kpi-value">{i["value"]}</div>'
        f'<div class="kpi-delta {i["cls"]}">{i["delta"]}</div>'
        f'<div class="kpi-note">{i["note"]}</div></div>' for i in kpi_items
    ) + "</div>")


    # ---------------------------------------------------------------------------
    # 1. TREND CHART (line, toggle arrivals / growth)
    # ---------------------------------------------------------------------------
    head_l, head_r = st.columns([2, 1], vertical_alignment="bottom")
    with head_l:
        html('<div class="panel-head-title"><h2><span class="tick">▍</span>'
             '34-Year Arrivals Trend</h2></div>')
    with head_r:
        trend_mode = st.segmented_control("Trend mode", ["ARRIVALS", "YoY %"],
                                          default="ARRIVALS", label_visibility="collapsed",
                                          key="trend_mode") or "ARRIVALS"
    html('<div class="panel-rule"></div>')

    rows = DATA["annual"]
    years = [r["year"] for r in rows]
    fig = go.Figure()
    covid_band(fig)

    if trend_mode == "ARRIVALS":
        vals = [r["arrivals"] for r in rows]
        fig.add_trace(go.Scatter(
            x=years, y=vals, mode="lines", fill="tozeroy",
            fillcolor="rgba(242,169,59,0.12)", line=dict(color=AMBER, width=2),
            customdata=[f'{r["year"]} · {r["term"]}' for r in rows],
            hovertemplate="<span style='color:%s;font-family:%s;font-size:11px'>%%{customdata}</span>"
                          "<br>%%{y:,.0f} visitors<extra></extra>" % (MUTED, FONT_BODY),
            hoverlabel=dict(bgcolor=PANEL_ALT),
        ))
        y_range = [0, max(vals) * 1.12]
        tickvals = [y_range[1] * i / 5 for i in range(6)]
        ticktext = [f"{round(v / 1000)}k" for v in tickvals]
    else:
        vals = [r["growth"] for r in rows]
        ext = max(abs(v) for v in vals if v is not None)
        fig.add_trace(go.Scatter(
            x=years, y=vals, mode="lines", connectgaps=False,
            line=dict(color=TEAL, width=2),
            customdata=[f'{r["year"]} · {r["term"]}' for r in rows],
            hovertemplate="<span style='color:%s;font-family:%s;font-size:11px'>%%{customdata}</span>"
                          "<br>%%{y:+.1f}%%<extra></extra>" % (MUTED, FONT_BODY),
        ))
        y_range = [-ext * 1.08, ext * 1.08]
        tickvals = [y_range[0] + (y_range[1] - y_range[0]) * i / 5 for i in range(6)]
        ticktext = [f"{round(v)}%" for v in tickvals]
        fig.add_hline(y=0, line=dict(color=LINE, width=1))

    lay = base_layout(300, dict(t=20, r=20, b=30, l=54))
    lay["hovermode"] = "x unified"
    lay["xaxis"].update(range=[years[0], years[-1]],
                        tickmode="array",
                        tickvals=[y for y in years if y % 5 == 0], tickfont=dict(size=11))
    lay["yaxis"].update(range=y_range, tickmode="array", tickvals=tickvals,
                        ticktext=ticktext, tickfont=dict(size=11))
    fig.update_layout(**lay)
    st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG, key="trend")

    if trend_mode == "ARRIVALS":
        html('<div class="callout">Arrivals cratered <span class="rose">-64%</span> in 2020 and '
             'bottomed at <b>4,284</b> in 2021, then rebounded past pre-pandemic levels &mdash; '
             '2025 closed at <b>30,171</b>, the highest year on record. 2026 is tracking roughly '
             'flat through May.</div>')
    else:
        html('<div class="callout">Post-pandemic growth was explosive &mdash; '
             '<span class="teal">+167%</span> in 2022 and <span class="teal">+85%</span> in 2023 '
             '&mdash; before settling to a steadier <b>+12&ndash;27%</b> pace in 2024&ndash;25.</div>')
    spacer()

    # ---------------------------------------------------------------------------
    # 2. SEASONALITY + PURPOSE
    # ---------------------------------------------------------------------------
    left, right = st.columns([1.3, 1], gap="large")

    with left:
        panel_head("Monthly Seasonality", "Arrivals by month, 2023&ndash;2026")
        rows = DATA["seasonality"]
        months = [r["month"].replace(".", "") for r in rows]
        season_colors = {"2023": "#3d4658", "2024": GREY, "2025": TEAL, "2026": AMBER}
        fig = go.Figure()
        for y, color in season_colors.items():
            fig.add_trace(go.Bar(
                x=months, y=[r[y] for r in rows], marker=dict(color=color, line_width=0),
                name=y,
                hovertemplate="<span style='color:%s;font-family:%s;font-size:11px'>%%{x} "
                              "%s</span><br>%%{y:,.0f}<extra></extra>" % (MUTED, FONT_BODY, y),
            ))
        vmax = max(v for r in rows for v in
                   (r["2023"], r["2024"], r["2025"], r["2026"]) if v is not None) * 1.12
        tickvals = [vmax * i / 4 for i in range(5)]
        lay = base_layout(280, dict(t=16, r=10, b=26, l=44))
        lay["barmode"] = "group"
        lay["bargap"] = 0.28
        lay["bargroupgap"] = 0.14
        lay["xaxis"].update(tickfont=dict(size=10.5))
        lay["yaxis"].update(range=[0, vmax], tickmode="array", tickvals=tickvals,
                            ticktext=[(f"{round(v / 1000 * 10) / 10:g}k") for v in tickvals],
                            tickfont=dict(size=10.5))
        fig.update_layout(**lay)
        st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG, key="season")
        legend([("2023", "#3d4658"), ("2024", GREY), ("2025", TEAL), ("2026 (YTD)", AMBER)])

    with right:
        panel_head("Purpose of Visit", "Annual mix, 1992&ndash;2026")
        rows = DATA["purpose_by_year"]
        cats = [("Tourism", AMBER), ("Business", TEAL), ("Others", GREY), ("Transit", ROSE)]
        fig = go.Figure()
        for cat, color in cats:
            fig.add_trace(go.Bar(
                x=[r["year"] for r in rows], y=[r.get(cat, 0) for r in rows],
                marker=dict(color=color, line_width=0), name=cat,
                hovertemplate="<span style='color:%s;font-family:%s;font-size:11px'>%%{x} · "
                              "%s</span><br>%%{y:,.0f}<extra></extra>" % (MUTED, FONT_BODY, cat),
            ))
        vmax = max(sum(r.get(c, 0) for c, _ in cats) for r in rows) * 1.1
        tickvals = [vmax * i / 4 for i in range(5)]
        lay = base_layout(280, dict(t=16, r=10, b=26, l=44))
        lay["barmode"] = "stack"
        lay["bargap"] = 0.18
        lay["xaxis"].update(range=[rows[0]["year"], rows[-1]["year"]], tickmode="array",
                            tickvals=[1995, 2005, 2015, 2025], tickfont=dict(size=10.5))
        lay["yaxis"].update(range=[0, vmax], tickmode="array", tickvals=tickvals,
                            ticktext=[f"{round(v / 1000)}k" for v in tickvals],
                            tickfont=dict(size=10.5))
        fig.update_layout(**lay)
        st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG, key="purpose")
        legend(cats)

    spacer()

    # ---------------------------------------------------------------------------
    # 2b. PURPOSE BY MONTH (2022 snapshot)
    # ---------------------------------------------------------------------------
    panel_head("Purpose Split by Month",
               "2022 snapshot &mdash; the only year this monthly-by-purpose file "
               "reconciles against")
    rows = DATA["purpose_by_month_2022"]
    months = [r["month"].replace(".", "") for r in rows]
    cats = [("Tourism", AMBER), ("Business", TEAL), ("Others", GREY)]
    fig = go.Figure()
    for cat, color in cats:
        fig.add_trace(go.Bar(
            x=months, y=[r.get(cat, 0) for r in rows],
            marker=dict(color=color, line_width=0), name=cat,
            hovertemplate="<span style='color:%s;font-family:%s;font-size:11px'>%%{x} 2022 · "
                          "%s</span><br>%%{y:,.0f}<extra></extra>" % (MUTED, FONT_BODY, cat),
        ))
    vmax = max(sum(r.get(c, 0) for c, _ in cats) for r in rows) * 1.12
    tickvals = [vmax * i / 4 for i in range(5)]
    lay = base_layout(260, dict(t=16, r=16, b=26, l=44))
    lay["barmode"] = "stack"
    lay["bargap"] = 0.44
    lay["xaxis"].update(tickfont=dict(size=10.5))
    lay["yaxis"].update(range=[0, vmax], tickmode="array", tickvals=tickvals,
                        ticktext=[f"{round(v)}" for v in tickvals], tickfont=dict(size=10.5))
    fig.update_layout(**lay)
    st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG, key="purpose_month")
    legend(cats)
    spacer()

    # ---------------------------------------------------------------------------
    # 3. DEMOGRAPHICS
    # ---------------------------------------------------------------------------
    left, right = st.columns([1.3, 1], gap="large")

    with left:
        panel_head("Age &amp; Gender, 2024", "Entries by age band")
        rows = DATA["age_snapshot"]
        ages = [r["age"] for r in rows]
        vmax = max(max(r["male"], r["female"]) for r in rows) * 1.08
        # The original reserves a 34px gutter down the middle for the age labels,
        # so no bar is ever drawn underneath them. Half of it, in data units:
        half_px = (PYRAMID_W - 16 - PYRAMID_MID) / 2
        gutter = vmax * (PYRAMID_MID / 2) / half_px
        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=ages, x=[-r["male"] for r in rows], base=[-gutter] * len(rows),
            orientation="h", marker=dict(color=TEAL, line_width=0), name="Male",
            customdata=[r["male"] for r in rows],
            hovertemplate="<span style='color:%s;font-family:%s;font-size:11px'>%%{y} · Male"
                          "</span><br>%%{customdata:,.0f}<extra></extra>" % (MUTED, FONT_BODY),
        ))
        fig.add_trace(go.Bar(
            y=ages, x=[r["female"] for r in rows], base=[gutter] * len(rows),
            orientation="h", marker=dict(color=AMBER, line_width=0), name="Female",
            hovertemplate="<span style='color:%s;font-family:%s;font-size:11px'>%%{y} · Female"
                          "</span><br>%%{x:,.0f}<extra></extra>" % (MUTED, FONT_BODY),
        ))
        lay = base_layout(len(rows) * 22 + 30, dict(t=10, r=8, b=20, l=8))
        lay["barmode"] = "overlay"
        lay["bargap"] = 7 / 22
        lay["xaxis"].update(range=[-(vmax + gutter), vmax + gutter], showticklabels=False)
        lay["yaxis"].update(autorange="reversed", showgrid=False, showticklabels=False)
        fig.update_layout(**lay)
        for age in ages:
            fig.add_annotation(x=0, y=age, text=age, showarrow=False,
                               font=dict(family=FONT_BODY, size=10.5, color=MUTED))
        st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG, key="pyramid")
        legend([("Male", TEAL), ("Female", AMBER)])

    with right:
        panel_head("Gender Trend", "Total entries, 2013&ndash;2024")
        rows = DATA["gender_trend"]
        yrs = [r["year"] for r in rows]
        fig = go.Figure()
        for key, color in (("Male", TEAL), ("Female", AMBER)):
            fig.add_trace(go.Scatter(
                x=yrs, y=[r[key] for r in rows], mode="lines",
                line=dict(color=color, width=2), name=key,
                hovertemplate="<span style='color:%s;font-family:%s;font-size:11px'>%%{x} · %s"
                              "</span><br>%%{y:,.0f}<extra></extra>" % (MUTED, FONT_BODY, key),
            ))
        vmax = max(max(r["Male"], r["Female"]) for r in rows) * 1.12
        tickvals = [vmax * i / 4 for i in range(5)]
        lay = base_layout(280, dict(t=16, r=14, b=26, l=48))
        lay["xaxis"].update(range=[yrs[0], yrs[-1]], tickmode="array",
                            tickvals=[y for y in yrs if y % 2 == 1], tickfont=dict(size=10.5))
        lay["yaxis"].update(range=[0, vmax], tickmode="array", tickvals=tickvals,
                            ticktext=[f"{round(v / 1000)}k" for v in tickvals],
                            tickfont=dict(size=10.5))
        fig.update_layout(**lay)
        st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG, key="gender")
        legend([("Male", TEAL), ("Female", AMBER)])

    spacer()

    # ---------------------------------------------------------------------------
    # 4. PORTS + LENGTH OF STAY
    # ---------------------------------------------------------------------------
    left, right = st.columns([1.3, 1], gap="large")

    with left:
        panel_head("Ports of Entry, 2024", "Top gateways into Japan")
        rows = DATA["ports_2024"]
        fig = go.Figure(go.Bar(
            y=[r["port"] for r in rows], x=[r["entries"] for r in rows], orientation="h",
            marker=dict(color=[TEAL if r["type"] == "Seaport" else AMBER for r in rows],
                        opacity=[1] + [0.82] * (len(rows) - 1), line_width=0),
            customdata=[r["type"] for r in rows],
            hovertemplate="<span style='color:%s;font-family:%s;font-size:11px'>%%{y} · "
                          "%%{customdata}</span><br>%%{x:,.0f}<extra></extra>" % (MUTED, FONT_BODY),
        ))
        lay = base_layout(len(rows) * 30 + 16, dict(t=6, r=60, b=10, l=104))
        lay["bargap"] = 0.4
        for r in rows:
            fig.add_annotation(x=r["entries"], y=r["port"], text=fmt(r["entries"]),
                               showarrow=False, xanchor="left", xshift=8,
                               font=dict(family=FONT_MONO, size=11.5, color=MUTED))
        lay["xaxis"].update(range=[0, rows[0]["entries"] * 1.05], showticklabels=False)
        lay["yaxis"].update(autorange="reversed", showgrid=False,
                            tickfont=dict(family=FONT_BODY, size=12, color=INK))
        fig.update_layout(**lay)
        st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG, key="ports")

    with right:
        panel_head("Average Length of Stay", "Days per trip, 2012&ndash;2024")
        rows = DATA["avg_stay"]
        yrs = [r["year"] for r in rows]
        fig = go.Figure(go.Scatter(
            x=yrs, y=[r["days"] for r in rows], mode="lines+markers",
            line=dict(color=ROSE, width=2),
            marker=dict(color=ROSE, size=[8 if r["year"] == 2021 else 5 for r in rows]),
            hovertemplate="<span style='color:%s;font-family:%s;font-size:11px'>%%{x}</span>"
                          "<br>%%{y:.1f} days<extra></extra>" % (MUTED, FONT_BODY),
        ))
        vmax = max(r["days"] for r in rows) * 1.1
        tickvals = [vmax * i / 4 for i in range(5)]
        lay = base_layout(280, dict(t=20, r=14, b=26, l=40))
        lay["xaxis"].update(range=[yrs[0], yrs[-1]], tickmode="array", tickvals=yrs,
                            tickfont=dict(size=10.5))
        lay["yaxis"].update(range=[0, vmax], tickmode="array", tickvals=tickvals,
                            ticktext=[f"{round(v)}d" for v in tickvals], tickfont=dict(size=10.5))
        fig.update_layout(**lay)
        st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG, key="stays")

    spacer()

    # ---------------------------------------------------------------------------
    # 5. PAKISTAN'S SHARE OF JAPAN'S INBOUND MARKET
    # ---------------------------------------------------------------------------
    panel_head("Pakistan's Share of Japan's Inbound Market",
               "Pakistan arrivals as % of all-country visitor arrivals to Japan, "
               "1992&ndash;2026")
    rows = DATA["pak_share_of_japan_inbound"]
    yrs = [r["year"] for r in rows]
    fig = go.Figure()
    covid_band(fig)
    fig.add_trace(go.Scatter(
        x=yrs, y=[r["share_pct"] for r in rows], mode="lines",
        line=dict(color=TEAL, width=2),
        hovertemplate="<span style='color:%s;font-family:%s;font-size:11px'>%%{x}</span>"
                      "<br>%%{y:.3f}%% of Japan's inbound<extra></extra>" % (MUTED, FONT_BODY),
    ))
    vmax = max(r["share_pct"] for r in rows) * 1.1
    tickvals = [vmax * i / 4 for i in range(5)]
    lay = base_layout(260, dict(t=20, r=20, b=30, l=54))
    lay["hovermode"] = "x unified"
    lay["xaxis"].update(range=[yrs[0], yrs[-1]], tickmode="array",
                        tickvals=[y for y in yrs if y % 5 == 0], tickfont=dict(size=11))
    lay["yaxis"].update(range=[0, vmax], tickmode="array", tickvals=tickvals,
                        ticktext=[f"{v:.2f}%" for v in tickvals], tickfont=dict(size=11))
    fig.update_layout(**lay)
    st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG, key="share")

    # The share callout, footer and reading note are one flow in the original, so
    # they are emitted as one block -- separate blocks would lose .foot's top margin.
    html('<div class="callout">This ratio spiked to <b>1.74%</b> in 2021 &mdash; not because '
         'Pakistan’s market grew, but because Japan’s <i>total</i> inbound arrivals '
         'collapsed to just 246,000 that year under border restrictions, while Pakistan’s '
         'much smaller, less tourism-driven traveler base (residents, workers, students) held up '
         'comparatively better. Once Japan reopened, the ratio normalized: it ran '
         '<b>0.05&ndash;0.15%</b> pre-pandemic, briefly touched <b>0.30%</b> in the first '
         'reopening year (2022), and has since settled near <b>'
         + fmt1(K["pak_share_2025"]) + '%</b> in 2025 &mdash; meaning Japan’s overall '
         'inbound boom has been growing faster than the Pakistan market specifically, even as '
         'Pakistan’s own arrival counts hit records.</div>'
         """
    <div class="foot">
      <span>JNTO Pakistan market brief &middot; compiled from 9 source tables</span>
      <span>Figures reflect Japan-side entry statistics, not Pakistan departure records</span>
    </div>

    <div class="callout" style="margin-top:14px; border-top:1px dashed var(--line-soft); padding-top:12px;">
      <b>Reading note:</b> this brief blends two official series that measure related but
      different things. <span class="amber">Visitor Arrivals</span> (JNTO's tourism-market
      estimate) drives the arrivals trend, seasonality, purpose-of-visit and share-of-market
      charts. <span class="teal">Foreigners Entries</span> (Ministry of Justice immigration
      counts, which include residents, workers and students, not just tourists) drives the
      age/gender, gender-trend and ports-of-entry charts. The two are never summed together,
      and 2026 figures throughout are partial-year (through May).
    </div>
    """)




FTAS_PAGE_CSS = """
<style>
/* The FTAS board replaces the dark ground with washi paper and lets the
   sections span the whole main area, the way index.html fills the viewport. */
html, body, .stApp,
[data-testid="stAppViewContainer"], [data-testid="stHeader"]{
  background:#F7F3EA !important;
}
.block-container{
  max-width:none !important;
  padding:60px 0 0 !important;     /* 60px clears Streamlit's header band */
}
</style>
"""

FTAS_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Shippori+Mincho:wght@500;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap');

/* The board runs the full width of the main area (FTAS_PAGE_CSS clears the
   column's max-width), so sections centre themselves exactly as index.html's
   `section.panel` does, with no negative-margin tricks. */

/* The forecast chart is a Streamlit element, so the frame inside its container
   carries the .chart-card chrome. Horizontal card padding only: Streamlit's
   chart box is a fixed-height border box, so the 1.4rem top/bottom is paid
   inside the figure instead. */
[data-testid="stElementContainer"].st-key-ftas_demand [data-testid="stFullScreenFrame"]{
  width:1132px;
  max-width:calc(100% - 3rem);
  margin:0 auto;
  background:#FFFDF8;
  border:1px solid rgba(15,43,70,0.12);
  border-radius:10px;
  padding:0 1.4rem;
}
[data-testid="stElementContainer"]:has(iframe) iframe{
  width:1132px !important;
  max-width:calc(100% - 3rem) !important;
  margin:0 auto !important;
  display:block;
}

.ftas{
  --ai-deep:#0F2B46; --ai-mid:#1C4A73; --ai-line:#2E6592;
  --washi:#F7F3EA; --washi-card:#FFFDF8;
  --ink:#12202C; --ink-soft:#4A5C6A;
  --torii:#B5432E; --torii-soft:#F3E1DB;
  --gold:#C79A46;
  --seafoam:#3E8E86; --seafoam-soft:#E0EFEC;
  --amber:#C08A2E; --amber-soft:#F6EBD6;
  --crit:#9C2E2E; --crit-soft:#F5DEDC;
  --hairline:rgba(15,43,70,0.12);
  color:var(--ink) !important;
  font-family:'Inter',sans-serif;
  font-size:16px;
  line-height:normal;
  -webkit-font-smoothing:antialiased;
}
.ftas *{ box-sizing:border-box; }
.ftas div, .ftas span, .ftas p, .ftas td, .ftas th{
  color:inherit; font-family:inherit; line-height:normal;
}
.ftas .font-mono{ font-family:'JetBrains Mono', monospace; }

/* ---------- hero ---------- */
.ftas .ftas-hero{
  background:linear-gradient(180deg, #0F2B46 0%, #1C4A73 100%);
  color:#F7F3EA !important;
  position:relative;
  overflow:hidden;
}
.ftas .ftas-hero .grain{
  position:absolute; inset:0;
  background-image: radial-gradient(circle at 15% 25%, rgba(255,255,255,0.05) 0, transparent 40%),
                     radial-gradient(circle at 85% 75%, rgba(255,255,255,0.04) 0, transparent 45%);
  pointer-events:none;
}
.ftas .ftas-hero-inner{ max-width:1180px; margin:0 auto; padding:2.4rem 1.5rem 2.8rem; position:relative; }
.ftas .ftas-hero-row{ display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:1rem; }
.ftas .ftas-h1{
  font-family:'Shippori Mincho', serif;
  font-size:2.1rem; font-weight:700; margin:.5rem 0 .3rem;
  color:#F7F3EA !important; line-height:normal;
}
.ftas .ftas-hero-lede{ color:rgba(247,243,234,0.75) !important; font-size:.92rem; max-width:36rem; margin:1em 0; }
.ftas .eyebrow{
  letter-spacing:.18em; text-transform:uppercase; font-size:.68rem;
  color:#C79A46 !important; font-weight:600;
}
.ftas .status-pill{
  display:inline-flex; align-items:center; gap:.4rem;
  padding:.3rem .7rem; border-radius:999px;
  font-size:.72rem; font-weight:600;
  border:1px solid rgba(247,243,234,0.25); color:#F7F3EA !important;
}
.ftas .status-dot{ width:6px; height:6px; border-radius:999px; background:#7BD389; }
.ftas .generated-at{
  margin-top:.6rem; font-size:.72rem; color:rgba(247,243,234,0.55) !important;
  font-family:'JetBrains Mono', monospace;
}
.ftas .wave-divider{ width:100%; height:28px; display:block; }

/* ---------- section shell ---------- */
.ftas .ftas-panel{ max-width:1180px; margin:0 auto; padding:2.6rem 1.5rem; }
.ftas .ftas-panel.tight{ padding-top:0; }
.ftas .ftas-panel.head-only{ padding-bottom:0; }
.ftas .section-head{
  display:flex; align-items:baseline; justify-content:space-between;
  margin-bottom:1.4rem; border-bottom:1px solid var(--hairline); padding-bottom:.9rem;
}
.ftas .section-title{
  font-family:'Shippori Mincho', serif; font-size:1.55rem; font-weight:700;
  color:#0F2B46 !important;
}
.ftas .section-sub{ font-size:.82rem; color:#4A5C6A !important; }

/* ---------- KPI cards ---------- */
.ftas .kpi-grid{
  display:grid; grid-template-columns:repeat(4,1fr); gap:1px;
  background:var(--hairline); border:1px solid var(--hairline);
}
.ftas .kpi-card{ background:var(--washi-card); padding:1.4rem 1.3rem; position:relative; }
.ftas .kpi-label{
  font-size:.7rem; letter-spacing:.08em; text-transform:uppercase;
  color:#4A5C6A !important; margin-bottom:.5rem;
}
.ftas .kpi-value{
  font-family:'JetBrains Mono', monospace; font-size:1.9rem; font-weight:700;
  color:#0F2B46 !important; line-height:1.1;
}
.ftas .kpi-delta{ margin-top:.45rem; font-size:.78rem; font-weight:600; }
.ftas .kpi-delta.up{ color:#3E8E86 !important; }
.ftas .kpi-delta.down{ color:#B5432E !important; }
.ftas .kpi-delta.muted{ color:#4A5C6A !important; }

/* ---------- badges ---------- */
.ftas .badge{
  display:inline-flex; align-items:center; gap:.35rem;
  padding:.28rem .62rem; border-radius:5px;
  font-size:.72rem; font-weight:700; letter-spacing:.02em;
  font-family:'JetBrains Mono', monospace;
}
.ftas .badge-HOT{ background:var(--torii-soft); color:#B5432E !important; }
.ftas .badge-OK{ background:var(--seafoam-soft); color:#3E8E86 !important; }
.ftas .badge-WARN{ background:var(--amber-soft); color:#C08A2E !important; }
.ftas .badge-CRIT{ background:var(--crit-soft); color:#9C2E2E !important; }

/* ---------- weather strip ---------- */
.ftas .weather-scroll{ display:flex; gap:.7rem; overflow-x:auto; padding-bottom:.4rem; scrollbar-width:thin; }
.ftas .weather-day{
  min-width:108px; background:var(--washi-card); border:1px solid var(--hairline);
  border-radius:8px; padding:.8rem .6rem; text-align:center; flex-shrink:0;
}
.ftas .weather-day.rain-risk{ border-color:var(--torii); box-shadow:inset 0 0 0 1px var(--torii); }
.ftas .weather-date{ font-size:.68rem; color:#4A5C6A !important; font-family:'JetBrains Mono', monospace; }
.ftas .weather-desc{ font-size:.72rem; margin:.5rem 0 .35rem; color:#12202C !important; min-height:2.4em; }
.ftas .weather-pop{ font-family:'JetBrains Mono', monospace; font-weight:700; font-size:.95rem; }
.ftas .weather-pop.risk{ color:#B5432E !important; }
.ftas .weather-pop.safe{ color:#1C4A73 !important; }

/* ---------- estimated outlook ---------- */
.ftas .outlook-banner{
  display:flex; align-items:center; gap:.6rem;
  background:var(--amber-soft); border:1px dashed var(--amber); border-radius:8px;
  padding:.7rem 1rem; font-size:.8rem; color:#6B4E14 !important; margin-bottom:1rem;
}
.ftas .outlook-scroll{ display:flex; gap:.7rem; overflow-x:auto; padding-bottom:.4rem; scrollbar-width:thin; }
.ftas .outlook-day{
  min-width:128px; background:var(--washi-card); border:1px dashed var(--amber);
  border-radius:8px; padding:.8rem .6rem; text-align:center; flex-shrink:0;
}
.ftas .outlook-date{ font-size:.68rem; color:#4A5C6A !important; font-family:'JetBrains Mono', monospace; }
.ftas .outlook-desc{ font-size:.7rem; margin:.45rem 0 .35rem; color:#12202C !important; min-height:2.2em; }
.ftas .outlook-value{ font-family:'JetBrains Mono', monospace; font-weight:700; font-size:1.1rem; color:#C08A2E !important; }
.ftas .outlook-tag{
  display:inline-block; margin-top:.4rem; font-size:.6rem; letter-spacing:.06em;
  text-transform:uppercase; font-weight:700; color:#C08A2E !important;
  background:var(--amber-soft); border-radius:4px; padding:.15rem .4rem;
}

/* ---------- chart card / table ---------- */
.ftas .chart-card{
  background:var(--washi-card); border:1px solid var(--hairline);
  border-radius:10px; padding:1.4rem;
}
.ftas .chart-card.flush{ padding:0; overflow-x:auto; }
.ftas table.pacing{ width:100%; border-collapse:collapse; font-size:.86rem; margin:0; background:transparent; }
.ftas table.pacing thead th{
  text-align:left; font-size:.68rem; letter-spacing:.08em; text-transform:uppercase;
  color:#4A5C6A !important; padding:.55rem .7rem; border:none;
  border-bottom:1px solid var(--hairline); background:transparent; font-weight:600;
}
.ftas table.pacing tbody td{
  padding:.6rem .7rem; border:none; border-bottom:1px solid var(--hairline);
  font-family:'JetBrains Mono', monospace; color:#12202C !important; background:transparent;
}
.ftas table.pacing tbody tr{ background:transparent; }
.ftas table.pacing tbody tr:hover{ background:rgba(15,43,70,0.03); }

/* ---------- nudges / export / footer ---------- */
.ftas .nudge-card{
  background:var(--washi-card); border:1px solid var(--hairline);
  border-left:3px solid var(--gold); border-radius:6px;
  padding:.9rem 1.1rem; font-size:.86rem; margin-bottom:.6rem;
}
.ftas .nudge-card.weather{ border-left-color:var(--ai-mid); }
.ftas .nudge-card.demand{ border-left-color:var(--torii); }
.ftas .nudge-type{
  font-size:.65rem; letter-spacing:.08em; text-transform:uppercase;
  font-weight:700; color:#4A5C6A !important; margin-bottom:.25rem;
}
.ftas .nudge-empty{ color:#4A5C6A !important; font-size:.86rem; }
.ftas .ftas-footer{
  background:#0F2B46; color:rgba(247,243,234,0.6) !important;
  text-align:center; padding:1.6rem 1rem; font-size:.75rem;
}
.ftas .ftas-tail{ height:0; }

@media print{
  .ftas .ftas-hero{ -webkit-print-color-adjust:exact; print-color-adjust:exact; }
  [data-testid="stElementContainer"]:has(iframe){ display:none; }
}

@media (max-width: 860px){
  .ftas .kpi-grid{ grid-template-columns:repeat(2,1fr); }
}
@media (max-width: 560px){
  .ftas .kpi-grid{ grid-template-columns:1fr; }
  .ftas .section-title{ font-size:1.25rem; }
}
</style>
"""


# ===========================================================================
# FTAS EXECUTIVE DASHBOARD
# ---------------------------------------------------------------------------
# A replication of public/index.html, driven by the same payload that page
# fetches: public/data/dashboard_data.json. (public/data/latest_rsv_sum.csv is
# the pipeline's source extract; the dashboard itself never reads it.)
# ===========================================================================

FTAS_DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "public", "data", "dashboard_data.json")

# en-GB abbreviates September as "Sept"; every other month is three letters.
EN_GB_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sept", "Oct", "Nov", "Dec"]

BADGE_LABEL = {"HOT": "Superb", "OK": "Strong", "WARN": "Warning", "CRIT": "Critical"}


@st.cache_data(show_spinner=False)
def load_ftas_data():
    with open(FTAS_DATA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def js_round(n):
    """Math.round: half away from zero upward, unlike Python's half-to-even."""
    return math.floor(n + 0.5) if n >= 0 else -math.floor(-n + 0.5)


def ftas_num(n):
    """fmtNum: Math.round(n).toLocaleString('en-US')."""
    if n is None:
        return "\u2014"
    return f"{js_round(n):,}"


def ftas_short_date(date_str):
    """fmtShortDate: en-GB {day:'2-digit', month:'short'} -> '01 Sept'."""
    try:
        d = datetime.date.fromisoformat(date_str)
    except ValueError:
        return date_str
    return f"{d.day:02d} {EN_GB_MONTHS[d.month - 1]}"


def ftas_rate(rate):
    """(rate * 100).toFixed(0) + '%'."""
    return f"{js_round(rate * 100)}%"


def ftas_generated(ts):
    """en-GB medium date + short time, in the viewer's local zone."""
    dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
    return f"{dt.day} {EN_GB_MONTHS[dt.month - 1]} {dt.year}, {dt:%H:%M}"


def badge(code):
    return f'<span class="badge badge-{code}">{BADGE_LABEL.get(code, code)}</span>'


def ftas_head(title, sub=""):
    """A .section-head: serif title left, muted sub right, hairline under."""
    right = f'<div class="section-sub">{sub}</div>' if sub else "<div></div>"
    return ('<div class="section-head">'
            f'<div><div class="section-title">{title}</div></div>{right}</div>')


F = load_ftas_data()
FS = F.get("summary", {})
P30 = FS.get("past_30_day", {})
WEEK = FS.get("this_week_pacing", {})

# ---------------------------------------------------------------------------
# BOARD 2 -- FTAS Executive Dashboard
# ---------------------------------------------------------------------------
def render_ftas_board():
    # The FTAS board is a light washi page: drop the dark ground and let the
    # sections run the full width of the main area, as they do in index.html.
    html(FTAS_PAGE_CSS)

    html(FTAS_CSS)

    # --- hero + Executive Summary ----------------------------------------------
    yoy = P30.get("yoy_pct")
    yoy_up = yoy is not None and yoy >= 0
    yoy_text = "\u2014" if yoy is None else ("+" if yoy_up else "") + f"{yoy:g}%"
    diff = P30.get("diff")
    week_rate = ftas_rate(WEEK["rate"]) if WEEK.get("rate") is not None else "\u2014"

    html(f'''
    <div class="ftas ftas-zone ftas-bleed">
      <div class="ftas-hero">
        <div class="grain"></div>
        <div class="ftas-hero-inner">
          <div class="ftas-hero-row">
            <div>
              <div class="eyebrow">\u798f\u4e95\u770c\u89b3\u5149\u30c7\u30fc\u30bf\u5206\u6790\u30b7\u30b9\u30c6\u30e0 \u00b7 Fukui Tourism Analytics System</div>
              <div class="ftas-h1">FTAS Executive Dashboard</div>
              <p class="ftas-hero-lede">
                Operational demand intelligence for DMOs, hotel operators, and municipal planners across the Reihoku and Reinan corridors.
              </p>
            </div>
            <div style="text-align:right;">
              <span class="status-pill"><span class="status-dot"></span> Live pipeline</span>
              <div class="generated-at">Generated {ftas_generated(F["generated_at"])}</div>
            </div>
          </div>
        </div>
        <svg class="wave-divider" viewBox="0 0 1200 28" preserveAspectRatio="none">
          <path d="M0,14 C150,28 350,0 600,14 C850,28 1050,0 1200,14 L1200,28 L0,28 Z" fill="#F7F3EA"/>
        </svg>
      </div>
    </div>
    ''')

    html(f'''
    <div class="ftas">
      <div class="ftas-panel">
        {ftas_head("Executive Summary")}
        <div class="kpi-grid">
          <div class="kpi-card">
            <div class="kpi-label">Past 30 Days</div>
            <div class="kpi-value">{ftas_num(P30.get("current_total"))}</div>
            <div class="kpi-delta {"up" if yoy_up else "down"}">{yoy_text} YoY</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">Same Period Last Year</div>
            <div class="kpi-value">{ftas_num(P30.get("previous_year_total"))}</div>
            <div class="kpi-delta muted">baseline</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">Net Difference</div>
            <div class="kpi-value">{"+" if (diff or 0) >= 0 else ""}{ftas_num(diff)}</div>
            <div class="kpi-delta muted">visitors vs. last year</div>
          </div>
          <div class="kpi-card">
            <div class="kpi-label">This Week Pacing</div>
            <div class="kpi-value" style="font-size:1.35rem;">{week_rate}</div>
            <div style="margin-top:.5rem;">{badge(WEEK["badge"]) if WEEK.get("badge") else ""}</div>
          </div>
        </div>
      </div>
    </div>
    ''')

    # --- 14-day weather & pacing strip -----------------------------------------
    days = F.get("weather_strip", [])
    if days:
        cards = "".join(
            f'''<div class="weather-day{" rain-risk" if d.get("rain_risk") else ""}">
              <div class="weather-date">{ftas_short_date(d["date"])}</div>
              <div class="weather-desc">{d.get("weather") or "\u2014"}</div>
              <div class="weather-pop {"risk" if d.get("rain_risk") else "safe"}">'''
            f'''{str(d["precipitation_pct"]) + "%" if d.get("precipitation_pct") is not None else "\u2014"}'''
            f"</div></div>" for d in days)
    else:
        cards = '<p style="color:#4A5C6A;font-size:.85rem;">Weather forecast unavailable.</p>'

    html(f'''
    <div class="ftas">
      <div class="ftas-panel tight">
        {ftas_head("14-Day Weather &amp; Pacing Strip", "Rain risk \u2265 40% outlined in vermillion")}
        <div class="weather-scroll">{cards}</div>
      </div>
    </div>
    ''')

    # --- actual vs. model forecast ---------------------------------------------
    html(f'''
    <div class="ftas">
      <div class="ftas-panel tight head-only">
        {ftas_head("Actual vs. Model Forecast", "Last 60 days \u00b7 Random Forest")}
      </div>
    </div>
    ''')

    rows = F.get("demand_forecast", [])
    labels = [r["date"] for r in rows]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=labels, y=[r["actual"] for r in rows], name="Actual Visitors",
        mode="lines", line=dict(color="#0F2B46", width=2, shape="spline", smoothing=0.6),
        fill="tozeroy", fillcolor="rgba(15,43,70,0.08)",
        hovertemplate="Actual Visitors: %{y:,.0f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=labels, y=[r["forecast"] for r in rows], name="Model Forecast",
        mode="lines", line=dict(color="#B5432E", width=2, dash="4px,3px",
                                shape="spline", smoothing=0.6),
        hovertemplate="Model Forecast: %{y:,.0f}<extra></extra>",
    ))
    # Chart.js draws this canvas 325px tall with the plot area inset 42/32/1/26.
    # The card's 1.4rem (22.4px) top/bottom padding is added to the figure and paid
    # straight back into the margins, so the plot area is unchanged and the card
    # measures the original's 372px.
    CARD_PAD = 22.4
    fig.update_layout(
        height=325 + 2 * CARD_PAD,
        margin=dict(l=42, r=1, t=32 + CARD_PAD, b=26 + CARD_PAD),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", size=12, color="#666"),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="rgba(0,0,0,0.8)", bordercolor="rgba(0,0,0,0)",
                        font=dict(family="Inter, sans-serif", size=12, color="#fff")),
        legend=dict(orientation="h", x=0.5, xanchor="center", y=1, yanchor="bottom",
                    font=dict(family="Inter, sans-serif", size=12, color="#666"),
                    itemsizing="constant"),
        dragmode=False,
        xaxis=dict(type="category", showgrid=False, showline=True,
                   linecolor="rgba(15,43,70,0.1)", ticks="", tickmode="array",
                   tickvals=[labels[i] for i in range(0, len(labels), 6)],
                   tickfont=dict(family="JetBrains Mono, monospace", size=10, color="#666")),
        yaxis=dict(range=[0, 25000], gridcolor="rgba(15,43,70,0.06)", zeroline=False,
                   showline=True, linecolor="rgba(15,43,70,0.1)", ticks="",
                   tickmode="array", tickvals=[5000 * i for i in range(6)],
                   ticktext=[f"{5000 * i:,}" for i in range(6)],
                   tickfont=dict(family="JetBrains Mono, monospace", size=10, color="#666")),
    )
    st.plotly_chart(fig, width="stretch", config=PLOT_CONFIG, key="ftas_demand")

    # section.panel's own 2.6rem bottom padding, which the chart element sits outside of
    html('<div class="ftas"><div class="ftas-panel" style="padding:0 1.5rem 2.6rem;"></div></div>')

    # --- near-term outlook (only when the local weather file is stale) ---------
    outlook = F.get("estimated_outlook", [])
    if outlook:
        cards = "".join(
            f'''<div class="outlook-day">
              <div class="outlook-date">{ftas_short_date(d["date"])}</div>
              <div class="outlook-desc">{d.get("weather") or "\u2014"}</div>
              <div class="outlook-value">{ftas_num(d.get("estimated_demand"))}</div>
              <div class="outlook-tag">Estimated</div>
            </div>''' for d in outlook)
        html(f'''
    <div class="ftas">
      <div class="ftas-panel tight">
        {ftas_head("Near-Term Outlook (Estimated)", "Based on live weather forecast")}
        <div class="outlook-banner">
          \u26a0\ufe0f The local historical weather file is out of date, so these days are an approximate estimate built from the live weather forecast and recent averages \u2014 not a full model-quality prediction. Treat as directional only.
        </div>
        <div class="outlook-scroll">{cards}</div>
      </div>
    </div>
    ''')

    # --- day-by-day pacing ------------------------------------------------------
    pacing = F.get("weekly_pacing", [])
    if pacing:
        body = "".join(
            f"<tr><td>{r['date']}</td><td>{ftas_num(r['actual'])}</td>"
            f"<td>{ftas_num(r['forecast'])}</td><td>{ftas_rate(r['rate'])}</td>"
            f"<td>{badge(r['badge'])}</td></tr>" for r in reversed(pacing))
    else:
        body = ('<tr><td colspan="5" style="color:#4A5C6A;font-family:Inter;">'
                "No pacing data available.</td></tr>")

    html(f'''
    <div class="ftas">
      <div class="ftas-panel tight">
        {ftas_head("Day-by-Day Pacing", "Achievement rate = actual \u00f7 forecast")}
        <div class="chart-card flush">
          <table class="pacing">
            <thead>
              <tr><th>Date</th><th>Actual</th><th>Forecast</th><th>Rate</th><th>Status</th></tr>
            </thead>
            <tbody>{body}</tbody>
          </table>
        </div>
      </div>
    </div>
    ''')

    # --- governance & vendor nudges --------------------------------------------
    nudges = F.get("nudges", [])
    if nudges:
        cards = "".join(
            f'''<div class="nudge-card {n["type"]}">
              <div class="nudge-type">{"Weather Risk" if n["type"] == "weather" else "Demand Signal"} \u00b7 {n["date"]}</div>
              <div>{n["message"]}</div>
            </div>''' for n in nudges)
    else:
        cards = ('<div class="nudge-empty">No active recommendations \u2014 '
                 "pacing and weather are within normal range.</div>")

    html(f'''
    <div class="ftas">
      <div class="ftas-panel tight">
        {ftas_head("Governance &amp; Vendor Nudges")}
        {cards}
      </div>
    </div>
    ''')

    # --- report export hub ------------------------------------------------------
    html(f'''
    <div class="ftas">
      <div class="ftas-panel tight head-only">
        {ftas_head("Report Export Hub")}
      </div>
    </div>
    ''')

    # The export buttons need scripts (window.print and PptxGenJS), which Streamlit
    # strips from markdown, so they live in a component iframe carrying the same
    # payload and the same three-slide deck the original builds.
    EXPORT_PAYLOAD = json.dumps({"summary": FS, "nudges": F.get("nudges", [])})
    st.iframe(f'''
    <html><head>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/pptxgenjs@3.12.0/dist/pptxgen.bundle.js"></script>
    <style>
      html,body{{ margin:0; padding:0; background:#F7F3EA; font-family:'Inter',sans-serif; }}
      .row{{ display:flex; gap:.8rem; flex-wrap:wrap; }}
      .export-btn{{
        display:inline-flex; align-items:center; gap:.5rem;
        background:#0F2B46; color:#F7F3EA; border:none;
        padding:.65rem 1.2rem; border-radius:6px;
        font-size:.85rem; font-weight:600; font-family:'Inter',sans-serif;
        cursor:pointer; transition:background .15s ease;
      }}
      .export-btn:hover{{ background:#1C4A73; }}
      .export-btn.secondary{{ background:transparent; color:#0F2B46; border:1px solid #0F2B46; }}
      .export-btn.secondary:hover{{ background:rgba(15,43,70,0.06); }}
    </style>
    </head><body>
    <div class="row">
      <button class="export-btn" onclick="printBoard()">&darr; Export PDF Summary</button>
      <button class="export-btn secondary" onclick="exportPPTX()">&darr; Export PPTX Deck</button>
    </div>
    <script>
    const DASHBOARD_DATA = {EXPORT_PAYLOAD};

    function printBoard(){{
      try {{ window.parent.print(); }} catch (e) {{ window.print(); }}
    }}

    function exportPPTX(){{
      if (typeof PptxGenJS === 'undefined') {{
        alert('The PowerPoint export library failed to load. Check your internet connection and try again.');
        return;
      }}
      const data = DASHBOARD_DATA;
      const pptx = new PptxGenJS();
      pptx.defineLayout({{ name:'FTAS', width:10, height:5.63 }});
      pptx.layout = 'FTAS';

      const slide1 = pptx.addSlide();
      slide1.background = {{ color:'0F2B46' }};
      slide1.addText('FTAS Executive Dashboard', {{ x:0.5, y:1.8, w:9, h:0.8, fontSize:32, bold:true, color:'F7F3EA', fontFace:'Georgia' }});
      slide1.addText('Fukui Tourism Analytics System \u2014 Summary Report', {{ x:0.5, y:2.6, w:9, h:0.5, fontSize:16, color:'C79A46' }});

      const p30 = (data.summary || {{}}).past_30_day || {{}};
      const slide2 = pptx.addSlide();
      slide2.addText('Executive Summary', {{ x:0.4, y:0.3, fontSize:24, bold:true, color:'0F2B46' }});
      slide2.addText([
        {{ text: `Past 30 Days: ${{p30.current_total ?? '\u2014'}}\\n`, options:{{ fontSize:16 }} }},
        {{ text: `Same Period Last Year: ${{p30.previous_year_total ?? '\u2014'}}\\n`, options:{{ fontSize:16 }} }},
        {{ text: `Net Difference: ${{p30.diff ?? '\u2014'}} (${{p30.yoy_pct ?? '\u2014'}}% YoY)\\n`, options:{{ fontSize:16 }} }},
      ], {{ x:0.4, y:1.1, w:9, h:2 }});

      const slide3 = pptx.addSlide();
      slide3.addText('Recommended Actions', {{ x:0.4, y:0.3, fontSize:24, bold:true, color:'0F2B46' }});
      const nudgeText = (data.nudges || []).map(n => `\u2022 [${{n.date}}] ${{n.message}}`).join('\\n') || 'No active recommendations.';
      slide3.addText(nudgeText, {{ x:0.4, y:1.1, w:9, h:3.5, fontSize:14 }});

      pptx.write({{ outputType:'blob' }}).then(function(blob){{
        const name = 'FTAS_Executive_Summary.pptx';
        try {{
          // This iframe is sandboxed; hand the file to the parent document, whose
          // downloads are not restricted. Same-origin, so the blob URL carries.
          const doc = window.parent.document;
          const url = URL.createObjectURL(blob);
          const a = doc.createElement('a');
          a.href = url; a.download = name;
          doc.body.appendChild(a); a.click(); a.remove();
          setTimeout(function(){{ URL.revokeObjectURL(url); }}, 10000);
        }} catch (e) {{
          pptx.writeFile({{ fileName:name }});
        }}
      }}).catch(function(e){{
        alert('Could not build the deck: ' + e.message);
      }});
    }}
    </script>
    </body></html>
    ''', height=42)

    # --- footer -----------------------------------------------------------------
    html('''
    <div class="ftas">
      <div class="ftas-panel tight" style="padding-bottom:2.6rem;"></div>
    </div>
    ''')

    html('''
    <div class="ftas ftas-bleed">
      <div class="ftas-footer">
        Fukui Tourism Analytics System \u2014 Distributed Human Data Engine \u00b7 Data refreshed on load
      </div>
    </div>
    ''')


# ---------------------------------------------------------------------------
# NAVIGATION
# ---------------------------------------------------------------------------
NAV_CSS = f"""
<style>
[data-testid="stSidebar"]{{
  background:{BG_2} !important;
  border-right:1px solid {LINE};
  width:264px !important; min-width:264px !important;
}}
[data-testid="stSidebar"] > div{{ background:transparent !important; }}
/* Drop the sidebar's 20px side padding so nav rows span its full width; the
   nav blocks below carry their own 14px inset instead. */
[data-testid="stSidebarContent"]{{ padding:14px 0 0 !important; }}
[data-testid="stSidebar"] [data-testid="stSidebarHeader"]{{ padding:0 20px !important; }}
[data-testid="stSidebar"] [data-testid="stElementContainer"]:has([data-testid="stRadio"]),
[data-testid="stSidebar"] [data-testid="stRadio"],
[data-testid="stSidebar"] [data-testid="stRadioGroup"]{{ width:100% !important; }}
[data-testid="stSidebarCollapseButton"] svg,
[data-testid="stSidebarCollapsedControl"] svg{{ color:{MUTED} !important; }}

.nav-brand{{
  font-family:{FONT_MONO}; font-size:15px; font-weight:600;
  letter-spacing:.06em; color:{INK} !important; padding:6px 14px 0;
}}
.nav-brand .tick{{ color:{AMBER}; margin-right:7px; }}
.nav-sub{{
  font-size:11px; color:{MUTED_2} !important; padding:4px 14px 0;
  letter-spacing:.03em;
}}
.nav-eyebrow{{
  font-size:10px; letter-spacing:.16em; text-transform:uppercase;
  color:{MUTED_2} !important; padding:0 14px; margin:26px 0 8px;
}}

/* The radio becomes a nav list: no dots, full-width rows, amber active rail. */
[data-testid="stSidebar"] [role="radiogroup"]{{
  gap:1px !important; width:100% !important; align-items:stretch !important;
}}
[data-testid="stSidebar"] [role="radiogroup"] label{{
  display:flex; align-items:center; width:100% !important;
  padding:11px 14px !important; margin:0 !important;
  border-left:2px solid transparent; background:transparent;
  cursor:pointer; transition:background .12s ease;
}}
/* Hide the radio dot: any wrapper in the row that holds no label text. */
[data-testid="stSidebar"] [role="radiogroup"] label
  div:not([data-testid="stMarkdownContainer"]):not(:has([data-testid="stMarkdownContainer"])){{
  display:none !important;
}}
[data-testid="stSidebar"] [role="radiogroup"] label p{{
  font-family:{FONT_BODY}; font-size:13px; line-height:1.35;
  color:{MUTED} !important; margin:0 !important;
}}
[data-testid="stSidebar"] [role="radiogroup"] label:hover{{
  background:rgba(255,255,255,.035);
}}
[data-testid="stSidebar"] [role="radiogroup"] label:hover p{{ color:{INK} !important; }}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked),
[data-testid="stSidebar"] [role="radiogroup"] label[data-selected="true"]{{
  background:rgba(242,169,59,.10); border-left-color:{AMBER};
}}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p,
[data-testid="stSidebar"] [role="radiogroup"] label[data-selected="true"] p{{
  color:{INK} !important; font-weight:600;
}}

.nav-foot{{
  margin:26px 14px 0; padding-top:14px; border-top:1px solid {LINE_SOFT};
  font-size:11px; line-height:1.55; color:{MUTED_2} !important;
}}
.nav-foot b{{ color:{MUTED} !important; font-weight:600; }}
</style>
"""

BOARDS = {
    "PAK ⟶ JPN Arrivals": render_pak_board,
    "FTAS Executive Board": render_ftas_board,
}
# ?board=pak / ?board=ftas deep-links a board, so a link can point at either.
SLUGS = dict(zip(("pak", "ftas"), BOARDS))
_default = SLUGS.get(st.query_params.get("board"), next(iter(BOARDS)))

with st.sidebar:
    html(NAV_CSS)
    html('<div class="nav-brand"><span class="tick">▍</span>DHDE</div>'
         '<div class="nav-sub">Tourism data boards</div>'
         '<div class="nav-eyebrow">Dashboards</div>')
    board = st.radio("Dashboard", list(BOARDS), label_visibility="collapsed",
                     index=list(BOARDS).index(_default), key="board")
    html('<div class="nav-foot">'
         '<b>JNTO</b> visitor arrivals &amp; MOJ entries · through May 2026<br>'
         '<b>FTAS</b> demand pipeline · generated 31 Aug 2026'
         "</div>")

st.query_params["board"] = next(k for k, v in SLUGS.items() if v == board)

BOARDS[board]()
