#!/bin/sh
# 以 root 啟動：先把資料目錄（照片等上傳檔）交給 app 使用者，再降權執行後端。
# 平台掛上來的 volume（Zeabur、docker compose 具名 volume）通常屬於 root，
# 直接以非 root 啟動會寫不進去，拍照點檢上傳就會失敗。
#
# QCM_LITESTREAM=1（Cloudflare 部署）：容器磁碟是暫時的，SQLite 交給 Litestream——
#   1. 啟動前從 R2 還原資料庫（第一次部署、R2 還沒有備份時略過）
#   2. 以 `litestream replicate -exec` 執行後端，每次寫入約 1 秒內備份到 R2；
#      收到停止訊號時 Litestream 先停後端、再做最後一次同步。
set -e

DATA_DIR="${QCM_DATA_DIR:-/app/data}"
DB_PATH="/app/data/qcm.db"  # 與 litestream.yml 的 dbs[].path 一致
APP_CMD="uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips=*"

as_app() {
  if [ "$(id -u)" = "0" ]; then
    setpriv --reuid=app --regid=app --init-groups "$@"
  else
    "$@"
  fi
}

if [ "$(id -u)" = "0" ]; then
  mkdir -p "$DATA_DIR"
  # 只有擁有者不對時才遞迴 chown，避免照片多了之後每次啟動都掃一遍
  if [ "$(stat -c %u "$DATA_DIR")" != "$(id -u app)" ]; then
    chown -R app:app "$DATA_DIR" || echo "[entrypoint] 警告：無法變更 $DATA_DIR 的擁有者，上傳可能失敗"
  fi
fi

if [ "${QCM_LITESTREAM:-0}" = "1" ]; then
  if [ -n "${QCM_DATABASE_URL:-}" ] && [ "${QCM_DATABASE_URL}" != "sqlite:///${DB_PATH}" ]; then
    echo "[entrypoint] QCM_LITESTREAM=1 只支援 SQLite（${DB_PATH}），請不要設定 QCM_DATABASE_URL" >&2
    exit 1
  fi
  if [ "${DATA_DIR}" != "/app/data" ]; then
    echo "[entrypoint] QCM_LITESTREAM=1 時 QCM_DATA_DIR 必須是 /app/data（與 litestream.yml 一致）" >&2
    exit 1
  fi
  : "${QCM_S3_REGION:=auto}"
  export QCM_S3_REGION
  # R2 的 S3 金鑰：Access Key ID 32 字元、Secret 64 字元。常見錯誤是貼成 Token value，
  # 那樣 R2 只會回「length 48, should be 32」且容器不斷重啟，這裡先給清楚的訊息。
  case "${QCM_S3_ENDPOINT:-}" in
    *r2.cloudflarestorage.com*)
      if [ "${#QCM_S3_ACCESS_KEY_ID}" -ne 32 ]; then
        echo "[entrypoint] R2 Access Key ID 應為 32 個字元，目前是 ${#QCM_S3_ACCESS_KEY_ID} 個（是否貼成了 Token value？）。請重新 wrangler secret put QCM_S3_ACCESS_KEY_ID" >&2
        exit 1
      fi
      if [ "${#QCM_S3_SECRET_ACCESS_KEY}" -ne 64 ]; then
        echo "[entrypoint] R2 Secret Access Key 應為 64 個字元，目前是 ${#QCM_S3_SECRET_ACCESS_KEY} 個。請重新 wrangler secret put QCM_S3_SECRET_ACCESS_KEY" >&2
        exit 1
      fi
      ;;
  esac
  echo "[entrypoint] 從 R2 還原資料庫（若有備份）…"
  as_app litestream restore -config /etc/litestream.yml -if-replica-exists -if-db-not-exists "$DB_PATH"
  echo "[entrypoint] 啟動後端，Litestream 持續備份到 R2"
  if [ "$(id -u)" = "0" ]; then
    exec setpriv --reuid=app --regid=app --init-groups \
      litestream replicate -config /etc/litestream.yml -exec "$APP_CMD"
  fi
  exec litestream replicate -config /etc/litestream.yml -exec "$APP_CMD"
fi

if [ "$(id -u)" = "0" ]; then
  exec setpriv --reuid=app --regid=app --init-groups "$@"
fi
exec "$@"
