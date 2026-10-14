import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { AppShell } from '../components/AppShell'

import {
  api,
  type CheckMonitorResponse,
  type ChangeKind,
  type ComplaintSummary,
  type ProcessSummary,
  type ChangeWindow,
  type LevelChangesResponse,
  type FiltersResponse,
  type HistoryResponse,
  type KpovItem,
  type QuadrantResponse,
  type TrendResponse,
} from '../api/client'
import { VIEW_LABELS } from '../constants'
import { HOTSPOTS } from '../layoutConfig'
import { CheckMonitorTable } from '../components/CheckMonitorTable'
import { DeviationPanel } from '../components/DeviationPanel'
import { ImportDialog } from '../components/ImportDialog'
import { KpovList } from '../components/KpovList'
import { LevelCountBar } from '../components/LevelCountBar'
import { LevelTallyBar } from '../components/LevelTallyBar'
import { MeasureTable } from '../components/MeasureTable'
import { LayoutMap } from '../components/LayoutMap'
import { StationRiskMap } from '../components/StationRiskMap'
import { LevelTimeline } from '../components/LevelTimeline'
import { MultiSelect } from '../components/MultiSelect'
import { QuadrantChart } from '../components/QuadrantChart'
import { TrendChart } from '../components/TrendChart'

const ATTRIBUTE_LABELS: Record<string, string> = { CTP: 'CTP 自動站', OP: 'OP 人工站' }

// 天／週／月／年＝近 1／7／30／365 天：影響象限圖（只算期間內有維修或客訴的 KPOV）、
// 客訴／製程問題追蹤、等級異動總覽與站別風險地圖
const WINDOWS: { value: ChangeWindow; label: string; hint: string }[] = [
  { value: 'day', label: '天', hint: '近 1 天' },
  { value: 'week', label: '週', hint: '近 7 天' },
  { value: 'month', label: '月', hint: '近 30 天' },
  { value: 'year', label: '年', hint: '近 365 天' },
]
const DEFAULT_WINDOW: ChangeWindow = 'month'

