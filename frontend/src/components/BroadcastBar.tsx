import { useEffect, useState, type ReactNode } from 'react'

import { api, type BroadcastResponse, type ChangeWindow } from '../api/client'
import { LevelChange } from './LevelChip'

type Tone = 'bad' | 'good' | 'info' | 'warn' | 'muted'

const TONES: Record<Tone, string> = {
  bad: 'border-red-200 bg-red-50 text-red-800',
  good: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  info: 'border-sky-200 bg-sky-50 text-sky-800',
  warn: 'border-amber-200 bg-amber-50 text-amber-800',
  muted: 'border-slate-200 bg-slate-50 text-slate-600',
}

// 點檢次數每分鐘更新一次（拍照點檢是在別的裝置上做的）
const REFRESH_MS = 60_000
// 等級提升的站別最多列幾個，其餘以「等 N 站」帶過
const MAX_STATIONS = 3

function Item({ tone, label, children }: { tone: Tone; label: string; children: ReactNode }) {
  return (
    <div className={`flex min-w-0 flex-1 items-center gap-2 rounded-md border px-3 py-2 text-sm ${TONES[tone]}`}>
      <span className="shrink-0 text-xs font-semibold opacity-70">{label}</span>
      <span className="min-w-0">{children}</span>
    </div>
  )
}

/**
 * 總覽頁頂端的廣播（spec §16）：整條線、不吃篩選器，只跟期間連動。
 * a. Level 3 個數有沒有變化（期初 → 現在）
 * b. 當班（白班／夜班）點檢了幾次
 * c. 期間內有沒有站別的 Level 提升
 */
export function BroadcastBar({
  window,
  windowHint,
  reloadKey,
}: {
  window: ChangeWindow
  windowHint: string
  reloadKey: number
}) {
  const [data, setData] = useState<BroadcastResponse | null>(null)

  useEffect(() => {
    let alive = true
    const load = () =>
      api
        .broadcast(window)
        .then((d) => alive && setData(d))
        .catch(() => alive && setData(null))
    void load()
    const timer = setInterval(load, REFRESH_MS)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [window, reloadKey])

  if (!data) return null
  const { level3, inspection, escalations, escalatedStations } = data

  const level3Tone: Tone = level3.delta > 0 ? 'bad' : level3.delta < 0 ? 'good' : 'muted'
  const level3Text =
    level3.delta === 0
      ? `無變化，維持 ${level3.now} 項`
      : `${level3.delta > 0 ? '增加' : '減少'} ${Math.abs(level3.delta)} 項（${level3.start} → ${level3.now}）`

  const done = inspection.completed >= inspection.expected
  const inspectionTone: Tone =
    inspection.warn > 0 ? 'bad' : done ? 'good' : inspection.shift.ended ? 'warn' : 'info'

  // 每站取最近一次提升（後端已依時間新到舊排序）
  const latestByStation = new Map<string, BroadcastResponse['escalations'][number]>()
  for (const e of escalations) if (!latestByStation.has(e.station)) latestByStation.set(e.station, e)
  const shown = [...latestByStation.values()].slice(0, MAX_STATIONS)
  const detail = escalations
    .map((e) => `${e.station}・${e.kpovName}：L${e.levelBefore ?? '—'} → L${e.levelAfter}`)
    .join('\n')

  return (
    <section aria-label="廣播" className="flex flex-col gap-2 rounded-lg border border-slate-200 bg-white p-3 lg:flex-row lg:items-stretch">
      <div className="flex shrink-0 items-center gap-1.5 px-1 text-sm font-semibold text-slate-700">
        <svg viewBox="0 0 24 24" className="h-4 w-4 text-[#0086DB]" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
          <path d="M3 11v2a1 1 0 0 0 1 1h2l5 4V6L6 10H4a1 1 0 0 0-1 1Z" />
          <path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13" strokeLinecap="round" />
        </svg>
        廣播
      </div>

      <Item tone={level3Tone} label={`Level 3・${windowHint}`}>
        {level3Text}
      </Item>

      <Item tone={inspectionTone} label={`點檢・${inspection.shift.label}${inspection.shift.ended ? '（已結束）' : ''}`}>
        已點檢 <b className="tabular-nums">{inspection.completed}</b> / {inspection.expected} 次
        {inspection.warn > 0 && <span className="ml-1 font-semibold">・異常 {inspection.warn}</span>}
      </Item>

      <Item tone={escalatedStations.length ? 'bad' : 'good'} label={`站別等級・${windowHint}`}>
        {escalatedStations.length === 0 ? (
          '無站別等級提升'
        ) : (
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1" title={detail}>
            <span>{escalatedStations.length} 站提升：</span>
            {shown.map((e) => (
              <span key={e.station} className="inline-flex items-center gap-1 whitespace-nowrap">
                {e.station}
                <LevelChange before={e.levelBefore} after={e.levelAfter} />
              </span>
            ))}
            {escalatedStations.length > shown.length && <span>等</span>}
          </span>
        )}
      </Item>
    </section>
  )
}
