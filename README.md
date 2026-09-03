<div align="center">

# Hokuriku Tourism AI Governance Framework

### AI-Driven Visitor Demand Forecasting & Spatial Under-vibrancy Analysis

**Amil Khanzada** — *Specially Appointed Professor, Headquarters for Regional Revitalization, University of Fukui*

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21271429.svg)](https://doi.org/10.5281/zenodo.21271429)
[![Tests](https://img.shields.io/badge/tests-pytest-green.svg)](tests/)
[![Data Validated](https://img.shields.io/badge/rows%20audited-1.4M-brightgreen.svg)](src/validator.py)

</div>

> **Executive Reports:** [English](EXECUTIVE_REPORT.en.md) · [日本語](EXECUTIVE_REPORT.ja.md)
> **Read in:** [日本語](README.ja.md)

---

## Abstract

This repository implements the **Distributed Human Data Engine (DHDE)** — a research framework that fuses heterogeneous tourism data sources (AI camera people-flow, JMA meteorological observations, Route search impression (RSI) intent signals, and 97,719 Hokuriku survey responses) into a unified predictive and diagnostic pipeline.

The system quantifies Fukui Prefecture's structural tourism deficit: the **¥11.96 billion annual Opportunity Gap** — revenue lost due to weather-induced demand suppression during winter months, when Fukui ranks **47th out of 47 prefectures** nationally.

**Keywords:** Tourism Demand Forecasting · Kansei Engineering · Discomfort Index · Spatial Saturation · Under-vibrancy · Hokuriku Regional Governance

---

## Quickstart: Running the Application Locally

The project includes an interactive web dashboard powered by pre-processed telemetry and machine learning models stored in `public/data/dashboard_data.json`.

### 1. Preview the Web Dashboard

You do not need to re-run the entire data ingestion or ML training pipeline to develop or test the dashboard UI:

```bash
# From the repository root, start a local HTTP server:
python -m http.server 8000
```

Open your browser and navigate to:

```plaintext
http://localhost:8000/public/
```

* **Entry Point:** `public/index.html`
* **Static Assets:** `public/`
* **Data Payload:** `public/data/dashboard_data.json`

### 2. (Optional) Re-generating Model Telemetry

If you are modifying model architectures or feature engineering:
* **Script:** `scripts/generate_report_data.py`
* **Prerequisites:** Sibling data repositories (`fukui-kanko-people-flow-data`, `opendata`, etc.) mounted in your workspace directory.
* **Target Output:** Re-generates `public/data/dashboard_data.json`

---

---

## 1. Theoretical Framework: The Distributed Human Data Engine (DHDE)

The DHDE integrates four sensor modalities into a single analytical pipeline:

```
┌─────────────────────────────────────────────────────────────────┐
│                  DISTRIBUTED HUMAN DATA ENGINE                  │
│                                                                 │
│  ┌────────────┐  ┌────────────┐  ┌──────────────┐  ┌───────────┐│
│  │ AI Camera  │  │ JMA Weather│  │ RSI (route)  │  │ Hokuriku  ││
│  │ People-Flow│  │ 8-Variable │  │ Route Intent │  │  Survey   ││
│  │  (Edge-AI) │  │ (Hourly)   │  │  (Daily)     │  │ (97,719)  ││
│  └─────┬──────┘  └─────┬──────┘  └──────┬───────┘  └─────┬─────┘│
│        │               │                │                │      │
│        └───────────┬───┴────────────────┴────────┬───────┘      │
│                    │     Feature Engineering     │              │
│                    │ Calendar · Weather Severity │              │
│                    │ Lags · Rolling · Interaction│              │
│                    └─────────────┬───────────────┘              │
│                                  │                              │
│              ┌───────────────────┴───────────────────┐          │
│              │  OLS Regression + Random Forest (RF)  │          │
│              │  Robustness: DW, NW-HAC, FD, LDV, VIF │          │
│              └───────────────────┬───────────────────┘          │
│                                  │                              │
│         ┌────────────────────────┼────────────────────────┐     │
│         │                        │                        │     │
│  ┌──────▼───────┐  ┌─────────────▼───────────┐  ┌─────────▼────┐│
│  │ Opportunity  │  │ Kansei Assessment       │  │ Spatial      ││
│  │ Gap / Lost   │  │ DI · WC · Overtourism   │  │ Saturation   ││
│  │ Population   │  │ Text Mining (NLP)       │  │ Multi-Node   ││
│  └──────────────┘  └─────────────────────────┘  └──────────────┘│
│                                                                 │
│                   ──► analysis_metrics.txt                      │
│                   ──► LaTeX tables for paper                    │
└─────────────────────────────────────────────────────────────────┘
```

**Nodes in the spatial network:**

| Node | Location | Camera Source | Weather Station |
|------|----------|--------------|-----------------|
| A | Tojinbo (東尋坊) | tojinbo-shotaro | Mikuni (JMA) |
| B | Fukui Station East | fukui-station-east | Fukui (JMA) |
| C | Katsuyama (勝山) | katsuyama | Katsuyama (JMA) |
| D | Rainbow Line (レインボーライン) | rainbow-line-parking-lot-1-gate | Mihama (JMA) |

---

## 2. Key Results

| Metric | Value | Interpretation |
|--------|-------|---------------|
| **OLS R²** | 0.810 (Adj R² = 0.802) | Baseline explanatory power |
| **RF 5-fold CV R²** | 0.557 ± 0.131 | Out-of-sample predictive accuracy |
| **First-Difference R²** | 0.708 | Autocorrelation-corrected |
| **LDV R² / DW** | 0.848 / 1.899 | Dynamic model, clean residuals |
| **#1 Predictor** | `directions` (RSI) | Route-search intent, *β* = +0.456 |
| **Ishikawa → Tojinbo lag** | *r* = +0.549 | Cross-prefectural demand pipeline |
| **Visitors vs Satisfaction** | *r*<sub>s</sub> = +0.150 (*p* = 0.002) | **No overtourism** detected |
| **Lost Visitors** | 85,522 (single-node) | Annual Opportunity Gap |
| **Winter Weather Sensitivity** | 6.26× summer | Seasonal asymmetry |
| **Under-vibrancy Ratio** | 11.5× | Low-satisfaction review prevalence |
| **National Ranking** | 47th / 47 (least-visited prefecture) | Fukui's structural deficit |

---

## 3. The ¥11.96 Billion Opportunity Gap

The **Opportunity Gap** measures the difference between *expected* visitors (based on RSI intent signals) and *actual* arrivals on weather-degraded days:

$$
\text{Lost Visitors}_d = \hat{y}_d^{\text{OLS}} - y_d^{\text{actual}} \quad \text{when} \quad y_d < \hat{y}_d
$$

$$
\text{Total Economic Loss} = \sum_{d \in \mathcal{G}} \text{Lost Visitors}_d \times \bar{S}
$$

where $\bar{S} = ¥13{,}811$ is the mean spending per visitor (from Fukui survey, $n = 97{,}719$), and $\mathcal{G}$ is the set of gap days.

| Component | Value |
|-----------|-------|
| Gap days | 42 (high-friction days) |
| Total lost visitors | 85,522 |
| Mean spending per visitor | ¥13,811 (~$88) |
| **Total annual revenue loss** | **¥11.96 billion (~USD 72.6M)** |

---

## 4. Kansei Environmental Assessment

### 4.1 Discomfort Index (不快指数)

The thermal comfort metric used in this framework:

$$
DI = 0.81 \cdot T + 0.01 \cdot H \cdot (0.99 \cdot T - 14.3) + 46.3
$$

where $T$ is temperature (°C) and $H$ is relative humidity (%).

### 4.2 Wind Chill (体感温度)

$$
WC = 13.12 + 0.6215T - 11.37V^{0.16} + 0.3965TV^{0.16}
$$

where $V$ is wind speed in km/h. Valid for $T \leq 10°C$ and $V > 4.8$ km/h.

### 4.3 Overtourism Threshold

Spearman correlation between daily visitor count and mean satisfaction:

*r*<sub>s</sub>(visitors, satisfaction) = +0.150 (*p* = 0.002)

The **positive** correlation confirms Fukui's problem is *under-vibrancy*, not overtourism. More visitors → higher satisfaction.

---

## 5. Spatial Saturation Map

The multi-node analysis achieves **geographic saturation** of Fukui Prefecture:

```
              ┌──── Node C: Katsuyama (Mountain / East) ────┐
              │                                             │
   Node A: Tojinbo ─── Node B: Fukui Station ─── Node D: Rainbow Line
   (Coastal / North)   (Urban / Central)          (Scenic / South)
```

Each node is modelled independently with local JMA weather, enabling:
- **Weather Shield Network**: When Mikuni (coast) is stormy, Katsuyama (inland) may be clear
- **Demand redistribution** via real-time atmospheric nudging

---

## 6. Model Robustness

| Diagnostic | Statistic | Interpretation |
|-----------|-----------|---------------|
| Durbin–Watson (OLS) | 1.005 | Corrected via Newey-West HAC |
| Durbin–Watson (1st-diff) | 2.525 | **Clean** residuals |
| Newey–West HAC | lags = 8, 9 significant | Robust to heteroskedasticity |
| First-Difference R² | 0.708 | Controls for trend |
| LDV R² | 0.848 | Dynamic specification |
| VIF (max) | 15.0 (calendar interaction) | Elevated but does not invalidate significance |
| Weather data value | +0.056 R² | JMA contribution quantified |

---

## 7. Repository Structure

```
hokuriku-tourism-ai-governance/
├── pyproject.toml                # PEP 517/621 package definition → pip install .
├── requirements.txt              # Runtime dependencies (minimum versions)
├── SUPPLEMENT.md                 # Reproducibility supplement (params, schema, SHAs)
├── EXECUTIVE_REPORT.en.md        # English executive report (pandoc → PDF source)
├── EXECUTIVE_REPORT.ja.md        # Japanese executive report (pandoc → PDF source)
├── DATA_DICTIONARY.md            # Full variable reference
├── config/
│   └── settings.yaml             # Pipeline configuration (all paths & params)
├── src/
│   ├── __init__.py               # Package metadata
│   ├── config.py                 # YAML config loader & path resolver
│   ├── data_loader.py            # Camera, JMA, RSI, Survey loaders
│   ├── feature_engineering.py    # Calendar, severity, lags, interactions
│   ├── models.py                 # OLS + Random Forest + robustness suite
│   ├── kansei.py                 # Discomfort Index, Wind Chill, text mining
│   ├── economics.py              # Opportunity Gap, lost population, ranking
│   ├── spatial.py                # Cross-prefectural CCF, multi-node governance
│   ├── validator.py              # Data integrity auditing (schema, drift, outliers)
│   ├── visualizer.py             # Figure generation
│   ├── latex_export.py           # LaTeX table generator for paper
│   ├── report.py                 # Centralized Reporter for logging & metrics
│   └── run_analysis.py           # Main pipeline entry-point
├── tests/
│   ├── test_models.py            # OLS, RF, robustness tests
│   ├── test_kansei.py            # DI & Wind Chill formula verification
│   ├── test_validator.py         # Schema, outlier, drift detection tests
│   ├── test_features.py          # Feature engineering pipeline tests
│   └── test_math.py              # Core statistical function checks
├── jma/                          # JMA weather observations (committed)
│   ├── fetch_jma_monthly.py      # Scraper for JMA hourly CSVs
│   ├── merge_clean_jma.py        # Merge rawdata into per-station CSVs
│   └── jma_*.csv                 # Merged per-station 8-field datasets
└── output/                       # Key generated artifacts (committed)
    ├── analysis_metrics.txt      # Machine-readable key metrics
    ├── paper_fig{1-5}_*.png      # Paper figures (Figures 1–5)
    └── table{1-3}_*.tex          # LaTeX tables (Tables 1–3)
```

---

## 8. Data Sources

| Source | Type | Coverage | Rows |
|--------|------|----------|------|
| **AI Camera** (Tojinbo-Shotaro) | Edge-AI person counts (5-min intervals) | 2024-12 → 2026-02 | ~170K |
| **JMA** (Mikuni, Fukui, Katsuyama) | Hourly: precip, temp, sun, wind, humidity, snow | 2024-01 → 2026-02 | ~140K |
| **Route Search Impressions (RSI)** | Daily: route searches, map views, reviews for 47 locations | 2024-01 → 2026-02 | ~35K |
| **Hokuriku Tourism Survey** | Satisfaction, NPS, free text (Fukui/Ishikawa/Toyama) | 2023 → 2026 | **97,719** |
| **Fukui Kanko Survey (raw)** | Spending, demographics, travel patterns | 2022 → 2025 | 90,317 records (576K raw CSV lines) |

**Total records:** ~530K

---

## 9. Reproduction Steps

### Setup

```bash
# Create workspace with sibling data repos
mkdir hokuriku-workspace && cd hokuriku-workspace
git clone https://github.com/code4fukui/fukui-kanko-people-flow-data.git
git clone https://github.com/code4fukui/fukui-kanko-trend-report.git
git clone https://github.com/hokuriku-inbound-kanko/opendata.git
git clone https://github.com/code4fukui/fukui-kanko-survey.git

# Clone and install this repository
git clone https://github.com/code4fukui/hokuriku-tourism-ai-governance.git
cd hokuriku-tourism-ai-governance
git checkout submission/scs-v1
pip install -e ".[dev]"
```
## IMPORTANT: Initialize Submodules

This project requires Git submodules for dataset access. Before running any commands, initialize them:

```bash
git submodule update --init --recursive
```

### Commands

| Command | What it does |
|---------|-------------|
| `python3 -m src.run_analysis` | Run full pipeline → figures, metrics, LaTeX tables |
| `pytest` | Run test suite (verifies core math & formulas) |
| `pytest --cov=src --cov-report=html` | Tests with coverage report |
| `ruff check src/ tests/` | Lint check |
| `pandoc output/pdf/executive_report_en.md -o output/pdf/executive_report_en.pdf --pdf-engine=xelatex` | Build English executive report PDF |
| `pandoc output/pdf/executive_report_ja.md -o output/pdf/executive_report_ja.pdf --pdf-engine=xelatex` | Build Japanese executive report PDF |

> **Note:** 
> Set `HTAG_CONFIG=/path/to/settings.yaml` to use a custom config (default: `config/settings.yaml`). 
> Use `python` on Windows and `python3` on Linux/macOS.

> **PDF prerequisites (Debian/Ubuntu/WSL):** `sudo apt-get install -y pandoc texlive-xetex texlive-lang-japanese fonts-noto-cjk`

All artifacts are written to `output/`: paper figures and LaTeX tables.

---

## 10. Modular Architecture

The pipeline follows a strict **separation of concerns**:

```python
# Entrypoint: src/run_analysis.py
cfg = load_config()                           # config.py
rpt = Reporter(cfg)                           # report.py
validation = validate_pipeline(cfg, rpt)      # validator.py
data = load_all_data(cfg, rpt)                # data_loader.py
daily, features = build_features(daily, ..)   # feature_engineering.py
ols = fit_ols(model_df, features, rpt)        # models.py
rf  = fit_random_forest(model_df, ..)         # models.py
robust = robustness_suite(model_df, ..)       # models.py
gap = compute_opportunity_gap(daily, ..)      # economics.py
kansei = discomfort_index_analysis(..)        # kansei.py
spatial = multi_node_analysis(cfg, ..)        # spatial.py
export_all_tables(results, ..)                # latex_export.py
```

Every module accepts a `Reporter` instance for deterministic logging. No module uses `print()` directly — all output flows through the centralized reporter.

---

## 11. Testing & Validation

### Test Suite

```
tests/
├── test_models.py     # OLS R², RF importance, DW, edge cases
├── test_kansei.py     # DI hand-calculations, wind chill, golden values
├── test_validator.py  # Schema, outliers, date gaps, drift detection
├── test_features.py   # Calendar, severity, lags, encodings
└── test_math.py       # Core statistical function correctness
```

### Data Validation (`src/validator.py`)

Automatically audits every data source for:
- **Schema mismatches** — columns added/removed between data versions
- **Data drift** — Kolmogorov–Smirnov tests on 3-month sliding windows
- **Outliers** — IQR and Z-score detection per column
- **Date gaps** — Missing days in time-series continuity
- **Domain violations** — Negative precipitation, extreme temperatures

Results are included in `output/analysis_metrics.txt`.

---

## License

This project is released under the [MIT License](LICENSE). Copyright © 2026 Amil Khanzada.

The tagged release [v1.0.0](https://github.com/amilkh/hokuriku-tourism-ai-governance/releases/tag/v1.0.0) is the reproducibility archive for the *Measurement* article (DOI: [10.1016/j.measurement.2026.122500](https://doi.org/10.1016/j.measurement.2026.122500)), permanently archived at Zenodo (DOI: [10.5281/zenodo.21271429](https://doi.org/10.5281/zenodo.21271429)).

> Note: this public history has been curated for publication (internal manuscripts, meeting documents, and generated artifacts removed; data-source naming aligned with the published article).

## Contributors

Developed by Amil Khanzada with valued open-source contributions:

- **Ibrahim Mustafa** — chronological benchmark and Random Forest ablation framework (`src/benchmark.py`)
- **Mohammed Abdullah** — privacy sanitization layer and opt-in zero-shot Kansei diagnostics (`src/privacy_nlp.py`)
- **Dina Belay** — reproducibility documentation and cross-platform runtime fixes
- **Dawood Imtiaz** — interactive analytics dashboard (`dashboard/`)
- **Mitali (Hacxmr)** — Windows encoding compatibility fix

