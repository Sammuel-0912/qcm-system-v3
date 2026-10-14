import { LEVEL_COLORS } from '../constants'

type Series = { label: string; counts: Record<string, number> }

type Props = {
  title: string
  /** 一個或兩個數列（例：改善前／改善後），每格依序顯示 */
  series: Series[]
  total: number
}

/** Level 3 → Level 0 的筆數列（客訴筆數、維修筆數） */
export function LevelTallyBar({ title, series, total }: Props) {
  const levels = [3, 2, 1, 0]
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between text-xs text-slate-500">
        <span className="font-medium text-slate-700">{title}</span>
        {series.length > 1 && <span>{series.map((s) => s.label).join('／')}</span>}
      </div>
      <div className="grid grid-cols-5 gap-1.5">
        {levels.map((level) => {
          const any = series.some((s) => (s.counts[String(level)] ?? 0) > 0)
          return (
            <div
              key={level}
              className={`rounded-md border border-slate-200 px-1 py-1.5 text-center text-xs ${any ? '' : 'opacity-60'}`}
              style={{ backgroundColor: any ? LEVEL_COLORS[level] : undefined }}
            >
              <span className="block font-semibold text-slate-800">Level {level}</span>
              <span className="block tabular-nums text-slate-700">
                {series.map((s) => s.counts[String(level)] ?? 0).join('／')}
              </span>
            </div>
          )
        })}
        <div className="rounded-md border border-slate-200 bg-slate-50 px-1 py-1.5 text-center text-xs">
          <span className="block font-semibold text-slate-800">全部</span>
          <span className="block tabular-nums text-slate-700">{total}</span>
        </div>
      </div>
    </div>
  )
}
