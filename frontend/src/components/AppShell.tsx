import { useEffect, useState, type ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'

import { usePresence } from '../hooks/usePresence'

type NavItem = { to: string; label: string; hint?: string }
type NavGroup = { title: string; items: NavItem[] }

// 導覽結構。新增頁面只改這裡。
const NAV: NavGroup[] = [
  {
    title: '品質管控',
    items: [
      { to: '/quality', label: '整線品控力總覽', hint: 'KPOV 等級分佈與異動' },
      { to: '/complaints', label: '客訴清單', hint: '客訴報表（8D）' },
      { to: '/process', label: '製程清單', hint: '修護報表' },
    ],
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

function isActive(pathname: string, to: string) {
  return pathname === to || pathname.startsWith(to + '/')
}

function SideNav() {
  const { pathname } = useLocation()
  return (
    <nav aria-label="主要導覽" className="space-y-5 px-3 py-4">
      {NAV.map((group) => (
        <div key={group.title}>
          <div className="px-2 pb-1.5 text-[11px] font-medium uppercase tracking-wide text-slate-400">
            {group.title}
          </div>
          <ul className="space-y-0.5">
            {group.items.map((item) => {
              const active = isActive(pathname, item.to)
              return (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    aria-current={active ? 'page' : undefined}
                    className={`block rounded-md px-2.5 py-2 transition ${
                      active ? 'bg-slate-900 text-white' : 'text-slate-700 hover:bg-slate-100'
                    }`}
                  >
                    <span className="block text-sm font-medium">{item.label}</span>
                    {item.hint && (
                      <span className={`block text-xs ${active ? 'text-slate-300' : 'text-slate-400'}`}>
                        {item.hint}
                      </span>
                    )}
                  </Link>
                </li>
              )
            })}
          </ul>
        </div>
      ))}
    </nav>
  )
}

type Props = {
  title: string
  /** 右側的頁面專屬操作（口徑切換、匯入…） */
  actions?: ReactNode
  children: ReactNode
}

/**
 * 一般頁面的外殼：左側導覽列 + 頁首 + 內容區。桌機導覽列固定，手機改為可收合的抽屜。
 *
 * AR 掃描頁刻意不使用這個外殼——它會把 A-Frame 的 scene 以 position:fixed
 * 蓋滿整個視窗，頁首會被遮住或反過來擋住相機畫面（見 ar-integration-spec.md §2）。
 */
export function AppShell({ title, actions, children }: Props) {
  const online = usePresence()
  const { pathname } = useLocation()
  const [drawer, setDrawer] = useState(false)

  // 換頁就收起手機抽屜
  useEffect(() => setDrawer(false), [pathname])

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-56 overflow-y-auto border-r border-slate-200 bg-white lg:block">
        <div className="border-b border-slate-100 px-5 py-4 text-sm font-semibold text-slate-800">WJ1 DCS 品控力平台</div>
        <SideNav />
      </aside>

      {drawer && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            aria-label="關閉選單"
            className="absolute inset-0 bg-black/30"
            onClick={() => setDrawer(false)}
          />
          <aside className="absolute inset-y-0 left-0 w-64 overflow-y-auto bg-white shadow-xl">
            <div className="border-b border-slate-100 px-5 py-4 text-sm font-semibold text-slate-800">
              WJ1 DCS 品控力平台
            </div>
            <SideNav />
          </aside>
        </div>
      )}

      <div className="lg:pl-56">
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-4 px-6 py-4">
            <button
              type="button"
              onClick={() => setDrawer(true)}
              aria-label="開啟選單"
              className="rounded-md border border-slate-300 px-2.5 py-1.5 text-sm text-slate-700 lg:hidden"
            >
              ☰
            </button>
            <h1 className="text-xl font-semibold">{title}</h1>
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
    </div>
  )
}
