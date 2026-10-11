import { useEffect, useState } from 'react'

import { api } from '../api/client'

// 後端 TTL 為 45 秒（backend/app/services/presence.py），間隔要明顯小於它
const INTERVAL_MS = 15_000
const SID_KEY = 'qcm-presence-sid'

// 每個頁面各自掛一個 AppShell，換頁時 hook 會重掛；記住上次的數字避免頁首閃爍
let lastOnline: number | null = null

// crypto.randomUUID 只在安全環境（https / localhost）存在；內網用 http://IP 開啟時要退回
function randomId(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}

// sessionStorage：每個分頁各算一人。換成 localStorage 則同一瀏覽器多分頁只算一人。
function sessionId(): string {
  try {
    let sid = sessionStorage.getItem(SID_KEY)
    if (!sid) {
      sid = randomId()
      sessionStorage.setItem(SID_KEY, sid)
    }
    return sid
  } catch {
    // 無痕模式或儲存被封鎖時，退回單次載入有效的 ID
    return randomId()
  }
}

/**
 * 回報「我還在看」並取得目前線上人數。
 * 分頁在背景時暫停心跳，伺服器會在 TTL 後自動把這個分頁算作離開。
 */
export function usePresence(): number | null {
  const [online, setOnline] = useState<number | null>(lastOnline)

  useEffect(() => {
    const sid = sessionId()
    let timer: ReturnType<typeof setInterval> | undefined

    const beat = () => {
      api
        .heartbeat(sid)
        .then((r) => {
          lastOnline = r.online
          setOnline(r.online)
        })
        .catch(() => {})
    }
    const start = () => {
      if (timer) return
      beat()
      timer = setInterval(beat, INTERVAL_MS)
    }
    const stop = () => {
      clearInterval(timer)
      timer = undefined
    }
    const onVisibility = () => (document.hidden ? stop() : start())
    // 頁面可能進 bfcache 再被還原；先停掉計時器，還原時 visibilitychange 會重新 start
    const onPageHide = () => {
      stop()
      api.leave(sid)
    }

    if (!document.hidden) start()
    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener('pagehide', onPageHide)
    return () => {
      stop()
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('pagehide', onPageHide)
    }
  }, [])

  return online
}
