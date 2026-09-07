/**
 * Strict types for public/data/dashboard_data.json, as produced by
 * scripts/generate_report_data.py's build_dashboard_payload().
 */

export type NodeKey = 'tojinbo' | 'fukui_station' | 'katsuyama' | 'rainbow_line'

/** Stable render order for the node switcher tab bar. */
export const NODE_ORDER: NodeKey[] = ['tojinbo', 'fukui_station', 'katsuyama', 'rainbow_line']

export type NodeDataSource = 'camera' | 'survey_proxy'

export type PacingBadge = 'HOT' | 'OK' | 'WARN' | 'CRIT'
export type PacingLabel = 'Superb' | 'Strong' | 'Warning' | 'Critical'

export interface PacingStatus {
  rate: number
  badge: PacingBadge
  label: PacingLabel
}

export interface Past30DaySummary {
  current_total: number
  previous_year_total: number
  diff: number
  yoy_pct: number | null
}

export interface NodeSummary {
  past_30_day: Past30DaySummary
  this_week_pacing: PacingStatus
}

export interface WeatherStripDay {
  date: string
  weather: string | null
  wind: string | null
  precipitation_pct: number | null
  rain_risk: boolean
}

export interface DemandForecastPoint {
  date: string
  actual: number
  forecast: number
}

export interface WeeklyPacingPoint extends DemandForecastPoint, PacingStatus {}

export interface Nudge {
  type: 'weather' | 'demand'
  date: string
  message: string
}

export interface EstimatedOutlookDay {
  date: string
  estimated_demand: number
  weather: string | null
  precipitation_pct: number | null
  rain_risk: boolean | null
  is_estimated: true
}

export interface NodeData {
  label: string
  description: string
  data_source: NodeDataSource
  summary: NodeSummary
  weather_strip: WeatherStripDay[]
  demand_forecast: DemandForecastPoint[]
  weekly_pacing: WeeklyPacingPoint[]
  nudges: Nudge[]
  weather_data_is_stale: boolean
  feature_cols: string[]
  estimated_outlook: EstimatedOutlookDay[]
}

export interface DashboardAggregate {
  node_count: number
  opportunity_gap_visitors: number
  opportunity_gap_yen: number
  /** e.g. { tojinbo: 0.1234, fukui_station: 0.0876, ... } — weather-lift R² per node. */
  seasonal_weather_sensitivity_ratio: Partial<Record<NodeKey, number>>
}

export interface DashboardData {
  generated_at: string
  aggregate: DashboardAggregate
  /** A node key can be absent entirely if the pipeline had no usable data for it. */
  nodes: Partial<Record<NodeKey, NodeData>>
}