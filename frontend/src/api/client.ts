import { apiFetch, withDataset } from './session'

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
  /** 期間第一天當時的 Level 分佈（同一組 KPOV）；未給期間時為 null */
  start: LevelCounts | null
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

/** 完成期限（spec §17）：8D 預計完成 vs 實際完成 */
export type DueKey = 'planned' | 'overdue' | 'lt7' | 'd7_14' | 'gt14'
export type Due = {
  status: 'planned' | 'ontime' | 'overdue'
  overdueDays: number
  bucket: 'lt7' | 'd7_14' | 'gt14' | null
  plannedAt: string
  doneAt: string | null
}
export type DueStats = Record<DueKey, number>

/** 製程風險管理／客訴案件管理的篩選（日期為 YYYY-MM-DD，起訖皆含） */
export type ListFilter = {
  occurredFrom: string
  occurredTo: string
  /** 製程＝機種；客訴＝客戶 */
  groups: string[]
  stations: string[]
  kpovs: string[]
  improvedFrom: string
  improvedTo: string
  due: DueKey | ''
}

export type FilteredPaged<T> = Paged<T> & {
  dueStats: DueStats
  options: { groups: string[]; stations: string[]; kpovs: { value: string; label: string }[] }
}

function listParams(f: ListFilter, page: number) {
  return {
    occurredFrom: f.occurredFrom || undefined,
    occurredTo: f.occurredTo || undefined,
    group: f.groups,
    station: f.stations,
    kpov: f.kpovs,
    improvedFrom: f.improvedFrom || undefined,
    improvedTo: f.improvedTo || undefined,
    due: f.due || undefined,
    page: String(page),
  }
}

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
  /** 緊急措施與緊急措施時間（修護報表 BM／BN；客訴報表同名欄） */
  emergency: TimedText
  /** 長期措施＝改善措施與改善時間（修護報表 BR／BQ；客訴報表同名欄） */
  longTerm: TimedText
  /** 措施層別：一律由 Excel 8D 區塊的管理解／技術解組成，唯讀 */
  layer: { summary: string | null }
  levelChanged: LevelShift | null
  improvedAt: string | null
  improvePlanned: boolean
  improveOverdue: boolean
  complaintCount: number
  repairSerial: string | null
  /** 開 8D 明細用：維修列有 repairId，客訴列有 complaintId */
  repairId: number | null
  complaintId: number | null
  occurredAt: string | null
}

export type TimedText = { text: string | null; at: string | null }

/** 8D 區塊一側（現狀或改善後）的盤查內容 */
export type EightDSide = {
  bigY: { item: string | null; method: string | null; score: number | null }
  smallY: { kpov: string | null; method: string | null; score: number | null }
  level: number | null
  kpiv: {
    factor: string | null
    foolproof: string | null
    foolproofDesc: string | null
    monitor: string | null
    monitorDesc: string | null
    level: string | null
  }
}

/** 8D：現狀盤查 → 原因 → 改善對策 → 改善後盤查（客訴與維修共用） */
export type EightD = {
  processUnit: string | null
  before: EightDSide
  causes: { occur: string | null; escape: string | null }
  measures: {
    mgmtVerdict: string | null
    mgmt: string | null
    tech: {
      ccscInterception: string | null
      kpovDesignElimination: string | null
      kpovInterception: string | null
      kpivFoolproof: string | null
      kpivSmart: string | null
    }
    content: string | null
    owner: string | null
    plannedText: string | null
    doneText: string | null
    plannedAt: string | null
    doneAt: string | null
    effectiveness: string | null
  }
  after: EightDSide
  verdict: string | null
}

