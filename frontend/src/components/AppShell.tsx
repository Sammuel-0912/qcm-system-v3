import { useEffect, useState, type ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'

import { AR_MARKER_ENABLED } from '../features'
import { usePresence } from '../hooks/usePresence'

type NavItem = { to: string; label: string; hint?: string }
/** title 為空：第一層直接列項目；有 title：顯示為第一層標題，items 縮排成第二層 */
type NavGroup = { title?: string; hint?: string; items: NavItem[] }

// 導覽結構（平台_左邊目錄列修改方案 1015）。新增頁面只改這裡。
const NAV: NavGroup[] = [
  {
    items: [
      { to: '/quality', label: '總覽', hint: 'Overview' },
      { to: '/process', label: '製程風險管理', hint: 'Process Risk Mgmt' },
      { to: '/complaints', label: '客訴案件管理', hint: 'RMA Event' },
    ],
  },
  {
    title: '點檢控制中心',
    hint: 'Inspection Control Center',
    items: [
      { to: '/ar/dashboard', label: '點檢看板', hint: 'Dashboard' },
      ...(AR_MARKER_ENABLED ? [{ to: '/ar/devices', label: '設備管理', hint: 'Marker 與作業指引' }] : []),
      { to: '/ar/photo', label: '拍照點檢', hint: 'Photo Verification' },
      ...(AR_MARKER_ENABLED ? [{ to: '/ar/inspect', label: 'AR 掃描點檢', hint: '需相機權限' }] : []),
    ],
  },
]

function isActive(pathname: string, to: string) {
  return pathname === to || pathname.startsWith(to + '/')
}

function NavLinkItem({ item, active }: { item: NavItem; active: boolean }) {
  return (
    <Link
      to={item.to}
      aria-current={active ? 'page' : undefined}
      className={`block rounded-md px-2.5 py-2 transition ${
        active ? 'bg-[#0086DB] text-white' : 'text-slate-700 hover:bg-slate-100'
      }`}
    >
      <span className="block text-sm font-medium">{item.label}</span>
      {item.hint && (
        <span className={`block text-xs ${active ? 'text-sky-100' : 'text-slate-400'}`}>{item.hint}</span>
      )}
    </Link>
  )
}

function SideNav() {
  const { pathname } = useLocation()
  return (
    <nav aria-label="主要導覽" className="space-y-4 px-3 py-4">
      {NAV.map((group, gi) => (
        <div key={group.title ?? gi}>
          {group.title && (
            <div className="px-2.5 pb-1.5">
              <span className="block text-sm font-semibold text-slate-800">{group.title}</span>
              {group.hint && <span className="block text-xs text-slate-400">{group.hint}</span>}
            </div>
          )}
          <ul className={`space-y-0.5 ${group.title ? 'ml-3 border-l border-slate-200 pl-2' : ''}`}>
            {group.items.map((item) => (
              <li key={item.to}>
                <NavLinkItem item={item} active={isActive(pathname, item.to)} />
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  )
}

export const PLATFORM_NAME = 'CNE WJ1 DCS 品控力風險智控平台'
const PIN_KEY = 'qcm.sidebar.pinned'

function readPinned(): boolean {
  try {
    return window.localStorage.getItem(PIN_KEY) !== 'false'
  } catch {
    return true
  }
}

function writePinned(pinned: boolean) {
  try {
    window.localStorage.setItem(PIN_KEY, String(pinned))
  } catch {
    // 無法存取瀏覽器儲存（私密模式等）時只是不記住，不影響使用
  }
}

function SidebarTitle() {
  return (
    <div className="whitespace-nowrap border-b border-slate-100 px-4 py-4 text-sm font-semibold text-slate-800">
      {PLATFORM_NAME}
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
 * 一般頁面的外殼：左側導覽列 + 頁首 + 內容區。桌機導覽列可固定或收合（記在瀏覽器），手機改為抽屜。
 *
 * AR 掃描頁刻意不使用這個外殼——它會把 A-Frame 的 scene 以 position:fixed
 * 蓋滿整個視窗，頁首會被遮住或反過來擋住相機畫面（見 ar-integration-spec.md §2）。
 */
export function AppShell({ title, actions, children }: Props) {
  const online = usePresence()
  const { pathname } = useLocation()
  const [drawer, setDrawer] = useState(false)
  // 桌機：固定時常駐展開並推開內容；取消固定後收成窄條，滑過或點擊才浮出展開
  const [pinned, setPinned] = useState(readPinned)
  const [peek, setPeek] = useState(false)
  const expanded = pinned || peek

  // 換頁就收起手機抽屜與浮出的側邊欄
  useEffect(() => {
    setDrawer(false)
    setPeek(false)
  }, [pathname])

  const togglePin = () => {
    const next = !pinned
    setPinned(next)
    setPeek(false)
    writePinned(next)
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <aside
        onMouseEnter={() => !pinned && setPeek(true)}
        onMouseLeave={() => setPeek(false)}
        className={`fixed inset-y-0 left-0 z-30 hidden flex-col overflow-hidden border-r border-slate-200 bg-white transition-[width] duration-200 lg:flex ${
          expanded ? 'w-[17rem]' : 'w-12'
        } ${peek && !pinned ? 'shadow-xl' : ''}`}
      >
        {expanded ? (
          <>
            <SidebarTitle />
            <div className="flex-1 overflow-y-auto">
              <SideNav />
            </div>
            <button
              type="button"
              onClick={togglePin}
              aria-pressed={pinned}
              title={pinned ? '取消固定，側邊欄收合成窄條' : '固定側邊欄，常駐展開'}
              className="flex items-center gap-2 whitespace-nowrap border-t border-slate-100 px-4 py-3 text-left text-xs text-slate-500 transition hover:bg-slate-50 hover:text-slate-800"
            >
              <span aria-hidden>{pinned ? '«' : '📌'}</span>
              {pinned ? '收合選單' : '固定選單'}
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={() => setPeek(true)}
            aria-label="展開選單"
            title="展開選單"
            className="flex h-14 w-full items-center justify-center text-slate-600 hover:bg-slate-50"
          >
            ☰
          </button>
        )}
      </aside>

      {drawer && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            aria-label="關閉選單"
            className="absolute inset-0 bg-black/30"
            onClick={() => setDrawer(false)}
          />
          <aside className="absolute inset-y-0 left-0 w-[17rem] overflow-y-auto bg-white shadow-xl">
            <SidebarTitle />
            <SideNav />
          </aside>
        </div>
      )}

      <div className={`transition-[padding] duration-200 ${pinned ? 'lg:pl-[17rem]' : 'lg:pl-12'}`}>
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
