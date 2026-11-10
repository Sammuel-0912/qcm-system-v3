# 部署到 Linux VM（Docker Compose）

整套服務共三個容器，設定都在 [`docker-compose.yml`](docker-compose.yml)：

| 服務 | 映像 | 說明 |
|---|---|---|
| `db` | `postgres:16-alpine` | 資料庫，資料存在 volume `pgdata`，不對外開 port |
| `api` | `qcm-api`（`backend/Dockerfile`） | FastAPI。照片與上傳檔存在 volume `apidata` |
| `web` | `qcm-web`（`frontend/Dockerfile`） | nginx：提供網頁，並把 `/api/` 轉給 `api`。唯一對外的服務 |

瀏覽器開 `http://<VM IP>:8080`（port 由 `.env` 的 `WEB_PORT` 決定）。

VM 需求：Linux x86_64、Docker Engine 24 以上（含 `docker compose` 外掛）、記憶體 2 GB 以上。

---

## 方式 A：離線打包（VM 不能連外網時，推薦）

在開發機建好映像、用 `docker save` 打包，搬到 VM 用 `docker load` 載入。VM 不需要原始碼、也不需要連 Docker Hub 或 npm。

### A-1. 開發機：建置並打包

開發機須能連網，且已啟動 Docker（Windows 用 Docker Desktop，在 Git Bash 執行以下指令）。

```bash
cd qcm-system-v3
git checkout main                          # 要部署的分支（feat/rbac 已合併到 main）
git pull
git log --oneline -1                       # 記下部署的版本，之後回報問題時用

# 開發機沒有 .env 時，compose 會因 POSTGRES_PASSWORD 必填而拒絕建置；給一個只用來建置的值即可
#（不會寫進映像，VM 上的密碼在 A-3 的 .env 另外設定）
POSTGRES_PASSWORD=build-only docker compose build   # 產生 qcm-api:latest、qcm-web:latest
docker pull postgres:16-alpine

docker save qcm-api:latest qcm-web:latest postgres:16-alpine | gzip > qcm-images.tar.gz
```

> 上面是 Git Bash 語法。`VAR=值 指令` 和 `gzip` 在 Windows 的 cmd／PowerShell 不能用，改用：
>
> - **cmd**：`set "POSTGRES_PASSWORD=build-only"`，再 `docker compose build`
> - **PowerShell**：`$env:POSTGRES_PASSWORD="build-only"`，再 `docker compose build`
>
> 打包改成 `docker save -o qcm-images.tar qcm-api:latest qcm-web:latest postgres:16-alpine`（不壓縮，約大一倍）。之後步驟的 `qcm-images.tar.gz` 都換成 `qcm-images.tar`，`docker load -i` 兩種都能讀。
>
> 開發機若是 Apple Silicon（ARM）等非 x86 機器，建置時要指定平台：
> `DOCKER_DEFAULT_PLATFORM=linux/amd64 POSTGRES_PASSWORD=build-only docker compose build`，再 `docker pull --platform linux/amd64 postgres:16-alpine`。

要搬到 VM 的三個檔案：

```
qcm-images.tar.gz      映像（約 300 MB）
docker-compose.yml
.env.example
```

### A-2. 傳到 VM

```bash
ssh user@<VM IP> 'mkdir -p ~/qcm'
scp qcm-images.tar.gz docker-compose.yml .env.example user@<VM IP>:~/qcm/
```

### A-3. VM：載入並啟動

VM 不能用 `apt`／`yum` 線上安裝，請先確認已經裝好 Docker；沒有的話，要事先準備對應作業系統版本的 Docker 離線安裝包（`.deb`／`.rpm`）帶過去。

