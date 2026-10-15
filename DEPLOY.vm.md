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
cd QualityControlModeling
git pull                                   # 確認是要部署的版本

docker compose build                       # 產生 qcm-api:latest、qcm-web:latest
docker pull postgres:16-alpine

docker save qcm-api:latest qcm-web:latest postgres:16-alpine | gzip > qcm-images.tar.gz
```

> 開發機若是 Apple Silicon（ARM）等非 x86 機器，建置時要指定平台：
> `DOCKER_DEFAULT_PLATFORM=linux/amd64 docker compose build`，再 `docker pull --platform linux/amd64 postgres:16-alpine`。

要搬到 VM 的三個檔案：

```
qcm-images.tar.gz      映像（約 200 MB）
docker-compose.yml
.env.example
```

### A-2. 傳到 VM

```bash
ssh user@<VM IP> 'mkdir -p ~/qcm'
scp qcm-images.tar.gz docker-compose.yml .env.example user@<VM IP>:~/qcm/
```

### A-3. VM：載入並啟動

```bash
cd ~/qcm
gunzip -c qcm-images.tar.gz | docker load

cp .env.example .env
vi .env                                    # 必改 POSTGRES_PASSWORD，視需要改 WEB_PORT

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

---

## 方式 B：VM 直接建置（VM 能連外網時）

```bash
git clone https://github.com/Sammuel-0912/qcm-system.git qcm
cd qcm
cp .env.example .env && vi .env            # 必改 POSTGRES_PASSWORD
docker compose up -d --build
```

更新：`git pull && docker compose up -d --build`。

---

## 首次使用

1. 開 `http://<VM IP>:8080`，畫面會提示「尚無資料，請先匯入 Excel」。
2. 按右上角「匯入資料」，上傳 `數據庫-1011.xlsx`（或最新版）。
3. 匯入完成後即可使用；之後每次有新資料，同樣從畫面匯入。

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