// 篩選、口徑與 layout 選取全部同步到 URL（spec.md REQ-UI-09）
function readUrl(params: URLSearchParams) {
  const list = (key: string) => (params.get(key) ? params.get(key)!.split(',').filter(Boolean) : [])
  const view = params.get('view')
  const window = params.get('window')
  return {
    window: (WINDOWS.some((w) => w.value === window) ? window : DEFAULT_WINDOW) as ChangeWindow,
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
  if (state.window !== DEFAULT_WINDOW) params.set('window', state.window)
  return params
}

export default function QualityPage() {
  // 由 router 託管網址狀態：直接動 history.replaceState 會讓 router 的 location
  // 與實際網址脫鉤，切到別的路由再回來時會拿到過期的篩選條件。
  const [searchParams, setSearchParams] = useSearchParams()
  const [state, setState] = useState(() => readUrl(searchParams))
  const [filters, setFilters] = useState<FiltersResponse | null>(null)
  const [quadrant, setQuadrant] = useState<QuadrantResponse | null>(null)
  // 等級異動總覽：時間區間 × 惡化／已改善 × 頁碼（後端分頁，每頁 10 筆）
  const [changes, setChanges] = useState<LevelChangesResponse | null>(null)
  const changeWindow = state.window
  const [changeKind, setChangeKind] = useState<ChangeKind>('escalated')
  const [changePage, setChangePage] = useState(1)
  const [checks, setChecks] = useState<CheckMonitorResponse | null>(null)
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
      const [f, q] = await Promise.all([
        api.filters(),
        api.quadrant({ view: state.view, station, line, attribute, window: changeWindow }),
      ])
      setFilters(f)
      setQuadrant(q)
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入失敗')
    } finally {
      setLoading(false)
    }
  }, [state.view, station, line, attribute, changeWindow])

  // 左半邊：客訴問題追蹤（客訴報表）與製程問題追蹤（修護報表），吃上方篩選器，各自後端分頁
  const [complaints, setComplaints] = useState<ComplaintSummary | null>(null)
  const [complaintPage, setComplaintPage] = useState(1)
  const [processRows, setProcessRows] = useState<ProcessSummary | null>(null)
  const [processPage, setProcessPage] = useState(1)

  useEffect(() => {
    api
      .complaintSummary({ station, line, attribute, page: complaintPage, window: changeWindow })
      .then(setComplaints)
      .catch(() => setComplaints(null))
  }, [station, line, attribute, complaintPage, changeWindow, reloadKey])

  useEffect(() => {
    api
      .processSummary({ station, line, attribute, page: processPage, window: changeWindow })
      .then(setProcessRows)
      .catch(() => setProcessRows(null))
  }, [station, line, attribute, processPage, changeWindow, reloadKey])

  useEffect(() => {
    setComplaintPage(1)
    setProcessPage(1)
  }, [station, line, attribute, changeWindow])

  const loadChanges = useCallback(async () => {
    try {
      setChanges(
        await api.levelChanges({ station, line, attribute, window: changeWindow, kind: changeKind, page: changePage }),
      )
    } catch {
      setChanges(null)
    }
  }, [station, line, attribute, changeWindow, changeKind, changePage])

  useEffect(() => {
    void loadChanges()
  }, [loadChanges, reloadKey])

  // 篩選範圍或期間變了，回到第 1 頁
  useEffect(() => setChangePage(1), [station, line, attribute, changeWindow])

  // 下半部（趨勢 + 點檢監控）吃 layout 選取；未選時沿用上方篩選範圍
  const bottomScope = useMemo(
    () => (state.target ? { target: state.target } : { station, line, attribute }),
    [state.target, station, line, attribute],
  )

  const loadBottom = useCallback(async () => {
    try {
      setTrend(await api.trend(bottomScope))
    } catch {
      setTrend(null)
    }
  }, [bottomScope])

  const loadChecks = useCallback(async () => {
    try {
      setChecks(await api.checkMonitor(bottomScope))
    } catch {
      setChecks(null)
    }
  }, [bottomScope])

  useEffect(() => {
    void loadTop()
  }, [loadTop, reloadKey])

  useEffect(() => {
    void loadBottom()
  }, [loadBottom, reloadKey])

  // 點檢狀況會隨 AR 點檢與時間（逾期）變化，每分鐘重抓
  useEffect(() => {
    void loadChecks()
    const timer = window.setInterval(() => void loadChecks(), 60_000)
    return () => window.clearInterval(timer)
  }, [loadChecks, reloadKey])

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
        window: changeWindow,
      })
      .then(setKpovList)
      .catch(() => setKpovList(null))
  }, [selectedLevel, state.view, state.deviatedOnly, state.target, station, line, attribute, changeWindow])

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
            <div>
              <span className="mb-1 block text-xs font-medium text-slate-500">期間</span>
              <div
                className="inline-flex rounded-md border border-slate-300 bg-white p-0.5"
                role="tablist"
                aria-label="期間"
              >
                {WINDOWS.map((w) => (
                  <button
                    key={w.value}
                    type="button"
                    role="tab"
                    aria-selected={changeWindow === w.value}
                    title={`${w.hint}：象限圖、客訴／製程問題追蹤、等級異動總覽、站別風險地圖`}
                    onClick={() => setState((s) => ({ ...s, window: w.value }))}
                    className={`rounded px-3 py-1.5 text-sm font-medium transition ${
                      changeWindow === w.value ? 'bg-[#0086DB] text-white' : 'text-slate-600 hover:bg-slate-100'
                    }`}
                  >
                    {w.label}
                  </button>
                ))}
              </div>
            </div>
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
              {quadrant && (
                <LevelCountBar
                  counts={quadrant.scope}
                  onSelect={setSelectedLevel}
                  caption={`${WINDOWS.find((w) => w.value === changeWindow)?.hint}有維修或客訴的 KPOV`}
                />
              )}

              <div className="mt-5 space-y-4 border-t border-slate-100 pt-4">
                <LevelTallyBar
                  title="Level 3 – Level 0 客訴筆數"
                  series={[{ label: '客訴筆數', counts: complaints?.levelCounts ?? {} }]}
                  total={complaints?.levelCounts.total ?? 0}
                />
                <MeasureTable
                  title="客訴問題追蹤"
                  data={complaints}
                  onPageChange={setComplaintPage}
                  onSelect={openHistory}
                  emptyText="此範圍沒有客訴"
                  storageKey="qcm.tracking.complaints"
                />
              </div>

              <div className="mt-5 space-y-4 border-t border-slate-100 pt-4">
                <LevelTallyBar
                  title="Level 3 – Level 0 維修筆數（依 KPOV 現況等級）"
                  series={[{ label: '現況', counts: processRows?.levelCounts.current ?? {} }]}
                  total={processRows?.levelCounts.total ?? 0}
                />
                <MeasureTable
                  title="製程問題追蹤（修護報表）"
                  data={processRows}
                  onPageChange={setProcessPage}
                  onSelect={openHistory}
                  emptyText="此範圍沒有維修紀錄"
                  storageKey="qcm.tracking.process"
                />
              </div>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <DeviationPanel
                data={changes}
                window={changeWindow}
                kind={changeKind}
                onKindChange={(k) => {
                  setChangeKind(k)
                  setChangePage(1)
                }}
                onPageChange={setChangePage}
                onSelect={openHistory}
              />
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
          <StationRiskMap
            window={changeWindow}
            selected={state.target}
            onSelect={(target) => setState((s) => ({ ...s, target }))}
            reloadKey={reloadKey}
          />
        </section>

        {/* ── 下層：趨勢折線圖 + Level 3 點檢監控 ── */}
        <section className="grid gap-6 lg:grid-cols-2">
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            {trend && <TrendChart data={trend} scopeLabel={scopeLabel} />}
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <CheckMonitorTable data={checks} scopeLabel={scopeLabel} onChanged={() => void loadChecks()} />
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
