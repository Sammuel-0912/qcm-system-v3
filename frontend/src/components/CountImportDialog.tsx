import { useEffect, useState } from 'react'

import { api, type CountImportResult, type CountImportSummary } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { formatLocalDateTime } from '../utils/datetime'

const day = (iso: string) => formatLocalDateTime(iso).slice(0, 10)

/**
 * 匯入歷史點檢數量（spec §19，最高權限管理者）：重新部署後補回點檢看板站別卡片的正常／異常次數。
 * 只累加卡片，不會出現在點檢紀錄、趨勢圖或點檢監控。
 */
export function CountImportDialog({ onClose }: { onClose: () => void }) {
  const { dataset } = useAuth()
  const [summary, setSummary] = useState<CountImportSummary | null>(null)
  const [result, setResult] = useState<CountImportResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmClear, setConfirmClear] = useState(false)

  useEffect(() => {
    api.countImportSummary().then(setSummary).catch(() => setSummary(null))
  }, [])

  async function upload(file: File) {
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const r = await api.countImport(file)
      setResult(r)
      setSummary(r.summary)
    } catch (err) {
      setError(err instanceof Error ? err.message : '匯入失敗')
    } finally {
      setBusy(false)
    }
  }

  async function clear() {
    setBusy(true)
    setError(null)
    try {
      await api.clearCountImport()
      setResult(null)
      setConfirmClear(false)
      setSummary(await api.countImportSummary())
    } catch (err) {
      setError(err instanceof Error ? err.message : '清除失敗')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true">
      <div className="max-h-[85vh] w-full max-w-2xl space-y-4 overflow-y-auto rounded-lg bg-white p-6 shadow-xl">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900">匯入歷史點檢數量</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700" aria-label="關閉">
            ✕
          </button>
        </div>

        <div className="space-y-2 text-sm text-slate-600">
          <p>
            重新部署後拍照點檢紀錄會從零開始；把舊系統匯出的點檢紀錄 Excel 匯入，即可補回<b>站別卡片的正常／異常次數</b>。
            匯入的資料<b>不會</b>出現在下方點檢紀錄、趨勢圖或點檢監控。
          </p>
          <p className="rounded-md bg-slate-50 px-3 py-2 text-xs">
            格式：直接使用點檢看板「匯出紀錄（含照片）」的檔案（舊版匯出也可）。系統依表頭找欄位，需要
            <b>設備代碼</b>、<b>點檢結果</b>（正常／異常）、<b>點檢時間</b>（廠區時間）；站別、點檢內容選填。
            同一筆（設備＋點檢內容＋點檢時間）已匯入過或系統內已有的會自動略過，重複匯入不會重算。
          </p>
          <p className="text-xs text-slate-500">
            匯入到目前的線：<span className="font-mono text-slate-700">{dataset}</span>
          </p>
        </div>

        <input
          type="file"
          accept=".xlsx,.xlsm"
          disabled={busy}
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) void upload(file)
            e.target.value = ''
          }}
          className="w-full rounded-md border border-dashed border-slate-300 p-5 text-sm"
        />
        {busy && <p className="text-sm text-slate-500">處理中…</p>}
        {error && <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

        {result && (
          <div className="space-y-2 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
            <p>
              <b>{result.source}</b>：新增 <b className="tabular-nums">{result.added}</b> 筆（正常 {result.addedOk}・異常{' '}
              {result.addedWarn}）
              {result.duplicates > 0 && <span className="text-slate-600">，重複略過 {result.duplicates} 筆</span>}
              {result.invalid > 0 && <span className="text-amber-700">，無法辨識略過 {result.invalid} 筆</span>}
            </p>
            {result.invalidReasons.length > 0 && (
              <ul className="list-inside list-disc text-xs text-amber-700">
                {result.invalidReasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            )}
            {result.stations.length > 0 && (
              <table className="w-full text-xs">
                <thead className="text-left text-slate-500">
                  <tr>
                    <th className="py-1 font-medium">站別</th>
                    <th className="py-1 font-medium">設備代碼</th>
                    <th className="py-1 text-right font-medium">新增正常</th>
                    <th className="py-1 text-right font-medium">新增異常</th>
                  </tr>
                </thead>
                <tbody>
                  {result.stations.map((s) => (
                    <tr key={s.equipmentCode} className="border-t border-emerald-100">
                      <td className="py-1">{s.station}</td>
                      <td className="py-1 font-mono">{s.equipmentCode}</td>
                      <td className="py-1 text-right tabular-nums">{s.okCount}</td>
                      <td className="py-1 text-right tabular-nums">{s.warnCount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        <div className="border-t border-slate-100 pt-3">
          <h3 className="mb-2 text-sm font-medium text-slate-700">
            這條線已匯入：<span className="tabular-nums">{summary?.total ?? 0}</span> 次
          </h3>
          {summary && summary.files.length > 0 ? (
            <ul className="space-y-1 text-xs text-slate-600">
              {summary.files.map((f) => (
                <li key={f.source ?? ''} className="flex flex-wrap gap-x-3">
                  <span className="font-medium text-slate-700">{f.source ?? '（未命名）'}</span>
                  <span className="tabular-nums">
                    {f.count} 次（正常 {f.okCount}・異常 {f.warnCount}）
                  </span>
                  <span className="tabular-nums text-slate-400">
                    點檢 {day(f.from)}～{day(f.to)}・{formatLocalDateTime(f.importedAt).slice(0, 16)} 由 {f.importedBy ?? '—'} 匯入
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-slate-400">尚未匯入</p>
          )}
          {summary && summary.total > 0 && (
            <div className="mt-3">
              {confirmClear ? (
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="text-red-700">確定清除這條線全部 {summary.total} 次匯入數量？（拍照點檢紀錄不受影響）</span>
                  <button
                    onClick={() => void clear()}
                    disabled={busy}
                    className="rounded-md bg-red-600 px-3 py-1 text-white hover:bg-red-700 disabled:opacity-60"
                  >
                    確定清除
                  </button>
                  <button onClick={() => setConfirmClear(false)} className="rounded-md border border-slate-300 px-3 py-1">
                    取消
                  </button>
                </div>
              ) : (
                <button onClick={() => setConfirmClear(true)} className="text-sm text-red-600 hover:underline">
                  清除匯入數量
                </button>
              )}
            </div>
          )}
        </div>

        <button onClick={onClose} className="w-full rounded-md bg-slate-900 py-2 text-sm font-medium text-white hover:bg-slate-700">
          完成
        </button>
      </div>
    </div>
  )
}