```bash
docker version && docker compose version   # 兩個都要有輸出

cd ~/qcm
gunzip -c qcm-images.tar.gz | docker load
docker images | grep -E "qcm-api|qcm-web|postgres"   # 三個都要在；缺 postgres 時 db 會因為抓不到映像而起不來

cp .env.example .env
vi .env                                    # 必改 POSTGRES_PASSWORD、QCM_JWT_SECRET、QCM_ADMIN_PASSWORD，視需要改 WEB_PORT

docker compose up -d --no-build            # --no-build：直接用載入的映像，不找原始碼
docker compose ps                          # 三個服務都顯示 healthy 即完成
```

### A-4. 之後更新版本

開發機重做 A-1，把新的 `qcm-images.tar.gz`（以及有變動的 `docker-compose.yml`）傳上去，然後：

```bash
cd ~/qcm
gunzip -c qcm-images.tar.gz | docker load
docker compose up -d --no-build            # 只會重建映像有變的容器，資料保留
docker image prune -f                      # 清掉舊版映像
```

> **從沒有登入功能的舊版升級時**（VM 上已經跑過舊版）：
> 1. `docker-compose.yml` 這次有改（api 多了登入用的環境變數），**一定要連同新的 `docker-compose.yml`、`.env.example` 一起傳上去**。
> 2. 在 VM 既有的 `.env` 最後補上三行（值請自行修改，不要直接用範例）：
>    ```
>    QCM_JWT_SECRET=<openssl rand -hex 32 的結果>
>    QCM_ADMIN_USERNAME=admin
>    QCM_ADMIN_PASSWORD=<至少 8 碼>
>    ```
> 3. 啟動後資料庫會自動補欄位，舊資料一律歸到 `WJ1-DCS-PM1`；拍照點檢紀錄與照片都保留。
> 4. 之後匯入 Excel 時，檔名必須改成 `WJ1-DCS-PM1-數據庫-月日.xlsx` 這種格式（見「首次使用」）。

---

## 方式 B：VM 直接建置（VM 能連外網時）

```bash
git clone -b main https://github.com/Sammuel-0912/qcm-system-v3.git qcm   # private repo，需要 GitHub 帳號或 token
cd qcm
cp .env.example .env && vi .env            # 必改 POSTGRES_PASSWORD、QCM_JWT_SECRET、QCM_ADMIN_PASSWORD
docker compose up -d --build
```

更新：`git pull && docker compose up -d --build`。

---

## 首次使用

1. 開 `http://<VM IP>:8080`，用 `.env` 的 `QCM_ADMIN_USERNAME`／`QCM_ADMIN_PASSWORD` 登入（最高權限管理者）。
   登入後建議先從右上角選單 **修改密碼**。
2. 畫面會提示「尚無資料，請管理者匯入 Excel」。按 **匯入資料**，上傳例如 `WJ1-DCS-PM1-數據庫-1026.xlsx`。
   **檔名必須是 `廠-產品廠-線別-數據庫-月日.xlsx`**（廠為 WJ1～WJ8），系統依檔名決定資料屬於哪個廠、哪條線；
   同一條線只保留最新一次匯入，不同線互不影響。
3. 側邊欄 **系統管理 › 使用者管理**：指派各廠的廠管理者；廠管理者再自行新增該廠的一般使用者。
4. （選用）要補回舊系統的點檢次數時：**點檢看板 › 匯入歷史點檢數量**（只有最高權限管理者看得到），
   上傳舊系統點檢看板「匯出紀錄（含照片）」的 Excel。只累加站別卡片的正常／異常次數，不會出現在點檢紀錄；重複匯入不會重算。
   匯入的對象是畫面上方目前選的廠／線別。

| 角色 | 看資料 | 拍照點檢 | 匯入 Excel | 使用者管理 |
|---|---|---|---|---|
| 最高權限管理者 | 所有廠 | ✓ | 任何廠 | 所有帳號，可指派廠管理者 |
| 廠管理者 | 自己的廠 | ✓ | 只限自己廠的檔名 | 自己廠的一般使用者 |
| 一般使用者 | 自己的廠 | ✓ | ✗ | ✗ |

