# 部署到 Cloudflare（逐步說明）

這份文件帶你把「CNE WJ1 DCS 品控力風險智控平台」部署到 Cloudflare，**不需要另外開資料庫**。

## 架構

```
瀏覽器 ──▶ Cloudflare Worker（cloudflare/src/index.ts）
             ├─ /api/*、/health ──▶ 後端容器（backend/Dockerfile，FastAPI，只跑 1 個）
             │                        ├─ 資料庫：容器內的 SQLite，由 Litestream 每秒備份到 R2 的 db/
             │                        └─ 照片：直接存 R2（checks/、device_*）
             └─ 其他路徑 ──▶ 前端靜態檔（frontend/dist）
```

- **Cloudflare Containers** 跑後端。容器的磁碟是暫時的（重開就清空），所以資料一律放在 **R2**：
  - SQLite 由 Litestream 持續複製到 R2；容器每次啟動都先從 R2 還原，再啟動後端。
  - 拍照點檢的照片直接寫進 R2。
- 只需要兩項 Cloudflare 服務：**Workers（含 Containers）** 和 **R2**。

> 為什麼不用 D1：後端是容器裡的 Python，只能透過 HTTP API 存取 D1，匯入 Excel 會失去「整批成功或全部還原」的交易保證，速度也慢，等於要重寫資料層。

---

## 步驟 0：事前準備

| 項目 | 說明 |
|---|---|
| Cloudflare 帳號 | <https://dash.cloudflare.com/sign-up> |
| **Workers 付費方案** | Containers 需要 Workers Paid（每月 5 美元，含基本用量）。到 Dashboard → **Workers & Pages → Plans** 升級 |
| **R2** | 到 Dashboard → **R2 Object Storage** 啟用（需綁付款方式；有免費額度，這個系統的用量通常在免費額度內） |
| Node.js 20 以上 | <https://nodejs.org/>，安裝後在終端機執行 `node -v` 確認 |
| **Docker Desktop** | 部署時要在本機建置後端映像，**部署前必須先開啟 Docker Desktop**（`docker info` 不報錯即可） |
| 程式碼 | `git clone https://github.com/Sammuel-0912/qcm-system-v3.git` |

以下指令都在 **Git Bash** 或 PowerShell 執行，路徑以專案根目錄 `qcm-system-v3` 為準。

---

## 步驟 1：安裝部署工具並登入 Cloudflare

```bash
cd qcm-system-v3/cloudflare
npm ci
npx wrangler login
```

`wrangler login` 會開瀏覽器要你授權，按 **Allow**。完成後用下面指令確認登入的帳號：

```bash
npx wrangler whoami
```

畫面會顯示你的 **Account ID**（一串 32 字元的英數字），**記下來**，步驟 3 會用到。

---

## 步驟 2：建立 R2 bucket

```bash
npx wrangler r2 bucket create qcm-v3
```

看到 `Created bucket 'qcm-v3'` 即完成。（也可以在 Dashboard → R2 → **Create bucket** 建立，名稱填 `qcm-v3`。）

> 要用別的名稱也可以，但步驟 3 的 `QCM_S3_BUCKET` 要一起改。

---

## 步驟 3：建立 R2 存取金鑰

後端透過 R2 的 S3 相容 API 讀寫資料，需要一組專用金鑰：

1. Dashboard → **R2 Object Storage** → 右側 **Manage R2 API Tokens**（或「API → Manage API tokens」）。
2. **Create API token**：
   - Token name：`qcm-v3-backend`
   - Permissions：**Object Read & Write**
   - Specify bucket(s)：選 **Apply to specific buckets only** → 勾 `qcm-v3`
   - TTL：Forever（或依公司規定）
3. 按 **Create API Token**，畫面會顯示好幾個值，**要用的是「S3 用戶端」那一區**：
   - **Access Key ID**：**32 個字元**
   - **Secret Access Key**：**64 個字元**（**只會顯示這一次**，請立刻複製保存）
   - S3 endpoint：`https://<Account ID>.r2.cloudflarestorage.com`

   > ⚠ 同一頁最上面的 **Token value** 是 Cloudflare API 權杖，**不是** S3 金鑰，不要拿來用。
   > 填錯時容器會啟動失敗，記錄出現 `Credential access key has length 48, should be 32`。

---

## 步驟 4：填寫設定

