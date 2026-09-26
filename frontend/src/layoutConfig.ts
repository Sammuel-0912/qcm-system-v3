// PM1 整線 layout 熱區設定
// ---------------------------------------------------------------------------
// 座標是背景圖的百分比（0~100），改圖不用改程式，只要重抓這份表。
//
// 為什麼熱區綁 targetId 而不是站別名稱：
//   KPOV 庫的「站別」與現場實際名稱不完全相符（例如 OT00420105 在 KPOV 庫是
//   「鎖保險絲」，現場實際是「鎖銅排3」；OT00420108 在庫裡是「鎖軟銅排」，
//   現場是「鎖Fuse」）。設備代碼才是穩定的唯一權威，所以 CTP 熱區一律綁
//   `equip:<設備代碼>`，顯示則走 displayName（現場名稱）。
//   OP 站沒有設備代碼，只能綁 `op:<站別>`。
//
// confidence:
//   'confirmed' = 名稱與位置都對得上，可直接用
//   'guess'     = 我依標註圖推測的位置，需要現場確認
// ---------------------------------------------------------------------------

import layoutImage from './assets/pm1-layout.jpg'

export type Hotspot = {
  targetId: string
  displayName: string
  kpovStation: string
  kind: 'CTP' | 'OP'
  /** 背景圖百分比座標 */
  rect: { x: number; y: number; w: number; h: number }
  confidence: 'confirmed' | 'guess'
  note?: string
}

// 必須用 import，不能寫成路徑字串：Vite 只處理 import 進來的資源，
// 純字串它不會解析 —— dev 下會變成相對於當前網址的路徑，build 後
// dist/ 裡也沒有 src/ 目錄，兩邊都會 404。
// 走 import 另有一個好處：產出檔名帶內容 hash，換圖後 URL 自動改變，
// 不會被瀏覽器或 CDN 的舊快取擋住。
export const LAYOUT_IMAGE = layoutImage
/** 背景圖原始尺寸，用來維持長寬比 */
export const LAYOUT_ASPECT = { width: 3822, height: 1120 }

// 座標取自 2026-09-26 版整線 layout 圖的標籤位置（百分比）。
// 換圖時只要重抓這份表，程式不用動。
export const HOTSPOTS: Hotspot[] = [
  // ---------- CTP（綁設備代碼） ----------
  {
    targetId: 'equip:OT00420112',
    displayName: '鎖PWB板機1',
    kpovStation: '鎖PWB',
    kind: 'CTP',
    rect: { x: 16.8, y: 24.38, w: 3.19, h: 4.02 },
    confidence: 'confirmed',
    note: 'layout 標籤：鎖付螺絲/螺柱（左半）；Dim_Equipment 稱鎖PCB板1',
  },
  {
    targetId: 'equip:OT00420110',
    displayName: '鎖PWB板機2',
    kpovStation: '鎖螺柱',
    kind: 'CTP',
    rect: { x: 19.99, y: 24.38, w: 3.19, h: 4.02 },
    confidence: 'confirmed',
    note: 'layout 標籤：鎖付螺絲/螺柱（右半）；Dim_Equipment 稱鎖PCB板2',
  },
  {
    targetId: 'equip:OT00420118',
    displayName: '鎖銅排1',
    kpovStation: '鎖銅排',
    kind: 'CTP',
    rect: { x: 23.44, y: 24.38, w: 6.54, h: 4.02 },
    confidence: 'confirmed',
    note: 'layout 標籤：固定電感&銅排',
  },
  {
    targetId: 'equip:OT00420104',
    displayName: '鎖銅排2',
    kpovStation: '鎖電感',
    kind: 'CTP',
    rect: { x: 30.09, y: 24.38, w: 6.62, h: 4.02 },
    confidence: 'confirmed',
    note: 'layout 標籤：鎖付電感&銅排；KPOV 庫稱鎖電感',
  },
  {
    targetId: 'equip:OT00420105',
    displayName: '鎖銅排3',
    kpovStation: '鎖保險絲',
    kind: 'CTP',
    rect: { x: 40.21, y: 24.38, w: 4.29, h: 4.02 },
    confidence: 'confirmed',
    note: 'layout 標籤：鎖付銅排；KPOV 庫稱鎖保險絲',
  },
  {
    targetId: 'equip:OT00420108',
    displayName: '鎖Fuse',
    kpovStation: '鎖軟銅排',
    kind: 'CTP',
    rect: { x: 33.88, y: 55.18, w: 5.39, h: 4.82 },
    confidence: 'confirmed',
    note: 'layout 標籤：固定fuse；KPOV 庫稱鎖軟銅排',
  },
  {
    targetId: 'equip:OT00420114',
    displayName: '鎖上蓋1',
    kpovStation: '鎖上蓋1',
    kind: 'CTP',
    rect: { x: 51.62, y: 53.75, w: 2.46, h: 4.91 },
    confidence: 'confirmed',
    note: 'layout 標籤：鎖上蓋板（左半）',
  },
  {
    targetId: 'equip:OT00420115',
    displayName: '鎖上蓋2',
    kpovStation: '鎖上蓋2',
    kind: 'CTP',
    rect: { x: 54.08, y: 53.75, w: 2.46, h: 4.91 },
    confidence: 'confirmed',
    note: 'layout 標籤：鎖上蓋板（右半）',
  },
  {
    targetId: 'equip:OT00420102',
    displayName: '輔綫自動鎖付',
    kpovStation: '輔綫自動鎖付',
    kind: 'CTP',
    // 副線前面板的四格接縫量測為 x = 666 / 789 / 917 / 1046 / 1173（原圖像素），
    // 「左數來第二格」即 789~917。
    rect: { x: 20.64, y: 54.46, w: 3.35, h: 12.05 },
    confidence: 'confirmed',
    note: 'layout 無文字標籤；下方副線由左數來第二格（現場確認）',
  },
  {
    targetId: 'equip:OT00400010',
    displayName: '散熱膏塗布',
    kpovStation: '散热膏涂布',
    kind: 'CTP',
    // 副線第三格 917~1046（接在輔綫自動鎖付右邊）。
    // 注意：layout 上的「固定散熱塊」是另一個站，與本站無關。
    rect: { x: 23.99, y: 54.46, w: 3.38, h: 12.05 },
    confidence: 'confirmed',
    note: 'layout 無文字標籤；下方副線由左數來第三格，即輔綫自動鎖付右邊一格（現場確認）',
  },

  // ---------- OP（綁站別，無設備代碼） ----------
  {
    targetId: 'op:插線/理線',
    displayName: '插線/理線',
    kpovStation: '插線/理線',
    kind: 'OP',
    rect: { x: 11.05, y: 51.61, w: 4.47, h: 3.75 },
    confidence: 'confirmed',
    note: 'layout 標籤：插線&理線',
  },
  {
    targetId: 'op:固定絕緣片',
    displayName: '固定絕緣片',
    kpovStation: '固定絕緣片',
    kind: 'OP',
    rect: { x: 40.55, y: 64.38, w: 13.71, h: 5.62 },
    confidence: 'confirmed',
    note: 'layout 標籤：鎖絕緣片/固定PWB板（與舊圖的鎖絕緣片/PWB板為同一站）',
  },
]

export const UNPLACED_TARGETS = [
  { targetId: 'op:鎖後蓋', displayName: '鎖後蓋', reason: '依指示暫不放熱區' },
  { targetId: 'op:鎖銅排', displayName: '鎖銅排（人工）', reason: 'layout 位置待確認' },
]
