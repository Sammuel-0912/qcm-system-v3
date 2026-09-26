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

export const LAYOUT_IMAGE = '/pm1-layout.jpg'
/** 背景圖原始尺寸，用來維持長寬比 */
export const LAYOUT_ASPECT = { width: 1024, height: 286 }

// 座標取自 2026-09-26 版整線 layout 圖的標籤位置（以百分比表示）。
// 換圖時只要重抓這份表，程式不用動。
export const HOTSPOTS: Hotspot[] = [
  // ---------- CTP（綁設備代碼） ----------
  {
    targetId: 'equip:OT00420112',
    displayName: '鎖PWB板機1',
    kpovStation: '鎖PWB',
    kind: 'CTP',
    rect: { x: 16.3, y: 21.3, w: 3.1, h: 4.9 },
    confidence: 'confirmed',
    note: 'layout 標籤：鎖付螺絲/螺柱（左半）；Dim_Equipment 稱鎖PCB板1',
  },
  {
    targetId: 'equip:OT00420110',
    displayName: '鎖PWB板機2',
    kpovStation: '鎖螺柱',
    kind: 'CTP',
    rect: { x: 19.4, y: 21.3, w: 3.1, h: 4.9 },
    confidence: 'confirmed',
    note: 'layout 標籤：鎖付螺絲/螺柱（右半）；Dim_Equipment 稱鎖PCB板2',
  },
  {
    targetId: 'equip:OT00420118',
    displayName: '鎖銅排1',
    kpovStation: '鎖銅排',
    kind: 'CTP',
    rect: { x: 23.3, y: 21.3, w: 6.2, h: 4.9 },
    confidence: 'confirmed',
    note: 'layout 標籤：固定電感&銅排',
  },
  {
    targetId: 'equip:OT00420104',
    displayName: '鎖銅排2',
    kpovStation: '鎖電感',
    kind: 'CTP',
    rect: { x: 30.3, y: 21.3, w: 6.1, h: 4.9 },
    confidence: 'confirmed',
    note: 'layout 標籤：鎖付電感/銅排；KPOV 庫稱鎖電感',
  },
  {
    targetId: 'equip:OT00420105',
    displayName: '鎖銅排3',
    kpovStation: '鎖保險絲',
    kind: 'CTP',
    rect: { x: 40.3, y: 21.3, w: 4.1, h: 4.9 },
    confidence: 'confirmed',
    note: 'layout 標籤：鎖付銅排；KPOV 庫稱鎖保險絲',
  },
  {
    targetId: 'equip:OT00420108',
    displayName: '鎖Fuse',
    kpovStation: '鎖軟銅排',
    kind: 'CTP',
    rect: { x: 33.8, y: 53.1, w: 5.3, h: 5.6 },
    confidence: 'confirmed',
    note: 'layout 標籤：固定fuse；KPOV 庫稱鎖軟銅排',
  },
  {
    targetId: 'equip:OT00420114',
    displayName: '鎖上蓋1',
    kpovStation: '鎖上蓋1',
    kind: 'CTP',
    rect: { x: 52.5, y: 53.1, w: 2.2, h: 5.6 },
    confidence: 'confirmed',
    note: 'layout 標籤：鎖上蓋板（左半）',
  },
  {
    targetId: 'equip:OT00420115',
    displayName: '鎖上蓋2',
    kpovStation: '鎖上蓋2',
    kind: 'CTP',
    rect: { x: 54.7, y: 53.1, w: 2.2, h: 5.6 },
    confidence: 'confirmed',
    note: 'layout 標籤：鎖上蓋板（右半）',
  },
  {
    targetId: 'equip:OT00420102',
    displayName: '輔綫自動鎖付',
    kpovStation: '輔綫自動鎖付',
    kind: 'CTP',
    rect: { x: 19.5, y: 51.7, w: 4.9, h: 11.2 },
    confidence: 'guess',
    note: '新版 layout 無此標籤，依下方副線機台位置推測',
  },
  {
    targetId: 'equip:OT00400010',
    displayName: '散熱膏塗布',
    kpovStation: '散热膏涂布',
    kind: 'CTP',
    rect: { x: 24.9, y: 51.7, w: 5.4, h: 11.2 },
    confidence: 'guess',
    note: '新版 layout 無此標籤，依下方副線機台位置推測',
  },

  // ---------- OP（綁站別，無設備代碼） ----------
  {
    targetId: 'op:插線/理線',
    displayName: '插線/理線',
    kpovStation: '插線/理線',
    kind: 'OP',
    rect: { x: 10.3, y: 49.6, w: 4.6, h: 4.9 },
    confidence: 'confirmed',
    note: 'layout 標籤：插線&理線',
  },
  {
    targetId: 'op:固定絕緣片',
    displayName: '固定絕緣片',
    kpovStation: '固定絕緣片',
    kind: 'OP',
    rect: { x: 44.1, y: 53.1, w: 5.5, h: 5.6 },
    confidence: 'guess',
    note: 'layout 標籤：固定PWB；名稱不完全相符，待現場確認',
  },
]

export const UNPLACED_TARGETS = [
  { targetId: 'op:鎖銅排', displayName: '鎖銅排（人工）', reason: 'layout 位置待確認' },
  { targetId: 'op:鎖後蓋', displayName: '鎖後蓋', reason: '新版 layout 圖沒有這個標籤' },
]
