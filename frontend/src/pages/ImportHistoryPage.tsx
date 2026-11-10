import { Fragment, useEffect, useState } from 'react'

import { api, type ImportHistoryRow } from '../api/client'
import { AppShell } from '../components/AppShell'
import { COUNT_LABELS } from '../components/ImportDialog'
import { formatLocalDateTime } from '../utils/datetime'

// 列表上直接顯示的筆數；其餘在展開後列出
const MAIN_COUNTS = ['kpov', 'repairs', 'complaints', 'alarms', 'checkItems', 'levelEvents'] as const
const LABELS: Record<string, string> = { ...COUNT_LABELS, complaints: '客訴', checkItems: '點檢項目' }

/**
 * 匯入歷程（v2.16）：每次匯入數據庫 Excel 留一筆紀錄——時間、檔名、廠／線別、匯入者、是否生效中、各類筆數與匯入警告。
 * 只列自己看得到的廠（最高權限管理者看全部）。
 */
export default function ImportHistoryPage() {
  const [rows, setRows] = useState<ImportHistoryRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<number | null>(null)
  const [dataset, setDataset] = useState('')

  useEffect(() => {
    api
      .importHistory()
      .then(setRows)
      .catch((err) => setError(err instanceof Error ? err.message : '載入失敗'))
  }, [])

  const datasets = [...new Set((rows ?? []).map((r) => r.dataset).filter((d): d is string => Boolean(d)))].sort()
  const shown = (rows ?? []).filter((r) => !dataset || r.dataset === dataset)

  return (
    <AppShell title="匯入歷程">
      <main className="mx-auto max-w-7xl space-y-4 px-6 py-6">
        <div className="flex flex-wrap items-end gap-3">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-500">廠／線別</span>
            <select
              value={dataset}
              onChange={(e) => setDataset(e.target.value)}
              className="min-w-[180px] rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
            >
              <option value="">全部</option>
              {datasets.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
          {rows && <span className="pb-2 text-sm text-slate-500">共 {shown.length} 次匯入</span>}
        </div>
        {error && <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-700 text-xs text-white">
              <tr>
                {['匯入時間', '檔名', '廠／線別', '匯入者', '狀態', ...MAIN_COUNTS.map((k) => LABELS[k] ?? k), '警告', ''].map((h, i) => (
                  <th key={`${h}-${i}`} className="whitespace-nowrap px-3 py-2 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => {
                const expanded = open === r.id
                return (
                  <Fragment key={r.id}>
                    <tr className="border-b border-slate-100 align-top">
                      <td className="whitespace-nowrap px-3 py-2 tabular-nums">{r.importedAt ? formatLocalDateTime(r.importedAt).slice(0, 16) : '—'}</td>
                      <td className="max-w-xs break-all px-3 py-2 text-xs">{r.filename}</td>
                      <td className="whitespace-nowrap px-3 py-2 font-mono text-xs">{r.dataset ?? '—'}</td>
                      <td className="whitespace-nowrap px-3 py-2 text-xs">{r.importedBy ?? '—'}</td>
                      <td className="whitespace-nowrap px-3 py-2">
                        {r.status !== 'success' ? (
                          <span className="rounded bg-red-100 px-1.5 py-0.5 text-xs text-red-700">失敗</span>
                        ) : r.isActive ? (
                          <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-xs font-medium text-emerald-800">生效中</span>
                        ) : (
                          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-500">已被新批次取代</span>
                        )}
                      </td>
                      {MAIN_COUNTS.map((k) => (
                        <td key={k} className="px-3 py-2 text-right tabular-nums">
                          {r.rowCounts[k] ?? '—'}
                        </td>
                      ))}
                      <td className="px-3 py-2 text-right tabular-nums">
                        <span className={r.warnings.length ? 'font-medium text-amber-700' : 'text-slate-400'}>{r.warnings.length}</span>
                      </td>
                      <td className="whitespace-nowrap px-3 py-2">
                        <button type="button" onClick={() => setOpen(expanded ? null : r.id)} className="text-xs text-[#0086DB] hover:underline">
                          {expanded ? '收合' : '明細'}
                        </button>
                      </td>
                    </tr>
                    {expanded && (
                      <tr className="border-b border-slate-100 bg-slate-50">
                        <td colSpan={MAIN_COUNTS.length + 7} className="px-4 py-3">
                          <ImportDetail row={r} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
              {rows && shown.length === 0 && (
                <tr>
                  <td colSpan={MAIN_COUNTS.length + 7} className="py-8 text-center text-slate-400">
                    還沒有匯入紀錄
                  </td>
                </tr>
              )}
              {!rows && !error && (
                <tr>
                  <td colSpan={MAIN_COUNTS.length + 7} className="py-8 text-center text-slate-400">
                    載入中…
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </main>
    </AppShell>
  )
}

function ImportDetail({ row }: { row: ImportHistoryRow }) {
  const summary = row.levelEventSummary
  return (
    <div className="space-y-3 text-sm">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
        {Object.entries(row.rowCounts).map(([key, value]) => (
          <div key={key} className="rounded border border-slate-200 bg-white p-2">
            <div className="font-semibold tabular-nums text-slate-800">{value}</div>
            <div className="text-xs text-slate-500">{LABELS[key] ?? key}</div>
          </div>
        ))}
      </div>
      {summary && (
        <p className="text-slate-600">
          等級異動 {summary.total} 筆：惡化 {summary.escalated}、改善 {summary.improved}、不變 {summary.unchanged}
          {row.unmatchedCount > 0 && `；對不到的資料 ${row.unmatchedCount} 筆`}
          {row.skippedRepairCount > 0 && `；略過的維修列 ${row.skippedRepairCount} 筆`}
        </p>
      )}
      <div>
        <h3 className="mb-1 font-medium text-slate-700">匯入警告（{row.warnings.length}）</h3>
        {row.warnings.length === 0 ? (
          <p className="text-slate-400">沒有警告</p>
        ) : (
          <ul className="max-h-64 list-disc space-y-0.5 overflow-y-auto pl-5 text-xs text-amber-800">
            {row.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
