import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { BarResponse } from '../api/client'
import { LEVEL_COLORS } from '../constants'

type Props = { data: BarResponse; view: string; onSelect: (level: number) => void }

export function LevelBarChart({ data, view, onSelect }: Props) {
  // 四根柱固定存在，數量為 0 也保留柱位（spec.md REQ-UI-10）
  const rows = data.bars.map((bar) => ({
    name: `Level ${bar.level}`,
    level: bar.level,
    count: bar.count,
    baselineCount: bar.baselineCount,
  }))
  const max = Math.max(1, ...rows.map((r) => Math.max(r.count, r.baselineCount)))

  // 基準值標在各自的柱子上方，而不是橫跨整張圖的參考線——
  // 四條全寬虛線看不出對應哪一根柱。
  function renderLabel(props: any) {
    const { x, y, width, index } = props
    const row = rows[index]
    if (!row) return null
    const cx = x + width / 2
    const delta = row.count - row.baselineCount
    const showBaseline = view !== 'baseline' && delta !== 0
    return (
      <g>
        <text x={cx} y={y - 8} textAnchor="middle" fontSize={13} fontWeight={600} fill="#37474f">
          {row.count}
        </text>
        {showBaseline && (
          // Level 0 是唯一「良好」的等級：它增加為綠，其他等級增加為紅
          <text
            x={cx}
            y={y - 24}
            textAnchor="middle"
            fontSize={11}
            fill={(delta > 0) === (row.level === 0) ? '#2e7d32' : '#c62828'}
          >
            基準 {row.baselineCount} ({delta > 0 ? `+${delta}` : delta})
          </text>
        )}
      </g>
    )
  }

  return (
    <div>
      <div style={{ width: '100%', height: 320 }}>
        <ResponsiveContainer>
          <BarChart data={rows} margin={{ top: 28, right: 24, bottom: 8, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eceff1" />
            <XAxis dataKey="name" tickLine={false} axisLine={{ stroke: '#cfd8dc' }} />
            <YAxis
              allowDecimals={false}
              domain={[0, Math.ceil(max * 1.15)]}
              tickLine={false}
              axisLine={false}
              width={44}
            />
            <Tooltip
              cursor={{ fill: '#00000008' }}
              formatter={(value: number, name) => [
                `${value} 項`,
                name === 'count' ? '目前口徑' : '基準',
              ]}
            />
            <Bar dataKey="count" radius={[6, 6, 0, 0]} onClick={(d: any) => onSelect(d.level)} cursor="pointer">
              {rows.map((row) => (
                <Cell key={row.level} fill={LEVEL_COLORS[row.level]} stroke="#00000022" />
              ))}
              <LabelList dataKey="count" position="top" content={renderLabel} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-4 text-sm text-slate-600">
        {data.bars.map((bar) => (
          <span key={bar.level} className="flex items-center gap-1.5">
            <span
              className="inline-block h-3 w-3 rounded-sm border border-black/10"
              style={{ backgroundColor: bar.color }}
            />
            Level {bar.level}
          </span>
        ))}
      </div>

      {/* 未評估的 KPOV 不畫成第五根柱（spec.md REQ-UI-12） */}
      {data.unrated > 0 && (
        <p className="mt-2 text-sm text-slate-500">另有 {data.unrated} 筆 KPOV 未評估偵測度</p>
      )}
    </div>
  )
}
