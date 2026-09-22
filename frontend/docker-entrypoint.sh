#!/bin/sh
set -e

: "${PORT:=80}"
: "${API_URL:=http://api.zeabur.internal:8000}"

# 取容器實際使用的 DNS（Docker 為 127.0.0.11，K8s 為 kube-dns），供 nginx resolver 使用
if [ -z "${NGINX_RESOLVER}" ]; then
  NGINX_RESOLVER=$(awk '/^nameserver/ { printf "%s ", $2 }' /etc/resolv.conf)
  [ -z "${NGINX_RESOLVER}" ] && NGINX_RESOLVER="127.0.0.11"
fi

# PORT 被設成非 80 時，同時也聽 80。平台對外轉發的 port 若與 PORT 不一致
# （例如依 Dockerfile 的 EXPOSE 80 轉發），仍然接得到。
EXTRA_LISTEN=""
if [ "${PORT}" != "80" ]; then
  EXTRA_LISTEN="listen 80;"
fi

export PORT API_URL NGINX_RESOLVER EXTRA_LISTEN

envsubst '${PORT} ${API_URL} ${NGINX_RESOLVER} ${EXTRA_LISTEN}' \
  < /etc/nginx/nginx.conf.template > /etc/nginx/conf.d/default.conf

echo "[entrypoint] listen=${PORT}${EXTRA_LISTEN:+ +80} api_url=${API_URL} resolver=${NGINX_RESOLVER}"

exec nginx -g 'daemon off;'
