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

export const LAYOUT_IMAGE = '/pm1-layout.png'
/** 背景圖原始尺寸，用來維持長寬比 */
export const LAYOUT_ASPECT = { width: 1242, height: 288 }

export const HOTSPOTS: Hotspot[] = [
  // ---------- CTP（綁設備代碼） ----------
  // 位置依使用者在 layout 上的手寫標註推定：
  //   「鎖付螺絲/螺柱」位置實為兩台 PWB 板機（Dim_Equipment 稱鎖PCB板1/2），
  //   銅排家族由左至右為 鎖銅排1 → 鎖銅排2 → 鎖銅排3，
  //   「固定保險絲/銅排」位置實為鎖 Fuse。
  {
    targetId: 'equip:OT00420112',
    displayName: '鎖PWB板機1',
    kpovStation: '鎖PWB',
    kind: 'CTP',
    rect: { x: 11.1, y: 38.2, w: 2.8, h: 5.9 },
    confidence: 'confirmed',
    note: 'layout 標籤：鎖付螺絲/螺柱（左半）；Dim_Equipment 稱鎖PCB板1',
  },
  {
    targetId: 'equip:OT00420110',
    displayName: '鎖PWB板機2',
    kpovStation: '鎖螺柱',
    kind: 'CTP',
    rect: { x: 13.9, y: 38.2, w: 2.8, h: 5.9 },
    confidence: 'confirmed',
    note: 'layout 標籤：鎖付螺絲/螺柱（右半）；Dim_Equipment 稱鎖PCB板2，KPOV 庫稱鎖螺柱',
  },
  {
    targetId: 'equip:OT00420118',
    displayName: '鎖銅排1',
    kpovStation: '鎖銅排',
    kind: 'CTP',
    rect: { x: 17.3, y: 38.2, w: 6.0, h: 5.9 },
    confidence: 'confirmed',
    note: 'layout 標籤：固定電感&銅排',
  },
  {
    targetId: 'equip:OT00420104',
    displayName: '鎖銅排2',
    kpovStation: '鎖電感',
    kind: 'CTP',
    rect: { x: 24.0, y: 38.5, w: 6.0, h: 5.9 },
    confidence: 'confirmed',
    note: 'layout 標籤：鎖付電感/銅排；KPOV 庫稱鎖電感',
  },
  {
    targetId: 'equip:OT00420105',
    displayName: '鎖銅排3',
    kpovStation: '鎖保險絲',
    kind: 'CTP',
    rect: { x: 35.2, y: 39.2, w: 4.8, h: 5.6 },
    confidence: 'confirmed',
    note: 'layout 標籤：鎖付銅排；KPOV 庫稱鎖保險絲',
  },
  {
    targetId: 'equip:OT00420108',
    displayName: '鎖Fuse',
    kpovStation: '鎖軟銅排',
    kind: 'CTP',
    rect: { x: 28.7, y: 68.1, w: 6.2, h: 5.6 },
    confidence: 'confirmed',
    note: 'layout 標籤：固定保險絲/銅排；KPOV 庫稱鎖軟銅排',
  },
  {
    targetId: 'equip:OT00420114',
    displayName: '鎖上蓋1',
    kpovStation: '鎖上蓋1',
    kind: 'CTP',
    rect: { x: 49.4, y: 50.5, w: 2.9, h: 10.0 },
    confidence: 'confirmed',
    note: '鎖上蓋板下方左側六軸螺絲機',
  },
  {
    targetId: 'equip:OT00420115',
    displayName: '鎖上蓋2',
    kpovStation: '鎖上蓋2',
    kind: 'CTP',
    rect: { x: 52.3, y: 50.5, w: 2.9, h: 10.0 },
    confidence: 'confirmed',
    note: '鎖上蓋板下方右側六軸螺絲機',
  },
  {
    targetId: 'equip:OT00420102',
    displayName: '輔綫自動鎖付',
    kpovStation: '輔綫自動鎖付',
    kind: 'CTP',
    rect: { x: 14.3, y: 65.6, w: 2.6, h: 6.9 },
    confidence: 'guess',
    note: '標註圖紅框標於下方副線（左）',
  },
  {
    targetId: 'equip:OT00400010',
    displayName: '散熱膏塗布',
    kpovStation: '散热膏涂布',
    kind: 'CTP',
    rect: { x: 16.9, y: 65.6, w: 2.6, h: 6.9 },
    confidence: 'guess',
    note: '標註圖紅框標於下方副線（右）',
  },

  // ---------- OP（綁站別，無設備代碼） ----------
  {
    targetId: 'op:插線/理線',
    displayName: '插線/理線',
    kpovStation: '插線/理線',
    kind: 'OP',
    rect: { x: 4.4, y: 64.2, w: 4.8, h: 5.9 },
    confidence: 'confirmed',
  },
  {
    targetId: 'op:鎖後蓋',
    displayName: '鎖後蓋',
    kpovStation: '鎖後蓋',
    kind: 'OP',
    rect: { x: 16.8, y: 59.4, w: 3.4, h: 5.9 },
    confidence: 'confirmed',
  },
  {
    targetId: 'op:固定絕緣片',
    displayName: '固定絕緣片',
    kpovStation: '固定絕緣片',
    kind: 'OP',
    rect: { x: 40.3, y: 68.1, w: 6.7, h: 5.6 },
    confidence: 'guess',
    note: 'layout 標籤：鎖絕緣片/PWB板',
  },
  // op:鎖銅排（人工）尚未確認在 layout 上的位置，依指示暫不放熱區。
]

export const UNPLACED_TARGETS = [
  { targetId: 'op:鎖銅排', displayName: '鎖銅排（人工）', reason: 'layout 位置待確認' },
]
