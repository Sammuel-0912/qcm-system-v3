FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    QCM_DATA_DIR=/app/data \
    PORT=8000

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# 後端以非 root 的 app 使用者執行。容器仍以 root 啟動，由 entrypoint 先把資料目錄
# （照片等上傳檔，Zeabur／compose 的 volume 掛在這裡）交給 app，再降權——
# 平台掛上的 volume 多半屬於 root，直接 USER app 會寫不進去。
RUN useradd --system --uid 10001 --home-dir /app app \
    && mkdir -p /app/data \
    && chown -R app:app /app/data
# Litestream：Cloudflare 部署時把 SQLite 持續備份到 R2（QCM_LITESTREAM=1 才啟用，見 entrypoint）
COPY --from=litestream/litestream:0.5.17 /usr/local/bin/litestream /usr/local/bin/litestream
COPY litestream.yml /etc/litestream.yml
COPY docker-entrypoint.sh /entrypoint.sh
# Windows 簽出可能帶 CRLF，去掉以免 /bin/sh 無法執行
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/health', timeout=4)" || exit 1

# 單一 worker：線上人數（presence）存在程序記憶體內，多 worker 會各算各的。
# --proxy-headers：前面有 nginx，記錄與轉址才會用到真實來源。
ENTRYPOINT ["/entrypoint.sh"]
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
