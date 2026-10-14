import type { Paged, TrackingRow } from '../api/client'
import { LevelChange } from './LevelChip'

type Props = {
  title: string
  /** 「客訴筆數」或「維修筆數」 */
  countLabel: string
  data: Paged<TrackingRow> | null
  onPageChange: (page: number) => void
  /** 點列開 KPOV 側欄（僅對應到 KPOV 的列） */
  onSelect?: (kpovNo: string, equipmentCode: string) => void
  emptyText: string
}

/** 客訴問題追蹤／製程問題追蹤共用表格（後端分頁） */
export function TrackingTable({ title, countLabel, data, onPageChange, onSelect, emptyText }: Props) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-slate-800">{title}</h3>
      {!data ? (
        <p className="py-4 text-center text-sm text-slate-400">載入中…</p>
      ) : data.items.length === 0 ? (
        <p className="py-4 text-center text-sm text-slate-400">{emptyText}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-700 text-xs text-white">
              <tr>
                <th className="px-2 py-2 font-medium">站別</th>
                <th className="px-2 py-2 font-medium">KPOV</th>
                <th className="px-2 py-2 text-right font-medium">{countLabel}</th>
                <th className="px-2 py-2 font-medium">改善措施</th>
                <th className="px-2 py-2 font-medium">Level 變化</th>
                <th className="px-2 py-2 font-medium">切入時間</th>
                <th className="px-2 py-2 text-right font-medium">追蹤狀況</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((row, idx) => {
                const clickable = Boolean(onSelect && row.mapped && row.kpovNo && row.equipmentCode)
                return (
                  <tr
                    key={`${row.equipmentCode}-${row.kpovNo}-${row.kpovName}-${idx}`}
                    onClick={clickable ? () => onSelect!(row.kpovNo!, row.equipmentCode!) : undefined}
                    className={`border-b border-slate-100 align-top ${clickable ? 'cursor-pointer hover:bg-slate-50' : ''}`}
                  >
                    <td className="px-2 py-2 text-slate-800">{row.station ?? '—'}</td>
                    <td className="px-2 py-2">
                      <span className="block text-slate-800">{row.kpovName ?? '—'}</span>
                      {row.mapped ? (
                        <span className="font-mono text-xs text-slate-400">{row.kpovNo}</span>
                      ) : (
                        <span className="text-xs text-amber-600" title="來源未填設備ID／KPOV 編號">
                          未對應 KPOV
                        </span>
                      )}
                    </td>
                    <td className="px-2 py-2 text-right font-semibold tabular-nums text-slate-800">{row.count}</td>
                    <td className="max-w-[16rem] px-2 py-2 text-xs text-slate-700">
                      <span className="line-clamp-3" title={row.improvement ?? undefined}>
                        {row.improvement || '—'}
                      </span>
                    </td>
                    <td className="px-2 py-2">
                      <LevelChange before={row.levelBefore} after={row.levelAfter} />
                    </td>
                    <td className="whitespace-nowrap px-2 py-2 text-xs tabular-nums text-slate-600">
                      {row.cutoverAt ? row.cutoverAt.slice(0, 10) : '—'}
                      {row.cutoverPlanned && (
                        <span
                          className={`mt-0.5 block w-fit rounded border border-dashed px-1 text-[10px] ${
                            row.cutoverOverdue ? 'border-red-400 text-red-600' : 'border-emerald-400 text-emerald-700'
                          }`}
                        >
                          {row.cutoverOverdue ? '預計・已逾期' : '預計'}
                        </span>
                      )}
                    </td>
                    <td className="px-2 py-2 text-right tabular-nums text-slate-500">{row.tracking}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      {data && data.total > data.pageSize && (
        <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
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
