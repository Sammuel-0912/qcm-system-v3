import { useEffect, useState } from 'react'

import { api, type Complaint, type HistoryResponse, type RepairRecord } from '../api/client'
import { formatLocalDateTime } from '../utils/datetime'
import { EightDPanel } from './EightDPanel'
import { LevelTimeline } from './LevelTimeline'

/** 要開的紀錄：維修或客訴，另帶 KPOV×設備供「等級歷程」分頁使用 */
export type RecordTarget = {
  repairId?: number | null
  complaintId?: number | null
  kpovNo?: string | null
  equipmentCode?: string | null
}

type Tab = 'detail' | 'history'

function day(value: string | null) {
  return value ? value.slice(0, 10) : null
}

function Measure({ title, text, at, tone }: { title: string; text: string | null; at: string | null; tone: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3">
      <h4 className="mb-1 text-xs font-semibold text-[#1F5C7A]">{title}</h4>
      <p className="whitespace-pre-wrap text-sm text-slate-800">{text || '—'}</p>
      {at && <p className={`mt-1 text-xs tabular-nums ${tone}`}>{day(at)}</p>}
    </div>
  )
}

function Facts({ lines }: { lines: [string, string | number | null | undefined][] }) {
  return (
    <dl className="grid gap-x-4 gap-y-1.5 rounded-md border border-slate-200 bg-white p-3 text-sm sm:grid-cols-2">
      {lines.map(([term, value]) => (
        <div key={term} className="min-w-0">
          <dt className="text-xs text-slate-400">{term}</dt>
          <dd className="whitespace-pre-wrap break-words text-slate-800">{value ?? '—'}</dd>
        </div>
      ))}
    </dl>
  )
}

/**
 * 措施表的列明細：「8D 明細」（緊急措施、長期措施、8D 四段）與「等級歷程」（KPOV 時間軸）兩個分頁。
 * 維修讀 GET /repairs/{id}，客訴讀 GET /complaints/{id}。
 */
export function RecordDetailDrawer({ target, onClose }: { target: RecordTarget; onClose: () => void }) {
  const [tab, setTab] = useState<Tab>('detail')
  const [repair, setRepair] = useState<RepairRecord | null>(null)
  const [complaint, setComplaint] = useState<Complaint | null>(null)
  const [history, setHistory] = useState<HistoryResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const canHistory = Boolean(target.kpovNo && target.equipmentCode)

  useEffect(() => {
    setError(null)
    setRepair(null)
    setComplaint(null)
    setHistory(null)
    setTab('detail')
    const fail = (err: unknown) => setError(err instanceof Error ? err.message : '載入失敗')
    if (target.repairId) void api.repair(target.repairId).then(setRepair).catch(fail)
    else if (target.complaintId) void api.complaint(target.complaintId).then(setComplaint).catch(fail)
    if (target.kpovNo && target.equipmentCode) {
      void api.history(target.kpovNo, target.equipmentCode).then(setHistory).catch(() => setHistory(null))
    }
  }, [target])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const loading = !error && !repair && !complaint
  const heading = repair
    ? `維修 ${repair.serialNo ?? ''}`
    : complaint
      ? `客訴 ${complaint.reportNo && complaint.reportNo !== 'NA' ? complaint.reportNo : `序號 ${complaint.seq ?? ''}`}`
      : '明細'

  return (
    <aside
      className="fixed inset-y-0 right-0 z-50 flex w-full max-w-2xl flex-col border-l border-slate-200 bg-slate-50 shadow-2xl"
      role="dialog"
      aria-label={heading}
    >
      <div className="flex items-start justify-between gap-3 border-b border-slate-200 bg-white px-5 py-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-800">{heading}</h2>
          {(target.kpovNo || target.equipmentCode) && (
            <p className="font-mono text-xs text-slate-400">
              {target.equipmentCode} · {target.kpovNo}
            </p>
          )}
        </div>
        <button onClick={onClose} className="text-slate-400 hover:text-slate-700" aria-label="關閉">
          ✕
        </button>
      </div>

      <div className="flex gap-1 border-b border-slate-200 bg-white px-5" role="tablist">
        {(
          [
            ['detail', '8D 明細'],
            ['history', '等級歷程'],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            role="tab"
            aria-selected={tab === value}
            disabled={value === 'history' && !canHistory}
            onClick={() => setTab(value)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm transition disabled:cursor-not-allowed disabled:opacity-40 ${
              tab === value ? 'border-[#0086DB] font-semibold text-[#0086DB]' : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-5">
        {error && <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
        {tab === 'history' ? (
          history ? <LevelTimeline data={history} /> : <p className="text-sm text-slate-400">載入中…</p>
        ) : loading ? (
          <p className="text-sm text-slate-400">載入中…</p>
        ) : repair ? (
          <>
            <Facts
              lines={[
                ['測試時間', repair.testedAt ? formatLocalDateTime(repair.testedAt) : null],
                ['站別', repair.station],
                ['機種／工單', [repair.productModel, repair.workOrder].filter(Boolean).join('／') || null],
                ['線別／組別', [repair.line, repair.team].filter(Boolean).join('／') || null],
                ['產品不良描述', repair.productDefectDesc],
                ['不良原因／小分類', [repair.defectCause, repair.subCategory].filter(Boolean).join('／') || null],
                ['處理對策', repair.countermeasure],
                ['維修人員', repair.technician],
                ['維修備註', repair.remark],
              ]}
            />
            <div className="grid gap-3 sm:grid-cols-2">
              <Measure title="緊急措施" text={repair.emergencyMeasure} at={repair.emergencyMeasureAt} tone="text-red-600" />
              <Measure title="長期措施（改善措施）" text={repair.improvement} at={repair.improvementAt} tone="text-slate-500" />
            </div>
            <EightDPanel data={repair.eightD} />
          </>
        ) : complaint ? (
          <>
            <Facts
              lines={[
                ['日期', day(complaint.complainedAt)],
                ['客戶', complaint.customer],
                ['類別', complaint.category],
                ['客訴項目', complaint.item],
                ['廠區／產品廠', [complaint.site, complaint.plant].filter(Boolean).join('／') || null],
              ]}
            />
            <div className="grid gap-3 sm:grid-cols-2">
              <Measure
                title="緊急措施"
                text={complaint.emergencyMeasure}
                at={complaint.emergencyMeasureAt}
                tone="text-red-600"
              />
              <Measure
                title="長期措施（改善措施）"
                text={complaint.improvement}
                at={complaint.improvementAt}
                tone="text-slate-500"
              />
            </div>
            <EightDPanel data={complaint.eightD} />
          </>
        ) : null}
      </div>
    </aside>
  )
}
