import { useCallback, useEffect, useState } from 'react'
import type { DashboardData } from '../types/dashboard'

interface UseDashboardDataResult {
  data: DashboardData | null
  isLoading: boolean
  error: Error | null
  refetch: () => void
}

// import.meta.env.BASE_URL resolves to '/' in dev and to whatever `base` is
// set to in the production build — since vite.config.ts's publicDir points
// at the same repo-root public/ the Python pipeline writes to, this exact
// path resolves correctly in both dev and build without any manual
// dev/prod branching.
const DASHBOARD_DATA_PATH = `${import.meta.env.BASE_URL}data/dashboard_data.json`

export function useDashboardData(): UseDashboardDataResult {
  const [data, setData] = useState<DashboardData | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const [reloadToken, setReloadToken] = useState(0)

  const refetch = useCallback(() => setReloadToken((t) => t + 1), [])

  useEffect(() => {
    const controller = new AbortController()

    async function load() {
      setIsLoading(true)
      setError(null)
      try {
        // Dev-only cache-bust: the pipeline overwrites dashboard_data.json
        // in place, and a plain fetch() of a stable URL can otherwise
        // return a stale browser-cached copy while iterating locally.
        const url = import.meta.env.DEV
          ? `${DASHBOARD_DATA_PATH}?t=${Date.now()}`
          : DASHBOARD_DATA_PATH

        const res = await fetch(url, { signal: controller.signal })
        if (!res.ok) {
          throw new Error(`Failed to load dashboard data: ${res.status} ${res.statusText}`)
        }
        const json = (await res.json()) as DashboardData
        setData(json)
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return
        setError(err instanceof Error ? err : new Error('Unknown error loading dashboard data'))
      } finally {
        setIsLoading(false)
      }
    }

    void load()
    return () => controller.abort()
  }, [reloadToken])

  return { data, isLoading, error, refetch }
}