部署完成的快速檢查（在 VM 上）：

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/api/v1/filters   # 401＝nginx 轉發與登入保護都正常
docker compose exec -T api python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"   # {"status":"ok"}
docker compose logs api | grep -E "已建立最高權限管理者|未設定 QCM_JWT_SECRET|尚無最高權限管理者"
```

最後一行若出現「未設定 QCM_JWT_SECRET」或「尚無最高權限管理者」，表示 `.env` 少了設定，或 `QCM_ADMIN_PASSWORD` 不到 8 碼；補好後執行 `docker compose up -d --no-build`。

防火牆需開放 `WEB_PORT`（例：`sudo firewall-cmd --add-port=8080/tcp --permanent && sudo firewall-cmd --reload`，
或 Ubuntu 的 `sudo ufw allow 8080/tcp`）。資料庫與 api 都不對外，不需要開。

---

## `.env` 設定

| 變數 | 預設 | 說明 |
|---|---|---|
| `POSTGRES_PASSWORD` | （必填） | 資料庫密碼。建議只用英數字；含 `@ : /` 需 URL 編碼。**首次啟動後再改不會生效**（見下方） |
| `POSTGRES_DB`／`POSTGRES_USER` | `qcm` | 資料庫名稱與帳號 |
| `WEB_PORT` | `8080` | 對外網頁 port |
| `TZ` | `Asia/Taipei` | 容器時區 |
| `QCM_SITE_UTC_OFFSET` | `8` | 廠區時區，決定 Level 3 點檢的日班／夜班切分 |
| `QCM_JWT_SECRET` | （必填） | 登入權杖的簽章金鑰，用長隨機字串（`openssl rand -hex 32`）。沒設定時每次重啟都要重新登入；改掉它所有人都會被登出 |
| `QCM_ADMIN_USERNAME`／`QCM_ADMIN_PASSWORD` | （必填） | 第一位最高權限管理者，密碼至少 8 碼。**只在資料庫還沒有最高權限管理者時建立**；之後改密碼請從網頁改，改 `.env` 不會生效 |

> PostgreSQL 只在 volume 第一次建立時套用帳密。之後要改密碼，需在資料庫內 `ALTER USER`，
> 或備份後刪除 `pgdata` volume 重建。

---

## 日常維運

```bash
docker compose ps                          # 狀態（healthy／unhealthy）
docker compose logs -f api                 # 看後端記錄（匯入錯誤會在這裡）
docker compose restart api                 # 重啟單一服務
docker compose down                        # 停止（資料保留）
```

容器設定為 `restart: unless-stopped`，VM 重開機後會自動啟動（Docker 服務需設為開機啟動：`sudo systemctl enable docker`）。

### 備份

資料都在兩個 volume：資料庫 `pgdata`、上傳照片 `apidata`。

```bash
# 資料庫
docker compose exec -T db pg_dump -U qcm qcm | gzip > qcm-db-$(date +%F).sql.gz

# 照片與上傳檔
docker run --rm -v qcm_apidata:/data -v "$PWD":/backup alpine \
  tar czf /backup/qcm-uploads-$(date +%F).tar.gz -C /data .
```

> volume 名稱前綴是 compose 專案名稱，預設為資料夾名（放在 `~/qcm` 就是 `qcm_apidata`），可用 `docker volume ls` 確認。

### 還原資料庫

```bash
gunzip -c qcm-db-2026-10-15.sql.gz | docker compose exec -T db psql -U qcm qcm
```

### 注意

- **`docker compose down -v` 會刪除所有資料**（含資料庫與照片），除非要整個重來，否則不要加 `-v`。
- `api` 只能跑單一程序：線上人數存在程序記憶體裡，多開會各算各的。
- 前端的 `/api/` 由 nginx 轉發，瀏覽器只需連 `WEB_PORT`，不會有跨網域問題。
- 忘記最高權限管理者密碼時，改 `.env` 不會生效（帳號已存在）。請由另一位最高權限管理者在「使用者管理」重設；
  若只有一位，需進資料庫刪除該帳號後重啟 api，系統會依 `.env` 重新建立。
