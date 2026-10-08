import { Link } from 'react-router-dom'

import type { CheckMonitorResponse, CheckMonitorRow, CheckSlot, SlotState } from '../api/client'

type Props = { data: CheckMonitorResponse | null; scopeLabel: string }

const SLOT: Record<SlotState, { label: string; className: string }> = {
  ok: { label: '已點檢・正常', className: 'bg-emerald-500' },
  warn: { label: '已點檢・異常', className: 'bg-red-500' },
  missed: { label: '漏檢', className: 'bg-red-100 ring-1 ring-inset ring-red-300' },
  current: { label: '本時段待點檢', className: 'bg-white ring-2 ring-inset ring-amber-400' },
  upcoming: { label: '尚未到', className: 'bg-slate-100' },
}

function hhmm(value: string) {
  const d = new Date(value)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function slotTitle(slot: CheckSlot) {
  const range = `${hhmm(slot.start)}–${hhmm(slot.end)}`
  const at = slot.inspectedAt ? `（${hhmm(slot.inspectedAt)} 點檢）` : ''
  return `${range} ${SLOT[slot.state].label}${at}`
}

/** 需要處理的排前面：有異常 → 有漏檢 → 完成度低 */
function urgency(row: CheckMonitorRow) {
  const warn = row.slots.some((s) => s.state === 'warn') ? 0 : 1
  const missed = row.slots.some((s) => s.state === 'missed') ? 0 : 1
  return [warn, missed, row.progress] as const
}

function compare(a: CheckMonitorRow, b: CheckMonitorRow) {
  const ua = urgency(a)
  const ub = urgency(b)
  for (let i = 0; i < ua.length; i++) if (ua[i] !== ub[i]) return ua[i] - ub[i]
  return 0
}

function Progress({ row }: { row: CheckMonitorRow }) {
  return (
    <div className="flex items-center gap-2">
      <div className="flex gap-0.5" role="img" aria-label={`本班完成 ${row.progress}%`}>
        {row.slots.map((slot) => (
          <span
            key={slot.start}
            title={slotTitle(slot)}
            className={`h-3.5 w-5 rounded-sm ${SLOT[slot.state].className}`}
          />
        ))}
      </div>
      <span className="w-10 text-right text-sm font-semibold tabular-nums text-slate-800">{row.progress}%</span>
    </div>
  )
}

/** Level 3 高風險項點檢監控：點檢項目來自「高風險項點檢」，執行狀況來自 AR 逐項點檢 */
export function CheckMonitorTable({ data, scopeLabel }: Props) {
  const rows = data ? [...data.items].sort(compare) : []

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-baseline gap-2">
        <h2 className="text-base font-semibold text-slate-800">Level 3 項目點檢監控</h2>
        <span className="text-sm text-slate-500">{scopeLabel}</span>
        {data && data.summary.total > 0 && (
          <span className="ml-auto flex flex-wrap items-center gap-2 text-xs">
            <span className="text-slate-500">
              {data.shift.label}
              {data.shift.ended && '（已結束）'}
            </span>
            <span className="rounded bg-slate-100 px-1.5 py-0.5 font-semibold text-slate-800">
              平均完成 {data.summary.progress}%
            </span>
            {data.summary.warnSlots > 0 && (
              <span className="rounded bg-red-100 px-1.5 py-0.5 font-medium text-red-700">
                異常 {data.summary.warnSlots} 次
              </span>
            )}
            {data.summary.missedSlots > 0 && (
              <span className="rounded bg-red-50 px-1.5 py-0.5 font-medium text-red-600 ring-1 ring-inset ring-red-200">
                漏檢 {data.summary.missedSlots} 格
              </span>
            )}
          </span>
        )}
      </div>

      {!data ? (
        <p className="py-10 text-center text-sm text-slate-400">載入中…</p>
      ) : rows.length === 0 ? (
        <p className="py-10 text-center text-sm text-slate-400">此範圍沒有高風險點檢項目</p>
      ) : (
        <div className="max-h-[22rem] overflow-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-white text-xs text-slate-500">
              <tr className="border-b border-slate-200">
                <th className="py-2 pr-3 font-medium">站別</th>
                <th className="py-2 pr-3 font-medium">KPOV</th>
                <th className="py-2 pr-3 font-medium">點檢內容</th>
                <th className="py-2 pr-3 font-medium">點檢頻率</th>
                <th className="py-2 font-medium">執行狀況（本班）</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-b border-slate-100 align-top last:border-0">
                  <td className="py-2 pr-3">
                    <span className="block text-slate-800">{row.station ?? '—'}</span>
                    <span className="font-mono text-xs text-slate-400">{row.equipmentCode ?? '未對應設備'}</span>
                  </td>
                  <td className="py-2 pr-3">
                    <span className="block text-slate-800">{row.kpovName ?? '—'}</span>
                    <span className="font-mono text-xs text-slate-400">{row.kpovNo}</span>
                  </td>
                  <td className="py-2 pr-3 text-slate-700">{row.checkContent}</td>
                  <td className="py-2 pr-3 text-xs text-slate-500">
                    {row.frequency ?? `${row.intervalHours}h/次`}
                  </td>
                  <td className="py-2">
                    <Progress row={row} />
                    <span className="mt-1 block whitespace-nowrap text-xs tabular-nums text-slate-400">
                      {row.completed}/{row.slots.length} 次 · 上次{' '}
                      {row.lastInspectedAt ? hhmm(row.lastInspectedAt) : '—'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
        {(['ok', 'warn', 'missed', 'current', 'upcoming'] as SlotState[]).map((state) => (
          <span key={state} className="flex items-center gap-1.5">
            <span className={`inline-block h-3 w-4 rounded-sm ${SLOT[state].className}`} />
            {SLOT[state].label}
          </span>
        ))}
      </div>
      <p className="mt-1.5 text-xs text-slate-400">
        每 2 小時一格，每格 20%；同一時段點檢多次只算一次。結果來自{' '}
        <Link to="/ar/inspect" className="underline hover:text-slate-600">
          AR 點檢
        </Link>
        ，每分鐘自動更新。
      </p>
    </div>
  )
}
