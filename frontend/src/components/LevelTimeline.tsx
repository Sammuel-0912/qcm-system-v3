import type { HistoryResponse } from '../api/client'
import { LEVEL_COLORS } from '../constants'

type Props = { data: HistoryResponse }

function Level({ level }: { level: number | null }) {
  if (level === null) return <span className="text-slate-400">未評估</span>
  return (
    <span
      className="inline-flex h-6 items-center rounded px-2 text-sm font-semibold text-slate-800 ring-1 ring-black/10"
      style={{ backgroundColor: LEVEL_COLORS[level] }}
    >
      Level {level}
    </span>
  )
}

function Axis({
  label,
  before,
  after,
}: {
  label: string
  before: { method: string | null; score: number | null }
  after: { method: string | null; score: number }
}) {
  const worsened = before.score !== null && after.score > before.score
  const improved = before.score !== null && after.score < before.score
  return (
    <div className="flex flex-wrap items-baseline gap-1.5 text-xs">
      <span className="w-8 shrink-0 font-medium text-slate-500">{label}</span>
      <span className="text-slate-400">
        {before.method ?? '基準'}
        {before.score !== null && ` (${before.score})`}
      </span>
      <span className="text-slate-400">→</span>
      <span
        className={
          worsened ? 'font-medium text-red-600' : improved ? 'font-medium text-emerald-600' : 'text-slate-700'
        }
      >
        {after.method} ({after.score})
      </span>
    </div>
  )
}

export function LevelTimeline({ data }: Props) {
  return (
    <div>
      <div className="mb-1 flex items-baseline gap-2">
        <h3 className="text-lg font-semibold text-slate-900">{data.kpovName}</h3>
        <span className="text-sm text-slate-500">{data.kpovNo}</span>
      </div>
      <p className="mb-4 text-sm text-slate-500">
        {data.station} · {data.equipmentCode}
      </p>

      <ol className="relative space-y-4 border-l-2 border-slate-200 pl-5">
        <li className="relative">
          <span className="absolute -left-[27px] top-1 h-3 w-3 rounded-full border-2 border-white bg-slate-400" />
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-slate-700">基準</span>
            <Level level={data.baseline.level} />
          </div>
          <p className="mt-1 text-xs text-slate-500">
            小y {data.baseline.smallY.score} · 大Y {data.baseline.bigY.score}（KPOV 庫原始評分）
          </p>
        </li>

        {data.events.map((event, idx) => {
          const isDegrade = event.type === 'DEGRADE'
          return (
            <li key={idx} className="relative">
              <span
                className={`absolute -left-[27px] top-1 h-3 w-3 rounded-full border-2 border-white ${
                  event.transition === 'ESCALATED'
                    ? 'bg-red-500'
                    : event.transition === 'IMPROVED'
                      ? 'bg-emerald-500'
                      : 'bg-slate-400'
                }`}
              />
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`rounded px-1.5 py-0.5 text-xs font-semibold ${
                    isDegrade ? 'bg-red-100 text-red-700' : 'bg-emerald-100 text-emerald-700'
                  }`}
                >
                  {isDegrade ? '不良發生' : '改善完成'}
                </span>
                <Level level={event.levelBefore} />
                <span className="text-slate-400">→</span>
                <Level level={event.levelAfter} />
                <span className="ml-auto text-xs tabular-nums text-slate-400">
                  {event.effectiveAt.slice(0, 10)}
                </span>
              </div>

              <div className="mt-2 space-y-1 rounded-md bg-slate-50 p-2">
                <Axis label="小y" before={event.smallYBefore} after={event.smallY} />
                <Axis label="大Y" before={event.bigYBefore} after={event.bigY} />
              </div>

              {isDegrade && event.defectDesc && (
                <p className="mt-1.5 text-xs text-slate-600">不良描述：{event.defectDesc}</p>
              )}
              {!isDegrade && event.improvement && (
                <p className="mt-1.5 text-xs text-slate-600">改善措施：{event.improvement}</p>
              )}
              {event.repairSerial && (
                <p className="mt-0.5 text-xs text-slate-400">維修序號 {event.repairSerial}</p>
              )}
            </li>
          )
        })}

        <li className="relative">
          <span className="absolute -left-[27px] top-1 h-3 w-3 rounded-full border-2 border-white bg-slate-900" />
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-slate-700">現況</span>
            <Level level={data.current.level} />
          </div>
        </li>
      </ol>
    </div>
  )
}
