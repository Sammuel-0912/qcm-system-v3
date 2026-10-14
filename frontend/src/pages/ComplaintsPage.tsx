import { Fragment, useCallback, useEffect, useState } from 'react'

import { api, type Complaint, type Paged } from '../api/client'
import { AppShell } from '../components/AppShell'
import { LevelChange } from '../components/LevelChip'
import { Pager, SearchBox } from '../components/ListToolbar'

function day(value: string | null) {
  return value ? value.slice(0, 10) : '—'
}

function Detail({ c }: { c: Complaint }) {
  const blocks: { title: string; lines: [string, string | number | null][] }[] = [
    {
      title: '改善前盤查',
      lines: [
        ['Y-CC/SC 檢測項目', c.before.bigYItem],
        ['Y 偵測方式／偵測度', [c.before.bigYMethod, c.before.bigYScore].filter((v) => v !== null).join('／') || null],
        ['產品 KPOV', c.productKpov],
        ['y 偵測方式／偵測度', [c.before.smallYMethod, c.before.smallYScore].filter((v) => v !== null).join('／') || null],
      ],
    },
    {
      title: '客訴原因',
      lines: [
        ['發生原因', c.causeOccur],
        ['流出原因', c.causeEscape],
      ],
    },
    {
      title: '改善對策',
      lines: [
        ['對策內容', c.countermeasure],
        ['預計完成（原文）', c.plannedText],
        ['實際完成（原文）', c.doneText],
      ],
    },
    {
      title: '改善後盤查',
      lines: [
        ['y 偵測方式／偵測度', [c.after.smallYMethod, c.after.smallYScore].filter((v) => v !== null).join('／') || null],
        ['Y 偵測方式／偵測度', [c.after.bigYMethod, c.after.bigYScore].filter((v) => v !== null).join('／') || null],
        ['改善判定', c.verdict],
        ['對應 KPOV', c.kpovNo ? `${c.equipmentCode ?? ''} · ${c.kpovNo}` : '未填（設備ID／KPOV 編號）'],
      ],
    },
  ]
  return (
    <div className="grid gap-4 bg-slate-50 p-4 md:grid-cols-2">
      {blocks.map((b) => (
        <div key={b.title}>
          <h4 className="mb-1.5 text-xs font-semibold text-slate-500">{b.title}</h4>
          <dl className="space-y-1.5 text-sm">
            {b.lines.map(([term, value]) => (
              <div key={term}>
                <dt className="text-xs text-slate-400">{term}</dt>
                <dd className="whitespace-pre-wrap text-slate-800">{value ?? '—'}</dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </div>
  )
}

/** 客訴清單：客訴報表（8D）基本資訊，點列展開原因、對策與改善前後盤查 */
export default function ComplaintsPage() {
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<Paged<Complaint> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<number | null>(null)

  useEffect(() => {
    api
      .complaints({ q: q || undefined, page })
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
    <AppShell title="客訴清單">
      <main className="mx-auto max-w-7xl space-y-4 px-6 py-6">
        <SearchBox onSearch={onSearch} placeholder="搜尋 8D編號、客戶、客訴項目、製程單元、責任人…" />
        {error && <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-700 text-xs text-white">
              <tr>
                {['序號', '8D編號', '日期', '客戶', '類別', '客訴項目', '製程單元', 'Level 改善前→後', '責任人', '預計完成', '實際完成', '有效性'].map(
                  (h) => (
                    <th key={h} className="whitespace-nowrap px-3 py-2 font-medium">
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {data?.items.map((c) => (
                <Fragment key={c.id}>
                  <tr
                    onClick={() => setOpen(open === c.id ? null : c.id)}
                    aria-expanded={open === c.id}
                    className="cursor-pointer border-b border-slate-100 align-top hover:bg-slate-50"
                  >
                    <td className="px-3 py-2 tabular-nums">{c.seq}</td>
                    <td className="px-3 py-2 font-mono text-xs">{c.reportNo ?? '—'}</td>
                    <td className="whitespace-nowrap px-3 py-2 tabular-nums">{day(c.complainedAt)}</td>
                    <td className="px-3 py-2">{c.customer}</td>
                    <td className="px-3 py-2">{c.category}</td>
                    <td className="max-w-xs px-3 py-2">{c.item}</td>
                    <td className="px-3 py-2">{c.processUnit}</td>
                    <td className="px-3 py-2">
                      <LevelChange before={c.levelBefore} after={c.levelAfter} />
                    </td>
                    <td className="whitespace-pre-wrap px-3 py-2 text-xs">{c.owner}</td>
                    <td className="whitespace-nowrap px-3 py-2 tabular-nums">{day(c.plannedAt)}</td>
                    <td className="whitespace-nowrap px-3 py-2 tabular-nums">
                      {c.doneAt ? day(c.doneAt) : <span className="text-amber-600">未完成</span>}
                    </td>
                    <td className="px-3 py-2">{c.effectiveness}</td>
                  </tr>
                  {open === c.id && (
                    <tr className="border-b border-slate-200">
                      <td colSpan={12} className="p-0">
                        <Detail c={c} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
              {data && data.items.length === 0 && (
                <tr>
                  <td colSpan={12} className="py-8 text-center text-slate-400">
                    沒有符合的客訴
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
