FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
# 依 lock 檔安裝，VM 與開發機裝到的版本一致
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
RUN apk add --no-cache gettext
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/nginx.conf.template
COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENV PORT=80 API_URL=http://api.zeabur.internal:8000
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null "http://127.0.0.1:${PORT}/" || exit 1
ENTRYPOINT ["/entrypoint.sh"]
