// AR 點檢 API。與品控力同源，固定走 /api/ar——
// 原專案的 resolveBackendUrl() 會組出 http://<hostname>:8000 這種跨來源位址，
// 合併為單一服務後不再需要（ar-integration-spec.md REQ-API-03）。
const BASE = '/api/ar'

export type ArDevice = {
  markerId: number
  name: string
  description: string | null
  workInstruction: string | null
  imageUrl: string | null
  equipmentCode: string | null
  createdAt: string | null
}

export type ArInspectionRow = {
  id: number
  markerId: number
  deviceName: string
  status: 'ok' | 'warn'
  inspectedAt: string
}

export type ArStat = {
  markerId: number
  deviceName: string
  total: number
  okCount: number
  warnCount: number
  okRate: number
}

export type EquipmentOption = {
  equipmentCode: string
  station: string
  kpovCount: number
}

export type DeviceQuality =
  | { linked: false; equipmentCode?: string; reason: string }
  | {
      linked: true
      equipmentCode: string
      station: string | null
      kpovCount: number
      levelCounts: Record<string, number>
      worstLevel: number | null
      escalatedOpen: number
      deviations: {
        kpovNo: string | null
        kpovName: string
        levelBaseline: number | null
        levelCurrent: number | null
        transition: string | null
        effectiveAt: string | null
      }[]
      batch: { id: number; filename: string }
    }

export class ArApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, init)
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const detail = body?.detail
    throw new ArApiError(
      typeof detail === 'string' ? detail : `請求失敗（HTTP ${res.status}）`,
    )
  }
  return res.json() as Promise<T>
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== '') search.set(k, String(v))
  }
  const s = search.toString()
  return s ? `?${s}` : ''
}

export const arApi = {
  devices: () => request<ArDevice[]>('/devices'),
  device: (markerId: number) => request<ArDevice>(`/devices/${markerId}`),

  createDevice: (body: Partial<ArDevice> & { markerId: number; name: string }) =>
    request<ArDevice>('/devices', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        marker_id: body.markerId,
        name: body.name,
        description: body.description ?? null,
        work_instruction: body.workInstruction ?? null,
        equipment_code: body.equipmentCode ?? null,
      }),
    }),

  updateDevice: (markerId: number, patch: Partial<ArDevice>) =>
    request<ArDevice>(`/devices/${markerId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...(patch.name !== undefined && { name: patch.name }),
        ...(patch.description !== undefined && { description: patch.description }),
        ...(patch.workInstruction !== undefined && { work_instruction: patch.workInstruction }),
        ...(patch.equipmentCode !== undefined && { equipment_code: patch.equipmentCode }),
      }),
    }),

  deleteDevice: (markerId: number) =>
    request<{ deleted: boolean }>(`/devices/${markerId}`, { method: 'DELETE' }),

  uploadImage: (markerId: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ imageUrl: string }>(`/devices/${markerId}/image`, {
      method: 'POST',
      body: form,
    })
  },

  inspect: (markerId: number, status: 'ok' | 'warn') =>
    request<{ id: number; inspectedAt: string }>('/inspections', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ marker_id: markerId, status }),
    }),

  results: (p: { markerId?: number; start?: string; end?: string } = {}) =>
    request<{ total: number; items: ArInspectionRow[] }>(
      '/results' + query({ markerId: p.markerId, start: p.start, end: p.end }),
    ),

  deleteResult: (id: number) =>
    request<{ deleted: boolean }>(`/results/${id}`, { method: 'DELETE' }),

  stats: () => request<ArStat[]>('/stats'),

  equipmentOptions: () =>
    request<{ batch: { id: number; filename: string } | null; options: EquipmentOption[] }>(
      '/equipment-options',
    ),

  deviceQuality: (markerId: number) => request<DeviceQuality>(`/devices/${markerId}/quality`),

  exportUrl: () => `${BASE}/export`,
}

/** AR.js 3×3 barcode marker 的有效範圍 */
export const MAX_MARKER_ID = 63

export function markerImageSrc(markerId: number): string | null {
  return Number.isInteger(markerId) && markerId >= 0 && markerId <= MAX_MARKER_ID
    ? `/markers/3x3/${markerId}.png`
    : null
}
