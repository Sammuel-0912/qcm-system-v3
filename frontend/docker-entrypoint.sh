#!/bin/sh
set -e

: "${PORT:=80}"
: "${API_URL:=http://api.zeabur.internal:8000}"

# 取容器實際使用的 DNS（Docker 為 127.0.0.11，K8s 為 kube-dns），供 nginx resolver 使用
if [ -z "${NGINX_RESOLVER}" ]; then
  NGINX_RESOLVER=$(awk '/^nameserver/ { printf "%s ", $2 }' /etc/resolv.conf)
  [ -z "${NGINX_RESOLVER}" ] && NGINX_RESOLVER="127.0.0.11"
fi

# 從 API_URL 取出主機名（去掉 scheme、路徑與 port），供 Host header 與 TLS SNI 使用。
# API_URL 指向對外 https 網址時，這兩者若是前端自己的網域，邊緣路由會找不到服務。
API_HOST=$(printf '%s' "${API_URL}" | sed -e 's#^[a-zA-Z][a-zA-Z0-9+.-]*://##' -e 's#/.*$##' -e 's#:[0-9]*$##')
[ -z "${API_HOST}" ] && API_HOST="api.zeabur.internal"

# PORT 被設成非 80 時，同時也聽 80。平台對外轉發的 port 若與 PORT 不一致
# （例如依 Dockerfile 的 EXPOSE 80 轉發），仍然接得到。
EXTRA_LISTEN=""
if [ "${PORT}" != "80" ]; then
  EXTRA_LISTEN="listen 80;"
fi

export PORT API_URL API_HOST NGINX_RESOLVER EXTRA_LISTEN

envsubst '${PORT} ${API_URL} ${API_HOST} ${NGINX_RESOLVER} ${EXTRA_LISTEN}' \
  < /etc/nginx/nginx.conf.template > /etc/nginx/conf.d/default.conf

echo "[entrypoint] listen=${PORT}${EXTRA_LISTEN:+ +80} api_url=${API_URL} api_host=${API_HOST} resolver=${NGINX_RESOLVER}"

exec nginx -g 'daemon off;'
