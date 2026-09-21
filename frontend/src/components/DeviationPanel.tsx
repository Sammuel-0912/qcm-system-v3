import type { EventsResponse } from '../api/client'
import { LEVEL_COLORS } from '../constants'

type Props = {
  data: EventsResponse | null
  onSelect: (kpovNo: string, equipmentCode: string) => void
}

function LevelChip({ level }: { level: number | null }) {
  if (level === null) return <span className="text-slate-400">—</span>
  return (
    <span
      className="inline-flex h-5 items-center rounded px-1.5 text-xs font-semibold text-slate-800 ring-1 ring-black/10"
      style={{ backgroundColor: LEVEL_COLORS[level] }}
    >
      L{level}
    </span>
  )
}

const ARROW: Record<string, { symbol: string; className: string }> = {
  ESCALATED: { symbol: '↑', className: 'text-red-600' },
  IMPROVED: { symbol: '↓', className: 'text-emerald-600' },
  UNCHANGED: { symbol: '→', className: 'text-slate-400' },
}

export function DeviationPanel({ data, onSelect }: Props) {
  if (!data) {
    return <div className="text-sm text-slate-500">載入中…</div>
  }

  const { summary, items } = data
  const escalated = summary.escalatedOpen

  return (
    <div className="flex h-full flex-col">
      <h2 className="mb-3 text-base font-semibold text-slate-800">等級異動總覽</h2>

      <div className="mb-4 grid grid-cols-2 gap-3">
        <div
          className={`rounded-lg border p-3 ${
            escalated > 0 ? 'border-red-200 bg-red-50' : 'border-slate-200 bg-slate-50'
          }`}
        >
          <div className={`text-2xl font-bold ${escalated > 0 ? 'text-red-700' : 'text-slate-700'}`}>
            {escalated}
          </div>
          <div className={`text-xs ${escalated > 0 ? 'text-red-700' : 'text-slate-500'}`}>惡化中</div>
        </div>
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3">
          <div className="text-2xl font-bold text-emerald-700">{summary.improved}</div>
          <div className="text-xs text-emerald-700">已改善</div>
        </div>
      </div>

      <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">最近異動</div>

      {items.length === 0 ? (
        <p className="text-sm text-slate-500">目前沒有等級異動紀錄。</p>
      ) : (
        <ul className="flex-1 space-y-1.5 overflow-y-auto pr-1">
          {items.map((event, idx) => {
            const arrow = ARROW[event.transition]
            return (
              <li key={`${event.repairSerial}-${event.eventType}-${idx}`}>
                <button
                  type="button"
                  onClick={() => onSelect(event.kpovNo, event.equipmentCode)}
                  className="w-full rounded-md border border-slate-200 p-2 text-left transition hover:border-slate-400 hover:bg-slate-50"
                >
                  <div className="flex items-center gap-2 text-sm">
                    <span className="font-medium text-slate-800">{event.kpovName ?? event.kpovNo}</span>
                    <span className="text-xs text-slate-400">{event.station}</span>
                  </div>
                  <div className="mt-1 flex items-center gap-1.5 text-xs text-slate-600">
                    <LevelChip level={event.levelBefore} />
                    <span className={`font-bold ${arrow.className}`}>{arrow.symbol}</span>
                    <LevelChip level={event.levelAfter} />
                    <span className="ml-auto tabular-nums text-slate-400">
                      {event.effectiveAt.slice(0, 10)}
                    </span>
                  </div>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
