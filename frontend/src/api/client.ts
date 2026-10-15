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
  /** 改善時間在未來：預計改善，尚未生效 */
  planned?: boolean
}

export type EventsResponse = {
  summary: { escalatedOpen: number; improved: number; totalEvents: number }
  /** 各「變化後 Level」的筆數（不受 levelAfter 篩選影響） */
  levelCounts?: Record<string, number>
  items: EventItem[]
}

export type ChangeWindow = 'day' | 'week' | 'month' | 'year'

/** 站別柱狀圖：設備代碼＋站別名稱；同名站可能是不同設備 */
export type StationRef = { equipmentCode: string; station: string }
/** 依 Level 的筆數，鍵為 '0'～'3' */
export type StationLevelCounts = Record<string, number>
export type ChangeKind = 'escalated' | 'improved'

/** 高風險異動的緊急措施分類：技術解（KPOV／KPIV）或管理解，二選一 */
export type EmergencyMeasure = {
  solutionType: 'technical' | 'management'
  techTarget: 'KPOV' | 'KPIV' | null
  designElimination: boolean
  equipmentInterception: boolean
  foolproof: boolean
  smartMonitoring: boolean
  managementNote: string | null
  updatedAt?: string | null
}

/** 等級異動總覽：區間內的一筆惡化或改善（列內容同 MeasureRow） */
export type LevelChangeItem = MeasureRow & {
  transition: 'ESCALATED' | 'IMPROVED'
  effectiveAt: string
}

export type LevelChangesResponse = {
  window: ChangeWindow
  since: string
  kind: ChangeKind
  counts: Record<ChangeKind, number>
  page: number
  pageSize: number
  total: number
  pages: number
  items: LevelChangeItem[]
}

export type Paged<T> = { page: number; pageSize: number; total: number; pages: number; items: T[] }

export type LevelShift = { before: number | null; after: number | null; planned: boolean }

/**
 * 四張措施表（高風險、已改善、客訴問題追蹤、製程問題追蹤）共用的一列：
 * 高風險站別｜高風險KPOV｜Level(原)｜緊急措施｜長期措施｜措施層別｜Level(變化後)｜改善時間｜客訴筆數
 */
export type MeasureRow = {
  station: string | null
  kpovNo: string | null
  kpovName: string | null
  equipmentCode: string | null
  /** 是否對應到 KPOV 庫；客訴未填設備ID／KPOV 編號者為 false */
  mapped: boolean
  levelOrig: LevelShift | null
  /** 緊急措施（原改善措施）與緊急措施時間（維修＝修復時間；客訴＝預計完成） */
  emergency: { text: string | null; at: string | null }
  longTerm: string | null
  /** 措施層別：editable 時可編輯（以 measure 為準）；唯讀時可能只有 summary（客訴讀 Excel） */
  layer: { editable: boolean; measure: EmergencyMeasure | null; summary: string | null }
  levelChanged: LevelShift | null
  improvedAt: string | null
  improvePlanned: boolean
  improveOverdue: boolean
  complaintCount: number
  repairSerial: string | null
  occurredAt: string | null
}

export type ComplaintSummary = Paged<MeasureRow> & {
  /** 各 Level 客訴筆數（依改善後 Level）＋ total */
  levelCounts: Record<string, number>
}

export type ProcessSummary = Paged<MeasureRow> & {
  levelCounts: { current: Record<string, number>; total: number }
}

export type Complaint = {
  id: number
  seq: number | null
  reportNo: string | null
  complainedAt: string | null
  customer: string | null
  category: string | null
  item: string | null
  processUnit: string | null
  productKpov: string | null
  levelBefore: number | null
  levelAfter: number | null
  owner: string | null
  plannedAt: string | null
  doneAt: string | null
  plannedText: string | null
  doneText: string | null
  effectiveness: string | null
  equipmentCode: string | null
  kpovNo: string | null
  site: string | null
  plant: string | null
  causeOccur: string | null
  causeEscape: string | null
  countermeasure: string | null
  verdict: string | null
  before: {
    bigYItem: string | null
    bigYMethod: string | null
    bigYScore: number | null
    smallYMethod: string | null
    smallYScore: number | null
  }
  after: { smallYMethod: string | null; smallYScore: number | null; bigYMethod: string | null; bigYScore: number | null }
}

