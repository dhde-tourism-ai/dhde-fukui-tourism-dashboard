import { useState } from 'react';
import { useDashboardData } from './hooks/useDashboardData';
import type { NodeKey } from './types/dashboard';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend
} from 'recharts';

function fmtNum(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  return Math.round(n).toLocaleString('en-US');
}

function fmtShortDate(dateStr: any): string {
  if (!dateStr || typeof dateStr !== 'string') return String(dateStr ?? '');
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return dateStr;
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
}

function badgeLabel(b: string): string {
  const map: Record<string, string> = { HOT: 'Superb', OK: 'Strong', WARN: 'Warning', CRIT: 'Critical' };
  return map[b] || b;
}

export default function App() {
  const hookResult = useDashboardData();
  // Support either isLoading or loading property names
  const isLoading = 'isLoading' in hookResult ? (hookResult as any).isLoading : (hookResult as any).loading;
  const { data, error } = hookResult as any;

  const [selectedNode, setSelectedNode] = useState<NodeKey | 'all'>('all');

  if (isLoading) {
    return (
      <div style={{ padding: '4rem', textAlign: 'center', color: '#0F2B46' }}>
        <p style={{ fontFamily: 'Shippori Mincho, serif', fontSize: '1.4rem' }}>
          Loading Fukui Tourism Analytics System...
        </p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div style={{ padding: '4rem', textAlign: 'center', color: '#9C2E2E' }}>
        <p>Could not load data/dashboard_data.json — make sure this file is served alongside index.html.</p>
        <p style={{ fontSize: '0.8rem', color: '#4A5C6A' }}>
          {error instanceof Error ? error.message : String(error || 'Unknown error')}
        </p>
      </div>
    );
  }

  const nodes = data.nodes || {};
  const activeNodeKey = selectedNode !== 'all' ? (selectedNode as NodeKey) : undefined;
  const activeNodeData = activeNodeKey ? nodes[activeNodeKey] : undefined;

  // Fallback to Tojinbo or first node if in "all" view to mirror original dashboard defaults
  const defaultNode = nodes['tojinbo' as NodeKey] || Object.values(nodes)[0];
  const summary = activeNodeData?.summary || (data as any).summary || defaultNode?.summary || {};
  const p30 = summary.past_30_day || {};
  const week = summary.this_week_pacing || {};
  const weatherStrip = activeNodeData?.weather_strip || (data as any).weather_strip || defaultNode?.weather_strip || [];
  const demandForecast = activeNodeData?.demand_forecast || (data as any).demand_forecast || defaultNode?.demand_forecast || [];
  const estimatedOutlook = activeNodeData?.estimated_outlook || (data as any).estimated_outlook || defaultNode?.estimated_outlook || [];
  const pacingRows = activeNodeData?.weekly_pacing || (data as any).weekly_pacing || defaultNode?.weekly_pacing || [];
  const nudges = activeNodeData?.nudges || (data as any).nudges || defaultNode?.nudges || [];

  const yoy = p30.yoy_pct;
  const yoyUp = yoy !== null && yoy !== undefined && yoy >= 0;
  const yoyText = yoy === null || yoy === undefined ? '—' : (yoyUp ? '+' : '') + yoy + '%';

  return (
    <>
      {/* HEADER */}
      <header className="hero">
        <div className="grain"></div>
        <div style={{ maxWidth: '1180px', margin: '0 auto', padding: '2.4rem 1.5rem 2.8rem', position: 'relative' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
            <div>
              <div className="eyebrow">福井県観光データ分析システム · Fukui Tourism Analytics System</div>
              <h1 className="font-display" style={{ fontSize: '2.1rem', margin: '.5rem 0 .3rem', color: 'var(--washi)' }}>
                FTAS Executive Dashboard
              </h1>
              <p style={{ color: 'rgba(247,243,234,0.75)', fontSize: '.92rem', maxWidth: '36rem', margin: 0 }}>
                Operational demand intelligence for DMOs, hotel operators, and municipal planners across the Reihoku and Reinan corridors.
              </p>
            </div>
            <div style={{ textAlign: 'right' }}>
              <span className="status-pill">
                <span className="status-dot"></span> Live pipeline
              </span>
              <div style={{ marginTop: '.6rem', fontSize: '.72rem', color: 'rgba(247,243,234,0.55)', fontFamily: 'JetBrains Mono, monospace' }}>
                {data.generated_at ? 'Generated ' + new Date(data.generated_at).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' }) : ''}
              </div>
            </div>
          </div>

          {/* Node Switcher */}
          <div className="node-bar">
            <button
              className={`node-btn ${selectedNode === 'all' ? 'active' : ''}`}
              onClick={() => setSelectedNode('all')}
            >
              All Nodes Overview
            </button>
            {(Object.keys(nodes) as NodeKey[]).map((key) => {
              const n = nodes[key];
              if (!n) return null;
              return (
                <button
                  key={key}
                  className={`node-btn ${selectedNode === key ? 'active' : ''}`}
                  onClick={() => setSelectedNode(key)}
                >
                  {n.label}
                </button>
              );
            })}
          </div>
        </div>

        <svg className="wave-divider" viewBox="0 0 1200 28" preserveAspectRatio="none">
          <path d="M0,14 C150,28 350,0 600,14 C850,28 1050,0 1200,14 L1200,28 L0,28 Z" fill="#F7F3EA"/>
        </svg>
      </header>

      {/* SECTION 1 — Executive Summary */}
      <section className="panel">
        <div className="section-head">
          <div>
            <div className="section-title">
              {activeNodeData ? `${activeNodeData.label} — Executive Summary` : 'Executive Summary'}
            </div>
          </div>
          <div className="section-sub">
            {activeNodeData ? activeNodeData.description : ''}
          </div>
        </div>

        {/* Aggregate macro indicators when in Overview */}
        {selectedNode === 'all' && data.aggregate && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '1rem', marginBottom: '1.4rem' }}>
            <div className="kpi-card" style={{ border: '1px solid var(--hairline)', borderRadius: '6px' }}>
              <div className="kpi-label">Annual Opportunity Gap (¥)</div>
              <div className="kpi-value" style={{ color: 'var(--torii)' }}>
                ¥{fmtNum(data.aggregate.opportunity_gap_yen)}
              </div>
              <div className="kpi-delta" style={{ color: 'var(--ink-soft)' }}>weather-induced demand deficit</div>
            </div>
            <div className="kpi-card" style={{ border: '1px solid var(--hairline)', borderRadius: '6px' }}>
              <div className="kpi-label">Opportunity Gap (visitors)</div>
              <div className="kpi-value">
                {fmtNum(data.aggregate.opportunity_gap_visitors)}
              </div>
              <div className="kpi-delta" style={{ color: 'var(--ink-soft)' }}>annual deficit across active nodes</div>
            </div>
          </div>
        )}

        <div className="kpi-grid">
          <div className="kpi-card">
            <div className="kpi-label">Past 30 Days</div>
            <div className="kpi-value">{fmtNum(p30.current_total)}</div>
            <div className={`kpi-delta ${yoyUp ? 'up' : 'down'}`}>{yoyText} YoY</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">Same Period Last Year</div>
            <div className="kpi-value">{fmtNum(p30.previous_year_total)}</div>
            <div className="kpi-delta" style={{ color: 'var(--ink-soft)' }}>baseline</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">Net Difference</div>
            <div className="kpi-value">{p30.diff !== undefined && p30.diff >= 0 ? '+' : ''}{fmtNum(p30.diff)}</div>
            <div className="kpi-delta" style={{ color: 'var(--ink-soft)' }}>visitors vs. last year</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">This Week Pacing</div>
            <div className="kpi-value" style={{ fontSize: '1.35rem' }}>
              {week.rate !== undefined ? (week.rate * 100).toFixed(0) + '%' : '—'}
            </div>
            <div style={{ margin: '.5rem 0 0 0' }}>
              {week.badge && <span className={`badge badge-${week.badge}`}>{badgeLabel(week.badge)}</span>}
            </div>
          </div>
        </div>
      </section>

      {/* SECTION 2 — Weather Strip */}
      <section className="panel" style={{ paddingTop: 0 }}>
        <div className="section-head">
          <div>
            <div className="section-title">14-Day Weather &amp; Pacing Strip</div>
          </div>
          <div className="section-sub">Rain risk ≥ 40% outlined in vermillion</div>
        </div>
        <div className="weather-scroll">
          {weatherStrip.length === 0 ? (
            <p style={{ color: 'var(--ink-soft)', fontSize: '.85rem' }}>Weather forecast unavailable.</p>
          ) : (
            weatherStrip.map((d: any, i: number) => (
              <div key={i} className={`weather-day ${d.rain_risk ? 'rain-risk' : ''}`}>
                <div className="weather-date">{fmtShortDate(d.date)}</div>
                <div className="weather-desc">{d.weather || '—'}</div>
                <div className={`weather-pop ${d.rain_risk ? 'risk' : 'safe'}`}>
                  {d.precipitation_pct !== null && d.precipitation_pct !== undefined ? `${d.precipitation_pct}%` : '—'}
                </div>
              </div>
            ))
          )}
        </div>
      </section>

      {/* SECTION 3 — Demand Forecast */}
      <section className="panel" style={{ paddingTop: 0 }}>
        <div className="section-head">
          <div>
            <div className="section-title">Actual vs. Model Forecast</div>
          </div>
          <div className="section-sub">
            Last 60 days · Random Forest {selectedNode === ('fukui_station' as NodeKey) ? '(with Hotel Reservation Lags)' : ''}
          </div>
        </div>
        <div className="chart-card">
          <div style={{ width: '100%', height: 320 }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={demandForecast} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorActual" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#0F2B46" stopOpacity={0.12}/>
                    <stop offset="95%" stopColor="#0F2B46" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,43,70,0.06)" />
                <XAxis
                  dataKey="date"
                  tick={{ fontFamily: 'JetBrains Mono', fontSize: 10 }}
                  tickFormatter={fmtShortDate}
                />
                <YAxis
                  tick={{ fontFamily: 'JetBrains Mono', fontSize: 10 }}
                  tickFormatter={(val: any) => Number(val).toLocaleString('en-US')}
                />
                <Tooltip
                  formatter={(val: any) => [Number(val).toLocaleString('en-US'), '']}
                  labelFormatter={fmtShortDate}
                  contentStyle={{ backgroundColor: 'var(--washi-card)', borderColor: 'var(--hairline)' }}
                />
                <Legend wrapperStyle={{ fontFamily: 'Inter', fontSize: 12, paddingTop: 10 }} />
                <Area
                  type="monotone"
                  dataKey="actual"
                  name="Actual Visitors"
                  stroke="#0F2B46"
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#colorActual)"
                />
                <Line
                  type="monotone"
                  dataKey="forecast"
                  name="Model Forecast"
                  stroke="#B5432E"
                  strokeWidth={2}
                  strokeDasharray="4 3"
                  dot={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>

      {/* SECTION 3B — Estimated Outlook */}
      {estimatedOutlook.length > 0 && (
        <section className="panel" style={{ paddingTop: 0 }}>
          <div className="section-head">
            <div>
              <div className="section-title">Near-Term Outlook (Estimated)</div>
            </div>
            <div className="section-sub">Based on live weather forecast</div>
          </div>
          <div className="outlook-banner">
            ⚠️ The local historical weather telemetry is catching up, so these days are an approximate estimate built from the live weather forecast and recent averages — not a full model-quality prediction. Treat as directional only.
          </div>
          <div className="outlook-scroll">
            {estimatedOutlook.map((d: any, i: number) => (
              <div key={i} className="outlook-day">
                <div className="outlook-date">{fmtShortDate(d.date)}</div>
                <div className="outlook-desc">{d.weather || '—'}</div>
                <div className="outlook-value">{fmtNum(d.estimated_demand)}</div>
                <div className="outlook-tag">Estimated</div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* SECTION 4 — Weekly Pacing Table */}
      <section className="panel" style={{ paddingTop: 0 }}>
        <div className="section-head">
          <div>
            <div className="section-title">Day-by-Day Pacing</div>
          </div>
          <div className="section-sub">Achievement rate = actual ÷ forecast</div>
        </div>
        <div className="chart-card" style={{ padding: 0, overflowX: 'auto' }}>
          <table className="pacing">
            <thead>
              <tr>
                <th>Date</th>
                <th>Actual</th>
                <th>Forecast</th>
                <th>Rate</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {pacingRows.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ color: 'var(--ink-soft)', fontFamily: 'Inter' }}>
                    No pacing data available.
                  </td>
                </tr>
              ) : (
                pacingRows.slice().reverse().map((r: any, i: number) => (
                  <tr key={i}>
                    <td>{r.date}</td>
                    <td>{fmtNum(r.actual)}</td>
                    <td>{fmtNum(r.forecast)}</td>
                    <td>{r.rate !== undefined ? `${(r.rate * 100).toFixed(0)}%` : '—'}</td>
                    <td>{r.badge && <span className={`badge badge-${r.badge}`}>{badgeLabel(r.badge)}</span>}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* SECTION 5 — Nudges */}
      <section className="panel" style={{ paddingTop: 0 }}>
        <div className="section-head">
          <div>
            <div className="section-title">Governance &amp; Vendor Nudges</div>
          </div>
        </div>
        {nudges.length === 0 ? (
          <div style={{ color: 'var(--ink-soft)', fontSize: '.86rem' }}>
            No active recommendations — pacing and weather are within normal range.
          </div>
        ) : (
          nudges.map((n: any, i: number) => (
            <div key={i} className={`nudge-card ${n.type}`}>
              <div className="nudge-type">
                {n.type === 'weather' ? 'Weather Risk' : 'Demand Signal'} · {n.date}
              </div>
              <div>{n.message}</div>
            </div>
          ))
        )}
      </section>

      {/* SECTION 6 — Export Hub */}
      <section className="panel" id="export-hub" style={{ paddingTop: 0 }}>
        <div className="section-head">
          <div>
            <div className="section-title">Report Export Hub</div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '.8rem', flexWrap: 'wrap' }}>
          <button className="export-btn" onClick={() => window.print()}>
            ↓ Export PDF Summary
          </button>
        </div>
      </section>

      <footer className="site">
        Fukui Tourism Analytics System — Distributed Human Data Engine · React 18 Migration
      </footer>
    </>
  );
}