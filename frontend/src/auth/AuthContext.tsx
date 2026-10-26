import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

import { api, type AuthUser, type DatasetInfo } from '../api/client'
import { getDataset, setDataset, UNAUTHORIZED_EVENT } from '../api/session'

type AuthState = {
  /** undefined＝載入中；null＝未登入 */
  user: AuthUser | null | undefined
  datasets: DatasetInfo[]
  /** 目前選的資料集（一條線），例 WJ1-DCS-PM1；尚無資料時為 null */
  dataset: string | null
  isAdmin: boolean
  isSuper: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  selectDataset: (key: string) => void
  /** 匯入後重新取得資料集清單；給 key 時順便切換過去 */
  refresh: (selectKey?: string) => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

/** 從使用者可看的資料集中挑出要用的：記住的選擇仍有效就沿用，否則用第一個 */
function pickDataset(datasets: DatasetInfo[], preferred: string | null): string | null {
  if (preferred && datasets.some((d) => d.key === preferred)) return preferred
  return datasets[0]?.key ?? null
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null | undefined>(undefined)
  const [datasets, setDatasets] = useState<DatasetInfo[]>([])
  const [dataset, setCurrent] = useState<string | null>(getDataset())

  const apply = useCallback((list: DatasetInfo[], preferred: string | null) => {
    const key = pickDataset(list, preferred)
    setDatasets(list)
    setDataset(key)
    setCurrent(key)
  }, [])

  const refresh = useCallback(
    async (selectKey?: string) => {
      try {
        const me = await api.me()
        const { datasets: list, ...rest } = me
        setUser(rest)
        apply(list, selectKey ?? getDataset())
      } catch {
        setUser(null)
      }
    },
    [apply],
  )

  useEffect(() => {
    void refresh()
  }, [refresh])

  // 任何 API 回 401（登入過期、帳號被停用）就回到登入頁
  useEffect(() => {
    const onUnauthorized = () => setUser(null)
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
  }, [])

  const login = useCallback(
    async (username: string, password: string) => {
      await api.login(username, password)
      await refresh()
    },
    [refresh],
  )

  const logout = useCallback(async () => {
    await api.logout().catch(() => undefined)
    setUser(null)
    setDatasets([])
  }, [])

  const selectDataset = useCallback((key: string) => {
    setDataset(key)
    setCurrent(key)
  }, [])

  const value = useMemo<AuthState>(
    () => ({
      user,
      datasets,
      dataset,
      isAdmin: user?.role === 'super_admin' || user?.role === 'plant_admin',
      isSuper: user?.role === 'super_admin',
      login,
      logout,
      selectDataset,
      refresh,
    }),
    [user, datasets, dataset, login, logout, selectDataset, refresh],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth 必須在 AuthProvider 之內使用')
  return ctx
}
