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

# 以非 root 執行。資料目錄（上傳的照片、SQLite 備援）先建好並交給 app 使用者，
# 具名 volume 第一次掛上時會沿用這個擁有者，容器才寫得進去。
RUN useradd --system --uid 10001 --home-dir /app app \
    && mkdir -p /app/data \
    && chown -R app:app /app/data
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/health', timeout=4)" || exit 1

# 單一 worker：線上人數（presence）存在程序記憶體內，多 worker 會各算各的。
# --proxy-headers：前面有 nginx，記錄與轉址才會用到真實來源。
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
