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
}

export type FiltersResponse = {
  stations: { code: string; equipmentCode: string; kpovCount: number }[]
  lines: { code: string; label: string }[]
  batch: BatchInfo
}

export type KpovItem = {
  kpovNo: string | null
  kpovName: string
  station: string
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

export type HistoryResponse = {
  kpovNo: string
  kpovName: string
  equipmentCode: string
  station: string
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

export const api = {
  filters: () => get<FiltersResponse>('/filters'),
  quadrant: (p: { view: string; station?: string; line?: string }) => get<QuadrantResponse>('/quadrant', p),
  bar: (p: { view: string; station?: string; line?: string }) => get<BarResponse>('/levels/bar', p),
  kpov: (p: { view: string; station?: string; line?: string; level?: string; deviatedOnly?: string }) =>
    get<{ total: number; items: KpovItem[] }>('/kpov', p),
  history: (kpovNo: string, equipmentCode: string) =>
    get<HistoryResponse>(`/kpov/${encodeURIComponent(kpovNo)}/${encodeURIComponent(equipmentCode)}/history`),
  events: (p: { station?: string; line?: string }) => get<EventsResponse>('/events', p),
  async import(file: File) {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`${BASE}/import`, { method: 'POST', body: form })
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    if (!res.ok) throw new ApiError(body.detail ?? '匯入失敗')
    return body
  },
}
