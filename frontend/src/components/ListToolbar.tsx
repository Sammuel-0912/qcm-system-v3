import type { Paged } from '../api/client'

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
