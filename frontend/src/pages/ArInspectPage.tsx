import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { arApi, type ArDevice, type DeviceQuality } from '../api/arClient'
import type { CheckMonitorRow, CheckStatus } from '../api/client'
import { LEVEL_COLORS } from '../constants'
import { usePresence } from '../hooks/usePresence'

// 以 ?url 取得套件預建檔的位址：Vite 會原樣複製到 dist/assets 並加 hash，不經 bundler 解析。
// AR.js 的預建檔是依賴全域 AFRAME 的 IIFE，無法當成 ESM import，故以 classic <script> 注入。
// 由自家伺服器供應、不依賴 CDN，內網或離線環境也能用。
import aframeUrl from 'aframe/dist/aframe-master.min.js?url'
import arjsUrl from '@ar-js-org/ar.js/aframe/build/aframe-ar.js?url'

const REQUEST_TIMEOUT_MS = 8000
const QR_AUTO_DETECT_DELAY_MS = 600
const MARKER_LOST_DELAY_MS = 2500
const FEEDBACK_DURATION_MS = 1800
const SCENE_ID = 'ar-scene-dynamic'

const CHECK_STATUS: Record<CheckStatus, { label: string; className: string }> = {
  ok: { label: '正常', className: 'bg-emerald-100 text-emerald-800' },
  warn: { label: '異常', className: 'bg-red-100 text-red-700' },
  overdue: { label: '逾期', className: 'bg-amber-100 text-amber-800' },
  never: { label: '未點檢', className: 'bg-slate-100 text-slate-600' },
}

// AR.js 與 A-Frame 執行時還會各抓一個外部檔案，套件本身沒有附：
//   AR.js  -> https://ar-js-org.github.io/.../camera_para.dat（相機校正，沒有它就偵測不到 marker）
//   A-Frame -> https://cdn.aframe.io/fonts/Roboto-msdf.json（a-text 的預設字型）
// 工廠內網連不到外網，這兩個請求會失敗而且不會有明顯錯誤訊息，
// 因此一併放進 public/ 由自家伺服器供應。
const CAMERA_PARAM_URL = '/ar/camera_para.dat'
const TEXT_FONT_URL = '/fonts/Roboto-msdf.json'

const MARKER_COLORS = [
  '#22c55e', '#3b82f6', '#f59e0b', '#a855f7',
  '#ef4444', '#06b6d4', '#84cc16', '#f97316',
  '#ec4899', '#14b8a6', '#eab308', '#8b5cf6',
]

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) {
      resolve()
      return
    }
    const el = document.createElement('script')
    el.src = src
    el.onload = () => resolve()
    el.onerror = () => reject(new Error('載入失敗：' + src))
    document.head.appendChild(el)
  })
}

/**
 * 移除 A-Frame 注入的 scene 並還原文件樣式。
 *
 * 這段一定要確實執行：AR 啟動時會把 body / html 的背景改成透明好讓相機畫面透出來，
 * 沒還原的話回到品控力頁面會整片透明（ar-integration-spec.md REQ-AR-02）。
 */
function teardownScene() {
  document.getElementById(SCENE_ID)?.remove()
  // A-Frame 會在 body 留下自己的 class 與 inline style
  document.body.style.background = ''
  document.documentElement.style.background = ''
  document.body.classList.remove('a-body', 'a-fullscreen')
  document.documentElement.classList.remove('a-fullscreen')
  // 保險：fullscreen 樣式殘留時 video 會蓋住整頁
  document.querySelectorAll('video.a-canvas, canvas.a-canvas').forEach((el) => el.remove())
}

type Phase = 'loading' | 'start' | 'ar'

