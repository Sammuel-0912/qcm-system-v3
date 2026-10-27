import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'

import { api, type BroadcastAlert, type BroadcastResponse, type ChangeWindow } from '../api/client'
import { LevelChange } from './LevelChip'

// 點檢次數每分鐘更新一次（拍照點檢是在別的裝置上做的）
const REFRESH_MS = 60_000
// 跑馬燈速度（px／秒）：內容越多一圈越久，速度不變
const SPEED = 60

const KINDS: Record<BroadcastAlert['kind'], { label: string; chip: string; order: number }> = {
  escalatedL3: { label: '升到 Level 3', chip: 'bg-red-600 text-white', order: 0 },
  level3New: { label: '新增 Level 3', chip: 'bg-red-100 text-red-800 ring-1 ring-red-200', order: 1 },
  warn: { label: '點檢異常', chip: 'bg-amber-100 text-amber-800 ring-1 ring-amber-200', order: 2 },
  missed: { label: '漏點檢', chip: 'bg-violet-100 text-violet-800 ring-1 ring-violet-200', order: 3 },
}

function AlertItem({ alert, shiftName, windowHint }: { alert: BroadcastAlert; shiftName: string; windowHint: string }) {
  const kind = KINDS[alert.kind]
  const scope = alert.kind === 'missed' || alert.kind === 'warn' ? shiftName : windowHint
  return (
    <span className="inline-flex items-center gap-2 whitespace-nowrap text-sm text-slate-700">
      <span className={`rounded px-1.5 py-0.5 text-xs font-semibold ${kind.chip}`}>
        {kind.label}・{scope}
      </span>
      <span className="font-medium text-slate-800">{alert.station}</span>
      {alert.text && <span className="text-slate-600">{alert.text}</span>}
      {alert.kind === 'escalatedL3' && <LevelChange before={alert.levelBefore ?? null} after={3} />}
      {alert.kind === 'missed' && <span className="font-semibold text-violet-700">{alert.count} 個時段未點檢</span>}
      {alert.kind === 'warn' && <span className="font-semibold text-amber-700">異常 {alert.count} 次</span>}
    </span>
  )
}

/**
 * 無限跑馬燈：一開始內容就在畫面上，往左捲；後面接一模一樣的一份，捲完一份剛好回到起點，看起來無限循環。
 * 內容比畫面窄時先重複到填滿一個畫面寬，避免中間出現空白。滑鼠移上去暫停。
 */
function Marquee({ contentKey, children }: { contentKey: string; children: ReactNode }) {
  const viewport = useRef<HTMLDivElement>(null)
  const group = useRef<HTMLDivElement>(null)
  const [copies, setCopies] = useState(1)
  const [duration, setDuration] = useState(30)

  useLayoutEffect(() => {
    const measure = () => {
      const view = viewport.current?.clientWidth ?? 0
      const width = group.current?.offsetWidth ?? 0
      if (!width) return
      const n = Math.max(1, Math.ceil(view / width))
      setCopies(n)
      setDuration((width * n) / SPEED)
    }
    measure()
    const observer = new ResizeObserver(measure)
    if (viewport.current) observer.observe(viewport.current)
    return () => observer.disconnect()
  }, [contentKey])

  const half = (prefix: string) =>
    Array.from({ length: copies }, (_, i) => (
      <div
        key={`${prefix}${i}`}
        ref={prefix === 'a' && i === 0 ? group : undefined}
        aria-hidden={prefix === 'b' || i > 0 ? true : undefined}
        className="flex shrink-0 items-center gap-8 pr-8"
      >
        {children}
      </div>
    ))

  return (
    <div ref={viewport} className="qcm-marquee-viewport min-w-0 flex-1 overflow-hidden">
      <div className="qcm-marquee flex w-max" style={{ animationDuration: `${duration}s` }}>
        {half('a')}
        {half('b')}
      </div>
    </div>
  )
}

/**
 * 總覽頁頂端的廣播（spec §16）：整條線、不吃篩選器，Level 相關跟期間連動。
 * v2.7 起改為跑馬燈，只列需要關注的項目：升到 Level 3、新增 Level 3、當班點檢異常、當班漏點檢。
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
  const alerts = [...data.alerts].sort((a, b) => KINDS[a.kind].order - KINDS[b.kind].order)
  const shiftName = data.inspection.shift.name
  const contentKey = JSON.stringify(alerts) + shiftName + windowHint

  return (
    <section aria-label="廣播" className="flex items-center gap-3 overflow-hidden rounded-lg border border-slate-200 bg-white px-3 py-2.5">
      <div className="flex shrink-0 items-center gap-1.5 text-sm font-semibold text-slate-700">
        <svg viewBox="0 0 24 24" className="h-4 w-4 text-[#0086DB]" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
          <path d="M3 11v2a1 1 0 0 0 1 1h2l5 4V6L6 10H4a1 1 0 0 0-1 1Z" />
          <path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13" strokeLinecap="round" />
        </svg>
        廣播
        {alerts.length > 0 && (
          <span className="rounded-full bg-red-600 px-1.5 text-xs tabular-nums text-white">{alerts.length}</span>
        )}
      </div>
      {alerts.length === 0 ? (
        <p className="min-w-0 truncate text-sm text-emerald-700">
          目前沒有需要關注的項目（{data.inspection.shift.label}無漏點檢與異常、{windowHint}無新增 Level 3）
        </p>
      ) : (
        <Marquee contentKey={contentKey}>
          {alerts.map((a) => (
            <AlertItem key={`${a.kind}:${a.equipmentCode}:${a.kpovNo}:${a.text}`} alert={a} shiftName={shiftName} windowHint={windowHint} />
          ))}
        </Marquee>
      )}
    </section>
  )
}
