import { useEffect, useState } from 'react'
import {
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { api, type CheckTrend } from '../api/client'
import { formatLocalDateTime } from '../utils/datetime'

const RANGES = [7, 14, 30] as const
const WARN = '#d97706' // 異常：與看板的「異常」標籤同色系
const MISSED = '#7c3aed' // 漏點檢
// 異常扇形：各點檢項目用不同的暖色，依異常次數由多到少
const WARN_SLICES = ['#b91c1c', '#ea580c', '#f59e0b', '#e11d48', '#c2410c', '#facc15']
const MAX_SLICES = WARN_SLICES.length

/**
 * 點檢看板上方（spec §18）：左＝每日異常次數＋漏點檢數折線；右＝KPIV 點檢內容的異常分布圓餅（只畫有異常的項目）。
 * 兩張圖共用期間（近 7／14／30 天），整條線、不吃下方紀錄的篩選；匯入的歷史點檢數量（spec §19）也算在內。
 * v2.15：都從起算日（預設 10/21，QCM_CHECK_MISSED_FROM）算；「不含星期日」勾選（預設勾）同時控制下方站別卡片。
 */
export function CheckTrendPanel({
  reloadKey,
  excludeOffDays,
  onExcludeOffDaysChange,
}: {
  reloadKey: number
  /** 不算星期日（休息日）；與下方站別卡片共用 */
  excludeOffDays: boolean
  onExcludeOffDaysChange: (value: boolean) => void
}) {
  const [days, setDays] = useState<number>(14)
  const [data, setData] = useState<CheckTrend | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .checkTrend(days, excludeOffDays)
      .then((d) => {
        setData(d)
        setError(null)
      })
      .catch((err) => setError(err instanceof Error ? err.message : '載入失敗'))
  }, [days, excludeOffDays, reloadKey])

  const rows = (data?.series ?? []).map((r) => ({ date: r.date.slice(5).replace('-', '/'), 異常次數: r.warn, 漏點檢數: r.missed }))

  const warnItems = (data?.items ?? []).filter((i) => i.warn > 0)
  // 超過色票數量時，最後一塊合併成「其他」
  const shown = warnItems.length <= MAX_SLICES ? warnItems : warnItems.slice(0, MAX_SLICES - 1)
  const rest = warnItems.slice(shown.length)
  const slices = [
    ...shown.map((i, n) => ({ name: i.checkContent ?? '—', station: i.station, value: i.warn, color: WARN_SLICES[n] })),
    ...(rest.length ? [{ name: `其他 ${rest.length} 項`, station: null, value: rest.reduce((s, i) => s + i.warn, 0), color: WARN_SLICES[MAX_SLICES - 1] }] : []),
  ]
  const total = data?.totals.total ?? 0
  const warnTotal = data?.totals.warn ?? 0
  const warnRate = total ? (warnTotal / total) * 100 : 0

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-xs font-medium uppercase tracking-wide text-slate-400">點檢趨勢與異常分布</h2>
        <label className="ml-auto flex items-center gap-1.5 text-sm text-slate-600" title="星期日休息：異常次數、漏點檢與站別卡片都不算星期日">
          <input type="checkbox" checked={excludeOffDays} onChange={(e) => onExcludeOffDaysChange(e.target.checked)} />
          不含星期日
        </label>
        <div className="inline-flex overflow-hidden rounded-md border border-slate-300 text-sm" role="group" aria-label="期間">
          {RANGES.map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setDays(d)}
              className={`px-3 py-1 ${days === d ? 'bg-[#0086DB] text-white' : 'bg-white text-slate-600 hover:bg-slate-50'}`}
            >
              近 {d} 天
            </button>
          ))}
        </div>
      </div>
      {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <h3 className="text-sm font-semibold text-slate-800">異常次數與漏點檢數</h3>
            {data && (
              <span className="text-xs text-slate-500">
                異常 <b className="tabular-nums text-amber-700">{data.totals.warn}</b>・漏點檢{' '}
                <b className="tabular-nums text-violet-700">{data.totals.missed}</b>
              </span>
            )}
          </div>
          <div className="h-60">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rows} margin={{ top: 8, right: 12, bottom: 0, left: -16 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} interval="preserveStartEnd" />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line type="monotone" dataKey="異常次數" stroke={WARN} strokeWidth={2} dot={{ r: 2 }} />
                <Line type="monotone" dataKey="漏點檢數" stroke={MISSED} strokeWidth={2} dot={{ r: 2 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-1 text-xs text-slate-400">
            依班別的開班日統計（夜班跨午夜算開班當天）。異常次數與漏點檢都自 {data?.countFrom ?? '—'} 起算（之前為試運行）
            {data?.excludeOffDays ? '，不含星期日' : ''}。漏點檢＝已結束的點檢時段沒有點檢
            {data?.trackingFrom ? `，從 ${formatLocalDateTime(data.trackingFrom).slice(0, 10)} 起；整班沒有任何點檢的班別不算` : '；尚無拍照點檢時不計'}。
            {data && data.totals.imported > 0 && `異常次數與漏點檢也算入匯入的歷史點檢（期間內 ${data.totals.imported} 筆）。`}
          </p>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="mb-2 text-sm font-semibold text-slate-800">KPIV 點檢內容異常分布</h3>
          {total === 0 ? (
            <p className="py-16 text-center text-sm text-slate-400">期間內沒有點檢</p>
          ) : warnTotal === 0 ? (
            <p className="py-16 text-center text-sm text-slate-400">期間內 {total} 次點檢都正常，沒有異常</p>
          ) : (
            <div className="flex flex-col items-center gap-3 2xl:flex-row 2xl:items-center">
              <div className="relative h-44 w-44 shrink-0">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={slices} dataKey="value" nameKey="name" innerRadius="58%" outerRadius="90%" startAngle={90} endAngle={-270} stroke="#fff">
                      {slices.map((s) => (
                        <Cell key={s.name} fill={s.color} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v: number) => [`${v} 次`, '']} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                  <span className="text-2xl font-bold tabular-nums text-amber-700">{warnTotal}</span>
                  <span className="text-xs text-slate-500">異常次數</span>
                </div>
              </div>
              <ul className="grid w-full min-w-0 flex-1 gap-x-4 gap-y-1 text-sm sm:grid-cols-2 2xl:grid-cols-1">
                {slices.map((s) => (
                  <li key={s.name} className="flex items-start gap-2">
                    <span className="mt-1 h-3 w-3 shrink-0 rounded-sm" style={{ backgroundColor: s.color }} />
                    <span className="min-w-0 flex-1 leading-snug" title={s.station ? `${s.station}・${s.name}` : s.name}>
                      <span className="line-clamp-2">{s.name}</span>
                      {s.station && <span className="block text-xs text-slate-400">{s.station}</span>}
                    </span>
                    <span className="shrink-0 tabular-nums text-slate-600">{s.value} 次</span>
                  </li>
                ))}
                <li className="pt-1 text-xs text-slate-400 sm:col-span-2 2xl:col-span-1">
                  共 {total} 次點檢{data!.totals.imported > 0 && `（含匯入 ${data!.totals.imported} 次）`}，異常 {warnTotal} 次・異常率 {warnRate.toFixed(1)}%
                </li>
              </ul>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
