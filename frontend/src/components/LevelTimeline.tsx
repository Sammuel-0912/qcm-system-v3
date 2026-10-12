import { useEffect, useRef, useState } from 'react'

import type { ChangeRecord, HistoryResponse } from '../api/client'
import { LEVEL_COLORS } from '../constants'
import { HOTSPOTS } from '../layoutConfig'

type Props = { data: HistoryResponse }

function Level({ level }: { level: number | null }) {
  if (level === null) return <span className="text-slate-400">未評估</span>
  return (
    <span
      className="inline-flex h-6 items-center rounded px-2 text-sm font-semibold text-slate-800 ring-1 ring-black/10"
      style={{ backgroundColor: LEVEL_COLORS[level] }}
    >
      Level {level}
    </span>
  )
}

/** 可點擊的目標等級：點開後顯示這次異動的原因或對策 */
function LevelWithDetail({
  level,
  label,
  lines,
}: {
  level: number
  label: string
  lines: { term: string; value: string }[]
}) {
  // hover 與 click 必須是兩個獨立狀態。共用一個的話，滑鼠移上去先展開、
  // 接著的 click 會把它 toggle 成關閉，點擊等於沒反應。
  const [pinned, setPinned] = useState(false)
  const [hovered, setHovered] = useState(false)
  const open = pinned || hovered
  const ref = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    if (!pinned) return
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setPinned(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setPinned(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [pinned])

  return (
    <span
      className="relative inline-block"
      ref={ref}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <button
        type="button"
        onClick={() => setPinned((v) => !v)}
        aria-expanded={open}
        aria-label={`Level ${level}，查看${label}`}
        className="inline-flex h-6 items-center gap-1 rounded px-2 text-sm font-semibold text-slate-800 ring-1 ring-black/20 transition hover:ring-2 hover:ring-slate-500"
        style={{ backgroundColor: LEVEL_COLORS[level] }}
      >
        Level {level}
        <span className="text-[10px] leading-none text-slate-600">ⓘ</span>
      </button>

      {open && (
        <span
          role="tooltip"
          className="absolute left-0 top-full z-20 mt-1 block w-72 rounded-md border border-slate-200 bg-white p-2.5 text-left shadow-lg"
        >
          <span className="mb-1 block text-[11px] font-medium uppercase tracking-wide text-slate-400">
            {label}
          </span>
          {lines.map((line) => (
            <span key={line.term} className="mb-1 block last:mb-0">
              {/* 只有一行且欄位名等同標題時不重複顯示欄位名 */}
              {!(lines.length === 1 && line.term === label) && (
                <span className="block text-[11px] text-slate-400">{line.term}</span>
              )}
              <span className="block text-xs leading-snug text-slate-700">{line.value}</span>
            </span>
          ))}
        </span>
      )}
    </span>
  )
}

/** 偵測度：依規格簡化為 y:3 Y:7（y = 站內、Y = 下游） */
function Scores({ smallY, bigY }: { smallY: number | null; bigY: number | null }) {
  return (
    <span className="inline-flex items-baseline gap-2 font-mono text-xs tabular-nums text-slate-600">
      <span title="y — 站內偵測度">y:{smallY ?? '—'}</span>
      <span title="Y — 下游偵測度">Y:{bigY ?? '—'}</span>
    </span>
  )
}

function Axis({
  label,
  before,
  after,
}: {
  label: string
  before: { method: string | null; score: number | null }
  after: { method: string | null; score: number }
}) {
  const worsened = before.score !== null && after.score > before.score
  const improved = before.score !== null && after.score < before.score
  return (
    <div className="flex flex-wrap items-baseline gap-1.5 text-xs">
      <span className="w-5 shrink-0 font-mono font-medium text-slate-500">{label}</span>
      <span className="text-slate-400">
        {before.method ?? '基準'}
        {before.score !== null && ` (${before.score})`}
      </span>
      <span className="text-slate-400">→</span>
      <span
        className={
          worsened ? 'font-medium text-red-600' : improved ? 'font-medium text-emerald-600' : 'text-slate-700'
        }
      >
        {after.method} ({after.score})
      </span>
    </div>
  )
}

/** 「Level 3」-> 3；PCN/ECN 的等級欄是文字 */
function parseLevel(value: string | null): number | null {
  const match = value?.match(/\d/)
  return match ? Number(match[0]) : null
}

/** PCN / ECN 變更節點：只標示時間與前後狀態，不參與等級計算 */
function ChangeNode({ change }: { change: ChangeRecord }) {
  const isPcn = change.kind === 'PCN'
  const before = parseLevel(change.levelBefore)
  const after = parseLevel(change.levelAfter)
  const hasScores = change.smallYBefore || change.bigYBefore || change.smallYAfter || change.bigYAfter
  return (
    <li className="relative">
      <span
        className={`absolute -left-[27px] top-1 h-3 w-3 rounded-full border-2 border-white ${
          isPcn ? 'bg-sky-500' : 'bg-violet-500'
        }`}
      />
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`rounded px-1.5 py-0.5 text-xs font-semibold ${
            isPcn ? 'bg-sky-100 text-sky-700' : 'bg-violet-100 text-violet-700'
          }`}
        >
          {isPcn ? 'PCN 變更' : `ECN ${change.ecnNo ?? ''}`.trim()}
        </span>
        {change.plantWide && <span className="text-xs text-slate-400">全廠</span>}
        {(before !== null || after !== null) && (
          <>
            <Level level={before} />
            <span className="text-slate-400">→</span>
            <Level level={after} />
          </>
        )}
        <span className="ml-auto text-xs tabular-nums text-slate-400">
          {change.effectiveAt?.slice(0, 10) ?? '日期未填'}
        </span>
      </div>
      {change.content && <p className="mt-1.5 text-sm text-slate-700">{change.content}</p>}
      {hasScores && (
        <div className="mt-2 rounded-md bg-slate-50 p-2 font-mono text-xs tabular-nums text-slate-600">
          y:{change.smallYBefore ?? '—'} Y:{change.bigYBefore ?? '—'}
          <span className="mx-1.5 text-slate-400">→</span>
          y:{change.smallYAfter ?? '—'} Y:{change.bigYAfter ?? '—'}
        </div>
      )}
    </li>
  )
}