export default function ArInspectPage() {
  // 此頁不用 AppShell，另外回報心跳，掃描中的人才會被算進線上人數（不顯示）
  usePresence()
  const [searchParams] = useSearchParams()
  const urlMarkerId = searchParams.get('marker_id')
  const qrMode = urlMarkerId !== null

  const [phase, setPhase] = useState<Phase>('loading')
  const [devices, setDevices] = useState<ArDevice[]>([])
  const [connError, setConnError] = useState<string | null>(null)
  const [scriptsReady, setScriptsReady] = useState(false)
  const [activeDevice, setActiveDevice] = useState<ArDevice | null>(null)
  const [quality, setQuality] = useState<DeviceQuality | null>(null)
  // 高風險項（Level 3）點檢項目；有項目時改為逐項點檢
  const [checkItems, setCheckItems] = useState<CheckMonitorRow[]>([])
  const checkItemsRef = useRef<CheckMonitorRow[]>([])
  checkItemsRef.current = checkItems
  const [sheetOpen, setSheetOpen] = useState(false)
  const [feedback, setFeedback] = useState<{ type: 'ok' | 'error'; msg: string } | null>(null)
  const [busy, setBusy] = useState(false)

  const cacheRef = useRef<Record<number, ArDevice>>({})
  const devicesRef = useRef<ArDevice[]>([])
  const markerIdRef = useRef<number | null>(null)
  const submitting = useRef(false)

  useEffect(() => {
    loadScript(aframeUrl)
      .then(() => loadScript(arjsUrl))
      .then(() => setScriptsReady(true))
      .catch((e) => setConnError(String(e.message ?? e)))
  }, [])

  // 離開頁面務必清乾淨
  useEffect(() => teardownScene, [])

  const onMarkerFound = useCallback((id: number) => {
    if (markerIdRef.current === id) return
    markerIdRef.current = id
    const dev =
      cacheRef.current[id] ??
      ({ markerId: id, name: `Marker ${id}`, description: null, workInstruction: null, imageUrl: null, equipmentCode: null, createdAt: null } as ArDevice)
    setActiveDevice(dev)
    setSheetOpen(true)
    setFeedback(null)
    setBusy(false)
    setQuality(null)
    setCheckItems([])
    // 掃到就順便抓這台機器的品控力狀態——點檢當下看得到它的等級，才是整合的意義
    arApi.deviceQuality(id).then(setQuality).catch(() => setQuality(null))
    arApi
      .checkItems(id)
      .then((r) => setCheckItems(r.items))
      .catch(() => setCheckItems([]))
  }, [])

  const onMarkerLost = useCallback(() => {
    if (qrMode) return
    setTimeout(() => {
      // 逐項點檢時要邊看設備邊按，鏡頭移開不關面板，改由「完成」按鈕關閉
      if (checkItemsRef.current.length > 0) return
      if (markerIdRef.current !== null) {
        markerIdRef.current = null
        setSheetOpen(false)
      }
    }, MARKER_LOST_DELAY_MS)
  }, [qrMode])

  useEffect(() => {
    let alive = true
    arApi
      .devices()
      .then((list) => {
        if (!alive) return
        list.forEach((d) => (cacheRef.current[d.markerId] = d))
        devicesRef.current = list
        setDevices(list)
      })
      .catch(() => alive && setConnError('無法取得設備清單，請確認後端是否正常'))
      .finally(() => {
        if (!alive) return
        setPhase('start')
        if (qrMode) setTimeout(() => onMarkerFound(Number(urlMarkerId)), QR_AUTO_DETECT_DELAY_MS)
      })
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const startAR = useCallback(() => {
    // 每次啟動前先清掉上一輪的殘留，避免重複進出頁面時疊加 scene
    teardownScene()
    setPhase('ar')

    document.body.style.background = 'transparent'
    document.documentElement.style.background = 'transparent'

    const scene = document.createElement('a-scene')
    scene.id = SCENE_ID
    scene.setAttribute(
      'arjs',
      'sourceType:webcam; detectionMode:mono_and_matrix; matrixCodeType:3x3; ' +
        `debugUIEnabled:false; cameraParametersUrl:${CAMERA_PARAM_URL};`,
    )
    scene.setAttribute('vr-mode-ui', 'enabled:false')
    scene.setAttribute('renderer', 'logarithmicDepthBuffer:true; precision:medium; alpha:true;')
    scene.style.cssText = 'position:fixed;top:0;left:0;width:100vw;height:100vh;z-index:1;'

    const camera = document.createElement('a-entity')
    camera.setAttribute('camera', '')
    scene.appendChild(camera)
    document.body.appendChild(scene)

    scene.addEventListener(
      'loaded',
      () => {
        devicesRef.current.forEach((dev) => {
          const color = MARKER_COLORS[dev.markerId % MARKER_COLORS.length]
          const marker = document.createElement('a-marker')
          marker.setAttribute('type', 'barcode')
          marker.setAttribute('value', String(dev.markerId))

          const box = document.createElement('a-box')
          box.setAttribute('position', '0 0.05 0')
          box.setAttribute('scale', '0.4 0.04 0.4')
          box.setAttribute('color', color)
          box.setAttribute('opacity', '0.85')
          marker.appendChild(box)

          if (dev.imageUrl) {
            const img = document.createElement('a-image')
            img.setAttribute('position', '0 0.6 0')
            img.setAttribute('scale', '0.9 0.65 1')
            // imageUrl 已是 /api/ar/uploads/... 的同源相對路徑，不需再拼 host
            img.setAttribute('src', dev.imageUrl)
            img.setAttribute('look-at', '[camera]')
            marker.appendChild(img)
          }

          const text = document.createElement('a-text')
          text.setAttribute('value', dev.name)
          text.setAttribute('position', '0 1.3 0')
          text.setAttribute('scale', '0.45 0.45 0.45')
          text.setAttribute('color', 'white')
          text.setAttribute('align', 'center')
          text.setAttribute('font', TEXT_FONT_URL)
          marker.appendChild(text)

          marker.addEventListener('markerFound', () => onMarkerFound(dev.markerId))
          marker.addEventListener('markerLost', () => onMarkerLost())
          scene.insertBefore(marker, camera)
        })
      },
      { once: true },
    )
  }, [onMarkerFound, onMarkerLost])

  async function submitItem(item: CheckMonitorRow, status: 'ok' | 'warn') {
    const markerId = markerIdRef.current
    if (submitting.current || markerId === null) return
    submitting.current = true
    setBusy(true)
    try {
      await arApi.inspect(markerId, status, { kpovNo: item.kpovNo, checkContent: item.checkContent })
      setFeedback({
        type: 'ok',
        msg: `已記錄「${item.checkContent}」：${status === 'ok' ? '正常' : '異常'}`,
      })
      // 逐項點檢不自動關閉：一台設備有多個項目，要全部點完
      const refreshed = await arApi.checkItems(markerId)
      setCheckItems(refreshed.items)
    } catch (err) {
      setFeedback({ type: 'error', msg: err instanceof Error ? err.message : '上傳失敗' })
    } finally {
      setBusy(false)
      submitting.current = false
    }
  }

  async function submit(status: 'ok' | 'warn') {
    if (submitting.current || markerIdRef.current === null) return
    submitting.current = true
    setBusy(true)
    const timer = setTimeout(() => {}, REQUEST_TIMEOUT_MS)
    try {
      await arApi.inspect(markerIdRef.current, status)
      setFeedback({ type: 'ok', msg: status === 'ok' ? '已記錄：正常' : '已記錄：異常' })
      if (!qrMode) {
        setTimeout(() => {
          setSheetOpen(false)
          markerIdRef.current = null
          setFeedback(null)
          setBusy(false)
        }, FEEDBACK_DURATION_MS)
      } else {
        setTimeout(() => {
          setFeedback(null)
          setBusy(false)
        }, FEEDBACK_DURATION_MS)
      }
    } catch (err) {
      setFeedback({ type: 'error', msg: err instanceof Error ? err.message : '上傳失敗' })
      setBusy(false)
    } finally {
      clearTimeout(timer)
      submitting.current = false
    }
  }

  // ── 掃描前的準備畫面 ───────────────────────────────────────────────
  if (phase !== 'ar') {
    return (
      <div className="min-h-screen bg-slate-900 text-slate-100">
        <div className="mx-auto flex min-h-screen max-w-lg flex-col justify-center px-6 py-10">
          <h1 className="text-xl font-semibold">AR 掃描點檢</h1>
          <p className="mt-1 text-sm text-slate-400">
            將鏡頭對準貼在設備上的 AR marker，系統會帶出作業指引與該機台的品控力狀態。
          </p>

          {connError && (
            <div className="mt-5 rounded-md border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
              {connError}
            </div>
          )}

          <div className="mt-6 rounded-lg border border-slate-700 bg-slate-800/60 p-4 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-slate-400">已登錄設備</span>
              <span className="font-semibold">{devices.length} 台</span>
            </div>
            <div className="mt-2 flex items-center justify-between">
              <span className="text-slate-400">AR 套件</span>
              <span className={scriptsReady ? 'text-emerald-400' : 'text-slate-400'}>
                {scriptsReady ? '已就緒' : '載入中…'}
              </span>
            </div>
          </div>

          {devices.length === 0 && !connError && phase === 'start' && (
            <p className="mt-4 text-sm text-amber-300">
              尚未登錄任何設備，掃描不會有反應。請先到設備管理建立 marker。
            </p>
          )}

          {!window.isSecureContext && (
            <p className="mt-4 rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
              目前不是安全連線（HTTPS 或 localhost），瀏覽器不會開放相機。
              AR 掃描在此環境下無法運作。
            </p>
          )}

          <button
            onClick={startAR}
            disabled={!scriptsReady || phase === 'loading'}
            className="mt-6 rounded-md bg-slate-100 px-4 py-3 text-sm font-semibold text-slate-900 transition hover:bg-white disabled:opacity-40"
          >
            {phase === 'loading' ? '準備中…' : '開始 AR 掃描'}
          </button>

          <div className="mt-4 flex gap-3 text-sm">
            <Link to="/ar/dashboard" className="text-slate-400 underline hover:text-slate-200">
              儀表板
            </Link>
            <Link to="/ar/devices" className="text-slate-400 underline hover:text-slate-200">
              設備管理
            </Link>
            <Link to="/quality" className="ml-auto text-slate-400 underline hover:text-slate-200">
              品控力象限
            </Link>
          </div>
        </div>
      </div>
    )
  }

  // ── 掃描中：A-Frame 的 canvas 在底下，這層是覆蓋的 UI ────────────────
  return (
    <div className="pointer-events-none fixed inset-0 z-10 flex flex-col">
      <div className="pointer-events-auto flex items-center gap-3 bg-black/60 px-4 py-3 text-sm text-white backdrop-blur">
        <span className="font-semibold tracking-wide">AR 點檢</span>
        {!sheetOpen && <span className="text-xs text-slate-300">對準設備上的 marker…</span>}
        <Link
          to="/ar/dashboard"
          onClick={teardownScene}
          className="ml-auto rounded-full border border-white/40 px-3 py-1 text-xs"
        >
          結束
        </Link>
      </div>

      <div className="flex-1" />

      {sheetOpen && activeDevice && (
        <div className="pointer-events-auto max-h-[70vh] overflow-y-auto rounded-t-2xl bg-white p-5 shadow-2xl">
          <div className="flex items-baseline gap-2">
            <h2 className="text-lg font-semibold text-slate-900">{activeDevice.name}</h2>
            <span className="font-mono text-xs text-slate-400">Marker {activeDevice.markerId}</span>
          </div>
          {activeDevice.description && (
            <p className="mt-0.5 text-sm text-slate-500">{activeDevice.description}</p>
          )}

          {quality?.linked && (
            <div className="mt-3 rounded-md bg-slate-50 p-2.5">
              <div className="flex flex-wrap items-center gap-1.5 text-xs">
                <span className="text-slate-500">{quality.station}</span>
                <span className="text-slate-400">·</span>
                <span className="text-slate-500">{quality.kpovCount} 個 KPOV</span>
                {[0, 1, 2, 3].map((level) => {
                  const n = quality.levelCounts[String(level)] ?? 0
                  if (!n) return null
                  return (
                    <span
                      key={level}
                      className="inline-flex h-4 items-center rounded px-1 text-[10px] font-semibold text-slate-800 ring-1 ring-black/10"
                      style={{ backgroundColor: LEVEL_COLORS[level] }}
                    >
                      L{level} {n}
                    </span>
                  )
                })}
              </div>
              {quality.escalatedOpen > 0 && (
                <p className="mt-1 text-xs font-medium text-red-700">
                  {quality.escalatedOpen} 項 KPOV 惡化中，點檢時請特別留意
                </p>
              )}
            </div>
          )}

          {activeDevice.imageUrl && (
            <img
              src={activeDevice.imageUrl}
              alt="作業圖"
              className="mt-3 max-h-48 w-full rounded border border-slate-200 object-contain"
            />
          )}

          {activeDevice.workInstruction && (
            <pre className="mt-3 whitespace-pre-wrap rounded bg-slate-50 p-3 text-sm leading-relaxed text-slate-700">
              {activeDevice.workInstruction}
            </pre>
          )}

          {feedback && (
            <div
              className={`mt-3 rounded-md px-3 py-2 text-sm ${
                feedback.type === 'ok'
                  ? 'bg-emerald-50 text-emerald-800'
                  : 'bg-red-50 text-red-700'
              }`}
            >
              {feedback.msg}
            </div>
          )}

          {checkItems.length > 0 ? (
            <div className="mt-4">
              <h3 className="text-sm font-semibold text-slate-800">
                Level 3 點檢項目
                <span className="ml-2 text-xs font-normal text-slate-500">
                  {checkItems.filter((i) => i.status === 'ok').length}/{checkItems.length} 已於時限內完成
                </span>
              </h3>
              <ul className="mt-2 space-y-2">
                {checkItems.map((item) => (
                  <li key={item.id} className="rounded-md border border-slate-200 p-3">
                    <div className="flex items-start gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-slate-800">{item.checkContent}</p>
                        <p className="mt-0.5 text-xs text-slate-400">
                          {item.kpovName} {item.kpovNo} · {item.frequency ?? `${item.intervalHours}h/次`}
                        </p>
                      </div>
                      <span
                        className={`shrink-0 rounded px-1.5 py-0.5 text-xs font-semibold ${CHECK_STATUS[item.status].className}`}
                      >
                        {CHECK_STATUS[item.status].label}
                      </span>
                    </div>
                    <div className="mt-2 grid grid-cols-2 gap-2">
                      <button
                        onClick={() => void submitItem(item, 'ok')}
                        disabled={busy}
                        className="rounded-md bg-emerald-600 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-40"
                      >
                        正常
                      </button>
                      <button
                        onClick={() => void submitItem(item, 'warn')}
                        disabled={busy}
                        className="rounded-md bg-amber-500 py-2 text-sm font-semibold text-white transition hover:bg-amber-600 disabled:opacity-40"
                      >
                        異常
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
              <button
                onClick={() => {
                  setSheetOpen(false)
                  setCheckItems([])
                  setFeedback(null)
                  markerIdRef.current = null
                }}
                className="mt-3 w-full rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                完成，繼續掃描
              </button>
            </div>
          ) : (
          <div className="mt-4 grid grid-cols-2 gap-3">
            <button
              onClick={() => void submit('ok')}
              disabled={busy}
              className="rounded-md bg-emerald-600 py-3 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:opacity-40"
            >
              正常
            </button>
            <button
              onClick={() => void submit('warn')}
              disabled={busy}
              className="rounded-md bg-amber-500 py-3 text-sm font-semibold text-white transition hover:bg-amber-600 disabled:opacity-40"
            >
              異常
            </button>
          </div>
          )}
        </div>
      )}
    </div>
  )
}
