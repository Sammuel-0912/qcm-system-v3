import { useState } from 'react'

import { api, type EmergencyMeasure } from '../api/client'

type Key = { repairSerial: string; kpovNo: string; equipmentCode: string }

type Props = {
  target: Key
  measure: EmergencyMeasure | null
  onSaved: (measure: EmergencyMeasure) => void
}

const EMPTY: EmergencyMeasure = {
  solutionType: 'technical',
  techTarget: null,
  designElimination: false,
  equipmentInterception: false,
  foolproof: false,
  smartMonitoring: false,
  managementNote: null,
}

// 技術解底下 KPOV／KPIV 各自的兩個多選框
const TECH_OPTIONS = {
  KPOV: [
    { field: 'designElimination', label: '設計消除' },
    { field: 'equipmentInterception', label: '設備攔截' },
  ],
  KPIV: [
    { field: 'foolproof', label: '防呆防錯' },
    { field: 'smartMonitoring', label: '智能監控' },
  ],
} as const

/** 分類摘要（列內顯示），例：「技術解・KPOV：設計消除、設備攔截」 */
export function measureSummary(m: EmergencyMeasure | null | undefined): string {
  if (!m) return '未分類'
  if (m.solutionType === 'management') return `管理解：${m.managementNote ?? ''}`
  if (!m.techTarget) return '技術解'
  const picked = TECH_OPTIONS[m.techTarget].filter((o) => m[o.field]).map((o) => o.label)
  return `技術解・${m.techTarget}${picked.length ? `：${picked.join('、')}` : ''}`
}

/**
 * 緊急措施分類編輯：技術解／管理解二選一；技術解再選 KPOV／KPIV，勾選即存；管理解填寫後按送出。
 */
export function EmergencyMeasureEditor({ target, measure, onSaved }: Props) {
  const [draft, setDraft] = useState<EmergencyMeasure>(measure ?? EMPTY)
  const [note, setNote] = useState(measure?.managementNote ?? '')
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  async function save(next: EmergencyMeasure) {
    setBusy(true)
    setStatus(null)
    try {
      const saved = await api.saveEmergencyMeasure(target, next)
      setDraft(saved)
      onSaved(saved)
      setStatus({ ok: true, text: '已儲存' })
    } catch (err) {
      setStatus({ ok: false, text: err instanceof Error ? err.message : '儲存失敗' })
    } finally {
      setBusy(false)
    }
  }

  const radio = 'h-4 w-4 accent-slate-900'
  const technical = draft.solutionType === 'technical'

  return (
    <div className="space-y-3 text-sm" onClick={(e) => e.stopPropagation()}>
      <fieldset className="flex flex-wrap items-center gap-4" disabled={busy}>
        <legend className="mb-1 text-xs font-medium text-slate-500">緊急措施類型</legend>
        <label className="flex items-center gap-1.5">
          <input
            type="radio"
            className={radio}
            checked={technical}
            onChange={() => setDraft({ ...EMPTY, solutionType: 'technical' })}
          />
          技術解
        </label>
        <label className="flex items-center gap-1.5">
          <input
            type="radio"
            className={radio}
            checked={!technical}
            onChange={() => setDraft({ ...EMPTY, solutionType: 'management' })}
          />
          管理解
        </label>
      </fieldset>

      {technical ? (
        <>
          <fieldset className="flex flex-wrap items-center gap-4" disabled={busy}>
            <legend className="mb-1 text-xs font-medium text-slate-500">對象</legend>
            {(['KPOV', 'KPIV'] as const).map((t) => (
              <label key={t} className="flex items-center gap-1.5">
                <input
                  type="radio"
                  className={radio}
                  checked={draft.techTarget === t}
                  onChange={() => void save({ ...EMPTY, solutionType: 'technical', techTarget: t })}
                />
                {t}
              </label>
            ))}
          </fieldset>

          {draft.techTarget ? (
            <fieldset className="flex flex-wrap items-center gap-4" disabled={busy}>
              <legend className="mb-1 text-xs font-medium text-slate-500">措施（可複選，勾選即儲存）</legend>
              {TECH_OPTIONS[draft.techTarget].map((o) => (
                <label key={o.field} className="flex items-center gap-1.5">
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-slate-900"
                    checked={draft[o.field]}
                    onChange={(e) => void save({ ...draft, [o.field]: e.target.checked })}
                  />
                  {o.label}
                </label>
              ))}
            </fieldset>
          ) : (
            <p className="text-xs text-slate-400">請先選擇 KPOV 或 KPIV</p>
          )}
        </>
      ) : (
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-500" htmlFor={`note-${target.repairSerial}`}>
            管理解內容
          </label>
          <textarea
            id={`note-${target.repairSerial}`}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            placeholder="例：加強稽核頻率、修訂作業標準書…"
            className="w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-sm"
          />
          <button
            type="button"
            disabled={busy || !note.trim()}
            onClick={() => void save({ ...EMPTY, solutionType: 'management', managementNote: note.trim() })}
            className="mt-1.5 rounded-md bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700 disabled:opacity-40"
          >
            送出
          </button>
        </div>
      )}

      {status && <p className={`text-xs ${status.ok ? 'text-emerald-700' : 'text-red-700'}`}>{status.text}</p>}
    </div>
  )
}
