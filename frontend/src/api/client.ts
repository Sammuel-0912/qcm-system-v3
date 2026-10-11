const BASE = '/api/v1'

export type LevelCounts = {
  level0: number
  level1: number
  level2: number
  level3: number
  unrated: number
  total: number
}

export type BatchInfo = { id: number; filename: string; importedAt: string | null }

export type LineInheritance = {
  inherited: boolean
  inheritedFrom: string | null
  inheritedStations: string[]
  opExemptFromLineFilter?: boolean
}

export type QuadrantResponse = {
  view: string
  scope: LevelCounts
  plant: LevelCounts
  baseline: LevelCounts
  filtered: boolean
  deviationCount: number
  lineInheritance: LineInheritance
  batch: BatchInfo
}

export type StationOption = {
  attribute: string
  code: string
  equipmentCode: string | null
  targetId: string
  kpovCount: number
  worstLevel: number | null
  levelCounts: Record<string, number>
}

export type FiltersResponse = {
  stations: StationOption[]
  attributes: string[]
  lines: { code: string; label: string }[]
  batch: BatchInfo
}

export type TrendPoint = {
  period: string
  escalated: number
  improved: number
  escalatedCumulative: number
  improvedCumulative: number
}

export type TrendResponse = {
  granularity: string
  points: TrendPoint[]
  totals: { escalated: number; improved: number }
  emptyReason: string | null
}

export type KpovItem = {
  kpovNo: string | null
  kpovName: string
  station: string
  attribute: string | null
  targetId: string
  category: string | null
  equipmentCode: string
  smallYBaseline: number | null
  bigYBaseline: number | null
  smallYCurrent: number | null
  bigYCurrent: number | null
  levelBaseline: number | null
  levelCurrent: number | null
  levelTarget: number | null
  deviates: boolean
  escalatedOpen: boolean
  lastEventAt: string | null
  transition: string | null
  eventCount: number
}

export type EventItem = {
  kpovNo: string
  kpovName: string | null
  station: string | null
  equipmentCode: string
  eventType: 'DEGRADE' | 'IMPROVE'
  effectiveAt: string
  levelBefore: number | null
  levelAfter: number
  transition: 'ESCALATED' | 'IMPROVED' | 'UNCHANGED'
  defectDesc: string | null
  improvement: string | null
  repairSerial: string | null
}

export type EventsResponse = {
  summary: { escalatedOpen: number; improved: number; totalEvents: number }
  items: EventItem[]
}

export type RepairDetail = {
  serialNo: string | null
  productDefectDesc: string | null
  subCategory: string | null
  defectCause: string | null
  countermeasure: string | null
  remark: string | null
  technician: string | null
  improvement: string | null
}

/** PCN / ECN 變更紀錄：只顯示在時間軸，不影響等級計算 */
export type ChangeRecord = {
  kind: 'PCN' | 'ECN'
  effectiveAt: string | null
  ecnNo: string | null
  content: string | null
  station: string | null
  plantWide: boolean
  smallYBefore: string | null
  bigYBefore: string | null
  levelBefore: string | null
  smallYAfter: string | null
  bigYAfter: string | null
  levelAfter: string | null
}

export type CheckStatus = 'ok' | 'warn' | 'overdue' | 'never'

export type SlotState = 'ok' | 'warn' | 'missed' | 'current' | 'upcoming'

export type CheckSlot = { start: string; end: string; state: SlotState; inspectedAt: string | null }

export type CheckShift = { name: string; label: string; start: string; end: string; ended: boolean }

export type CheckMonitorRow = {
  id: number
  station: string | null
  attribute: string | null
  equipmentCode: string | null
  kpovNo: string | null
  kpovName: string | null
  level: string | null
  checkContent: string
  frequency: string | null
  intervalHours: number
  status: CheckStatus
  lastResult: 'ok' | 'warn' | null
  lastInspectedAt: string | null
  nextDueAt: string | null
  overdue: boolean
  /** 本班各時段（2 小時一格），每格完成 = 一格進度 */
  slots: CheckSlot[]
  completed: number
  progress: number
  count24h: number
}

export type CheckMonitorResponse = {
  items: CheckMonitorRow[]
  summary: Record<CheckStatus, number> & {
    total: number
    progress: number
    missedSlots: number
    warnSlots: number
  }
  shift: CheckShift
}

export type HistoryResponse = {
  kpovNo: string
  kpovName: string
  equipmentCode: string | null
  station: string
  attribute: string | null
  targetId: string
  baseline: { smallY: { score: number | null }; bigY: { score: number | null }; level: number | null }
  events: {
    type: 'DEGRADE' | 'IMPROVE'
    effectiveAt: string
    transition: string
    levelBefore: number | null
    levelAfter: number
    smallY: { method: string | null; score: number }
    bigY: { method: string | null; score: number }
    smallYBefore: { method: string | null; score: number | null }
    bigYBefore: { method: string | null; score: number | null }
    defectDesc: string | null
    improvement: string | null
    repairSerial: string | null
    repair: RepairDetail | null
  }[]
  changes?: ChangeRecord[]
  current: { level: number | null }
  target: { level: number | null }
}

export class ApiError extends Error {}

async function get<T>(path: string, params: Record<string, string | undefined> = {}): Promise<T> {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value) search.set(key, value)
  }
  const query = search.toString()
  const res = await fetch(`${BASE}${path}${query ? `?${query}` : ''}`)
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }))
    throw new ApiError(detail.detail ?? '請求失敗')
  }
  return res.json() as Promise<T>
}

type Scope = { station?: string; line?: string; attribute?: string; target?: string }

export const api = {
  filters: () => get<FiltersResponse>('/filters'),
  quadrant: (p: Scope & { view: string }) => get<QuadrantResponse>('/quadrant', p),
  checkMonitor: (p: Scope) => get<CheckMonitorResponse>('/check-monitor', p),
  trend: (p: Scope) => get<TrendResponse>('/trend', p),
  kpov: (p: Scope & { view: string; level?: string; deviatedOnly?: string }) =>
    get<{ total: number; items: KpovItem[] }>('/kpov', p),
  history: (kpovNo: string, equipmentCode: string) =>
    get<HistoryResponse>(`/kpov/${encodeURIComponent(kpovNo)}/${encodeURIComponent(equipmentCode)}/history`),
  events: (p: Scope) => get<EventsResponse>('/events', p),
  async import(file: File) {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`${BASE}/import`, { method: 'POST', body: form })
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    if (!res.ok) throw new ApiError(body.detail ?? '匯入失敗')
    return body
  },
  async heartbeat(sid: string): Promise<{ online: number }> {
    const res = await fetch(`${BASE}/presence/heartbeat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sid }),
    })
    if (!res.ok) throw new ApiError('心跳失敗')
    return res.json()
  },
  /** 關閉分頁時用；sendBeacon 在 pagehide 期間仍會送出，fetch 則可能被瀏覽器取消 */
  leave(sid: string) {
    const body = new Blob([JSON.stringify({ sid })], { type: 'application/json' })
    navigator.sendBeacon(`${BASE}/presence/leave`, body)
  },
}
