import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { formatLocalDateTime } from '../utils/datetime'
import { useAuth } from '../auth/AuthContext'
import { AppShell } from '../components/AppShell'

import {
  api,
  type CheckMonitorResponse,
  type ChangeKind,
  type ChangeWindow,
  type LevelChangesResponse,
  type FiltersResponse,
  type HistoryResponse,
  type KpovItem,
  type QuadrantResponse,
  type TrendResponse,
} from '../api/client'
import { HOTSPOTS } from '../layoutConfig'
import { BroadcastBar } from '../components/BroadcastBar'
import { CheckMonitorTable } from '../components/CheckMonitorTable'
import { DeviationPanel } from '../components/DeviationPanel'
import { ImportDialog } from '../components/ImportDialog'
import { KpovList } from '../components/KpovList'
import { LevelCountBar } from '../components/LevelCountBar'
import { StationLevelChart } from '../components/StationLevelChart'
import { StationRiskMap } from '../components/StationRiskMap'
import { LevelTimeline } from '../components/LevelTimeline'
import { RecordDetailDrawer, type RecordTarget } from '../components/RecordDetailDrawer'
import { MultiSelect } from '../components/MultiSelect'
import { QuadrantChart } from '../components/QuadrantChart'
import { TrendChart } from '../components/TrendChart'

const ATTRIBUTE_LABELS: Record<string, string> = { CTP: 'CTP 自動站', OP: 'OP 人工站' }

// 天／週／月／年＝近 1／7／30／365 天：影響象限圖（全部 KPOV，期初 → 現在）、
// 客訴／製程柱狀圖、等級異動總覽與站別風險地圖
const WINDOWS: { value: ChangeWindow; label: string; hint: string }[] = [
  { value: 'day', label: '天', hint: '近 1 天' },
  { value: 'week', label: '週', hint: '近 7 天' },
  { value: 'month', label: '月', hint: '近 30 天' },
  { value: 'year', label: '年', hint: '近 365 天' },
]
const DEFAULT_WINDOW: ChangeWindow = 'month'

// 象限圖每格顯示全部 KPOV 的「期初（期間第一天）→ 現在」Level 個數；
// 點格子開的 Level 明細依現在的 Level 列出全部 KPOV。不提供口徑切換。
const VIEW = 'current'

// 篩選與 layout 選取全部同步到 URL（spec.md REQ-UI-09）
function readUrl(params: URLSearchParams) {
  const list = (key: string) => (params.get(key) ? params.get(key)!.split(',').filter(Boolean) : [])
  const window = params.get('window')
  return {
    window: (WINDOWS.some((w) => w.value === window) ? window : DEFAULT_WINDOW) as ChangeWindow,
    attributes: list('attribute'),
    stations: list('station'),
    lines: list('line'),
    deviatedOnly: params.get('deviatedOnly') === '1',
    target: params.get('target') || null,
  }
}

function toParams(state: ReturnType<typeof readUrl>): URLSearchParams {
  const params = new URLSearchParams()
  if (state.attributes.length) params.set('attribute', state.attributes.join(','))
  if (state.stations.length) params.set('station', state.stations.join(','))
  if (state.lines.length) params.set('line', state.lines.join(','))
  if (state.deviatedOnly) params.set('deviatedOnly', '1')
  if (state.target) params.set('target', state.target)
  if (state.window !== DEFAULT_WINDOW) params.set('window', state.window)
  return params
}

