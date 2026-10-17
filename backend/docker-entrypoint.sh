#!/bin/sh
# 以 root 啟動：先把資料目錄（照片等上傳檔）交給 app 使用者，再降權執行後端。
# 平台掛上來的 volume（Zeabur、docker compose 具名 volume）通常屬於 root，
# 直接以非 root 啟動會寫不進去，拍照點檢上傳就會失敗。
set -e

DATA_DIR="${QCM_DATA_DIR:-/app/data}"

if [ "$(id -u)" = "0" ]; then
  mkdir -p "$DATA_DIR"
  # 只有擁有者不對時才遞迴 chown，避免照片多了之後每次啟動都掃一遍
  if [ "$(stat -c %u "$DATA_DIR")" != "$(id -u app)" ]; then
    chown -R app:app "$DATA_DIR" || echo "[entrypoint] 警告：無法變更 $DATA_DIR 的擁有者，上傳可能失敗"
  fi
  exec setpriv --reuid=app --regid=app --init-groups "$@"
fi

exec "$@"