/** 單筆維修明細（GET /repairs/{id}） */
export type RepairRecord = {
  id: number
  serialNo: string | null
  month: string | null
  productModel: string | null
  workOrder: string | null
  line: string | null
  team: string | null
  testedAt: string | null
  defectDesc: string | null
  productDefectDesc: string | null
  repairPartLocation: string | null
  responsibility: string | null
  defectCause: string | null
  subCategory: string | null
  technician: string | null
  repairedAt: string | null
  countermeasure: string | null
  responsibleDept: string | null
  remark: string | null
  station: string | null
  equipmentCode: string | null
  kpovNo: string | null
  emergencyMeasure: string | null
  emergencyMeasureAt: string | null
  improvement: string | null
  improvementAt: string | null
  eightD: EightD | null
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
  emergencyMeasure: string | null
  emergencyMeasureAt: string | null
  improvement: string | null
  improvementAt: string | null
  /** 清單才有：KPOV 對應的站別（對不到時為製程單元）、KPOV 名稱、完成期限 */
  station?: string | null
  kpovName?: string | null
  due?: Due | null
  eightD: EightD | null
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
  emergencyMeasure: string | null
  emergencyMeasureAt: string | null
  improvement: string | null
  improvedAt: string | null
  improvePlanned: boolean
  levelBefore: number | null
  levelAfter: number | null
  due: Due | null
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
  /** KPIV(x) 管控等級，例「A: 防呆防錯+智能」 */
  kpivControlLevel: string | null
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

/** 一筆拍照點檢紀錄；inspectedAt 為帶時區的 UTC，顯示時轉本地時間 */
export type PhotoInspection = {
  id: number
  equipmentCode: string
  station: string
  kpovNo: string | null
  checkContent: string
  /** 目前點檢項目的 KPIV(x) 管控等級 */
  kpivControlLevel: string | null
  status: 'ok' | 'warn'
  note: string | null
  photoUrl: string
  inspectedAt: string
}

/** 點檢儀表板良率卡片：依設備（站別）彙總 */
export type PhotoInspectionStat = {
  equipmentCode: string
  station: string
  total: number
  okCount: number
  warnCount: number
  okRate: number
}

export class ApiError extends Error {}

export type Role = 'super_admin' | 'plant_admin' | 'user'

export type AuthUser = {
  id: number
  username: string
  displayName: string
  role: Role
  roleLabel: string
  plant: string | null
  isActive: boolean
  createdAt: string | null
  lastLoginAt: string | null
}

/** 資料集＝一條線的生效資料，例 WJ1-DCS-PM1 */
export type DatasetInfo = {
  key: string
  plant: string
  factory: string
  line: string
  filename: string
  importedAt: string | null
}

export const PLANTS = ['WJ1', 'WJ2', 'WJ3', 'WJ4', 'WJ5', 'WJ6', 'WJ7', 'WJ8'] as const

async function send<T>(method: string, path: string, body: unknown, fallback: string): Promise<T> {
  const res = await apiFetch(`${BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({ detail: res.statusText }))
  if (!res.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map((d: { msg: string }) => d.msg).join('；') : data.detail
    throw new ApiError(typeof detail === 'string' ? detail : fallback)
  }
  return data as T
}

async function get<T>(path: string, params: Record<string, string | string[] | undefined> = {}): Promise<T> {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    // 陣列＝多選，以重複的參數送出（?station=A&station=B）
    if (Array.isArray(value)) value.forEach((v) => search.append(key, v))
    else if (value) search.set(key, value)
  }
  const query = search.toString()
  const res = await apiFetch(`${BASE}${path}${query ? `?${query}` : ''}`)
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }))
    throw new ApiError(detail.detail ?? '請求失敗')
  }
  return res.json() as Promise<T>
}

/** 總覽廣播（spec §16）：整條線、不吃篩選器 */
export type BroadcastResponse = {
  window: ChangeWindow
  since: string
  level3: { start: number; now: number; delta: number }
  inspection: {
    shift: { name: string; label: string; start: string; end: string; ended: boolean }
    items: number
    expected: number
    completed: number
    warn: number
  }
  escalations: {
    station: string
    kpovNo: string
    kpovName: string
    equipmentCode: string
    levelBefore: number | null
    levelAfter: number
    at: string
  }[]
  escalatedStations: string[]
}

type Scope = { station?: string; line?: string; attribute?: string; target?: string }

export const api = {
  filters: () => get<FiltersResponse>('/filters'),
  quadrant: (p: Scope & { view: string; window?: ChangeWindow }) => get<QuadrantResponse>('/quadrant', p),
  checkMonitor: (p: Scope) => get<CheckMonitorResponse>('/check-monitor', p),
  broadcast: (window: ChangeWindow) => get<BroadcastResponse>('/broadcast', { window }),
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
  complaints: (f: ListFilter, page: number) => get<FilteredPaged<Complaint>>('/complaints', listParams(f, page)),
  repairs: (f: ListFilter, page: number) => get<FilteredPaged<RepairRow>>('/repairs', listParams(f, page)),
  /** 單筆維修／客訴明細（含 8D） */
  repair: (id: number) => get<RepairRecord>(`/repairs/${id}`),
  complaint: (id: number) => get<Complaint>(`/complaints/${id}`),
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
    const res = await apiFetch(`${BASE}/check-inspections`, { method: 'POST', body: form })
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    if (!res.ok) throw new ApiError(typeof body.detail === 'string' ? body.detail : '上傳失敗')
    return body as { id: number; status: string; photoUrl: string; inspectedAt: string }
  },
  /** 點檢儀表板：拍照點檢紀錄（新到舊）。start／end 傳帶時區的 ISO 時間 */
  photoInspections: (p: { equipmentCode?: string; start?: string; end?: string }) =>
    get<{ total: number; items: PhotoInspection[] }>('/check-inspections', p),
  photoInspectionStats: () => get<PhotoInspectionStat[]>('/check-inspections/stats'),
  /** 匯出含照片的 Excel；篩選條件同列表，baseUrl 用來組出可點的原圖連結 */
  photoInspectionExportUrl: (p: { equipmentCode?: string; start?: string; end?: string; baseUrl?: string }) => {
    const search = new URLSearchParams()
    for (const [key, value] of Object.entries(p)) if (value) search.set(key, value)
    const query = search.toString()
    // 瀏覽器直接下載帶不了 header，資料集放查詢參數
    return withDataset(`${BASE}/check-inspections/export${query ? `?${query}` : ''}`)
  },
  // ── 登入與帳號（spec §15 RBAC）──
  async login(username: string, password: string) {
    return send<AuthUser>('POST', '/auth/login', { username, password }, '登入失敗')
  },
  async logout() {
    await apiFetch(`${BASE}/auth/logout`, { method: 'POST' })
  },
  me: () => get<AuthUser & { datasets: DatasetInfo[] }>('/auth/me'),
  changePassword: (oldPassword: string, newPassword: string) =>
    send<{ ok: boolean }>('POST', '/auth/password', { oldPassword, newPassword }, '修改密碼失敗'),
  users: () => get<AuthUser[]>('/users'),
  createUser: (u: { username: string; displayName: string; password: string; role: Role; plant: string | null }) =>
    send<AuthUser>('POST', '/users', u, '新增帳號失敗'),
  updateUser: (id: number, patch: { displayName?: string; role?: Role; plant?: string | null; isActive?: boolean }) =>
    send<AuthUser>('PATCH', `/users/${id}`, patch, '更新帳號失敗'),
  resetPassword: (id: number, password: string) =>
    send<AuthUser>('POST', `/users/${id}/reset-password`, { password }, '重設密碼失敗'),
  async import(file: File) {
    const form = new FormData()
    form.append('file', file)
    const res = await apiFetch(`${BASE}/import`, { method: 'POST', body: form })
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    if (!res.ok) throw new ApiError(body.detail ?? '匯入失敗')
    return body
  },
  async heartbeat(sid: string): Promise<{ online: number }> {
    const res = await apiFetch(`${BASE}/presence/heartbeat`, {
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
