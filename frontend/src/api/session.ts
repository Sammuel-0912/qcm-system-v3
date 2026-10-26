/**
 * 登入狀態與目前資料集（spec §15 RBAC）。
 *
 * - 登入靠後端設定的 httpOnly cookie（qcm_session），前端碰不到權杖，fetch 同源會自動帶上。
 * - 目前選的資料集（一條線，例：WJ1-DCS-PM1）記在 localStorage，每個 API 請求以
 *   header `X-QCM-Dataset` 帶給後端；瀏覽器直接下載的網址（匯出 Excel）改用 `?dataset=`。
 * - 任何 API 回 401（未登入或登入失效）時發出 `qcm:unauthorized` 事件，由 AuthProvider 導回登入頁。
 */
const DATASET_KEY = 'qcm.dataset'
export const DATASET_HEADER = 'X-QCM-Dataset'
export const UNAUTHORIZED_EVENT = 'qcm:unauthorized'

let currentDataset: string | null = null

function readStored(): string | null {
  try {
    return window.localStorage.getItem(DATASET_KEY)
  } catch {
    return null
  }
}

export function getDataset(): string | null {
  if (currentDataset === null) currentDataset = readStored()
  return currentDataset
}

export function setDataset(key: string | null) {
  currentDataset = key
  try {
    if (key) window.localStorage.setItem(DATASET_KEY, key)
    else window.localStorage.removeItem(DATASET_KEY)
  } catch {
    // 無法存取瀏覽器儲存時只是不記住選擇
  }
}

/** 所有 API 請求都走這裡：帶上資料集 header；401 時通知登入頁。 */
export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  const dataset = getDataset()
  if (dataset && !headers.has(DATASET_HEADER)) headers.set(DATASET_HEADER, dataset)
  const res = await fetch(input, { ...init, headers, credentials: 'same-origin' })
  if (res.status === 401 && !input.includes('/auth/login')) {
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
  }
  return res
}

/** 直接下載用的網址：帶不了 header，把資料集放進查詢參數。 */
export function withDataset(url: string): string {
  const dataset = getDataset()
  if (!dataset) return url
  return `${url}${url.includes('?') ? '&' : '?'}dataset=${encodeURIComponent(dataset)}`
}