打開 `cloudflare/wrangler.jsonc`，修改 `vars` 這段：

```jsonc
"vars": {
  "QCM_S3_BUCKET": "qcm-v3",
  "QCM_S3_ENDPOINT": "https://<Account ID>.r2.cloudflarestorage.com",   // ← 換成你的 Account ID
  "QCM_SITE_UTC_OFFSET": "8"
}
```

Worker 名稱預設是 `qcm-v3`（同檔 `"name"`），網址會是 `https://qcm-v3.<你的子網域>.workers.dev`。

---

## 步驟 5：設定密鑰（R2 金鑰）

金鑰不能寫進檔案，用 wrangler 存成加密的 secret：

```bash
npx wrangler secret put QCM_S3_ACCESS_KEY_ID
```

貼上步驟 3 的 **Access Key ID**，按 Enter。

```bash
npx wrangler secret put QCM_S3_SECRET_ACCESS_KEY
```

貼上 **Secret Access Key**，按 Enter。

> 第一次執行時 Worker 還不存在，wrangler 會問是否要先建立 `qcm-v3` 再加 secret，回答 **Y**。

再設定登入用的三個 secret（沒設定的話沒有人能登入）：

```bash
npx wrangler secret put QCM_JWT_SECRET        # 長隨機字串，例：openssl rand -hex 32
npx wrangler secret put QCM_ADMIN_USERNAME    # 第一位最高權限管理者帳號，例：admin
npx wrangler secret put QCM_ADMIN_PASSWORD    # 至少 8 碼
```

> `QCM_ADMIN_*` 只在資料庫裡還沒有最高權限管理者時建立帳號；之後改密碼請從網頁右上角改。

---

## 步驟 6：部署

**確認 Docker Desktop 已開啟**，然後：

```bash
npm run deploy
```

這個指令會：

1. 建置前端（`frontend/dist`）
2. 用 Docker 建置後端映像（linux/amd64）並推到 Cloudflare
3. 部署 Worker、靜態檔與容器設定

完成時畫面會印出網址，例如 `https://qcm-v3.<你的子網域>.workers.dev`。

> **第一次部署後請等 3～5 分鐘**，Cloudflare 需要時間配置容器；這段時間打開網站，API 可能回 500／502，屬正常現象。

確認容器狀態：

```bash
npx wrangler containers list
```

---

## 步驟 7：驗證與匯入資料

1. 打開部署網址。第一次（或閒置 30 分鐘後）開啟時，後端要先從 R2 還原資料庫再啟動，**可能需要 10～60 秒**。
2. 確認後端已就緒：瀏覽器開 `https://<你的網址>/health`，看到 `{"status":"ok"}`。
3. 回到首頁，用步驟 5 的 `QCM_ADMIN_USERNAME`／`QCM_ADMIN_PASSWORD` 登入，右上角 **匯入資料** →
   選 `WJ1-DCS-PM1-數據庫-1026.xlsx`（檔名必須是 `廠-產品廠-線別-數據庫-月日.xlsx`）。
4. 匯入完成後，到 Dashboard → R2 → `qcm-v3`，應該看到：
   - `db/`：資料庫備份（Litestream）
   - 之後拍照點檢時會出現 `checks/`：照片
5. 到 **點檢控制中心 → 拍照點檢** 拍一張照，再到 **點檢看板** 確認縮圖顯示。

---

## 日常維運

### 更新版本

```bash
cd qcm-system-v3
git pull
cd cloudflare
npm run deploy
```

資料都在 R2，更新不會遺失。部署時容器會重開，重開後自動從 R2 還原。

### 看即時記錄（除錯用）

```bash
npx wrangler tail
```

### 休眠與冷啟動

- 後端閒置 **30 分鐘**後自動休眠（省費用），下一次開啟網站時重開，需要 10～60 秒。
- 想縮短或拉長，改 `cloudflare/src/index.ts` 的 `sleepAfter`（例：`'2h'`），再 `npm run deploy`。

### 備份

