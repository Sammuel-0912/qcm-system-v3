/**
 * Cloudflare Worker：前端靜態檔＋把 /api 轉給後端容器（../backend，FastAPI）。
 *
 * 後端固定只有一個執行個體（getContainer 用同一個名稱）：SQLite 由 Litestream 單一寫入者
 * 備份到 R2，線上人數也存在程序記憶體，多開會資料分歧。
 */
import { Container, getContainer } from '@cloudflare/containers'

export interface Env {
  ASSETS: Fetcher
  BACKEND: DurableObjectNamespace<Backend>
  QCM_S3_ENDPOINT: string
  QCM_S3_BUCKET: string
  QCM_SITE_UTC_OFFSET: string
  // 機密（wrangler secret put）
  QCM_S3_ACCESS_KEY_ID: string
  QCM_S3_SECRET_ACCESS_KEY: string
  // 登入（spec §15，選用；沒設定時後端會用隨機金鑰、且沒有管理者可登入）
  QCM_JWT_SECRET?: string
  QCM_ADMIN_USERNAME?: string
  QCM_ADMIN_PASSWORD?: string
}

export class Backend extends Container<Env> {
  defaultPort = 8000
  // 閒置 30 分鐘後休眠省資源；下次請求時重開，Litestream 會先從 R2 還原資料庫（首次約數秒到數十秒）
  sleepAfter = '30m'
  enableInternet = true // 要連 R2（S3 API）

  constructor(ctx: DurableObjectState<{}>, env: Env) {
    super(ctx, env)
    this.envVars = {
      PORT: '8000',
      TZ: 'Asia/Taipei',
      QCM_SITE_UTC_OFFSET: env.QCM_SITE_UTC_OFFSET ?? '8',
      // SQLite 存在容器內，由 Litestream 持續備份到 R2 的 db/ 底下
      QCM_LITESTREAM: '1',
      // 照片存 R2
      QCM_STORAGE: 's3',
      QCM_S3_ENDPOINT: env.QCM_S3_ENDPOINT,
      QCM_S3_BUCKET: env.QCM_S3_BUCKET,
      QCM_S3_REGION: 'auto',
      QCM_S3_ACCESS_KEY_ID: env.QCM_S3_ACCESS_KEY_ID,
      QCM_S3_SECRET_ACCESS_KEY: env.QCM_S3_SECRET_ACCESS_KEY,
      ...(env.QCM_JWT_SECRET ? { QCM_JWT_SECRET: env.QCM_JWT_SECRET } : {}),
      ...(env.QCM_ADMIN_USERNAME ? { QCM_ADMIN_USERNAME: env.QCM_ADMIN_USERNAME } : {}),
      ...(env.QCM_ADMIN_PASSWORD ? { QCM_ADMIN_PASSWORD: env.QCM_ADMIN_PASSWORD } : {}),
    }
  }

  override onError(error: unknown) {
    console.error('後端容器錯誤', error)
    throw error
  }
}

const SINGLETON = 'qcm-backend'

export default {
  async fetch(request, env): Promise<Response> {
    const { pathname } = new URL(request.url)
    if (pathname.startsWith('/api/') || pathname === '/health') {
      return getContainer(env.BACKEND, SINGLETON).fetch(request)
    }
    return env.ASSETS.fetch(request)
  },
} satisfies ExportedHandler<Env>
