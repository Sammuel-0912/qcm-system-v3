import { useEffect, useState } from 'react'

import type { Paged } from '../api/client'

/** 清單頁共用：關鍵字搜尋框（停止輸入 300ms 後送出） */
export function SearchBox({ onSearch, placeholder }: { onSearch: (q: string) => void; placeholder: string }) {
  const [value, setValue] = useState('')
  useEffect(() => {
    const timer = window.setTimeout(() => onSearch(value.trim()), 300)
    return () => window.clearTimeout(timer)
  }, [value, onSearch])
  return (
    <input
      type="search"
      value={value}
      onChange={(e) => setValue(e.target.value)}
      placeholder={placeholder}
      className="w-full max-w-sm rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
    />
  )
}

/** 清單頁共用：後端分頁列 */
export function Pager<T>({ data, onPageChange }: { data: Paged<T>; onPageChange: (page: number) => void }) {
  return (
    <div className="flex items-center justify-between text-sm text-slate-500">
      <button
        type="button"
        disabled={data.page <= 1}
        onClick={() => onPageChange(data.page - 1)}
        className="rounded border border-slate-300 bg-white px-3 py-1.5 hover:bg-slate-50 disabled:opacity-40"
      >
        上一頁
      </button>
      <span className="tabular-nums">
        第 {data.page} / {data.pages} 頁・共 {data.total} 筆
      </span>
      <button
        type="button"
        disabled={data.page >= data.pages}
        onClick={() => onPageChange(data.page + 1)}
        className="rounded border border-slate-300 bg-white px-3 py-1.5 hover:bg-slate-50 disabled:opacity-40"
      >
        下一頁
      </button>
    </div>
  )
}
