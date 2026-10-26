import { useState, type FormEvent } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'
import { PLATFORM_NAME } from '../components/AppShell'

/** 登入頁（spec §15）：帳號密碼由管理者建立，忘記密碼請洽管理者重設。 */
export default function LoginPage() {
  const { user, login } = useAuth()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const from = (location.state as { from?: string } | null)?.from ?? '/quality'
  if (user) return <Navigate to={from} replace />

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(username.trim(), password)
    } catch (err) {
      setError(err instanceof Error ? err.message : '登入失敗')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="mb-1 text-lg font-semibold text-slate-800">{PLATFORM_NAME}</h1>
        <p className="mb-5 text-sm text-slate-500">請登入</p>
        <label className="mb-3 block">
          <span className="mb-1 block text-xs font-medium text-slate-500">帳號</span>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoFocus
            required
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-[#0086DB] focus:outline-none"
          />
        </label>
        <label className="mb-4 block">
          <span className="mb-1 block text-xs font-medium text-slate-500">密碼</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-[#0086DB] focus:outline-none"
          />
        </label>
        {error && <p className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-md bg-[#0086DB] px-3 py-2 text-sm font-medium text-white hover:bg-[#0073bd] disabled:opacity-60"
        >
          {busy ? '登入中…' : '登入'}
        </button>
        <p className="mt-4 text-xs text-slate-400">忘記密碼請洽各廠管理者重設。</p>
      </form>
    </div>
  )
}
