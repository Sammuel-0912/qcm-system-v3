import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { api, type ChangeWindow } from '../api/client'
import { RISK_STATIONS } from '../layoutConfig'

type Props = {
  /** 與等級異動總覽共用的期間（近 1／7／30／365 天） */
  window: ChangeWindow
  selected: string | null
  onSelect: (targetId: string | null) => void
  reloadKey?: number
}

const WINDOW_HINT: Record<ChangeWindow, string> = {
  day: '近 1 天',
  week: '近 7 天',
  month: '近 30 天',
  year: '近 365 天',
}

type Risk = Awaited<ReturnType<typeof api.stationRisk>>

/**
 * 站別風險地圖：每站一張卡片，期間內有維修或客訴＝紅，都沒有＝綠。
 * 點卡片等同點 Layout 熱區（下方趨勢與點檢表切到該站），再點取消。
 */
export function StationRiskMap({ window, selected, onSelect, reloadKey }: Props) {
  const [risk, setRisk] = useState<Risk | null>(null)

  useEffect(() => {
    api
      .stationRisk(window)
      .then(setRisk)
      .catch(() => setRisk(null))
  }, [window, reloadKey])

  const alerted = RISK_STATIONS.filter((s) => {
    const c = risk?.stations[s.equipmentCode]
    return c && (c.repairs > 0 || c.complaints > 0)
  }).length

  return (
    <div className="mt-5 border-t border-slate-100 pt-4">
      <div className="mb-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h3 className="text-base font-semibold text-slate-800">站別風險地圖</h3>
        <span className="text-sm text-slate-500">
          {WINDOW_HINT[window]}・{risk ? `${alerted} / ${RISK_STATIONS.length} 站有預警` : '載入中…'}
        </span>
        {risk && risk.unmappedComplaints > 0 && (
          <Link to="/complaints" className="text-xs text-amber-700 underline underline-offset-2">
            另有 {risk.unmappedComplaints} 筆客訴未對應站別
          </Link>
        )}
        <span className="ml-auto flex items-center gap-3 text-xs text-slate-500">
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-red-500" />有維修或客訴
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />無預警
          </span>
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {RISK_STATIONS.map((station) => {
          const counts = risk?.stations[station.equipmentCode] ?? { repairs: 0, complaints: 0 }
          const red = counts.repairs > 0 || counts.complaints > 0
          const active = selected === station.targetId
          return (
            <button
              key={station.targetId}
              type="button"
              onClick={() => onSelect(active ? null : station.targetId)}
              aria-pressed={active}
              className={`relative overflow-hidden rounded-lg border bg-white p-3 pt-4 text-left transition hover:shadow-md ${
                active ? 'border-slate-900 ring-2 ring-slate-900' : 'border-slate-200'
              }`}
            >
              <span className={`absolute inset-x-0 top-0 h-1 ${red ? 'bg-red-500' : 'bg-emerald-500'}`} />
              <span className="flex items-center justify-between gap-2">
                <span
                  className={`rounded px-1.5 text-[10px] font-semibold ${
                    station.kind === 'CTP' ? 'bg-sky-100 text-sky-800' : 'bg-slate-200 text-slate-700'
                  }`}
                >
                  {station.kind}
                </span>
                <span
                  className={`h-2.5 w-2.5 rounded-full ${red ? 'bg-red-500' : 'bg-emerald-500'}`}
                  aria-label={red ? '有預警' : '無預警'}
                />
              </span>
              <span className="mt-1.5 block text-sm font-semibold leading-snug text-slate-900">
                {station.displayName}
              </span>
              <span className="mt-2 flex flex-wrap gap-1">
                {counts.repairs > 0 && (
                  <span className="rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-medium text-red-700 ring-1 ring-inset ring-red-200">
                    維修 {counts.repairs}
                  </span>
                )}
                {counts.complaints > 0 && (
                  <span className="rounded-full bg-red-600 px-2 py-0.5 text-[11px] font-medium text-white">
                    客訴 {counts.complaints}
                  </span>
                )}
                {!red && (
                  <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 ring-1 ring-inset ring-emerald-200">
                    無預警
                  </span>
                )}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
