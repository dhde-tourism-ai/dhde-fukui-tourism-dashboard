import { useMemo, useState } from 'react'
import { useDashboardData } from './hooks/useDashboardData'
import { NODE_ORDER, type NodeKey } from './types/dashboard'

type TabKey = 'overview' | NodeKey

const FALLBACK_LABELS: Record<NodeKey, string> = {
  tojinbo: 'Tojinbo',
  fukui_station: 'Fukui Station',
  katsuyama: 'Katsuyama',
  rainbow_line: 'Rainbow Line',
}

function formatGeneratedAt(iso: string): string {
  try {
    return new Date(iso).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })
  } catch {
    return iso
  }
}

export default function App() {
  const { data, isLoading, error, refetch } = useDashboardData()
  const [activeTab, setActiveTab] = useState<TabKey>('overview')

  const activeNode = activeTab === 'overview' ? null : (data?.nodes[activeTab] ?? null)
  const isStale = activeNode?.weather_data_is_stale ?? false

  const tabs = useMemo<{ key: TabKey; label: string }[]>(
    () => [
      { key: 'overview', label: 'All Nodes Overview' },
      ...NODE_ORDER.map((key) => ({
        key,
        label: data?.nodes[key]?.label ?? FALLBACK_LABELS[key],
      })),
    ],
    [data],
  )

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-300">
        Loading dashboard…
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-950 text-slate-300">
        <p className="text-red-400">{error ? error.message : 'No dashboard data available.'}</p>
        <button
          onClick={refetch}
          className="rounded-md bg-slate-800 px-4 py-2 text-sm font-medium hover:bg-slate-700"
        >
          Retry
        </button>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 px-6 py-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">
              Hokuriku Tourism Governance — Fukui Prefecture DHDE Network
            </h1>
            <p className="text-sm text-slate-400">Generated {formatGeneratedAt(data.generated_at)}</p>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <span
              className={`h-2.5 w-2.5 rounded-full ${isStale ? 'bg-amber-400' : 'bg-emerald-400'}`}
              aria-hidden="true"
            />
            <span className="text-slate-400">
              {activeTab === 'overview'
                ? 'Select a node for freshness detail'
                : isStale
                  ? 'Weather data stale — live forecast fallback active'
                  : 'Weather data fresh'}
            </span>
          </div>
        </div>

        <nav className="mt-4 flex flex-wrap gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                activeTab === tab.key
                  ? 'bg-slate-100 text-slate-900'
                  : 'text-slate-300 hover:bg-slate-800'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </header>

      <main className="grid grid-cols-1 gap-4 p-6 md:grid-cols-2 xl:grid-cols-4">
        <section className="rounded-lg border border-slate-800 bg-slate-900 p-4 xl:col-span-4">
          <h2 className="mb-3 text-sm font-medium text-slate-400">Key Metrics</h2>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <div className="rounded-md bg-slate-950 p-3">
              <p className="text-xs text-slate-500">Opportunity Gap (¥)</p>
              <p className="text-lg font-semibold">
                {data.aggregate.opportunity_gap_yen.toLocaleString()}
              </p>
            </div>
            <div className="rounded-md bg-slate-950 p-3">
              <p className="text-xs text-slate-500">Opportunity Gap (visitors)</p>
              <p className="text-lg font-semibold">
                {data.aggregate.opportunity_gap_visitors.toLocaleString()}
              </p>
            </div>
            <div className="rounded-md bg-slate-950 p-3">
              <p className="text-xs text-slate-500">Nodes Active</p>
              <p className="text-lg font-semibold">{data.aggregate.node_count}</p>
            </div>
            <div className="rounded-md bg-slate-950 p-3">
              <p className="text-xs text-slate-500">
                {activeTab === 'overview' ? 'Selected Node' : 'This Week Pacing'}
              </p>
              <p className="text-lg font-semibold">
                {activeNode ? activeNode.summary.this_week_pacing.label : '—'}
              </p>
            </div>
          </div>
        </section>

        <section className="rounded-lg border border-slate-800 bg-slate-900 p-4 xl:col-span-2">
          <h2 className="mb-2 text-sm font-medium text-slate-400">Demand Forecast</h2>
          <div className="flex h-64 items-center justify-center rounded-md border border-dashed border-slate-800 text-sm text-slate-600">
            Forecast chart goes here
          </div>
        </section>

        <section className="rounded-lg border border-slate-800 bg-slate-900 p-4 xl:col-span-2">
          <h2 className="mb-2 text-sm font-medium text-slate-400">Weekly Pacing</h2>
          <div className="flex h-64 items-center justify-center rounded-md border border-dashed border-slate-800 text-sm text-slate-600">
            Pacing chart goes here
          </div>
        </section>

        <section className="rounded-lg border border-slate-800 bg-slate-900 p-4 xl:col-span-4">
          <h2 className="mb-2 text-sm font-medium text-slate-400">
            Node Telemetry{activeNode ? ` — ${activeNode.label}` : ''}
          </h2>
          <div className="flex h-40 items-center justify-center rounded-md border border-dashed border-slate-800 text-sm text-slate-600">
            {activeTab === 'overview'
              ? 'Select a node tab to view telemetry (nudges, weather strip, hotel signal for Fukui Station, etc.)'
              : 'Node-specific panels go here'}
          </div>
        </section>
      </main>
    </div>
  )
}