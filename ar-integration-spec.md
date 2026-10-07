# AR 點檢整合規格書 v1.0

> 將 [webXR-test](https://github.com/Sammuel-0912/webXR-test) 的 AR 設備點檢整合進品控力系統。
> 決策：單一 SPA、單一後端、設備主檔以設備代碼串接。
>
> 文件狀態：**待確認 D-01 ~ D-04**
> 最後更新：2026-10-07

---

## 1. 現況對照

| | 品控力（qcm-system） | AR 點檢（webXR-test） |
|---|---|---|
| React | 18.3 | **19.2** |
| Vite | 5.4 | **8.0** |
| 語言 | TypeScript（strict） | **JSX，無型別** |
| 樣式 | Tailwind 3.4 | **Bootstrap 5.3 + 自訂 CSS 309 行** |
| 路由 | 無（URL query 參數） | react-router-dom 7 |
| 後端 | FastAPI + SQLAlchemy + Postgres/SQLite | FastAPI + **原生 sqlite3** |
| API 路徑 | `/api/v1/*` | **無前綴**（`/devices`、`/stats`…） |
| 靜態檔 | 無 | `/uploads` 掛載 |
| 深色模式 | 無（僅亮色） | **有**（Bootstrap `data-bs-theme`） |

程式碼規模（AR 端）：前端 1,029 行 JSX + 309 行 CSS，後端 360 行 `main.py`。

---

## 2. 最大風險：AR 頁面會接管整個文件

`ArInspectPage` 不是普通的 React 頁面，它對全域 DOM 動手：

```js
document.body.style.background = 'transparent'        // 讓相機畫面透出來
document.documentElement.style.background = 'transparent'

const scene = document.createElement('a-scene')       // 不走 React vdom
scene.style.cssText = 'position:fixed;top:0;left:0;width:100vw;height:100vh;z-index:1;'
document.body.appendChild(scene)
```

A-Frame 與 AR.js 以 classic `<script>` 注入 `document.head`，**註冊的全域元件無法反註冊**。

### 這對合併後的 SPA 意味著什麼

- **REQ-AR-01** AR 路由必須使用**全螢幕、無應用殼**的 layout。品控力的 header 與導覽列若仍渲染，會與 `position:fixed` 的 scene 互相遮蓋。
- **REQ-AR-02** 離開 AR 路由時，除了移除 `#ar-scene-dynamic`，必須確實還原 `body` 與 `html` 的 background，否則 Tailwind 的 `bg-slate-50` 會失效，整個系統變透明。現有程式有做，但合併後要測「進 AR → 返回 → 再進 AR」的循環。
- **REQ-AR-03** A-Frame 不支援卸載。重複進出 AR 路由可能累積全域狀態。**驗收必須包含連續進出 3 次**，若發現異常，改為離開 AR 路由時 `window.location.assign()` 強制重載該路由（犧牲 SPA 體驗換穩定）。
- **REQ-AR-04** AR 需要安全環境（HTTPS 或 localhost）才能開相機。內網若以 HTTP 提供，AR 功能會靜默失效。

---

## 3. 技術棧統一決策

- **REQ-TECH-01** React 升到 **19.2**，Vite 升到 **8**。
  連帶：Recharts 需從 2.12 升到 **2.13+**（2.12 不支援 React 19）。
  升級後必須重測四張圖表：象限圖、柱狀圖、趨勢折線圖、歷程時間軸。
- **REQ-TECH-02** 樣式統一用 **Tailwind**，移除 Bootstrap。
  Bootstrap 與 Tailwind 的全域 reset 會互相污染（button、form、字級），同頁共存必然出問題。
- **REQ-TECH-03** AR 的三個頁面以 TypeScript 重寫。`tsconfig` 不開 `allowJs`——留一半 JSX 等於放棄型別保護，而 AR 頁正是最需要的地方（大量 DOM 操作）。
- **REQ-TECH-04** 深色模式**不移植**。品控力目前只有亮色，為三個頁面引入主題系統不划算；AR 頁因為相機背景本來就是深色，單獨處理即可。

---

## 4. 路由設計

品控力目前沒有路由（用 URL query 參數）。導入 `react-router-dom` 7。

```
/                     -> 導向 /quality
/quality              品控力象限（現有畫面，保留既有 query 參數）
/ar/dashboard         AR 點檢儀表板
/ar/devices           AR 設備管理
/ar/inspect           AR 掃描點檢      ← 全螢幕，不套應用殼
```

- **REQ-ROUTE-01** 導覽下拉選單放在 header，兩組功能分群顯示。
- **REQ-ROUTE-02** `/quality` 既有的 `view`、`station`、`line`、`target`、`deviatedOnly` query 參數行為不變，現有分享連結不可失效。
- **REQ-ROUTE-03** `/ar/inspect` 使用獨立 layout（無 header、無 padding、全視窗）。其餘路由共用應用殼。
- **REQ-ROUTE-04** AR 的 QR 碼進入點 `?marker_id=N&backend=...` 需保留。`backend` 參數在同源架構下已無意義，但舊 QR 碼仍會帶，解析時忽略即可（不可報錯）。

---

## 5. API 改造

AR 的 12 支 API 全無前綴，合併後會被前端路由吃掉（`/devices` 會被當成 SPA 路由）。

- **REQ-API-01** AR 所有端點掛到 **`/api/ar`** 之下：

| 原路徑 | 新路徑 |
|---|---|
| `GET /devices` | `GET /api/ar/devices` |
| `GET /devices/{marker_id}` | `GET /api/ar/devices/{marker_id}` |
| `POST /devices` | `POST /api/ar/devices` |
| `PATCH /devices/{marker_id}` | `PATCH /api/ar/devices/{marker_id}` |
| `POST /devices/{marker_id}/image` | `POST /api/ar/devices/{marker_id}/image` |
| `DELETE /devices/{marker_id}` | `DELETE /api/ar/devices/{marker_id}` |
| `GET /results` | `GET /api/ar/results` |
| `POST /update` | `POST /api/ar/inspections` ※ |
| `DELETE /results/{record_id}` | `DELETE /api/ar/results/{record_id}` |
| `GET /stats` | `GET /api/ar/stats` |
| `GET /stats/{marker_id}` | `GET /api/ar/stats/{marker_id}` |
| `GET /export` | `GET /api/ar/export` |

※ `POST /update` 改名為語意明確的 `POST /api/ar/inspections`。

- **REQ-API-02** 靜態上傳目錄改掛 `/api/ar/uploads`。
- **REQ-API-03** `config.js` 的 `resolveBackendUrl()` 移除。同源之後 API base 固定為 `/api/ar`，不再有跨來源與 port 推導。
- **REQ-API-04** `image_url` 在 DB 中存**相對路徑**（如 `/uploads/xxx.jpg`）。前端目前做 `BACKEND + dev.image_url` 拼接，改前綴後必須同步調整，否則圖片 404。這包含 AR scene 內的 `a-image` src。
- **REQ-API-05** CORS middleware 可移除（同源）。保留亦無害，但不應再是 `*`。

---

## 6. 資料模型

### 6.1 新增兩張表

```sql
CREATE TABLE ar_device (
  marker_id        INTEGER PRIMARY KEY,          -- AR.js 3x3 barcode，有效值 0~63
  name             TEXT NOT NULL,
  description      TEXT,
  work_instruction TEXT,
  image_url        TEXT,                         -- 相對路徑
  equipment_code   TEXT,                         -- 橋接品控力設備主檔，見 6.2
  created_at       TIMESTAMPTZ NOT NULL
);

CREATE TABLE ar_inspection (
  id          BIGSERIAL PRIMARY KEY,
  marker_id   INTEGER NOT NULL REFERENCES ar_device(marker_id) ON DELETE CASCADE,
  status      TEXT NOT NULL CHECK (status IN ('ok','warn')),
  inspected_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX ON ar_inspection (marker_id, inspected_at DESC);
```

- **REQ-DATA-01** 這兩張表**不掛 `batch_id`**。品控力的維度表是批次式的（每次匯入 Excel 建立新批次），AR 的設備與點檢紀錄是連續累積的營運資料，不隨匯入批次更替。

### 6.2 設備代碼橋接（關鍵）

- **REQ-DATA-02** `ar_device.equipment_code` **不設外鍵**。
  `dim_equipment` 的主鍵是複合鍵 `(batch_id, equipment_code)`，每次匯入都會產生新的一組。若建立外鍵，AR 設備會被綁死在某個匯入批次上，下次匯入就斷裂。
  正確做法：`equipment_code` 存純字串，查詢時 join **當前 active 批次**的 `dim_equipment`。
- **REQ-DATA-03** 設備管理頁提供下拉選單，從 active 批次的 `dim_equipment` 選取 `equipment_code` 綁定。允許留空（不是每台 AR marker 都對應到有 KPOV 的設備）。
- **REQ-DATA-04** 新增 `GET /api/ar/devices/{marker_id}/quality`：回傳該設備在品控力系統的現況等級分佈與最近等級異動。這是兩個系統真正產生關聯的地方——**點檢時看得到這台機器的品控力狀態**。
- **REQ-DATA-05** `equipment_code` 在 active 批次中找不到對應時，UI 顯示「此設備代碼不在目前匯入批次中」，不可靜默忽略。

### 6.3 資料搬遷

- **REQ-DATA-06** 提供一次性搬遷腳本，把現有 `inspection.db`（SQLite）的 `devices` 與 `results` 匯入新表。搬遷前後筆數必須一致並列印對照。
- **REQ-DATA-07** `uploads/` 目錄下的圖檔一併搬到品控力後端的 `DATA_DIR/ar-uploads/`。

---

## 7. 工作量評估

| 項目 | 規模 | 風險 |
|---|---|---|
| React 19 + Vite 8 升級、Recharts 升級 | 小 | **中**（四張圖表需重測） |
| 導入 react-router，建立應用殼與下拉導覽 | 小 | 低 |
| AR 後端改寫為 SQLAlchemy（12 支 API） | 中 | 低 |
| 資料搬遷腳本 | 小 | 低 |
| `DashboardPage` 以 Tailwind 重寫（250 行） | 中 | 低 |
| `DeviceManagePage` 以 Tailwind 重寫（397 行） | **大** | 低 |
| `ArInspectPage` 重寫（339 行） | 中 | **高**（AR scene 與 SPA 共存） |
| 設備代碼橋接 + 品質狀態卡 | 中 | 中 |

`DeviceManagePage` 是純 CRUD 表格與表單，行數最多但最無風險。`ArInspectPage` 行數中等但風險最高，AR scene 的生命週期管理是整個整合最容易出事的地方。

---

## 8. 分期建議

**第一期（可獨立驗收）**
1. React 19 / Vite 8 / Recharts 升級，確認品控力四張圖表無異常
2. 導入 react-router，`/quality` 路由上線，既有 query 參數行為不變
3. AR 後端併入品控力 FastAPI（`/api/ar/*`），資料搬遷完成
4. AR 三個頁面以 Tailwind 重寫並掛上路由

**第二期**
5. 設備代碼橋接 UI 與 `GET /api/ar/devices/{marker_id}/quality`
6. 點檢頁顯示該設備的品控力等級

把第一期切成「升級」與「整合」兩個 PR 會更安全：升級若打壞圖表，不會跟整合的改動混在一起難以定位。

---

## 9. 驗收條件

| # | 條件 |
|---|---|
| AC-1 | 品控力四張圖表在 React 19 下渲染正常，數字與升級前一致 |
| AC-2 | 既有 `/quality?view=baseline&station=鎖銅排` 這類連結行為不變 |
| AC-3 | 下拉導覽可在品控力與 AR 三個頁面間切換，瀏覽器上一頁正常 |
| AC-4 | **進入 `/ar/inspect` → 返回 `/quality` → 再進入，連續三次，頁面背景與版面皆正常** |
| AC-5 | AR 設備圖片正確顯示（`/api/ar/uploads/...`），scene 內 `a-image` 亦然 |
| AC-6 | 舊 QR 碼 `?marker_id=5&backend=http://...` 仍可進入並自動觸發 marker |
| AC-7 | 搬遷後 `ar_device` 與 `ar_inspection` 筆數與原 `inspection.db` 一致 |
| AC-8 | 綁定 `equipment_code` 後，點檢頁顯示該設備的品控力等級分佈 |
| AC-9 | `equipment_code` 不在 active 批次時顯示提示，不靜默忽略 |
| AC-10 | Excel 匯出功能正常 |

---

## 10. 待確認項

| # | 問題 | 預設作法 |
|---|---|---|
| **D-01** | AR 的深色模式要不要保留？ | 不保留。僅 `/ar/inspect` 因相機背景維持深色外觀，其餘頁面統一亮色。 |
| **D-02** | 現有 `inspection.db` 有多少筆真實資料需要搬遷？還是可以從空的開始？ | 假設需要搬遷。若是測試資料可丟棄，第 6.3 節可省略。 |
| **D-03** | AR 的 marker 圖（64 張 PNG）與 `public/ar-inspect.html`、`iindex-barcode.html` 要不要一併帶過來？ | marker 圖帶過來（點檢要用）；兩個獨立 HTML 看起來是早期實驗檔，不帶。 |
| **D-04** | 部署形態：併成一個 Zeabur 服務，還是前端一個、後端一個？ | 維持現有品控力的形態（web + api + db 三個服務），AR 併入 api。需為 api 掛 volume 存上傳圖檔。 |
