import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'

import { usePresence } from '../hooks/usePresence'

type NavItem = { to: string; label: string; hint?: string }
type NavGroup = { title: string; items: NavItem[] }

// 導覽結構。新增頁面只改這裡。
const NAV: NavGroup[] = [
  {
    title: '品質管控',
    items: [{ to: '/quality', label: '品控力象限', hint: 'KPOV 等級分佈與異動' }],
  },
  {
    title: 'AR 點檢',
    items: [
      { to: '/ar/dashboard', label: '點檢儀表板', hint: '良率統計與報表' },
      { to: '/ar/devices', label: '設備管理', hint: 'Marker 與作業指引' },
      { to: '/ar/photo', label: '拍照點檢', hint: '免掃碼，手機拍照上傳' },
      { to: '/ar/inspect', label: 'AR 掃描點檢', hint: '需相機權限' },
    ],
  },
]

function currentLabel(pathname: string): string {
  for (const group of NAV) {
    for (const item of group.items) {
      if (pathname === item.to || pathname.startsWith(item.to + '/')) return item.label
    }
  }
  return '選擇功能'
}

function NavMenu() {
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()
  const ref = useRef<HTMLDivElement>(null)

  // 路由變了就收起選單
  useEffect(() => setOpen(false), [pathname])

  useEffect(() => {
    if (!open) return
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex items-center gap-2 rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 transition hover:border-slate-400 hover:bg-slate-50"
      >
        {currentLabel(pathname)}
        <span className="text-xs text-slate-400">▾</span>
      </button>

      {open && (
        <div
          role="menu"
          className="absolute left-0 z-40 mt-1 w-64 rounded-md border border-slate-200 bg-white p-1 shadow-lg"
        >
          {NAV.map((group, gi) => (
            <div key={group.title}>
              {gi > 0 && <div className="my-1 border-t border-slate-100" />}
              <div className="px-2 py-1 text-[11px] font-medium uppercase tracking-wide text-slate-400">
                {group.title}
              </div>
              {group.items.map((item) => {
                const active = pathname === item.to || pathname.startsWith(item.to + '/')
                return (
                  <Link
                    key={item.to}
                    to={item.to}
                    role="menuitem"
                    className={`block rounded px-2 py-1.5 transition ${
                      active ? 'bg-slate-900 text-white' : 'text-slate-800 hover:bg-slate-100'
                    }`}
                  >
                    <span className="block text-sm">{item.label}</span>
                    {item.hint && (
                      <span className={`block text-xs ${active ? 'text-slate-300' : 'text-slate-400'}`}>
                        {item.hint}
                      </span>
                    )}
                  </Link>
                )
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

type Props = {
  title: string
  /** 右側的頁面專屬操作（口徑切換、匯入…） */
  actions?: ReactNode
  children: ReactNode
}

/**
 * 一般頁面的外殼：頁首 + 導覽下拉 + 內容區。
 *
 * AR 掃描頁刻意不使用這個外殼——它會把 A-Frame 的 scene 以 position:fixed
 * 蓋滿整個視窗，頁首會被遮住或反過來擋住相機畫面（見 ar-integration-spec.md §2）。
 */
export function AppShell({ title, actions, children }: Props) {
  const online = usePresence()
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-4 px-6 py-4">
          <h1 className="text-xl font-semibold">{title}</h1>
          <NavMenu />
          <div className="ml-auto flex items-center gap-4">
            {online !== null && (
              <span className="flex items-center gap-1.5 text-sm text-slate-500" title="目前開著本網站的分頁數">
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                線上 {online} 人
              </span>
            )}
            {actions && <div className="flex items-center gap-2">{actions}</div>}
          </div>
        </div>
      </header>
      {children}
    </div>
  )
}
