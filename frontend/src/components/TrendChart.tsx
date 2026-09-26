import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import type { TrendResponse } from '../api/client'

type Props = { data: TrendResponse; scopeLabel: string }

// 惡化=紅、改善=綠。與象限圖的差異徽章同一套語意。
const ESCALATED = '#c62828'
const IMPROVED = '#2e7d32'

export function TrendChart({ data, scopeLabel }: Props) {
  const rows = data.points.map((p) => ({
    period: p.period,
    惡化: p.escalatedCumulative,
    改善: p.improvedCumulative,
  }))

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-baseline gap-2">
        <h2 className="text-base font-semibold text-slate-800">等級異動趨勢</h2>
        <span className="text-sm text-slate-500">累計 · {scopeLabel}</span>
        {rows.length > 0 && (
          <span className="ml-auto flex items-center gap-3 text-sm">
            <span style={{ color: ESCALATED }}>惡化 {data.totals.escalated}</span>
            <span style={{ color: IMPROVED }}>改善 {data.totals.improved}</span>
          </span>
        )}
      </div>

      {rows.length === 0 ? (
        <div className="flex h-[280px] flex-col items-center justify-center rounded-md border border-dashed border-slate-200 text-center">
          <p className="text-sm text-slate-500">{data.emptyReason ?? '尚無等級異動紀錄'}</p>
          <p className="mt-1 text-xs text-slate-400">
            等級異動來自維修報表；累積幾筆之後這裡就會出現趨勢線。
          </p>
        </div>
      ) : (
        <div style={{ width: '100%', height: 280 }}>
          <ResponsiveContainer>
            <LineChart data={rows} margin={{ top: 12, right: 20, bottom: 4, left: 4 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eceff1" />
              <XAxis dataKey="period" tickLine={false} axisLine={{ stroke: '#cfd8dc' }} />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={40} />
              <Tooltip
                cursor={{ stroke: '#cfd8dc' }}
                formatter={(value: number, name) => [`${value} 筆`, `累計${name}`]}
              />
              <Legend verticalAlign="top" height={28} iconType="plainline" />
              <Line
                type="stepAfter"
                dataKey="惡化"
                stroke={ESCALATED}
                strokeWidth={2.5}
                dot={{ r: 4, fill: ESCALATED }}
                activeDot={{ r: 6 }}
              />
              <Line
                type="stepAfter"
                dataKey="改善"
                stroke={IMPROVED}
                strokeWidth={2.5}
                dot={{ r: 4, fill: IMPROVED }}
                activeDot={{ r: 6 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
