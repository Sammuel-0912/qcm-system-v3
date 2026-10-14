import { LEVEL_COLORS } from '../constants'

/** Level 色塊（L0–L3）；null 顯示「—」 */
export function LevelChip({ level }: { level: number | null }) {
  if (level === null) return <span className="text-slate-400">—</span>
  return (
    <span
      className="inline-flex h-5 items-center rounded px-1.5 text-xs font-semibold text-slate-800 ring-1 ring-black/10"
      style={{ backgroundColor: LEVEL_COLORS[level] }}
    >
      L{level}
    </span>
  )
}

/** 前後 Level 與箭頭：變差紅色 ↑、變好綠色 ↓、不變灰色 → */
export function LevelChange({ before, after }: { before: number | null; after: number | null }) {
  const arrow =
    before === null || after === null || before === after
      ? { symbol: '→', className: 'text-slate-400' }
      : after > before
        ? { symbol: '↑', className: 'text-red-600' }
        : { symbol: '↓', className: 'text-emerald-600' }
  return (
    <span className="inline-flex items-center gap-1 whitespace-nowrap">
      <LevelChip level={before} />
      <span className={`font-bold ${arrow.className}`}>{arrow.symbol}</span>
      <LevelChip level={after} />
    </span>
  )
}
