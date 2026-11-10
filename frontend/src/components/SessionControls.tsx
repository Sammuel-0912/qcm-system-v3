import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { api } from '../api/client'
import { useAuth } from '../auth/AuthContext'

/**
 * 廠／線別切換（spec §15）：最高權限管理者看得到所有廠的線，其他人只看得到自己廠。
 * 依廠分組；只有一個資料集時直接顯示文字。
 */
export function DatasetSelect() {
  const { datasets, dataset, selectDataset } = useAuth()
  if (datasets.length === 0) {
    return <span className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-700">尚無資料</span>
  }
  if (datasets.length === 1) {
    return (
      <span className="font-mono text-lg font-bold text-sky-900" title="目前的廠／產品廠／線別">
        {datasets[0].key}
      </span>
    )
  }
  const plants = [...new Set(datasets.map((d) => d.plant))]
  return (
    <label className="flex items-center gap-1.5 text-xs text-slate-500">
      <span>廠／線別</span>
      <select
        value={dataset ?? ''}
        onChange={(e) => selectDataset(e.target.value)}
        aria-label="切換廠與線別"
        className="rounded-md border border-slate-300 bg-white px-2 py-1 font-mono text-lg font-bold text-sky-900"
      >
        {plants.map((plant) => (
          <optgroup key={plant} label={plant}>
            {datasets
              .filter((d) => d.plant === plant)
              .map((d) => (
                <option key={d.key} value={d.key}>
                  {d.key}
                </option>
              ))}
          </optgroup>
        ))}
      </select>
    </label>
  )
}

/** 右上角使用者選單：名稱、角色與廠別、修改密碼、登出 */
export function UserMenu() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [changing, setChanging] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    window.addEventListener('mousedown', onClick)
    return () => window.removeEventListener('mousedown', onClick)
  }, [open])

  if (!user) return null
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex items-center gap-2 rounded-md border border-slate-300 px-2.5 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
      >
        <span className="font-medium">{user.displayName}</span>
        <span className="text-xs text-slate-400">
          {user.displayName === user.roleLabel ? '' : user.roleLabel}
          {user.plant ? `・${user.plant}` : ''}
        </span>
        <span aria-hidden className="text-xs text-slate-400">▾</span>
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-1 w-44 overflow-hidden rounded-md border border-slate-200 bg-white text-sm shadow-lg">
          <div className="border-b border-slate-100 px-3 py-2 text-xs text-slate-400">帳號：{user.username}</div>
          <button
            type="button"
            onClick={() => {
              setOpen(false)
              setChanging(true)
            }}
            className="block w-full px-3 py-2 text-left hover:bg-slate-50"
          >
            修改密碼
          </button>
          <button
            type="button"
            onClick={async () => {
              await logout()
              navigate('/login', { replace: true })
            }}
            className="block w-full px-3 py-2 text-left text-red-600 hover:bg-red-50"
          >
            登出
          </button>
        </div>
      )}
      {changing && <ChangePasswordDialog onClose={() => setChanging(false)} />}
    </div>
  )
}

function ChangePasswordDialog({ onClose }: { onClose: () => void }) {
  const [oldPassword, setOld] = useState('')
  const [newPassword, setNew] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (newPassword.length < 8) return setError('新密碼至少 8 碼')
    if (newPassword !== confirm) return setError('兩次輸入的新密碼不一致')
    try {
      await api.changePassword(oldPassword, newPassword)
      setDone(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : '修改失敗')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true">
      <form onSubmit={submit} className="w-full max-w-sm rounded-lg bg-white p-5 shadow-xl">
        <h2 className="mb-4 text-base font-semibold text-slate-800">修改密碼</h2>
        {done ? (
          <p className="mb-4 text-sm text-emerald-700">密碼已更新；其他裝置上的登入已失效。</p>
        ) : (
          <>
            {(
              [
                ['目前密碼', oldPassword, setOld, 'current-password'],
                ['新密碼（至少 8 碼）', newPassword, setNew, 'new-password'],
                ['再輸入一次新密碼', confirm, setConfirm, 'new-password'],
              ] as const
            ).map(([label, value, set, auto]) => (
              <label key={label} className="mb-3 block">
                <span className="mb-1 block text-xs font-medium text-slate-500">{label}</span>
                <input
                  type="password"
                  value={value}
                  onChange={(e) => set(e.target.value)}
                  autoComplete={auto}
                  required
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                />
              </label>
            ))}
            {error && <p className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
          </>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm">
            {done ? '關閉' : '取消'}
          </button>
          {!done && (
            <button type="submit" className="rounded-md bg-[#0086DB] px-3 py-1.5 text-sm font-medium text-white">
              更新
            </button>
          )}
        </div>
      </form>
    </div>
  )
}
