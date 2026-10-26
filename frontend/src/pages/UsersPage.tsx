import { useCallback, useEffect, useState, type FormEvent } from 'react'

import { api, PLANTS, type AuthUser, type Role } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { AppShell } from '../components/AppShell'
import { formatLocalDateTime } from '../utils/datetime'

const ROLE_OPTIONS: { value: Role; label: string }[] = [
  { value: 'user', label: '一般使用者' },
  { value: 'plant_admin', label: '廠管理者' },
  { value: 'super_admin', label: '最高權限管理者' },
]

const ROLE_BADGE: Record<Role, string> = {
  super_admin: 'bg-purple-50 text-purple-700',
  plant_admin: 'bg-sky-50 text-sky-700',
  user: 'bg-slate-100 text-slate-600',
}

type Editing = { mode: 'create' } | { mode: 'edit'; user: AuthUser } | { mode: 'reset'; user: AuthUser }

/**
 * 使用者管理（spec §15）。
 * - 最高權限管理者：看全部帳號，可指定角色與廠別（廠管理者由此指派）。
 * - 廠管理者：只看自己廠的帳號，只能新增／停用／重設自己廠的一般使用者，角色與廠別固定。
 */
export default function UsersPage() {
  const { user: me, isSuper } = useAuth()
  const [users, setUsers] = useState<AuthUser[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<Editing | null>(null)

  const load = useCallback(async () => {
    try {
      setUsers(await api.users())
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入失敗')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function toggleActive(u: AuthUser) {
    try {
      await api.updateUser(u.id, { isActive: !u.isActive })
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : '更新失敗')
    }
  }

  // 廠管理者只能管理自己廠的一般使用者；任何人都不能停用自己
  const canManage = (u: AuthUser) => u.id !== me?.id && (isSuper || u.role === 'user')

  const actions = (
    <button
      onClick={() => setEditing({ mode: 'create' })}
      className="rounded-md bg-[#0086DB] px-3 py-1.5 text-sm font-medium text-white hover:bg-[#0073bd]"
    >
      新增帳號
    </button>
  )

  return (
    <AppShell title="使用者管理" actions={actions}>
      <main className="mx-auto max-w-6xl space-y-4 px-6 py-6">
        <p className="text-sm text-slate-500">
          {isSuper
            ? '最高權限管理者可管理所有廠的帳號，並指派各廠的廠管理者。'
            : `你是 ${me?.plant} 的廠管理者，可新增、停用 ${me?.plant} 的一般使用者並重設其密碼。`}
          密碼至少 8 碼；停用帳號或重設密碼後，該帳號已登入的裝置會立即登出。
        </p>
        {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="min-w-full whitespace-nowrap text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500">
              <tr>
                {['帳號', '名稱', '角色', '廠別', '狀態', '最後登入', ''].map((h) => (
                  <th key={h} className="px-4 py-2 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {users === null && (
                <tr>
                  <td colSpan={7} className="px-4 py-6 text-center text-slate-400">
                    載入中…
                  </td>
                </tr>
              )}
              {users?.map((u) => (
                <tr key={u.id} className={u.isActive ? '' : 'bg-slate-50 text-slate-400'}>
                  <td className="px-4 py-2 font-mono">{u.username}</td>
                  <td className="px-4 py-2">{u.displayName}</td>
                  <td className="px-4 py-2">
                    <span className={`rounded px-2 py-0.5 text-xs ${ROLE_BADGE[u.role]}`}>{u.roleLabel}</span>
                  </td>
                  <td className="px-4 py-2">{u.plant ?? '全部'}</td>
                  <td className="px-4 py-2">
                    {u.isActive ? <span className="text-emerald-700">啟用</span> : <span>已停用</span>}
                  </td>
                  <td className="px-4 py-2 tabular-nums">{u.lastLoginAt ? formatLocalDateTime(u.lastLoginAt) : '—'}</td>
                  <td className="px-4 py-2 text-right whitespace-nowrap">
                    {u.id === me?.id ? (
                      <span className="text-xs text-slate-400">（自己）</span>
                    ) : (
                      canManage(u) && (
                        <div className="flex justify-end gap-2 text-xs">
                          <button onClick={() => setEditing({ mode: 'edit', user: u })} className="text-[#0086DB] hover:underline">
                            編輯
                          </button>
                          <button onClick={() => setEditing({ mode: 'reset', user: u })} className="text-[#0086DB] hover:underline">
                            重設密碼
                          </button>
                          <button
                            onClick={() => toggleActive(u)}
                            className={u.isActive ? 'text-red-600 hover:underline' : 'text-emerald-700 hover:underline'}
                          >
                            {u.isActive ? '停用' : '啟用'}
                          </button>
                        </div>
                      )
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </main>
      {editing && (
        <UserDialog
          editing={editing}
          isSuper={isSuper}
          myPlant={me?.plant ?? null}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null)
            void load()
          }}
        />
      )}
    </AppShell>
  )
}

function UserDialog({
  editing,
  isSuper,
  myPlant,
  onClose,
  onSaved,
}: {
  editing: Editing
  isSuper: boolean
  myPlant: string | null
  onClose: () => void
  onSaved: () => void
}) {
  const target = editing.mode === 'create' ? null : editing.user
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState(target?.displayName ?? '')
  const [role, setRole] = useState<Role>(target?.role ?? 'user')
  const [plant, setPlant] = useState<string>(target?.plant ?? myPlant ?? 'WJ1')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const title =
    editing.mode === 'create' ? '新增帳號' : editing.mode === 'edit' ? `編輯 ${target?.username}` : `重設 ${target?.username} 的密碼`

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (editing.mode !== 'edit' && password.length < 8) return setError('密碼至少 8 碼')
    setBusy(true)
    try {
      const plantValue = role === 'super_admin' ? null : plant
      if (editing.mode === 'create') {
        await api.createUser({ username: username.trim(), displayName: displayName.trim(), password, role, plant: plantValue })
      } else if (editing.mode === 'edit') {
        await api.updateUser(editing.user.id, {
          displayName: displayName.trim(),
          ...(isSuper ? { role, plant: plantValue } : {}),
        })
      } else {
        await api.resetPassword(editing.user.id, password)
      }
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : '儲存失敗')
    } finally {
      setBusy(false)
    }
  }

  const input = 'w-full rounded-md border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-50 disabled:text-slate-400'
  const label = 'mb-1 block text-xs font-medium text-slate-500'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true">
      <form onSubmit={submit} className="w-full max-w-md space-y-3 rounded-lg bg-white p-5 shadow-xl">
        <h2 className="text-base font-semibold text-slate-800">{title}</h2>
        {editing.mode === 'create' && (
          <label className="block">
            <span className={label}>帳號（英數字，至少 3 碼）</span>
            <input value={username} onChange={(e) => setUsername(e.target.value)} required autoComplete="off" className={input} />
          </label>
        )}
        {editing.mode !== 'reset' && (
          <>
            <label className="block">
              <span className={label}>名稱</span>
              <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} required className={input} />
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className={label}>角色</span>
                <select value={role} onChange={(e) => setRole(e.target.value as Role)} disabled={!isSuper} className={input}>
                  {ROLE_OPTIONS.filter((o) => isSuper || o.value === 'user').map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className={label}>廠別</span>
                <select
                  value={role === 'super_admin' ? '' : plant}
                  onChange={(e) => setPlant(e.target.value)}
                  disabled={!isSuper || role === 'super_admin'}
                  className={input}
                >
                  {role === 'super_admin' && <option value="">全部</option>}
                  {PLANTS.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </>
        )}
        {editing.mode !== 'edit' && (
          <label className="block">
            <span className={label}>{editing.mode === 'create' ? '初始密碼（至少 8 碼）' : '新密碼（至少 8 碼）'}</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="new-password"
              className={input}
            />
          </label>
        )}
        {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <button type="button" onClick={onClose} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm">
            取消
          </button>
          <button
            type="submit"
            disabled={busy}
            className="rounded-md bg-[#0086DB] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60"
          >
            {busy ? '儲存中…' : '儲存'}
          </button>
        </div>
      </form>
    </div>
  )
}
