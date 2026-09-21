import { useCallback, useEffect, useState } from 'react'

import {
  api,
  type BarResponse,
  type EventsResponse,
  type FiltersResponse,
  type HistoryResponse,
  type KpovItem,
  type QuadrantResponse,
} from './api/client'
import { VIEW_LABELS } from './constants'
import { DeviationPanel } from './components/DeviationPanel'
import { ImportDialog } from './components/ImportDialog'
import { KpovList } from './components/KpovList'
import { LevelBarChart } from './components/LevelBarChart'
import { LevelTimeline } from './components/LevelTimeline'
import { MultiSelect } from './components/MultiSelect'
import { QuadrantChart } from './components/QuadrantChart'

// 篩選與口徑同步到 URL（spec.md REQ-UI-09）
function readUrl() {
  const params = new URLSearchParams(window.location.search)
  const list = (key: string) => (params.get(key) ? params.get(key)!.split(',').filter(Boolean) : [])
  const view = params.get('view')
  return {
    view: view && view in VIEW_LABELS ? view : 'current',
    stations: list('station'),
    lines: list('line'),
    deviatedOnly: params.get('deviatedOnly') === '1',
  }
}

function writeUrl(state: ReturnType<typeof readUrl>) {
  const params = new URLSearchParams()
  if (state.view !== 'current') params.set('view', state.view)
  if (state.stations.length) params.set('station', state.stations.join(','))
  if (state.lines.length) params.set('line', state.lines.join(','))
  if (state.deviatedOnly) params.set('deviatedOnly', '1')
  const query = params.toString()
  window.history.replaceState(null, '', query ? `?${query}` : window.location.pathname)
}

