import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { api, type PhotoInspection, type PhotoInspectionStat } from '../api/client'
import { AppShell } from '../components/AppShell'
import { formatLocalDateTime, localInputToIso } from '../utils/datetime'

function rateTone(rate: number): string {
  if (rate >= 0.9) return 'border-emerald-200 bg-emerald-50'
  if (rate >= 0.6) return 'border-amber-200 bg-amber-50'
  return 'border-red-200 bg-red-50'
}

function rateText(rate: number): string {
  if (rate >= 0.9) return 'text-emerald-700'
  if (rate >= 0.6) return 'text-amber-700'
  return 'text-red-700'
}

function StatusBadge({ status }: { status: 'ok' | 'warn' }) {
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-semibold ${
        status === 'ok' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'
      }`}
    >
      {status === 'ok' ? '正常' : '異常'}
    </span>
  )
}

/** 縮圖；照片檔遺失（例如 volume 未保留）時顯示文字，而不是破圖 */
function Thumbnail({ record, onOpen }: { record: PhotoInspection; onOpen: () => void }) {
  const [broken, setBroken] = useState(false)
  if (broken) return <span className="text-xs text-slate-400">照片遺失</span>
  return (
    <button
      type="button"
      onClick={onOpen}
      title="點擊放大照片"
      className="block h-12 w-12 overflow-hidden rounded border border-slate-200 bg-slate-100 transition hover:ring-2 hover:ring-[#0086DB]"
    >
      <img
        src={record.photoUrl}
        alt="點檢照片縮圖"
        loading="lazy"
        onError={() => setBroken(true)}
        className="h-full w-full object-cover"
      />
    </button>
  )
}

/** 照片大圖：點背景、✕ 或按 Esc 關閉 */
function PhotoViewer({ record, onClose }: { record: PhotoInspection; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="點檢照片"
    >
      <div
        className="flex max-h-full w-full max-w-4xl flex-col overflow-hidden rounded-lg bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-4 py-3">
          <div className="min-w-0 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-slate-800">{record.station}</span>
              <StatusBadge status={record.status} />
              <span className="tabular-nums text-slate-500">{formatLocalDateTime(record.inspectedAt)}</span>
            </div>
            <p className="mt-0.5 text-xs text-slate-500">
              {record.kpovNo ? `${record.kpovNo} · ` : ''}
              {record.checkContent}
              {record.note && <span className="ml-1 text-amber-700">（{record.note}）</span>}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="關閉"
            className="shrink-0 rounded px-2 py-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
          >
            ✕
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto bg-slate-900">
          <img src={record.photoUrl} alt={`${record.station} 點檢照片`} className="mx-auto max-h-[75vh] object-contain" />
        </div>
        <div className="border-t border-slate-200 px-4 py-2 text-right">
          <a
            href={record.photoUrl}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-sky-700 underline underline-offset-2"
          >
            在新分頁開啟原圖
          </a>
        </div>
      </div>
    </div>
  )
}

/** 點檢儀表板：拍照點檢的良率統計與紀錄（含照片）。AR 掃碼紀錄不在此顯示。 */
export default function ArDashboardPage() {
  const [stats, setStats] = useState<PhotoInspectionStat[]>([])
  const [rows, setRows] = useState<PhotoInspection[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [viewing, setViewing] = useState<PhotoInspection | null>(null)

  const [equipmentCode, setEquipmentCode] = useState('')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [s, r] = await Promise.all([
        api.photoInspectionStats(),
        api.photoInspections({
          equipmentCode: equipmentCode || undefined,
          // 輸入框是本地時間，轉成帶時區的 ISO，後端才能正確和 UTC 比較
          start: localInputToIso(start),
          end: localInputToIso(end),
        }),
      ])
      setStats(s)
      setRows(r.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入失敗')
    } finally {
      setLoading(false)
    }
  }, [equipmentCode, start, end])

  useEffect(() => {
    void load()
  }, [load])

  async function remove(id: number) {
    if (!window.confirm('確定要刪除這筆點檢紀錄？照片會一併刪除，且無法復原。')) return
    try {
      await api.deletePhotoInspection(id)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : '刪除失敗')
    }
  }

  const actions = (
    <>
      <Link
        to="/ar/photo"
        className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700"
      >
        拍照點檢
      </Link>
      <a
        href={api.photoInspectionExportUrl()}
        className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 transition hover:border-slate-400 hover:bg-slate-50"
      >
        匯出報表
      </a>
      <button
        onClick={() => void load()}
        className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 transition hover:border-slate-400 hover:bg-slate-50"
      >
        重新整理
      </button>
    </>
  )

  const filtered = Boolean(equipmentCode || start || end)

  return (
    <AppShell title="點檢儀表板" actions={actions}>
      <main className="mx-auto max-w-7xl space-y-6 px-6 py-6">
        {error && (
          <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
        )}

        <section>
          <h2 className="mb-3 text-xs font-medium uppercase tracking-wide text-slate-400">站別良率總覽</h2>
          {loading && stats.length === 0 ? (
            <p className="text-sm text-slate-500">載入中…</p>
          ) : stats.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-200 py-10 text-center">
              <p className="text-sm text-slate-500">尚無點檢紀錄</p>
              <p className="mt-1 text-xs text-slate-400">
                到<Link to="/ar/photo" className="mx-1 underline">拍照點檢</Link>上傳照片即可記錄點檢
              </p>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {stats.map((s) => (
                <div key={s.equipmentCode} className={`rounded-lg border p-4 ${rateTone(s.okRate)}`}>
                  <div className="flex items-baseline justify-between gap-2">
                    <h3 className="truncate text-sm font-semibold text-slate-800">{s.station}</h3>
                    <span className="shrink-0 font-mono text-xs text-slate-400">{s.equipmentCode}</span>
                  </div>
                  <div className={`mt-2 text-3xl font-bold tabular-nums ${rateText(s.okRate)}`}>
                    {(s.okRate * 100).toFixed(1)}%
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                    <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-emerald-700">正常 {s.okCount}</span>
                    <span className="rounded bg-amber-100 px-1.5 py-0.5 text-amber-700">異常 {s.warnCount}</span>
                    <span className="text-slate-500">共 {s.total} 次</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="mb-3 text-base font-semibold text-slate-800">點檢紀錄</h2>

          <div className="mb-4 flex flex-wrap items-end gap-3">
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-slate-500">站別</span>
              <select
                value={equipmentCode}
                onChange={(e) => setEquipmentCode(e.target.value)}
                className="min-w-[180px] rounded-md border border-slate-300 px-3 py-2 text-sm"
              >
                <option value="">全部站別</option>
                {stats.map((s) => (
                  <option key={s.equipmentCode} value={s.equipmentCode}>
                    {s.station}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-slate-500">開始時間</span>
              <input
                type="datetime-local"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                className="rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-slate-500">結束時間</span>
              <input
                type="datetime-local"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                className="rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </label>
            {filtered && (
              <button
                onClick={() => {
                  setEquipmentCode('')
                  setStart('')
                  setEnd('')
                }}
                className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
              >
                清除篩選
              </button>
            )}
          </div>

          {rows.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-500">{filtered ? '沒有符合條件的紀錄' : '尚無點檢紀錄'}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[40rem] text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-400">
                    <th className="py-2 pr-2 font-medium">站別</th>
                    <th className="py-2 pr-2 font-medium">狀態</th>
                    <th className="py-2 pr-2 font-medium">點檢時間</th>
                    <th className="py-2 pr-2 font-medium">照片</th>
                    <th className="py-2 text-right font-medium">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id} className="border-b border-slate-100 align-middle">
                      <td className="py-2 pr-2">
                        <span className="text-slate-800">{r.station}</span>
                        <span className="ml-1.5 font-mono text-xs text-slate-400">{r.equipmentCode}</span>
                        <span className="block text-xs text-slate-500">
                          {r.kpovNo ? `${r.kpovNo} · ` : ''}
                          {r.checkContent}
                        </span>
                        {r.note && <span className="block text-xs text-amber-700">備註：{r.note}</span>}
                      </td>
                      <td className="py-2 pr-2">
                        <StatusBadge status={r.status} />
                      </td>
                      <td className="whitespace-nowrap py-2 pr-2 tabular-nums text-slate-500">
                        {formatLocalDateTime(r.inspectedAt)}
                      </td>
                      <td className="py-2 pr-2">
                        <Thumbnail record={r} onOpen={() => setViewing(r)} />
                      </td>
                      <td className="py-2 text-right">
                        <button
                          onClick={() => void remove(r.id)}
                          className="rounded px-2 py-1 text-xs text-red-600 transition hover:bg-red-50"
                        >
                          刪除
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>

      {viewing && <PhotoViewer record={viewing} onClose={() => setViewing(null)} />}
    </AppShell>
  )
}
