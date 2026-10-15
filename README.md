# 品控力管理系統

依 [`spec.md`](./spec.md) 規格驅動開發。規格是唯一事實來源——改行為前先改規格。

## 這個系統做什麼

把原本的 Power BI 品控力模型換成獨立系統，並加上 Power BI 做不到的一件事：
**追蹤每個 KPOV 的品控力隨不良事件與改善措施升降的完整歷程**。

- 品控力 2×2 象限圖（現況／基準／目標三種口徑可切換）
- Level 0~3 KPOV 數量柱狀圖，疊上基準值對照
- 站別 / 線別篩選，DCS-PM2 自動繼承 DCS-PM1 的 KPOV 定義
- 等級異動總覽與單一 KPOV 的歷程時間軸
- Excel 上傳匯入，取代 Power Query

## 快速開始（本機開發，免安裝資料庫）

開發模式預設使用 SQLite，不需要 Docker 或 PostgreSQL。

```bash
# 後端
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端（另開一個終端）
cd frontend
npm install
npm run dev          # http://localhost:5173，已設定 /api 轉發到 8000
```

開啟前端後點右上角「匯入資料」，上傳 `raw_data.xlsx` 即可。

## 正式部署（Linux VM）

```bash
cp .env.example .env             # 必改 POSTGRES_PASSWORD
docker compose up -d --build     # http://<伺服器>:8080
```

VM 不能連外網時，在開發機 `docker save` 打包映像再搬過去，完整步驟見 [`DEPLOY.vm.md`](./DEPLOY.vm.md)。
雲端（Zeabur）部署見 [`DEPLOY.zeabur.md`](./DEPLOY.zeabur.md)。

`docker-compose.yml` 使用 PostgreSQL 16。後端以 `QCM_DATABASE_URL` 環境變數切換資料庫，
SQLite 與 PostgreSQL 共用同一套程式碼。

## 測試

```bash
cd backend && pytest
```

測試分兩層：

- `tests/test_level.py` — 等級判定與異動分類的單元測試，測資直接取自 spec.md §2.4 的驗證表格
- `tests/test_lifecycle.py` — 以真實 `raw_data.xlsx` 跑端到端驗收，逐項對應 spec.md §9 的 AC 編號

## 專案結構

```
backend/app/
  services/level.py        §2.3 等級判定 — 全系統唯一計算等級的地方
  services/lifecycle.py    §3 生命週期，現況等級推算
  services/query.py        §7 篩選與彙總，含 D-01 線別繼承
  importer/excel.py        §6 Excel 匯入
  importer/level_events.py §3.4 等級異動事件推導
  api/v1/routes.py         §7 API 端點
frontend/src/
  components/QuadrantChart.tsx   象限圖，座標取自 gemini-svg.svg
  components/LevelBarChart.tsx   柱狀圖
  components/LevelTimeline.tsx   等級歷程時間軸
  constants.ts                   LEVEL_COLORS 單一來源
```

## 兩個容易誤改的地方

**偵測度分數越小越好。** 1 = 失效模式不會實際發生，10 = 未建立。切點在 5/6 之間：
≤5 代表偵測能力高。如果覺得象限畫反了，先確認這一點。

**等級不是 KPOV 的屬性，是 (KPOV × 設備) 的狀態。** KPOV 編號會跨設備重複，
K00004 一個編號掛在 9 台設備上。某台設備出不良只降那一台，不連坐其他台。
`fact_kpov.level_baseline` 永不變動，所有升降記在 `fact_level_event`，只增不改。

## 與規格的兩處差異

1. **現況等級改在應用層推算**，而非 spec.md §5.4 的 SQL view。
   原規格使用 PostgreSQL 專有的 `LATERAL` join，SQLite 不支援；
   改用 `services/lifecycle.py` 後兩種資料庫行為一致。
2. **KPOV 筆數為 244 而非 246**。來源檔第 246 列為空白列、第 247 列是殘留公式
   `=COUNTA(UNIQUE(L2:L245))`，兩列都不是資料，因此也沒有「未評估」的 KPOV。
