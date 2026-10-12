import type { EventsResponse } from '../api/client'
import { LEVEL_COLORS } from '../constants'

type Props = {
  data: EventsResponse | null
  onSelect: (kpovNo: string, equipmentCode: string) => void
  /** 「變化後 Level」篩選：'0'–'3' 或 'all' */
  level: string
  onLevelChange: (level: string) => void
}

const LEVEL_OPTIONS = ['0', '1', '2', '3'] as const

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

export function DeviationPanel({ data, onSelect, level, onLevelChange }: Props) {
  if (!data) {
    return <div className="text-sm text-slate-500">載入中…</div>
  }

  const { summary, items } = data
  const escalated = summary.escalatedOpen
  const counts = data.levelCounts ?? {}
  const total = LEVEL_OPTIONS.reduce((sum, l) => sum + (counts[l] ?? 0), 0)

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

      <div className="mb-2 flex items-baseline justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-400">最近異動</span>
        <span className="text-xs text-slate-400">依變化後等級</span>
      </div>

      <div className="mb-3 grid grid-cols-5 gap-1" role="tablist" aria-label="依變化後等級篩選">
        {LEVEL_OPTIONS.map((l) => {
          const active = level === l
          const n = counts[l] ?? 0
          return (
            <button
              key={l}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => onLevelChange(l)}
              className={`rounded-md border px-1 py-1.5 text-center text-xs transition ${
                active ? 'border-slate-900 ring-1 ring-slate-900' : 'border-slate-200 hover:border-slate-400'
              } ${n === 0 ? 'opacity-50' : ''}`}
              style={{ backgroundColor: active ? LEVEL_COLORS[Number(l)] : undefined }}
            >
              <span className="block font-semibold text-slate-800">Level {l}</span>
              <span className="block tabular-nums text-slate-500">{n}</span>
            </button>
          )
        })}
        <button
          type="button"
          role="tab"
          aria-selected={level === 'all'}
          onClick={() => onLevelChange('all')}
          className={`rounded-md border px-1 py-1.5 text-center text-xs transition ${
            level === 'all' ? 'border-slate-900 bg-slate-100 ring-1 ring-slate-900' : 'border-slate-200 hover:border-slate-400'
          }`}
        >
          <span className="block font-semibold text-slate-800">全部</span>
          <span className="block tabular-nums text-slate-500">{total}</span>
        </button>
      </div>

      {items.length === 0 ? (
        <p className="text-sm text-slate-500">
          {level === 'all' ? '目前沒有等級異動紀錄。' : `沒有變化後為 Level ${level} 的異動。`}
        </p>
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
                    {event.planned && (
                      <span className="ml-auto rounded px-1 text-[10px] font-medium text-emerald-700 border border-dashed border-emerald-400">
                        預計改善
                      </span>
                    )}
                    <span className={`${event.planned ? '' : 'ml-auto '}tabular-nums text-slate-400`}>
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
