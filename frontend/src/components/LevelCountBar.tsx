import type { LevelCounts } from '../api/client'
import { LEVEL_COLORS } from '../constants'

type Props = {
  counts: LevelCounts
  /** 點 Level 開該 Level 的 KPOV 明細 */
  onSelect: (level: number) => void
  /** 範圍說明（例：近 30 天有維修或客訴的 KPOV） */
  caption?: string
}

/** 象限圖下方的各 Level KPOV 數（與象限圖同一口徑、同一範圍） */
export function LevelCountBar({ counts, onSelect, caption }: Props) {
  const levels = [0, 1, 2, 3] as const
  return (
    <div className="mt-1">
      <div className="mb-2 flex items-baseline justify-between text-xs text-slate-400">
        <span>
          各 Level KPOV 數{caption && <span className="ml-1 text-slate-500">・{caption}</span>}
        </span>
        <span>點選查看明細</span>
      </div>
      <div className="grid grid-cols-5 gap-1.5">
        {levels.map((level) => {
          const n = counts[`level${level}`]
          return (
            <button
              key={level}
              type="button"
              onClick={() => onSelect(level)}
              disabled={n === 0}
              className="rounded-md border border-slate-200 px-1 py-1.5 text-center text-xs transition hover:ring-2 hover:ring-slate-400 disabled:cursor-default disabled:opacity-50 disabled:hover:ring-0"
              style={{ backgroundColor: n ? LEVEL_COLORS[level] : undefined }}
            >
              <span className="block font-semibold text-slate-800">Level {level}</span>
              <span className="block tabular-nums text-slate-700">{n}</span>
            </button>
          )
        })}
        <div className="rounded-md border border-slate-200 bg-slate-50 px-1 py-1.5 text-center text-xs">
          <span className="block font-semibold text-slate-800">全部</span>
          <span className="block tabular-nums text-slate-700">{counts.total}</span>
        </div>
      </div>
      {counts.unrated > 0 && (
        <p className="mt-1.5 text-xs text-slate-400">另有 {counts.unrated} 項未評估</p>
      )}
    </div>
  )
}
