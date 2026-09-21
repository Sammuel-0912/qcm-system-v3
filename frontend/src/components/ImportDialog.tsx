import { useState } from 'react'

import { api } from '../api/client'

type Props = { onClose: () => void; onImported: () => void }

type Report = {
  rowCounts: Record<string, number>
  levelMismatches: { kpovNo: string; equipmentCode: string; sourceLevel: string; computedLevel: string }[]
  unknownDetectionMethods: { method: string; axis: string; serialNo: string }[]
  unmatchedKeys: { table: string; equipmentCode?: string; reason?: string }[]
  skippedRepairRows: { row: number; reason: string }[]
  levelEventSummary: { total: number; escalated: number; improved: number; unchanged: number }
  warnings: string[]
}

const COUNT_LABELS: Record<string, string> = {
  detectionMethods: '偵測方式字典',
  equipment: '設備',
  errorCodes: '錯誤碼',
  kpov: 'KPOV',
  alarms: '告警事件',
  repairs: '維修紀錄',
  levelEvents: '等級異動事件',
}

export function ImportDialog({ onClose, onImported }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [report, setReport] = useState<Report | null>(null)

  async function handleFile(file: File) {
    setBusy(true)
    setError(null)
    setReport(null)
    try {
      const result = await api.import(file)
      setReport(result.report)
      onImported()
    } catch (err) {
      setError(err instanceof Error ? err.message : '匯入失敗')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-lg bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900">匯入資料</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700" aria-label="關閉">
            ✕
          </button>
        </div>

        {!report && (
          <>
            <p className="mb-4 text-sm text-slate-600">
              上傳與 <code className="rounded bg-slate-100 px-1">raw_data.xlsx</code> 同格式的 Excel
              檔。匯入為單一交易，失敗不會留下半套資料。
            </p>
            <input
              type="file"
              accept=".xlsx,.xlsm"
              disabled={busy}
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) handleFile(file)
              }}
              className="w-full rounded-md border border-dashed border-slate-300 p-6 text-sm"
            />
            {busy && <p className="mt-3 text-sm text-slate-500">匯入中，請稍候…</p>}
          </>
        )}

        {error && (
          <div className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {report && (
          <div className="space-y-4 text-sm">
            <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-emerald-800">
              匯入成功。
            </div>

            <div>
              <h3 className="mb-2 font-medium text-slate-700">匯入筆數</h3>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {Object.entries(report.rowCounts).map(([key, value]) => (
                  <div key={key} className="rounded border border-slate-200 p-2">
                    <div className="text-lg font-semibold tabular-nums text-slate-800">{value}</div>
                    <div className="text-xs text-slate-500">{COUNT_LABELS[key] ?? key}</div>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h3 className="mb-2 font-medium text-slate-700">等級異動</h3>
              <p className="text-slate-600">
                共 {report.levelEventSummary.total} 筆 — 惡化 {report.levelEventSummary.escalated}、改善{' '}
                {report.levelEventSummary.improved}、同級 {report.levelEventSummary.unchanged}
              </p>
            </div>

            {report.levelMismatches.length > 0 && (
              <div>
                <h3 className="mb-2 font-medium text-amber-700">
                  等級與來源欄位不符（{report.levelMismatches.length} 筆，已以系統計算為準）
                </h3>
                <ul className="space-y-1 text-xs text-slate-600">
                  {report.levelMismatches.map((m, i) => (
                    <li key={i} className="rounded bg-amber-50 px-2 py-1">
                      {m.kpovNo} · {m.equipmentCode}：來源 {m.sourceLevel} → 實際 {m.computedLevel}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {report.unknownDetectionMethods.length > 0 && (
              <div>
                <h3 className="mb-2 font-medium text-red-700">
                  偵測方式查無字典（{report.unknownDetectionMethods.length} 筆，未產生事件）
                </h3>
                <ul className="space-y-1 text-xs text-slate-600">
                  {report.unknownDetectionMethods.map((m, i) => (
                    <li key={i} className="rounded bg-red-50 px-2 py-1">
                      {m.serialNo} · {m.axis}：{m.method}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {report.warnings.length > 0 && (
              <div>
                <h3 className="mb-2 font-medium text-slate-700">提醒</h3>
                <ul className="space-y-1 text-xs text-slate-500">
                  {report.warnings.map((w, i) => (
                    <li key={i}>· {w}</li>
                  ))}
                </ul>
              </div>
            )}

            <button
              onClick={onClose}
              className="w-full rounded-md bg-slate-900 py-2 text-sm font-medium text-white hover:bg-slate-700"
            >
              完成
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