/** 柱狀圖下方說明：畫不進圖的筆數（未填設備ID、算不出 Level） */
function eventNote(unmapped: number, unknown: number, noun: string): string | undefined {
  const parts = [
    unmapped > 0 ? `${unmapped} 筆${noun}未填設備ID，無法歸到站別` : null,
    unknown > 0 ? `${unknown} 筆${noun}算不出 Level，未畫入圖中` : null,
  ].filter(Boolean)
  return parts.length ? `另有 ${parts.join('；')}` : undefined
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
  // 措施表點列：8D 明細／等級歷程側欄
  const [detail, setDetail] = useState<RecordTarget | null>(null)
  const [showImport, setShowImport] = useState(false)
  const { isAdmin, refresh } = useAuth()
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
        api.quadrant({ view: VIEW, station, line, attribute, window: changeWindow }),
      ])
      setFilters(f)
      setQuadrant(q)
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入失敗')
    } finally {
      setLoading(false)
    }
  }, [station, line, attribute, changeWindow])

  // 左半邊：客訴（客訴報表）與製程（修護報表）站別柱狀圖，吃上方篩選器與期間
  const [stationEvents, setStationEvents] = useState<Awaited<ReturnType<typeof api.stationEventLevels>> | null>(null)
  // layout 下方：各站 KPOV 原始 Level 分佈，全線一覽，不吃篩選與期間
  const [stationKpov, setStationKpov] = useState<Awaited<ReturnType<typeof api.stationKpovLevels>> | null>(null)

  useEffect(() => {
    api
      .stationEventLevels({ station, line, attribute, window: changeWindow })
      .then(setStationEvents)
      .catch(() => setStationEvents(null))
  }, [station, line, attribute, changeWindow, reloadKey])

  useEffect(() => {
    api
      .stationKpovLevels()
      .then(setStationKpov)
      .catch(() => setStationKpov(null))
  }, [reloadKey])

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
        view: VIEW,
        ...scope,
        level: String(selectedLevel),
        deviatedOnly: state.deviatedOnly ? '1' : undefined,
      })
      .then(setKpovList)
      .catch(() => setKpovList(null))
  }, [selectedLevel, state.deviatedOnly, state.target, station, line, attribute])

  const selectedHotspot = HOTSPOTS.find((h) => h.targetId === state.target)
  const scopeLabel = selectedHotspot
    ? selectedHotspot.displayName
    : state.stations.length || state.lines.length || state.attributes.length
      ? '目前篩選範圍'
      : '全線'

  // 匯入完成：更新可看的線別並切到剛匯入的線；同一條線則就地重新載入
  function closeImport(importedDataset?: string) {
    setShowImport(false)
    if (!importedDataset) return
    void refresh(importedDataset).then(() => setReloadKey((k) => k + 1))
  }

  function openHistory(kpovNo: string, equipmentCode: string) {
    void api.history(kpovNo, equipmentCode).then(setHistory).catch(() => setHistory(null))
  }

  if (error) {
    // 包在 AppShell 裡：沒有資料時仍能切換線別、管理使用者、登出
    return (
      <AppShell title="總覽">
        <div className="flex min-h-[60vh] items-center justify-center p-6">
          <div className="max-w-md rounded-lg border border-slate-200 bg-white p-6 text-center">
            <p className="mb-4 text-slate-700">{error}</p>
            {isAdmin ? (
              <button
                onClick={() => setShowImport(true)}
                className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
              >
                匯入資料
              </button>
            ) : (
              <p className="text-sm text-slate-500">請洽廠管理者匯入 Excel。</p>
            )}
          </div>
        </div>
        {showImport && <ImportDialog onClose={closeImport} />}
      </AppShell>
    )
  }

  const inheritance = quadrant?.lineInheritance
  const windowHint = WINDOWS.find((w) => w.value === changeWindow)?.hint ?? ''

  const headerActions = isAdmin && (
    <>
      <button
        onClick={() => setShowImport(true)}
        className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 transition hover:border-slate-400 hover:bg-slate-50"
      >
        匯入資料
      </button>
    </>
  )

  return (
    <AppShell title="總覽" actions={headerActions}>

      <main className="mx-auto max-w-7xl space-y-6 px-6 py-6">
        {/* ── 廣播：Level 3 個數、當班點檢、等級提升的站別（整條線，只跟期間連動） ── */}
        <BroadcastBar window={changeWindow} windowHint={windowHint} reloadKey={reloadKey} />

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
                  start={quadrant.start}
                  startLabel={windowHint}
                  filtered={quadrant.filtered}
                  view={quadrant.view}
                  onSelect={setSelectedLevel}
                />
              )}
              {quadrant && (
                <LevelCountBar
                  counts={quadrant.scope}
                  onSelect={setSelectedLevel}
                  caption="全部 KPOV・現在 Level"
                />
              )}

              <div className="mt-5 border-t border-slate-100 pt-4">
                <StationLevelChart
                  title="客訴柱狀圖"
                  caption={`${windowHint}・客訴報表・依改善前 Level`}
                  stations={stationEvents?.stations.map((s) => ({ ...s, counts: s.complaints })) ?? null}
                  emptyText={`${windowHint}沒有對應到站別的客訴`}
                  note={eventNote(stationEvents?.unmappedComplaints ?? 0, stationEvents?.unknownLevel.complaints ?? 0, '客訴')}
                />
              </div>

              <div className="mt-5 border-t border-slate-100 pt-4">
                <StationLevelChart
                  title="製程柱狀圖"
                  caption={`${windowHint}・修護報表・依惡化後 Level`}
                  stations={stationEvents?.stations.map((s) => ({ ...s, counts: s.repairs })) ?? null}
                  emptyText={`${windowHint}沒有維修紀錄`}
                  note={eventNote(0, stationEvents?.unknownLevel.repairs ?? 0, '維修')}
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
                onOpen={(row) =>
                  setDetail({ repairId: row.repairId, complaintId: row.complaintId, kpovNo: row.kpovNo, equipmentCode: row.equipmentCode })
                }
              />
            </div>
          </section>
        )}

        {/* ── 中層：站別 Level 分佈＋站別風險地圖（點卡片連動下方）。
             PM1 整線 Layout 圖先拿掉（使用者 2026-10-20），元件 LayoutMap 保留，之後可放回 ── */}
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <div>
            <StationLevelChart
              title="站別 Level 分佈"
              caption="各站 KPOV 個數・KPOV 數據庫原始 Level"
              stations={stationKpov?.stations ?? null}
              emptyText="尚無 KPOV 資料"
              unit="個 KPOV"
            />
          </div>
          <StationRiskMap
            window={changeWindow}
            selected={state.target}
            onSelect={(target) => setState((s) => ({ ...s, target }))}
            reloadKey={reloadKey}
            kpovLevels={stationKpov ? Object.fromEntries(stationKpov.stations.map((s) => [s.equipmentCode, s.counts])) : null}
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
            {filters.batch.importedAt ? formatLocalDateTime(filters.batch.importedAt) : ''}
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

      {detail && <RecordDetailDrawer target={detail} onClose={() => setDetail(null)} />}

      {showImport && (
        <ImportDialog onClose={closeImport} />
      )}
    </AppShell>
  )
}