export function LevelTimeline({ data }: Props) {
  // 主標題以 KPOV 庫的站別為準（使用者指定）。
  // 現場名稱與庫內名稱不一致時（OT00420104 庫裡是「鎖電感」、現場是「鎖銅排2」），
  // 以小字附註現場名稱——使用者多半是從 layout 用現場名稱點進來的，兩邊要對得起來。
  const hotspot = HOTSPOTS.find((h) => h.targetId === data.targetId)
  const siteName = hotspot?.displayName
  const showSiteName = Boolean(siteName && siteName !== data.station)

  // 時間軸由新到舊：預計改善 → 現況 → 維修事件與 PCN/ECN 依日期交錯（倒序）→ 基準。
  // 預計改善（改善時間在未來）放在「現況」之上，表示尚未發生。
  // 同一天時 PCN/ECN 排在維修事件之後（較舊）：變更先切入，之後才觀察到不良。
  type Node =
    | { kind: 'event'; at: string; event: HistoryResponse['events'][number]; idx: number }
    | { kind: 'change'; at: string; change: ChangeRecord; idx: number }
  const sorted = [
    ...data.events.map((event, idx) => ({ kind: 'event' as const, at: event.effectiveAt, event, idx })),
    ...(data.changes ?? []).map((change, idx) => ({
      kind: 'change' as const,
      at: change.effectiveAt ?? '',
      change,
      idx,
    })),
  ].sort((a, b) => {
    const day = b.at.slice(0, 10).localeCompare(a.at.slice(0, 10))
    if (day !== 0) return day
    if (a.kind !== b.kind) return a.kind === 'event' ? -1 : 1
    return a.kind === 'event' ? b.at.localeCompare(a.at) || b.idx - a.idx : b.idx - a.idx
  })
  const now = Date.now()
  const isFuture = (n: Node) => n.kind === 'event' && n.event.type === 'IMPROVE' && new Date(n.at).getTime() > now
  const nodes: (Node | { kind: 'current' })[] = [
    ...sorted.filter(isFuture),
    { kind: 'current' },
    ...sorted.filter((n) => !isFuture(n)),
  ]

  return (
    <div>
      <div className="mb-1 flex flex-wrap items-baseline gap-2">
        <h3 className="text-lg font-semibold text-slate-900">{data.station}</h3>
        {data.equipmentCode && (
          <span className="font-mono text-sm text-slate-500">{data.equipmentCode}</span>
        )}
        {showSiteName && <span className="text-xs text-slate-400">（現場：{siteName}）</span>}
      </div>
      <p className="mb-4 text-sm text-slate-500">
        {data.kpovName} <span className="text-slate-400">{data.kpovNo}</span>
      </p>

      <ol className="relative space-y-4 border-l-2 border-slate-200 pl-5">
        {nodes.map((node) => {
          if (node.kind === 'current') {
            return (
              <li key="current" className="relative">
                <span className="absolute -left-[27px] top-1 h-3 w-3 rounded-full border-2 border-white bg-slate-900" />
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-slate-700">現況</span>
                  <Level level={data.current.level} />
                </div>
              </li>
            )
          }
          if (node.kind === 'change') {
            return <ChangeNode key={`change-${node.idx}`} change={node.change} />
          }
          const { event, idx } = node
          const isDegrade = event.type === 'DEGRADE'
          // 改善時間在未來：預計改善，現況等級尚未採用
          const isPlanned = !isDegrade && new Date(event.effectiveAt).getTime() > Date.now()
          const repair = event.repair
          // 區分兩種「沒東西」：後端沒帶回維修紀錄（多半是後端未更新或未重啟），
          // 與維修紀錄本身欄位空白。混為一談的話，出問題時只能靠猜。
          const missing = repair === null || repair === undefined
          const field = (value: string | null | undefined) =>
            missing ? '（後端未提供維修明細，請確認後端已更新並重啟）' : value || '（未填寫）'
          const lines = isDegrade
            ? [
                { term: '產品不良描述', value: field(repair?.productDefectDesc) },
                { term: '維修備註', value: field(repair?.remark) },
              ]
            : [{ term: '改善措施', value: event.improvement || field(repair?.improvement) }]

          return (
            <li
              key={`${event.repairSerial}-${event.type}-${idx}`}
              className={`relative ${isPlanned ? 'opacity-70' : ''}`}
            >
              <span
                className={`absolute -left-[27px] top-1 h-3 w-3 rounded-full border-2 ${
                  isPlanned
                    ? 'border-dashed border-emerald-500 bg-white'
                    : 'border-white ' +
                      (event.transition === 'ESCALATED'
                    ? 'bg-red-500'
                    : event.transition === 'IMPROVED'
                      ? 'bg-emerald-500'
                      : 'bg-slate-400')
                }`}
              />
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`rounded px-1.5 py-0.5 text-xs font-semibold ${
                    isDegrade
                      ? 'bg-red-100 text-red-700'
                      : isPlanned
                        ? 'bg-white text-emerald-700 border border-dashed border-emerald-400'
                        : 'bg-emerald-100 text-emerald-700'
                  }`}
                >
                  {isDegrade ? '不良發生' : isPlanned ? '預計改善' : '改善完成'}
                </span>
                <Level level={event.levelBefore} />
                <span className="text-slate-400">→</span>
                <LevelWithDetail
                  level={event.levelAfter}
                  label={isDegrade ? '惡化原因' : '改善措施'}
                  lines={lines}
                />
                <span className="ml-auto text-xs tabular-nums text-slate-400">
                  {event.effectiveAt.slice(0, 10)}
                </span>
              </div>

              <div className="mt-2 space-y-1 rounded-md bg-slate-50 p-2">
                <Axis label="y" before={event.smallYBefore} after={event.smallY} />
                <Axis label="Y" before={event.bigYBefore} after={event.bigY} />
              </div>

              {event.repairSerial && (
                <p className="mt-1 text-xs text-slate-400">導入產品序號 {event.repairSerial}</p>
              )}
            </li>
          )
        })}

        <li className="relative">
          <span className="absolute -left-[27px] top-1 h-3 w-3 rounded-full border-2 border-white bg-slate-400" />
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-slate-700">基準</span>
            <Level level={data.baseline.level} />
            <Scores smallY={data.baseline.smallY.score} bigY={data.baseline.bigY.score} />
          </div>
        </li>
      </ol>
    </div>
  )
}
