import type { ChangeKind, ChangeWindow, LevelChangesResponse } from '../api/client'
import { Fragment, useState } from 'react'

import type { EmergencyMeasure } from '../api/client'
import { EmergencyMeasureEditor, measureSummary } from './EmergencyMeasureEditor'
import { LevelChip } from './LevelChip'

type Props = {
  data: LevelChangesResponse | null
  window: ChangeWindow
  kind: ChangeKind
  onWindowChange: (window: ChangeWindow) => void
  onKindChange: (kind: ChangeKind) => void
  onPageChange: (page: number) => void
  onSelect: (kpovNo: string, equipmentCode: string) => void
}

// 天／週／月／年 = 近 1／7／30／365 天（滾動區間）
const WINDOWS: { value: ChangeWindow; label: string; hint: string }[] = [
  { value: 'day', label: '天', hint: '近 1 天' },
  { value: 'week', label: '週', hint: '近 7 天' },
  { value: 'month', label: '月', hint: '近 30 天' },
  { value: 'year', label: '年', hint: '近 365 天' },
]

export function DeviationPanel({ data, window, kind, onWindowChange, onKindChange, onPageChange, onSelect }: Props) {
  const windowHint = WINDOWS.find((w) => w.value === window)?.hint
  const escalated = kind === 'escalated'
  // 展開中的緊急措施編輯列，以及剛儲存、尚未重新載入的分類
  const [openRow, setOpenRow] = useState<string | null>(null)
  const [saved, setSaved] = useState<Record<string, EmergencyMeasure>>({})
  const columns = escalated ? 6 : 5
  const cards: { value: ChangeKind; label: string; tone: string; active: string }[] = [
    {
      value: 'escalated',
      label: '高風險',
      tone: 'border-red-200 bg-red-50 text-red-700',
      active: 'ring-2 ring-red-500',
    },
    {
      value: 'improved',
      label: '已改善',
      tone: 'border-emerald-200 bg-emerald-50 text-emerald-700',
      active: 'ring-2 ring-emerald-500',
    },
  ]

  return (
    <div className="flex h-full flex-col">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h2 className="text-base font-semibold text-slate-800">等級異動總覽</h2>
        <div
          className="ml-auto inline-flex rounded-md border border-slate-200 p-0.5"
          role="tablist"
          aria-label="時間範圍"
        >
          {WINDOWS.map((w) => (
            <button
              key={w.value}
              type="button"
              role="tab"
              aria-selected={window === w.value}
              title={w.hint}
              onClick={() => onWindowChange(w.value)}
              className={`rounded px-2.5 py-1 text-xs font-medium transition ${
                window === w.value ? 'bg-slate-900 text-white' : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              {w.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mb-3 grid grid-cols-2 gap-3">
        {cards.map((card) => (
          <button
            key={card.value}
            type="button"
            aria-pressed={kind === card.value}
            onClick={() => onKindChange(card.value)}
            className={`rounded-lg border p-3 text-left transition hover:brightness-95 ${card.tone} ${
              kind === card.value ? card.active : ''
            }`}
          >
            <div className="text-2xl font-bold">{data ? data.counts[card.value] : '—'}</div>
            <div className="text-xs underline underline-offset-2">
              {card.label}
              <span className="ml-1 opacity-70">· {windowHint}</span>
            </div>
          </button>
        ))}
      </div>

      {!data ? (
        <p className="text-sm text-slate-500">載入中…</p>
      ) : data.items.length === 0 ? (
        <p className="py-6 text-center text-sm text-slate-500">
          {windowHint}沒有{escalated ? '高風險' : '改善'}的項目。
        </p>
      ) : (
        <div className="flex-1 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-700 text-xs text-white">
              <tr>
                <th className="px-2 py-2 font-medium">站別</th>
                <th className="px-2 py-2 font-medium">KPOV</th>
                <th className="px-2 py-2 font-medium">Level 變化</th>
                {/* 高風險：修護報表的改善措施在此稱為「緊急措施」；已改善則稱「預防措施」 */}
                <th className="px-2 py-2 font-medium">{escalated ? '緊急措施' : '預防措施'}</th>
                {escalated && <th className="whitespace-nowrap px-2 py-2 text-right font-medium">客訴筆數</th>}
                <th className="px-2 py-2 font-medium">改善時間</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item, idx) => {
                const rowKey = `${item.repairSerial}|${item.kpovNo}|${item.equipmentCode}`
                const measure = saved[rowKey] ?? item.measure ?? null
                const editable = escalated && Boolean(item.repairSerial)
                const expanded = editable && openRow === `${rowKey}|${idx}`
                return (
                  <Fragment key={`${rowKey}-${item.effectiveAt}-${idx}`}>
                    <tr
                      onClick={() => onSelect(item.kpovNo, item.equipmentCode)}
                      className="cursor-pointer border-b border-slate-100 align-top hover:bg-slate-50"
                      title="點擊查看此 KPOV 的等級歷程"
                    >
                      <td className="px-2 py-2 text-slate-800">{item.station}</td>
                      <td className="px-2 py-2">
                        <span className="block text-slate-800">{item.kpovName}</span>
                        <span className="font-mono text-xs text-slate-400">{item.kpovNo}</span>
                      </td>
                      <td className="whitespace-nowrap px-2 py-2">
                        <span className="inline-flex items-center gap-1">
                          <LevelChip level={item.levelBefore} />
                          <span
                            className={`font-bold ${item.transition === 'ESCALATED' ? 'text-red-600' : 'text-emerald-600'}`}
                          >
                            {item.transition === 'ESCALATED' ? '↑' : '↓'}
                          </span>
                          <LevelChip level={item.levelAfter} />
                        </span>
                        <span className="mt-0.5 block text-xs tabular-nums text-slate-400">
                          {item.effectiveAt.slice(0, 10)}
                        </span>
                      </td>
                      <td className="px-2 py-2 text-xs text-slate-700">
                        {item.improvement || '—'}
                        {editable && (
                          <button
                            type="button"
                            aria-expanded={expanded}
                            onClick={(e) => {
                              e.stopPropagation()
                              setOpenRow(expanded ? null : `${rowKey}|${idx}`)
                            }}
                            title="點擊設定緊急措施分類"
                            className={`mt-1 block w-fit rounded px-1.5 py-0.5 text-left text-[11px] ring-1 ring-inset ${
                              measure ? 'bg-sky-50 text-sky-800 ring-sky-200' : 'bg-white text-slate-500 ring-slate-300'
                            } hover:ring-slate-500`}
                          >
                            {expanded ? '▾ ' : '▸ '}
                            {measureSummary(measure)}
                          </button>
                        )}
                      </td>
                      {escalated && (
                        <td className="px-2 py-2 text-right tabular-nums text-slate-600">{item.complaintCount ?? 0}</td>
                      )}
                      <td className="whitespace-nowrap px-2 py-2 text-xs tabular-nums text-slate-600">
                        {item.improvedAt ? item.improvedAt.slice(0, 10) : '—'}
                        {item.improvePlanned && (
                          <span className="mt-0.5 block w-fit rounded border border-dashed border-emerald-400 px-1 text-[10px] text-emerald-700">
                            預計改善
                          </span>
                        )}
                      </td>
                    </tr>
                    {expanded && (
                      <tr className="border-b border-slate-200 bg-slate-50">
                        <td colSpan={columns} className="px-3 py-3">
                          <EmergencyMeasureEditor
                            target={{
                              repairSerial: item.repairSerial!,
                              kpovNo: item.kpovNo,
                              equipmentCode: item.equipmentCode,
                            }}
                            measure={measure}
                            onSaved={(m) => setSaved((prev) => ({ ...prev, [rowKey]: m }))}
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {data && data.total > 0 && (
        <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
          <button
            type="button"
            disabled={data.page <= 1}
            onClick={() => onPageChange(data.page - 1)}
            className="rounded border border-slate-300 px-2.5 py-1 hover:bg-slate-50 disabled:opacity-40"
          >
            上一頁
          </button>
          <span className="tabular-nums">
            第 {data.page} / {data.pages} 頁・共 {data.total} 筆
          </span>
          <button
            type="button"
            disabled={data.page >= data.pages}
            onClick={() => onPageChange(data.page + 1)}
            className="rounded border border-slate-300 px-2.5 py-1 hover:bg-slate-50 disabled:opacity-40"
          >
            下一頁
          </button>
        </div>
      )}
    </div>
  )
}
