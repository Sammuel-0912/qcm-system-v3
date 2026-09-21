#!/bin/sh
set -e

: "${PORT:=80}"
: "${API_URL:=http://api.zeabur.internal:8000}"

# 取容器實際使用的 DNS（Docker 為 127.0.0.11，K8s 為 kube-dns），供 nginx resolver 使用
if [ -z "${NGINX_RESOLVER}" ]; then
  NGINX_RESOLVER=$(awk '/^nameserver/ { printf "%s ", $2 }' /etc/resolv.conf)
  [ -z "${NGINX_RESOLVER}" ] && NGINX_RESOLVER="127.0.0.11"
fi
export PORT API_URL NGINX_RESOLVER

envsubst '${PORT} ${API_URL} ${NGINX_RESOLVER}' \
  < /etc/nginx/nginx.conf.template > /etc/nginx/conf.d/default.conf

exec nginx -g 'daemon off;'