- R2 本身就是持久儲存；Litestream 每秒把資料庫變更寫進 `db/`。
- 另外想留一份 Excel 備份：點檢看板的 **匯出紀錄（含照片）**。
- 想把資料庫下載到本機（需 Docker，把 `<…>` 換成步驟 3 的值）：

  ```bash
  docker run --rm -v "$PWD:/out" \
    -e QCM_S3_BUCKET=qcm-v3 -e QCM_S3_REGION=auto \
    -e QCM_S3_ENDPOINT=https://<Account ID>.r2.cloudflarestorage.com \
    -e QCM_S3_ACCESS_KEY_ID=<Access Key ID> -e QCM_S3_SECRET_ACCESS_KEY=<Secret Access Key> \
    --entrypoint sh qcm-v3-api-sim -c \
    "litestream restore -config /etc/litestream.yml -o /out/qcm-backup.db /app/data/qcm.db"
  ```

  （`qcm-v3-api-sim` 是下方「本機模擬」建出來的映像；也可以先 `docker build -t qcm-v3-api-sim backend` 建置。
  在 Git Bash 執行時，指令前面加上 `MSYS_NO_PATHCONV=1 `，避免路徑被自動轉成 Windows 格式。）

  下載下來的 `qcm-backup.db` 可以用 [DB Browser for SQLite](https://sqlitebrowser.org/) 開啟。

### 自訂網域（選用）

Dashboard → **Workers & Pages → qcm-v3 → Settings → Domains & Routes → Add → Custom domain**，填入公司網域（該網域需在同一個 Cloudflare 帳號）。

---

## 注意事項

- **後端只能 1 個執行個體**（`wrangler.jsonc` 的 `max_instances: 1`）：SQLite 只能有一個寫入者，線上人數也存在程序記憶體。不要調高。
- 容器被強制終止的那一瞬間，最後約 1 秒內的寫入可能來不及備份；正常停止（部署、休眠）會先做最後一次同步。
- 規格：`instance_type: "standard-1"`（1/2 vCPU、4 GiB）。匯入上萬列的 Excel 需要記憶體；用量很小時可改 `"basic"` 省費用。
- 點檢紀錄不可刪除（稽核證據）；如需清除，請直接操作資料庫備份。

---

## 疑難排解

| 狀況 | 原因與處理 |
|---|---|
| `npm run deploy` 出現 Docker 相關錯誤 | Docker Desktop 沒開，或還在啟動中。開啟後執行 `docker info` 確認再部署 |
| 剛部署完網站 API 回 500／502 | 容器還在配置，等 3～5 分鐘；`npx wrangler containers list` 看狀態 |
| 閒置後第一次開很慢 | 正常：容器從休眠喚醒並從 R2 還原資料庫 |
| `wrangler tail` 看到 `QCM_STORAGE=s3 時必須設定環境變數 QCM_S3_…` | 步驟 5 的 secret 沒設好，重新 `npx wrangler secret put …` 後再 `npm run deploy` |
| 記錄出現 `Credential access key has length 48, should be 32`，或 `[entrypoint] R2 Access Key ID 應為 32 個字元` | `QCM_S3_ACCESS_KEY_ID` 填成了 Token value。改填 S3 的 **Access Key ID**（32 字元）與 **Secret Access Key**（64 字元），重設 secret 後 `npm run deploy` |
| 記錄出現 `There is no container instance…`、`Container exited with unexpected exit code: 1` | 容器啟動失敗後的連鎖錯誤，往上找第一個 `[entrypoint]` 或 `Error:` 訊息才是真正原因 |
| 照片顯示「照片遺失」 | R2 金鑰權限不足（需 Object Read & Write，且包含 `qcm-v3` bucket）或 endpoint 的 Account ID 打錯 |
| 匯入時逾時或容器重啟 | Excel 太大、記憶體不足：把 `instance_type` 改成 `"standard-2"` 再部署 |

---

## 本機模擬（開發者用）

Windows 上 `wrangler dev` 不支援容器，可用 Docker Compose 模擬 Cloudflare 的執行方式（後端不掛 volume、SeaweedFS 扮演 R2）：

```bash
cd qcm-system-v3/cloudflare
docker compose -f docker-compose.sim.yml -p qcmcf up -d --build
```

瀏覽器開 <http://localhost:8788>。把後端容器整個刪掉重建（`docker compose -f docker-compose.sim.yml -p qcmcf rm -sf api && docker compose -f docker-compose.sim.yml -p qcmcf up -d api`），資料與照片會從模擬的 R2 還原。

結束：

```bash
docker compose -f docker-compose.sim.yml -p qcmcf down
```
