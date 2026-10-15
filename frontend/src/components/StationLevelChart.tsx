import { Bar, BarChart, CartesianGrid, LabelList, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import type { StationLevelCounts, StationRef } from '../api/client'
import { LEVEL_COLORS } from '../constants'
import { RISK_STATIONS } from '../layoutConfig'

type Props = {
  title: string
  /** 標題旁的小字（期間、資料來源） */
  caption?: string
  stations: (StationRef & { counts: StationLevelCounts })[] | null
  /** 圖下方的補充說明（例：未對應站別的筆數） */
  note?: string
  emptyText?: string
  /** 總數的單位，例：筆、個 KPOV */
  unit?: string
}

// 與象限圖同色；柱子再加深色描邊，淺色底上才看得清楚
const LEVELS: number[] = [0, 1, 2, 3]
const STROKES: Record<number, string> = { 0: '#34A86A', 1: '#4A9FD8', 2: '#C9B930', 3: '#D27FD2' }

// 站別名稱優先用 layout 上的顯示名稱（與站別風險地圖一致），去掉「（人工三）」這類括號補註
const DISPLAY_NAMES = Object.fromEntries(
  RISK_STATIONS.map((s) => [s.equipmentCode, s.displayName.replace(/（[^）]*）$/, '').trim()]),
)
const TICK_CHARS = 5
const STATION_WIDTH = 72

/** X 軸站名分行：先在「/」斷開，每行最多 5 字，避免相鄰站名重疊 */
function tickLines(name: string): string[] {
  return name
    .split('/')
    .map((p, i, all) => (i < all.length - 1 ? `${p.trim()}/` : p.trim()))
    .flatMap((p) => Array.from({ length: Math.ceil(p.length / TICK_CHARS) }, (_, i) => p.slice(i * TICK_CHARS, (i + 1) * TICK_CHARS)))
}

function StationTick({ x, y, payload }: { x?: number; y?: number; payload?: { value: string } }) {
  const parts = tickLines(payload?.value ?? '')
  return (
    <text x={x} y={y} textAnchor="middle" fontSize={11} fill="#334155">
      {parts.map((p, i) => (
        <tspan key={i} x={x} dy={i === 0 ? 10 : 14}>
          {p}
        </tspan>
      ))}
    </text>
  )
}

/** 站別 × Level 柱狀圖：每站四根柱子（Level 0～3），顏色對應四象限。 */
export function StationLevelChart({ title, caption, stations, note, emptyText = '沒有資料', unit = '筆' }: Props) {
  const rows = (stations ?? []).map((s) => ({
    name: DISPLAY_NAMES[s.equipmentCode] ?? s.station,
    ...Object.fromEntries(LEVELS.map((l) => [`L${l}`, s.counts[String(l)] ?? 0])),
  }))
  const total = (stations ?? []).reduce((sum, s) => sum + LEVELS.reduce((n, l) => n + (s.counts[String(l)] ?? 0), 0), 0)

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="text-base font-semibold text-slate-800">{title}</h3>
        {caption && <span className="text-sm text-slate-500">{caption}</span>}
        {stations && <span className="text-xs text-slate-400">共 {total} {unit}</span>}
      </div>
      {!stations ? (
        <p className="py-8 text-center text-sm text-slate-400">載入中…</p>
      ) : rows.length === 0 || total === 0 ? (
        <p className="py-8 text-center text-sm text-slate-400">{emptyText}</p>
      ) : (
        // 十幾站 × 4 根柱子在窄欄位會擠在一起：給最小寬度，不夠時在框內左右捲動
        <div className="overflow-x-auto">
          <div style={{ minWidth: Math.max(rows.length * STATION_WIDTH, 480) }} className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={rows} margin={{ top: 20, right: 8, bottom: 8, left: -16 }} barCategoryGap="18%">
                <CartesianGrid vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="name" interval={0} tick={<StationTick />} height={58} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#64748b' }} />
                {/* 柱色是淺色底，文字一律改深色才讀得到 */}
                <Tooltip cursor={{ fill: '#f1f5f9' }} itemStyle={{ color: '#1e293b' }} />
                <Legend
                  wrapperStyle={{ fontSize: 12 }}
                  formatter={(value: string) => <span className="text-slate-700">{value}</span>}
                />
                {LEVELS.map((l) => (
                  <Bar
                    key={l}
                    dataKey={`L${l}`}
                    name={`Level ${l}`}
                    fill={LEVEL_COLORS[l]}
                    stroke={STROKES[l]}
                    isAnimationActive={false}
                  >
                    <LabelList
                      dataKey={`L${l}`}
                      position="top"
                      fontSize={11}
                      fill="#334155"
                      formatter={(v: unknown) => (v ? String(v) : '')}
                    />
                  </Bar>
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
      {note && <p className="mt-1 text-xs text-amber-700">{note}</p>}
    </div>
  )
}
