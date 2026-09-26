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

export type BarResponse = {
  bars: { level: number; count: number; baselineCount: number; color: string }[]
  unrated: number
  total: number
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
  bar: (p: Scope & { view: string }) => get<BarResponse>('/levels/bar', p),
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
}
