import { useCallback, useEffect, useState } from 'react'

import { api, type Paged, type RepairRow } from '../api/client'
import { AppShell } from '../components/AppShell'
import { LevelChange } from '../components/LevelChip'
import { Pager, SearchBox } from '../components/ListToolbar'

function stamp(value: string | null) {
  return value ? value.slice(0, 16).replace('T', ' ') : '—'
}

/** 製程清單：修護報表的維修紀錄 */
export default function ProcessPage() {
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<Paged<RepairRow> | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .repairs({ q: q || undefined, page })
      .then((d) => {
        setData(d)
        setError(null)
      })
      .catch((err) => setError(err instanceof Error ? err.message : '載入失敗'))
  }, [q, page])

  const onSearch = useCallback((value: string) => {
    setQ(value)
    setPage(1)
  }, [])

  return (
    <AppShell title="製程清單">
      <main className="mx-auto max-w-7xl space-y-4 px-6 py-6">
        <SearchBox onSearch={onSearch} placeholder="搜尋序號、機種、站別、設備ID、KPOV、不良描述…" />
        {error && <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-700 text-xs text-white">
              <tr>
                {['測試時間', '序號', '機種', '線別', '站別', '設備ID', 'KPOV', '產品不良描述', '改善措施', '改善時間', 'Level 基準→現況'].map(
                  (h) => (
                    <th key={h} className="whitespace-nowrap px-3 py-2 font-medium">
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {data?.items.map((r) => (
                <tr key={r.id} className="border-b border-slate-100 align-top">
                  <td className="whitespace-nowrap px-3 py-2 tabular-nums">{stamp(r.testedAt)}</td>
                  <td className="px-3 py-2 font-mono text-xs">{r.serialNo}</td>
                  <td className="px-3 py-2 text-xs">{r.productModel}</td>
                  <td className="px-3 py-2 text-xs">{r.line}</td>
                  <td className="px-3 py-2">{r.station}</td>
                  <td className="px-3 py-2 font-mono text-xs">{r.equipmentCode}</td>
                  <td className="px-3 py-2">
                    <span className="block">{r.kpovName ?? '—'}</span>
                    <span className="font-mono text-xs text-slate-400">{r.kpovNo}</span>
                  </td>
                  <td className="max-w-xs px-3 py-2 text-xs">{r.defectDesc}</td>
                  <td className="max-w-xs px-3 py-2 text-xs">{r.improvement ?? '—'}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-xs tabular-nums">
                    {r.improvedAt ? r.improvedAt.slice(0, 10) : '—'}
                    {r.improvePlanned && (
                      <span className="mt-0.5 block w-fit rounded border border-dashed border-emerald-400 px-1 text-[10px] text-emerald-700">
                        預計改善
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <LevelChange before={r.levelBefore} after={r.levelAfter} />
                  </td>
                </tr>
              ))}
              {data && data.items.length === 0 && (
                <tr>
                  <td colSpan={11} className="py-8 text-center text-slate-400">
                    沒有符合的維修紀錄
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {data && data.total > 0 && <Pager data={data} onPageChange={setPage} />}
      </main>
    </AppShell>
  )
}
