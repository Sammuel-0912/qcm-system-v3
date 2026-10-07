import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { AppShell } from '../components/AppShell'

import {
  api,
  type BarResponse,
  type EventsResponse,
  type FiltersResponse,
  type HistoryResponse,
  type KpovItem,
  type QuadrantResponse,
  type TrendResponse,
} from '../api/client'
import { VIEW_LABELS } from '../constants'
import { HOTSPOTS } from '../layoutConfig'
import { DeviationPanel } from '../components/DeviationPanel'
import { ImportDialog } from '../components/ImportDialog'
import { KpovList } from '../components/KpovList'
import { LayoutMap } from '../components/LayoutMap'
import { LevelBarChart } from '../components/LevelBarChart'
import { LevelTimeline } from '../components/LevelTimeline'
import { MultiSelect } from '../components/MultiSelect'
import { QuadrantChart } from '../components/QuadrantChart'
import { TrendChart } from '../components/TrendChart'

const ATTRIBUTE_LABELS: Record<string, string> = { CTP: 'CTP 自動站', OP: 'OP 人工站' }

// 篩選、口徑與 layout 選取全部同步到 URL（spec.md REQ-UI-09）
function readUrl(params: URLSearchParams) {
  const list = (key: string) => (params.get(key) ? params.get(key)!.split(',').filter(Boolean) : [])
  const view = params.get('view')
  return {
    view: view && view in VIEW_LABELS ? view : 'current',
    attributes: list('attribute'),
    stations: list('station'),
    lines: list('line'),
    deviatedOnly: params.get('deviatedOnly') === '1',
    target: params.get('target') || null,
  }
}

function toParams(state: ReturnType<typeof readUrl>): URLSearchParams {
  const params = new URLSearchParams()
  if (state.view !== 'current') params.set('view', state.view)
  if (state.attributes.length) params.set('attribute', state.attributes.join(','))
  if (state.stations.length) params.set('station', state.stations.join(','))
  if (state.lines.length) params.set('line', state.lines.join(','))
  if (state.deviatedOnly) params.set('deviatedOnly', '1')
  if (state.target) params.set('target', state.target)
  return params
}