export type RepairRow = {
  id: number
  testedAt: string | null
  serialNo: string | null
  productModel: string | null
  line: string | null
  station: string | null
  equipmentCode: string | null
  kpovNo: string | null
  kpovName: string | null
  defectDesc: string | null
  improvement: string | null
  improvedAt: string | null
  improvePlanned: boolean
  levelBefore: number | null
  levelAfter: number | null
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

export type CheckSlot = {
  start: string
  end: string
  state: SlotState
  inspectedAt: string | null
  photoUrl: string | null
}

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
  lastPhotoUrl: string | null
  lastNote: string | null
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
  quadrant: (p: Scope & { view: string; window?: ChangeWindow }) => get<QuadrantResponse>('/quadrant', p),
  checkMonitor: (p: Scope) => get<CheckMonitorResponse>('/check-monitor', p),
  trend: (p: Scope) => get<TrendResponse>('/trend', p),
  kpov: (p: Scope & { view: string; level?: string; deviatedOnly?: string; window?: ChangeWindow }) =>
    get<{ total: number; items: KpovItem[] }>('/kpov', p),
  history: (kpovNo: string, equipmentCode: string) =>
    get<HistoryResponse>(`/kpov/${encodeURIComponent(kpovNo)}/${encodeURIComponent(equipmentCode)}/history`),
  events: (p: Scope & { levelAfter?: string }) => get<EventsResponse>('/events', p),
  complaintSummary: (p: Scope & { page: number; window?: ChangeWindow }) =>
    get<ComplaintSummary>('/complaints/summary', { ...p, page: String(p.page) }),
  processSummary: (p: Scope & { page: number; window?: ChangeWindow }) =>
    get<ProcessSummary>('/process/summary', { ...p, page: String(p.page) }),
  complaints: (p: { q?: string; page: number }) =>
    get<Paged<Complaint>>('/complaints', { q: p.q, page: String(p.page) }),
  repairs: (p: { q?: string; page: number }) => get<Paged<RepairRow>>('/repairs', { q: p.q, page: String(p.page) }),
  async saveEmergencyMeasure(
    key: { repairSerial: string; kpovNo: string; equipmentCode: string },
    measure: Omit<EmergencyMeasure, 'updatedAt'>,
  ) {
    const res = await fetch(`${BASE}/emergency-measures`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...key, ...measure }),
    })
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    if (!res.ok) throw new ApiError(typeof body.detail === 'string' ? body.detail : '儲存失敗')
    return body as EmergencyMeasure
  },
  stationRisk: (window: ChangeWindow) =>
    get<{
      window: ChangeWindow
      since: string
      /** worstLevel：期間內維修／客訴發生當時最嚴重的 Level（無則 null） */
      stations: Record<string, { repairs: number; complaints: number; worstLevel: number | null }>
      unmappedComplaints: number
    }>('/station-risk', { window }),
  /** 各站 KPOV 個數（KPOV 數據庫原始 Level），站別依製程順序 */
  stationKpovLevels: () =>
    get<{ stations: (StationRef & { counts: StationLevelCounts })[]; unrated: number }>('/station-levels/kpov'),
  /** 期間內各站客訴／維修筆數，依發生當時的 Level */
  stationEventLevels: (p: Scope & { window: ChangeWindow }) =>
    get<{
      window: ChangeWindow
      stations: (StationRef & { complaints: StationLevelCounts; repairs: StationLevelCounts })[]
      unmappedComplaints: number
      unknownLevel: { complaints: number; repairs: number }
    }>('/station-levels/events', p),
  levelChanges: (p: Scope & { window: ChangeWindow; kind: ChangeKind; page: number }) =>
    get<LevelChangesResponse>('/level-changes', { ...p, page: String(p.page) }),
  checkItems: (station?: string) =>
    get<{ stations: string[]; items: CheckMonitorRow[]; shift: CheckShift }>('/check-items', { station }),
  /** 拍照點檢：照片上傳成功即記一次點檢 */
  async checkInspect(p: {
    item: Pick<CheckMonitorRow, 'equipmentCode' | 'kpovNo' | 'checkContent'>
    file: File
    status: 'ok' | 'warn'
    note?: string
  }) {
    const form = new FormData()
    form.append('equipmentCode', p.item.equipmentCode ?? '')
    if (p.item.kpovNo) form.append('kpovNo', p.item.kpovNo)
    form.append('checkContent', p.item.checkContent)
    form.append('status', p.status)
    if (p.note) form.append('note', p.note)
    form.append('file', p.file)
    const res = await fetch(`${BASE}/check-inspections`, { method: 'POST', body: form })
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    if (!res.ok) throw new ApiError(typeof body.detail === 'string' ? body.detail : '上傳失敗')
    return body as { id: number; status: string; photoUrl: string; inspectedAt: string }
  },
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
