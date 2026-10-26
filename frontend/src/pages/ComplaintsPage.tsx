import { useEffect, useState } from 'react'

import { api, type Complaint, type FilteredPaged, type ListFilter } from '../api/client'
import { AppShell } from '../components/AppShell'
import { DuePie, EMPTY_FILTER, ListFilterBar, OverdueBadge } from '../components/DueTracking'
import { LevelChange } from '../components/LevelChip'
import { Pager } from '../components/ListToolbar'
import { RecordDetailDrawer, type RecordTarget } from '../components/RecordDetailDrawer'

function day(value: string | null) {
  return value ? value.slice(0, 10) : '—'
}

/**
 * 客訴案件管理（RMA Event）：客訴報表基本資訊與緊急措施；點列開 8D 明細／等級歷程。
 * 上方為預計完成／逾期圓餅與篩選（日期、客戶、站別、KPOV、改善時間、完成期限，spec §17）。
 * 客訴報表沒有機種欄位，第二個篩選用客戶。
 */
export default function ComplaintsPage() {
  const [filter, setFilter] = useState<ListFilter>(EMPTY_FILTER)
  const [page, setPage] = useState(1)
  const [data, setData] = useState<FilteredPaged<Complaint> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [detail, setDetail] = useState<RecordTarget | null>(null)

  useEffect(() => {
    api
      .complaints(filter, page)
      .then((d) => {
        setData(d)
        setError(null)
      })
      .catch((err) => setError(err instanceof Error ? err.message : '載入失敗'))
  }, [filter, page])

  const changeFilter = (next: ListFilter) => {
    setFilter(next)
    setPage(1)
  }

  return (
    <AppShell title="客訴案件管理">
      <main className="mx-auto max-w-7xl space-y-4 px-6 py-6">
        {data && <DuePie stats={data.dueStats} selected={filter.due} onSelect={(due) => changeFilter({ ...filter, due })} />}
        <ListFilterBar value={filter} onChange={changeFilter} options={data?.options} occurredLabel="日期" groupLabel="客戶" />
        {error && <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-700 text-xs text-white">
              <tr>
                {['序號', '8D編號', '日期', '客戶', '類別', '客訴項目', '站別', 'KPOV', 'Level 改善前→後', '緊急措施', '責任人', '改善時間', '預計完成', '實際完成', '有效性'].map(
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
                  <tr
                    key={c.id}
                    onClick={() => setDetail({ complaintId: c.id, kpovNo: c.kpovNo, equipmentCode: c.equipmentCode })}
                    title="點擊查看 8D 明細與等級歷程"
                    className="cursor-pointer border-b border-slate-100 align-top hover:bg-slate-50"
                  >
                    <td className="px-3 py-2 tabular-nums">{c.seq}</td>
                    <td className="px-3 py-2 font-mono text-xs">{c.reportNo ?? '—'}</td>
                    <td className="whitespace-nowrap px-3 py-2 tabular-nums">{day(c.complainedAt)}</td>
                    <td className="px-3 py-2">{c.customer}</td>
                    <td className="px-3 py-2">{c.category}</td>
                    <td className="max-w-xs px-3 py-2">{c.item}</td>
                    <td className="px-3 py-2">
                      {c.station ?? '—'}
                      {c.processUnit && c.processUnit !== c.station && (
                        <span className="block text-xs text-slate-400">製程單元：{c.processUnit}</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <span className="block">{c.kpovName ?? '—'}</span>
                      <span className="font-mono text-xs text-slate-400">{c.kpovNo}</span>
                    </td>
                    <td className="px-3 py-2">
                      <LevelChange before={c.levelBefore} after={c.levelAfter} />
                    </td>
                    <td className="max-w-xs px-3 py-2 text-xs">
                      <span className="whitespace-pre-line">{c.emergencyMeasure ?? '—'}</span>
                      {c.emergencyMeasureAt && (
                        <span className="mt-0.5 block tabular-nums text-red-600">{c.emergencyMeasureAt.slice(0, 10)}</span>
                      )}
                    </td>
                    <td className="whitespace-pre-wrap px-3 py-2 text-xs">{c.owner}</td>
                    <td className="whitespace-nowrap px-3 py-2 text-xs tabular-nums">{day(c.improvementAt)}</td>
                    <td
                      className={`whitespace-nowrap px-3 py-2 tabular-nums ${c.due?.status === 'overdue' ? 'font-medium text-red-600' : ''}`}
                    >
                      {day(c.plannedAt)}
                    </td>
                    <td className="whitespace-nowrap px-3 py-2 tabular-nums">
                      {c.doneAt ? day(c.doneAt) : <span className="text-amber-600">未完成</span>}
                      <OverdueBadge due={c.due} />
                    </td>
                    <td className="px-3 py-2">{c.effectiveness}</td>
                  </tr>
              ))}
              {data && data.items.length === 0 && (
                <tr>
                  <td colSpan={15} className="py-8 text-center text-slate-400">
                    沒有符合的客訴
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {data && data.total > 0 && <Pager data={data} onPageChange={setPage} />}
      </main>
      {detail && <RecordDetailDrawer target={detail} onClose={() => setDetail(null)} />}
    </AppShell>
  )
}