export default function QualityPage() {
  // 由 router 託管網址狀態：直接動 history.replaceState 會讓 router 的 location
  // 與實際網址脫鉤，切到別的路由再回來時會拿到過期的篩選條件。
  const [searchParams, setSearchParams] = useSearchParams()
  const [state, setState] = useState(() => readUrl(searchParams))
  const [filters, setFilters] = useState<FiltersResponse | null>(null)
  const [quadrant, setQuadrant] = useState<QuadrantResponse | null>(null)
  const [events, setEvents] = useState<EventsResponse | null>(null)
  const [bar, setBar] = useState<BarResponse | null>(null)
  const [trend, setTrend] = useState<TrendResponse | null>(null)
  const [selectedLevel, setSelectedLevel] = useState<number | null>(null)
  const [kpovList, setKpovList] = useState<{ total: number; items: KpovItem[] } | null>(null)
  const [history, setHistory] = useState<HistoryResponse | null>(null)
  const [showImport, setShowImport] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const attribute = state.attributes.join(',') || undefined
  const station = state.stations.join(',') || undefined
  const line = state.lines.join(',') || undefined

  useEffect(() => {
    setSearchParams(toParams(state), { replace: true })
    // setSearchParams 的識別在每次 render 都會變，列入相依會造成無限迴圈
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state])

  // 上半部（象限圖 + 異動總覽）吃篩選器
  const loadTop = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [f, q, e] = await Promise.all([
        api.filters(),
        api.quadrant({ view: state.view, station, line, attribute }),
        api.events({ station, line, attribute }),
      ])
      setFilters(f)
      setQuadrant(q)
      setEvents(e)
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入失敗')
    } finally {
      setLoading(false)
    }
  }, [state.view, station, line, attribute])

  // 下半部（趨勢 + 現狀）吃 layout 選取；未選時沿用上方篩選範圍
  const loadBottom = useCallback(async () => {
    const scope = state.target
      ? { target: state.target }
      : { station, line, attribute }
    try {
      const [b, t] = await Promise.all([
        api.bar({ view: state.view, ...scope }),
        api.trend(scope),
      ])
      setBar(b)
      setTrend(t)
    } catch {
      setBar(null)
      setTrend(null)
    }
  }, [state.target, state.view, station, line, attribute])

  useEffect(() => {
    void loadTop()
  }, [loadTop, reloadKey])

  useEffect(() => {
    void loadBottom()
  }, [loadBottom, reloadKey])

  useEffect(() => {
    if (selectedLevel === null) {
      setKpovList(null)
      return
    }
    const scope = state.target ? { target: state.target } : { station, line, attribute }
    void api
      .kpov({
        view: state.view,
        ...scope,
        level: String(selectedLevel),
        deviatedOnly: state.deviatedOnly ? '1' : undefined,
      })
      .then(setKpovList)
      .catch(() => setKpovList(null))
  }, [selectedLevel, state.view, state.deviatedOnly, state.target, station, line, attribute])

  const worstLevels = useMemo(() => {
    const map: Record<string, number | null> = {}
    for (const s of filters?.stations ?? []) map[s.targetId] = s.worstLevel
    return map
  }, [filters])

  const selectedHotspot = HOTSPOTS.find((h) => h.targetId === state.target)
  const scopeLabel = selectedHotspot
    ? selectedHotspot.displayName
    : state.stations.length || state.lines.length || state.attributes.length
      ? '目前篩選範圍'
      : '全線'

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
          <ImportDialog onClose={() => setShowImport(false)} onImported={() => setReloadKey((k) => k + 1)} />
        )}
      </div>
    )
  }

  const inheritance = quadrant?.lineInheritance

  const headerActions = (
    <>
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
    </>
  )

  return (
    <AppShell title="WJ1 DCS 品控力風險智控平台" actions={headerActions}>

      <main className="mx-auto max-w-7xl space-y-6 px-6 py-6">
        {/* ── 頂部：篩選器（只影響象限圖與異動總覽） ── */}
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex flex-wrap items-end gap-4">
            <MultiSelect
              label="線別"
              options={(filters?.lines ?? []).map((l) => ({ value: l.code, label: l.label }))}
              selected={state.lines}
              onChange={(next) => setState((s) => ({ ...s, lines: next }))}
            />
            <MultiSelect
              label="屬性"
              options={(filters?.attributes ?? []).map((a) => ({
                value: a,
                label: ATTRIBUTE_LABELS[a] ?? a,
              }))}
              selected={state.attributes}
              onChange={(next) => setState((s) => ({ ...s, attributes: next }))}
            />
            <MultiSelect
              label="站別"
              options={(filters?.stations ?? []).map((s) => ({
                value: s.code,
                label: s.code,
                hint: `${s.attribute} · ${s.kpovCount}`,
              }))}
              selected={state.stations}
              onChange={(next) => setState((s) => ({ ...s, stations: next }))}
            />
            {(state.stations.length > 0 || state.lines.length > 0 || state.attributes.length > 0) && (
              <button
                onClick={() => setState((s) => ({ ...s, stations: [], lines: [], attributes: [] }))}
                className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
              >
                清除篩選
              </button>
            )}
          </div>

          {inheritance?.inherited && (
            <div className="mt-3 rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-800">
              {state.lines.join('、')} 的 KPOV 定義繼承自 {inheritance.inheritedFrom}
            </div>
          )}
          {inheritance?.opExemptFromLineFilter && (
            <div className="mt-2 text-xs text-slate-500">OP 人工站沒有設備代碼，不受線別篩選影響。</div>
          )}
        </section>

        {/* ── 上層：象限圖 + 異動總覽 ── */}
        {loading && !quadrant ? (
          <div className="py-20 text-center text-slate-500">載入中…</div>
        ) : (
          <section className="grid gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              {quadrant && (
                <QuadrantChart
                  scope={quadrant.scope}
                  plant={quadrant.plant}
                  baseline={quadrant.baseline}
                  filtered={quadrant.filtered}
                  view={quadrant.view}
                  onSelect={setSelectedLevel}
                />
              )}
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <DeviationPanel data={events} onSelect={openHistory} />
            </div>
          </section>
        )}

        {/* ── 中層：整線 layout（點站點連動下方） ── */}
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <LayoutMap
            selected={state.target}
            onSelect={(target) => setState((s) => ({ ...s, target }))}
            worstLevels={worstLevels}
          />
        </section>

        {/* ── 下層：趨勢折線圖 + 現狀柱狀圖 ── */}
        <section className="grid gap-6 lg:grid-cols-2">
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            {trend && <TrendChart data={trend} scopeLabel={scopeLabel} />}
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="mb-3 text-base font-semibold text-slate-800">
              Level 等級現狀
              <span className="ml-2 text-sm font-normal text-slate-500">
                {scopeLabel} · {VIEW_LABELS[state.view]}口徑
                {bar ? ` · 共 ${bar.total} 項` : ''}
              </span>
            </h2>
            {bar && (
              <LevelBarChart
                data={bar}
                view={state.view}
                onSelect={setSelectedLevel}
                scopeLabel={scopeLabel}
              />
            )}
          </div>
        </section>
      </main>

      <footer className="mx-auto max-w-7xl px-6 pb-8 text-xs text-slate-400">
        {filters?.batch && (
          <>
            資料批次：{filters.batch.filename} · 匯入於{' '}
            {filters.batch.importedAt?.slice(0, 19).replace('T', ' ')}
          </>
        )}
      </footer>

      {selectedLevel !== null && (
        <aside className="fixed inset-y-0 right-0 z-40 w-full max-w-2xl overflow-y-auto border-l border-slate-200 bg-white p-6 shadow-2xl">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">
              Level {selectedLevel} KPOV 明細
              <span className="ml-2 text-sm font-normal text-slate-500">{scopeLabel}</span>
            </h2>
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
    </AppShell>
  )
}
