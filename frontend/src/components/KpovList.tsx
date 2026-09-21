import type { KpovItem } from '../api/client'
import { LEVEL_COLORS } from '../constants'

type Props = {
  items: KpovItem[]
  total: number
  deviatedOnly: boolean
  onToggleDeviated: (value: boolean) => void
  onSelect: (kpovNo: string, equipmentCode: string) => void
}

function LevelCell({ level }: { level: number | null }) {
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

export function KpovList({ items, total, deviatedOnly, onToggleDeviated, onSelect }: Props) {
  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm text-slate-500">共 {total} 項</span>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={deviatedOnly}
            onChange={(e) => onToggleDeviated(e.target.checked)}
            className="h-3.5 w-3.5 accent-slate-700"
          />
          僅顯示有異動
        </label>
      </div>

      {items.length === 0 ? (
        <p className="py-8 text-center text-sm text-slate-500">沒有符合條件的 KPOV。</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-400">
              <th className="py-2 pr-2 font-medium">KPOV</th>
              <th className="py-2 pr-2 font-medium">站別</th>
              <th className="py-2 pr-2 font-medium">設備</th>
              <th className="py-2 pr-2 text-center font-medium">小y</th>
              <th className="py-2 pr-2 text-center font-medium">大Y</th>
              <th className="py-2 pr-2 text-center font-medium">基準</th>
              <th className="py-2 text-center font-medium">現況</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr
                key={`${item.kpovNo}-${item.equipmentCode}`}
                onClick={() => item.kpovNo && onSelect(item.kpovNo, item.equipmentCode)}
                className={`border-b border-slate-100 transition hover:bg-slate-50 ${
                  item.kpovNo ? 'cursor-pointer' : ''
                }`}
              >
                <td className="py-2 pr-2">
                  <div className="flex items-center gap-1.5">
                    {/* 現況與基準不同者加左側色條（spec.md REQ-UI-21） */}
                    {item.deviates && (
                      <span
                        className={`inline-block h-4 w-1 rounded-full ${
                          item.escalatedOpen ? 'bg-red-500' : 'bg-emerald-500'
                        }`}
                        title={item.escalatedOpen ? '惡化中' : '已改善'}
                      />
                    )}
                    <span className="font-medium text-slate-800">{item.kpovName}</span>
                  </div>
                  <span className="text-xs text-slate-400">{item.kpovNo}</span>
                </td>
                <td className="py-2 pr-2 text-slate-600">{item.station}</td>
                <td className="py-2 pr-2 font-mono text-xs text-slate-500">{item.equipmentCode}</td>
                <td className="py-2 pr-2 text-center tabular-nums text-slate-600">
                  {item.smallYCurrent}
                  {item.smallYCurrent !== item.smallYBaseline && (
                    <span className="ml-1 text-xs text-slate-400">({item.smallYBaseline})</span>
                  )}
                </td>
                <td className="py-2 pr-2 text-center tabular-nums text-slate-600">
                  {item.bigYCurrent}
                  {item.bigYCurrent !== item.bigYBaseline && (
                    <span className="ml-1 text-xs text-slate-400">({item.bigYBaseline})</span>
                  )}
                </td>
                <td className="py-2 pr-2 text-center">
                  <LevelCell level={item.levelBaseline} />
                </td>
                <td className="py-2 text-center">
                  <LevelCell level={item.levelCurrent} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
