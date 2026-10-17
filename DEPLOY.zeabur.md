# 部署到 Zeabur

本專案為三個服務：`postgres`（資料庫）、`api`（FastAPI）、`web`（React + nginx）。
Zeabur 會直接讀取各資料夾的 Dockerfile 來建置，不使用 docker-compose.yml。

## 1. GitHub repo（已完成）

程式碼已推上：<https://github.com/Sammuel-0912/qcm-system>（private，分支 `main`）

後續改動推上去後，Zeabur 會自動重新部署：

```bash
git add -A && git commit -m "..." && git push
```

> `raw_data.xlsx` 已被 `.gitignore` 的 `*.xlsx` 排除，不會進版控。
> 資料改用步驟 5 從網頁介面上傳。

## 2. 建立 Zeabur 專案與資料庫

1. 登入 <https://zeabur.com> → **Create Project**（區域建議選 `Tokyo` 或 `Hong Kong`）。
2. **Add Service → Prebuilt → PostgreSQL**，等它 Running。
3. 點 PostgreSQL 服務 → **Instruction** 分頁，記下 root 帳號、密碼與預設資料庫名稱。
   內網主機名與 port 在 **Networking** 分頁（`xxx.zeabur.internal`）。

## 3. 部署 api 服務

1. **Add Service → Git → 選你的 repo**。
2. 建立後進入該服務 **Settings**：
   - **Service Name** 設為 `api`（方便辨識；注意這**不等於**內網主機名，見步驟 5）
   - **Root Directory** 設為 `backend`
3. **Variables** 分頁新增 `QCM_DATABASE_URL`。

   到 **PostgreSQL 服務 → Instruction 分頁**（不是 Connect，Zeabur 沒有這個分頁），
   裡面有 root 帳號、密碼、預設資料庫與連線字串。內網主機名與 port 則在
   **Networking 分頁**，長得像 `xxx.zeabur.internal`。組起來像這樣：

   ```
   postgresql://root:<密碼>@postgresql.zeabur.internal:5432/zeabur
   ```

   把開頭的 `postgresql://` 改成 `postgresql+psycopg://`，其餘照抄：

   ```
   QCM_DATABASE_URL=postgresql+psycopg://root:<密碼>@postgresql.zeabur.internal:5432/zeabur
   ```

   > ⚠️ **請填實際值，不要用 `${POSTGRES_PORT}` 這類變數參照。**
   > Zeabur 的跨服務參照要求來源服務有 Expose 該變數才會代換，
   > 對不上時會把字串原樣傳進來，導致 api 啟動時噴
   > `ValueError: invalid literal for int() with base 10: '${POSTGRES_PORT}'`
   > 並進入 CrashLoopBackOff。
   >
   > ⚠️ `postgresql+psycopg://` 的 `+psycopg` 不能省略，SQLAlchemy 需要指定 driver。

4. **Variables** 再加一條 `PORT=8000`。

   Zeabur 會自行注入 `PORT`，明確釘死可確保與 `web` 的 `API_URL` port 一致。

5. 記下內網主機名：**Networking 分頁 → Private Domain**，形如 `xxxx.zeabur.internal`。

   > ⚠️ Zeabur 文件註明「**改服務名稱不會改變 private hostname**」，
   > 主機名在服務建立時就固定了。**請抄 Networking 顯示的實際值**，
   > 不要假設它等於你設定的 Service Name。

6. Redeploy，看 Logs 出現 `Application startup complete.` 即成功。

> api **不需要**開對外網域（Public Networking）。內網通訊是給同專案服務互連用的，
> 不開對外反而更安全。若想單獨測 API，再臨時開一個網域打 `/health` 即可。

## 4. 部署 web 服務

1. **Add Service → Git → 同一個 repo**（同 repo 可加入多個服務）。
2. **Settings**：
   - **Service Name** 設為 `web`
   - **Root Directory** 設為 `frontend`
3. **Variables** 新增。`<api的private domain>` 換成步驟 3-5 抄來的完整值
   （已含 `.zeabur.internal` 結尾，不要重複加）：

   ```
   API_URL=http://<api的private domain>:8000
   ```

   port 用 `8000`，對應 api 服務釘死的 `PORT=8000`。
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
- 後端的資料目錄 `QCM_DATA_DIR`（預設 `/app/data`）存放**拍照點檢的照片**與 AR 設備圖檔，
  **必須在 api 服務掛 Volume，掛載路徑 `/app/data`**，否則重新部署後照片全部消失。
  資料庫本身在 PostgreSQL 服務，不受影響。
  > 舊版 Dockerfile 的預設是 `/data`；若當時 Volume 掛在 `/app/data` 又沒設 `QCM_DATA_DIR`，
  > 照片其實寫在容器內的 `/data`，重新部署後就不在了，這些舊紀錄會顯示「照片遺失」。
- api 容器以 root 啟動，由 entrypoint 把 `/app/data` 的擁有者改成 app 使用者後再降權執行；
  Volume 屬於 root 也能正常寫入，不需另外調整權限。

## 本機驗證（與線上同一組 Dockerfile）

```bash
docker compose up --build
# 開 http://localhost:8080
```
