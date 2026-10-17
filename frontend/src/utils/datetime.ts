const pad = (n: number) => String(n).padStart(2, '0')

/**
 * 後端時間一律是帶時區的 UTC（例：2026-10-09T02:31:06+00:00），
 * 這裡轉成瀏覽器本地時間 `YYYY-MM-DD HH:mm:ss`。不可直接截字串，否則顯示的是 UTC。
 */
export function formatLocalDateTime(value: string): string {
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  )
}

/** `<input type="datetime-local">` 的值（本地時間、不帶時區）轉成帶時區的 ISO，供後端以 UTC 比較 */
export function localInputToIso(value: string): string | undefined {
  if (!value) return undefined
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? undefined : d.toISOString()
}
