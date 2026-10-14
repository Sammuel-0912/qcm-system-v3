import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { arApi, type ArInspectionRow, type ArStat } from '../api/arClient'
import { AppShell } from '../components/AppShell'
import { AR_MARKER_ENABLED } from '../features'

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

export default function ArDashboardPage() {
  const [stats, setStats] = useState<ArStat[]>([])
  const [rows, setRows] = useState<ArInspectionRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [markerId, setMarkerId] = useState('')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [s, r] = await Promise.all([
        arApi.stats(),
        arApi.results({
          markerId: markerId === '' ? undefined : Number(markerId),
          start: start || undefined,
          end: end || undefined,
        }),
      ])
      setStats(s)
      setRows(r.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入失敗')
    } finally {
      setLoading(false)
    }
  }, [markerId, start, end])

  useEffect(() => {
    void load()
  }, [load])

  async function remove(id: number) {
    if (!window.confirm('確定要刪除這筆點檢紀錄？刪除後無法復原。')) return
    try {
      await arApi.deleteResult(id)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : '刪除失敗')
    }
  }

  const actions = (
    <>
      {AR_MARKER_ENABLED ? (
        <Link
          to="/ar/inspect"
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700"
        >
          開始點檢
        </Link>
      ) : (
        <Link
          to="/ar/photo"
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700"
        >
          拍照點檢
        </Link>
      )}
      <a
        href={arApi.exportUrl()}
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

  return (
    <AppShell title="AR 點檢儀表板" actions={actions}>
      <main className="mx-auto max-w-7xl space-y-6 px-6 py-6">
        {error && (
          <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <section>
          <h2 className="mb-3 text-xs font-medium uppercase tracking-wide text-slate-400">
            設備良率總覽
          </h2>
          {loading && stats.length === 0 ? (
            <p className="text-sm text-slate-500">載入中…</p>
          ) : stats.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-200 py-10 text-center">
              <p className="text-sm text-slate-500">尚無點檢紀錄</p>
              <p className="mt-1 text-xs text-slate-400">
                {AR_MARKER_ENABLED ? (
                  <>
                    先到<Link to="/ar/devices" className="mx-1 underline">設備管理</Link>
                    建立設備與 marker，再用 AR 掃描點檢
                  </>
                ) : (
                  <>
                    到<Link to="/ar/photo" className="mx-1 underline">拍照點檢</Link>上傳照片即可記錄點檢
                  </>
                )}
              </p>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {stats.map((s) => (
                <div key={s.markerId} className={`rounded-lg border p-4 ${rateTone(s.okRate)}`}>
                  <div className="flex items-baseline justify-between gap-2">
                    <h3 className="truncate text-sm font-semibold text-slate-800">{s.deviceName}</h3>
                    <span className="shrink-0 font-mono text-xs text-slate-400">#{s.markerId}</span>
                  </div>
                  <div className={`mt-2 text-3xl font-bold tabular-nums ${rateText(s.okRate)}`}>
                    {(s.okRate * 100).toFixed(1)}%
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                    <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-emerald-700">
                      正常 {s.okCount}
                    </span>
                    <span className="rounded bg-amber-100 px-1.5 py-0.5 text-amber-700">
                      異常 {s.warnCount}
                    </span>
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
              <span className="mb-1 block text-xs font-medium text-slate-500">設備</span>
              <select
                value={markerId}
                onChange={(e) => setMarkerId(e.target.value)}
                className="min-w-[180px] rounded-md border border-slate-300 px-3 py-2 text-sm"
              >
                <option value="">全部設備</option>
                {stats.map((s) => (
                  <option key={s.markerId} value={s.markerId}>
                    {s.deviceName}
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
            {(markerId || start || end) && (
              <button
                onClick={() => {
                  setMarkerId('')
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
            <p className="py-8 text-center text-sm text-slate-500">
              {markerId || start || end ? '沒有符合條件的紀錄' : '尚無點檢紀錄'}
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-400">
                  <th className="py-2 pr-2 font-medium">設備</th>
                  <th className="py-2 pr-2 font-medium">狀態</th>
                  <th className="py-2 pr-2 font-medium">點檢時間</th>
                  <th className="py-2 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b border-slate-100">
                    <td className="py-2 pr-2">
                      <span className="text-slate-800">{r.deviceName}</span>
                      <span className="ml-1.5 font-mono text-xs text-slate-400">#{r.markerId}</span>
                      {r.checkContent && (
                        <span className="block text-xs text-slate-500">
                          {r.kpovNo} · {r.checkContent}
                        </span>
                      )}
                    </td>
                    <td className="py-2 pr-2">
                      <StatusBadge status={r.status} />
                    </td>
                    <td className="py-2 pr-2 tabular-nums text-slate-500">
                      {r.inspectedAt.slice(0, 19).replace('T', ' ')}
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
          )}
        </section>
      </main>
    </AppShell>
  )
}
