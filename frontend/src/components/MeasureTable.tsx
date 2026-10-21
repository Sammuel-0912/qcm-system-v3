import { useState } from 'react'

import type { MeasureRow, Paged, TimedText } from '../api/client'
import { formatLocalDateTime } from '../utils/datetime'
import { LevelChange, LevelChip } from './LevelChip'

type Props<T extends MeasureRow> = {
  data: Paged<T> | null
  onPageChange: (page: number) => void
  /** 點列開明細側欄（8D 明細／等級歷程）；只有帶 repairId 或 complaintId 的列可點 */
  onOpen?: (row: T) => void
  emptyText: string
  /** 有給標題時顯示標題列；搭配 storageKey 可收折（預設收起、記住展開狀態） */
  title?: string
  storageKey?: string
}

const HEADERS = [
  '高風險站別',
  '高風險KPOV',
  'Level 等級變化(原)',
  '緊急措施',
  '長期措施',
  '措施層別',
  'Level 等級變化(變化後)',
  '改善時間',
  '客訴筆數',
]

function day(value: string | null) {
  return value ? value.slice(0, 10) : null
}

function readOpen(key: string): boolean {
  try {
    return window.localStorage.getItem(key) === 'open'
  } catch {
    return false
  }
}

function writeOpen(key: string, open: boolean) {
  try {
    window.localStorage.setItem(key, open ? 'open' : 'closed')
  } catch {
    // 無法存取瀏覽器儲存（私密模式等）時只是不記住，不影響使用
  }
}

/** 措施文字＋下方日期（緊急措施為紅字緊急措施時間；長期措施為改善時間） */
function Timed({ value, tone }: { value: TimedText; tone: string }) {
  return (
    <>
      <span className="line-clamp-3 whitespace-pre-line" title={value.text ?? undefined}>
        {value.text || '—'}
      </span>
      {value.at && <span className={`mt-0.5 block tabular-nums ${tone}`}>{day(value.at)}</span>}
    </>
  )
}

/** Level(原)：客訴只有改善前單一等級（before 為 null），只畫一個色塊 */
function OrigLevel({ shift }: { shift: MeasureRow['levelOrig'] }) {
  if (!shift) return <span className="text-slate-400">—</span>
  if (shift.before === null) return <LevelChip level={shift.after} />
  return <LevelChange before={shift.before} after={shift.after} />
}

/**
 * 四張措施表共用：等級異動總覽（高風險／已改善）、客訴問題追蹤、製程問題追蹤。
 * 欄位：高風險站別｜高風險KPOV｜Level(原)｜緊急措施｜長期措施｜措施層別｜Level(變化後)｜改善時間｜客訴筆數
 */
export function MeasureTable<T extends MeasureRow>({
  data,
  onPageChange,
  onOpen,
  emptyText,
  title,
  storageKey,
}: Props<T>) {
  const collapsible = Boolean(title && storageKey)
  const [open, setOpen] = useState(() => (storageKey ? readOpen(storageKey) : true))

  const toggle = () =>
    setOpen((v) => {
      if (storageKey) writeOpen(storageKey, !v)
      return !v
    })

  const body = !data ? (
    <p className="py-4 text-center text-sm text-slate-400">載入中…</p>
  ) : data.items.length === 0 ? (
    <p className="py-4 text-center text-sm text-slate-400">{emptyText}</p>
  ) : (
    <div className="overflow-x-auto">
      {/* 九欄在窄欄位（右側總覽）會擠成一字一行：給最小寬度，不夠時在框內左右捲動 */}
      <table className="w-full min-w-[60rem] text-left text-sm">
        <thead className="bg-[#1F5C7A] text-xs text-white">
          <tr>
            {HEADERS.map((h) => (
              <th key={h} className="whitespace-nowrap px-2 py-2 text-center font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.items.map((row, idx) => {
            const rowKey = `${row.repairId ?? ''}|${row.complaintId ?? ''}|${row.kpovNo}|${idx}`
            const clickable = Boolean(onOpen && (row.repairId || row.complaintId))
            const layerText = row.layer.summary
            return (
                <tr
                  key={rowKey}
                  onClick={clickable ? () => onOpen!(row) : undefined}
                  className={`border-b border-slate-100 align-top ${clickable ? 'cursor-pointer hover:bg-slate-50' : ''}`}
                  title={clickable ? '點擊查看 8D 明細與等級歷程' : undefined}
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
                  <td className="whitespace-nowrap px-2 py-2">
                    <OrigLevel shift={row.levelOrig} />
                    {row.occurredAt && (
                      <span className="mt-0.5 block text-xs tabular-nums text-slate-400">{formatLocalDateTime(row.occurredAt).slice(0, 10)}</span>
                    )}
                  </td>
                  <td className="max-w-[14rem] px-2 py-2 text-xs text-slate-700">
                    <Timed value={row.emergency} tone="text-red-600" />
                  </td>
                  <td className="max-w-[14rem] px-2 py-2 text-xs text-slate-700">
                    <Timed value={row.longTerm} tone="text-slate-500" />
                  </td>
                  <td className="px-2 py-2 text-xs">
                    <span className={layerText ? 'text-slate-700' : 'text-slate-400'}>{layerText ?? '—'}</span>
                  </td>
                  <td className="whitespace-nowrap px-2 py-2">
                    {row.levelChanged ? (
                      <>
                        <LevelChange before={row.levelChanged.before} after={row.levelChanged.after} />
                        {row.levelChanged.planned && (
                          <span className="mt-0.5 block w-fit rounded border border-dashed border-emerald-400 px-1 text-[10px] text-emerald-700">
                            預計
                          </span>
                        )}
                      </>
                    ) : (
                      <span className="text-slate-400">—</span>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-2 py-2 text-xs tabular-nums text-slate-600">
                    {day(row.improvedAt) ?? '—'}
                    {row.improvePlanned && (
                      <span
                        className={`mt-0.5 block w-fit rounded border border-dashed px-1 text-[10px] ${
                          row.improveOverdue ? 'border-red-400 text-red-600' : 'border-emerald-400 text-emerald-700'
                        }`}
                      >
                        {row.improveOverdue ? '預計・已逾期' : '預計改善'}
                      </span>
                    )}
                  </td>
                  <td className="px-2 py-2 text-center tabular-nums text-slate-700">{row.complaintCount}</td>
                </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )

  const pager = data && data.total > data.pageSize && (
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
  )

  if (!title) {
    return (
      <div>
        {body}
        {pager}
      </div>
    )
  }

  const bodyId = `${storageKey ?? title}-body`
  return (
    <div>
      <h3>
        {collapsible ? (
          <button
            type="button"
            onClick={toggle}
            aria-expanded={open}
            aria-controls={bodyId}
            className="flex w-full items-center gap-2 rounded-md py-1 text-left text-sm font-semibold text-slate-800 hover:text-slate-950"
          >
            <span className={`inline-block text-xs text-slate-400 transition-transform ${open ? 'rotate-90' : ''}`}>
              ▶
            </span>
            {title}
            {data && <span className="text-xs font-normal text-slate-400">共 {data.total} 筆</span>}
            <span className="ml-auto text-xs font-normal text-slate-400">{open ? '收起' : '展開'}</span>
          </button>
        ) : (
          <span className="text-sm font-semibold text-slate-800">{title}</span>
        )}
      </h3>
      {open && (
        <div id={bodyId} className="mt-2">
          {body}
          {pager}
        </div>
      )}
    </div>
  )
}
