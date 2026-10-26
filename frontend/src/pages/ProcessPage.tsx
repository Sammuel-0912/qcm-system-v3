import { useEffect, useState } from 'react'

import { api, type FilteredPaged, type ListFilter, type RepairRow } from '../api/client'
import { AppShell } from '../components/AppShell'
import { DuePie, EMPTY_FILTER, ListFilterBar, DueBadge } from '../components/DueTracking'
import { LevelChange } from '../components/LevelChip'
import { Pager } from '../components/ListToolbar'
import { RecordDetailDrawer, type RecordTarget } from '../components/RecordDetailDrawer'
import { formatLocalDateTime } from '../utils/datetime'

// 測試時間是實際時刻（UTC 儲存），要轉本地時間；不可直接截字串（spec REQ-CHK-07）
function stamp(value: string | null) {
  return value ? formatLocalDateTime(value).slice(0, 16) : '—'
}

/**
 * 製程風險管理：修護報表的維修紀錄；點列開 8D 明細／等級歷程。
 * 上方為預計完成／逾期圓餅與篩選（測試時間、機種、站別、KPOV、改善時間、完成期限，spec §17）。
 */
export default function ProcessPage() {
  const [filter, setFilter] = useState<ListFilter>(EMPTY_FILTER)
  const [page, setPage] = useState(1)
  const [data, setData] = useState<FilteredPaged<RepairRow> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [detail, setDetail] = useState<RecordTarget | null>(null)

  useEffect(() => {
    api
      .repairs(filter, page)
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
    <AppShell title="製程風險管理">
      <main className="mx-auto max-w-7xl space-y-4 px-6 py-6">
        {data && <DuePie stats={data.dueStats} selected={filter.due} onSelect={(due) => changeFilter({ ...filter, due })} />}
        <ListFilterBar value={filter} onChange={changeFilter} options={data?.options} occurredLabel="測試時間" groupLabel="機種" />
        {error && <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-700 text-xs text-white">
              <tr>
                {['測試時間', '序號', '機種', '線別', '站別', '設備ID', 'KPOV', '產品不良描述', '緊急措施', '長期措施（改善措施）', '改善時間', 'Level 基準→現況'].map(
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
                <tr
                  key={r.id}
                  onClick={() => setDetail({ repairId: r.id, kpovNo: r.kpovNo, equipmentCode: r.equipmentCode })}
                  title="點擊查看 8D 明細與等級歷程"
                  className="cursor-pointer border-b border-slate-100 align-top hover:bg-slate-50"
                >
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
                  <td className="max-w-xs px-3 py-2 text-xs">
                    <span className="whitespace-pre-line">{r.emergencyMeasure ?? '—'}</span>
                    {r.emergencyMeasureAt && (
                      <span className="mt-0.5 block tabular-nums text-red-600">{r.emergencyMeasureAt.slice(0, 10)}</span>
                    )}
                  </td>
                  <td className="max-w-xs px-3 py-2 text-xs">{r.improvement ?? '—'}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-xs tabular-nums">
                    {r.improvedAt ? r.improvedAt.slice(0, 10) : '—'}
                    {r.improvePlanned && (
                      <span className="mt-0.5 block w-fit rounded border border-dashed border-emerald-400 px-1 text-[10px] text-emerald-700">
                        預計改善
                      </span>
                    )}
                    <DueBadge due={r.due} />
                  </td>
                  <td className="px-3 py-2">
                    <LevelChange before={r.levelBefore} after={r.levelAfter} />
                  </td>
                </tr>
              ))}
              {data && data.items.length === 0 && (
                <tr>
                  <td colSpan={12} className="py-8 text-center text-slate-400">
                    沒有符合的維修紀錄
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
