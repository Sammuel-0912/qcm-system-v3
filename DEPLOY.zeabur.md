# 部署到 Zeabur

本專案為三個服務：`postgres`（資料庫）、`api`（FastAPI）、`web`（React + nginx）。
Zeabur 會直接讀取各資料夾的 Dockerfile 來建置，不使用 docker-compose.yml。

## 1. 推上 GitHub

Zeabur 從 Git repo 部署，先建立 repo：

```bash
git init
git add .
git commit -m "init"
git branch -M main
git remote add origin https://github.com/<你的帳號>/<repo 名稱>.git
git push -u origin main
```

> `raw_data.xlsx`（1.8MB）與圖片會一起進版控。若不想上傳，先加入 `.gitignore`。

## 2. 建立 Zeabur 專案與資料庫

1. 登入 <https://zeabur.com> → **Create Project**（區域建議選 `Tokyo` 或 `Hong Kong`）。
2. **Add Service → Prebuilt → PostgreSQL**，等它 Running。
3. 點 PostgreSQL 服務 → **Connect** 分頁，記下內網連線資訊
   （`POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_USERNAME` / `POSTGRES_PASSWORD` / `POSTGRES_DATABASE`）。

## 3. 部署 api 服務

1. **Add Service → Git → 選你的 repo**。
2. 建立後進入該服務 **Settings**：
   - **Service Name** 改成 `api`（重要：`web` 是靠這個名字連到後端）
   - **Root Directory** 設為 `backend`
3. **Variables** 分頁新增：

   ```
   QCM_DATABASE_URL=postgresql+psycopg://${POSTGRES_USERNAME}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DATABASE}
   ```

   Zeabur 支援同專案的變數引用，上面那串可以直接貼。若你的版面沒有自動帶入，
   就從步驟 2 抄實際值填進去。
4. Redeploy，看 Logs 出現 `Application startup complete.` 即成功。

> api 不需要對外網域。它只透過內網被 `web` 呼叫。
> 若你想單獨測 API，可在 **Networking** 開一個網域後打 `/health`。

## 4. 部署 web 服務

1. **Add Service → Git → 同一個 repo**（同 repo 可加入多個服務）。
2. **Settings**：
   - **Service Name** 設為 `web`
   - **Root Directory** 設為 `frontend`
3. **Variables** 新增：

   ```
   API_URL=http://api.zeabur.internal:8000
   ```

   （若你把後端服務取名成別的，把 `api` 換成那個名字。）
4. **Networking → Generate Domain**，產生對外網址。

## 5. 匯入資料

打開產生的網域 → 用畫面上的匯入功能上傳 `raw_data.xlsx`。
首次開啟會顯示「尚無資料，請先匯入 Excel」，這是正常的。

---

## 運作說明

- `web` 的 nginx 把 `/api/` 反向代理到 `${API_URL}`，所以前端維持用相對路徑 `/api/v1`，
  不需要在前端寫死後端網址，也沒有 CORS 問題。
- nginx 以**變數**方式 `proxy_pass`，每次請求才解析後端 DNS。
  好處是 `api` 還沒起來時 `web` 不會 crash，會等 `api` 好了自動接上。
- 兩個服務都讀 `PORT` 環境變數，符合 Zeabur 的注入慣例。
- 後端 `QCM_DATA_DIR` 在使用 PostgreSQL 時只是個空目錄，不需要掛 Volume。

## 本機驗證（與線上同一組 Dockerfile）

```bash
docker compose up --build
# 開 http://localhost:8080
```
