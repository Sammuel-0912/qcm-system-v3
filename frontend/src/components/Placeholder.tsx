import { Link } from 'react-router-dom'

/** 尚未移植的頁面佔位。整合第二階段會換成真正的畫面。 */
export function Placeholder({ name, dark = false }: { name: string; dark?: boolean }) {
  return (
    <main className="mx-auto max-w-3xl px-6 py-20 text-center">
      <p className={`text-sm ${dark ? 'text-slate-300' : 'text-slate-500'}`}>
        {name} 尚未移植
      </p>
      <p className={`mt-2 text-xs ${dark ? 'text-slate-400' : 'text-slate-400'}`}>
        AR 點檢頁面將於整合第二階段以 Tailwind 重寫並接上 /api/ar
      </p>
      <Link
        to="/quality"
        className={`mt-6 inline-block rounded-md px-4 py-2 text-sm ${
          dark ? 'bg-slate-100 text-slate-900' : 'bg-slate-900 text-white'
        }`}
      >
        回到品控力象限
      </Link>
    </main>
  )
}