export default function App() {
  const [state, setState] = useState(readUrl)
  const [filters, setFilters] = useState<FiltersResponse | null>(null)
  const [quadrant, setQuadrant] = useState<QuadrantResponse | null>(null)
  const [bar, setBar] = useState<BarResponse | null>(null)
  const [events, setEvents] = useState<EventsResponse | null>(null)
  const [kpovList, setKpovList] = useState<{ total: number; items: KpovItem[] } | null>(null)
  const [selectedLevel, setSelectedLevel] = useState<number | null>(null)
  const [history, setHistory] = useState<HistoryResponse | null>(null)
  const [showImport, setShowImport] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const station = state.stations.join(',') || undefined
  const line = state.lines.join(',') || undefined

  useEffect(() => {
    writeUrl(state)
  }, [state])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [f, q, b, e] = await Promise.all([
        api.filters(),
        api.quadrant({ view: state.view, station, line }),
        api.bar({ view: state.view, station, line }),
        api.events({ station, line }),
      ])
      setFilters(f)
      setQuadrant(q)
      setBar(b)
      setEvents(e)
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入失敗')
    } finally {
      setLoading(false)
    }
  }, [state.view, station, line])

  useEffect(() => {
    void load()
  }, [load, reloadKey])

  useEffect(() => {
    if (selectedLevel === null) {
      setKpovList(null)
      return
    }
    void api
      .kpov({
        view: state.view,
        station,
        line,
        level: String(selectedLevel),
        deviatedOnly: state.deviatedOnly ? '1' : undefined,
      })
      .then(setKpovList)
      .catch(() => setKpovList(null))
  }, [selectedLevel, state.view, state.deviatedOnly, station, line])

  function openHistory(kpovNo: string, equipmentCode: string) {
    void api.history(kpovNo, equipmentCode).then(setHistory).catch(() => setHistory(null))
  }

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
        <div className="max-w-md rounded-lg border border-slate-200 bg-white p-6 text-center">
          <p className="mb-4 text-slate-700">{error}</p>
          <button
            onClick={() => setShowImport(true)}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
          >
            匯入資料
          </button>
        </div>
        {showImport && (
          <ImportDialog
            onClose={() => setShowImport(false)}
            onImported={() => setReloadKey((k) => k + 1)}
          />
        )}
      </div>
    )
  }

  const inheritance = quadrant?.lineInheritance

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-6 py-4">
          <h1 className="text-xl font-semibold">品質管控力</h1>

          <div className="ml-auto flex items-center gap-2">
            <span className="text-xs text-slate-500">口徑</span>
            <div className="flex rounded-md border border-slate-300 p-0.5">
              {Object.entries(VIEW_LABELS).map(([value, label]) => (
                <button
                  key={value}
                  onClick={() => setState((s) => ({ ...s, view: value }))}
                  className={`rounded px-3 py-1 text-sm transition ${
                    state.view === value ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <button
              onClick={() => setShowImport(true)}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 transition hover:border-slate-400 hover:bg-slate-50"
            >
              匯入資料
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-6">
        {loading && !quadrant ? (
          <div className="py-20 text-center text-slate-500">載入中…</div>
        ) : (
          <>
            <section className="grid gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
              <div className="rounded-lg border border-slate-200 bg-white p-4">
                {quadrant && (
                  <QuadrantChart
                    scope={quadrant.scope}
                    plant={quadrant.plant}
                    baseline={quadrant.baseline}
                    filtered={quadrant.filtered}
                    view={quadrant.view}
                    onSelect={(level) => setSelectedLevel(level)}
                  />
                )}
              </div>
              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <DeviationPanel data={events} onSelect={openHistory} />
              </div>
            </section>

            <section className="mt-6 rounded-lg border border-slate-200 bg-white p-4">
              <div className="flex flex-wrap items-end gap-4">
                <MultiSelect
                  label="CTP 站別"
                  options={(filters?.stations ?? []).map((s) => ({
                    value: s.code,
                    label: s.code,
                    hint: `${s.kpovCount}`,
                  }))}
                  selected={state.stations}
                  onChange={(next) => setState((s) => ({ ...s, stations: next }))}
                />
                <MultiSelect
                  label="線別"
                  options={(filters?.lines ?? []).map((l) => ({ value: l.code, label: l.label }))}
                  selected={state.lines}
                  onChange={(next) => setState((s) => ({ ...s, lines: next }))}
                />
                {(state.stations.length > 0 || state.lines.length > 0) && (
                  <button
                    onClick={() => setState((s) => ({ ...s, stations: [], lines: [] }))}
                    className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
                  >
                    清除篩選
                  </button>
                )}
              </div>

              {/* D-01 / REQ-LINE-03：線別無自有 KPOV 時標註繼承來源 */}
              {inheritance?.inherited && (
                <div className="mt-3 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-800">
                  {state.lines.join('、')} 的 KPOV 定義繼承自 {inheritance.inheritedFrom}
                </div>
              )}
            </section>

            <section className="mt-6 rounded-lg border border-slate-200 bg-white p-4">
              <h2 className="mb-3 text-base font-semibold text-slate-800">
                Level 0~3 KPOV 數量
                <span className="ml-2 text-sm font-normal text-slate-500">
                  （{VIEW_LABELS[state.view]}口徑）
                </span>
              </h2>
              {bar && <LevelBarChart data={bar} view={state.view} onSelect={setSelectedLevel} />}
            </section>
          </>
        )}
      </main>

      <footer className="mx-auto max-w-7xl px-6 pb-8 text-xs text-slate-400">
        {filters?.batch && (
          <>
            資料批次：{filters.batch.filename} · 匯入於{' '}
            {filters.batch.importedAt?.slice(0, 19).replace('T', ' ')}
          </>
        )}
      </footer>

      {/* 象限 / 柱狀圖下鑽面板 */}
      {selectedLevel !== null && (
        <aside className="fixed inset-y-0 right-0 z-40 w-full max-w-2xl overflow-y-auto border-l border-slate-200 bg-white p-6 shadow-2xl">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">Level {selectedLevel} KPOV 明細</h2>
            <button
              onClick={() => setSelectedLevel(null)}
              className="text-slate-400 hover:text-slate-700"
              aria-label="關閉"
            >
              ✕
            </button>
          </div>
          {kpovList ? (
            <KpovList
              items={kpovList.items}
              total={kpovList.total}
              deviatedOnly={state.deviatedOnly}
              onToggleDeviated={(value) => setState((s) => ({ ...s, deviatedOnly: value }))}
              onSelect={openHistory}
            />
          ) : (
            <p className="text-sm text-slate-500">載入中…</p>
          )}
        </aside>
      )}

      {/* 等級歷程時間軸 */}
      {history && (
        <aside className="fixed inset-y-0 right-0 z-50 w-full max-w-xl overflow-y-auto border-l border-slate-200 bg-white p-6 shadow-2xl">
          <div className="mb-4 flex justify-end">
            <button
              onClick={() => setHistory(null)}
              className="text-slate-400 hover:text-slate-700"
              aria-label="關閉"
            >
              ✕
            </button>
          </div>
          <LevelTimeline data={history} />
        </aside>
      )}

      {showImport && (
        <ImportDialog onClose={() => setShowImport(false)} onImported={() => setReloadKey((k) => k + 1)} />
      )}
    </div>
  )
}
