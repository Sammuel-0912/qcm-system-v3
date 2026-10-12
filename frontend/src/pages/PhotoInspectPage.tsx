import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { api, type CheckMonitorRow, type CheckShift, type SlotState } from '../api/client'
import { AppShell } from '../components/AppShell'
import { PhotoCheckButton } from '../components/PhotoCheckButton'

const SLOT_CLASS: Record<SlotState, string> = {
  ok: 'bg-emerald-500',
  warn: 'bg-red-500',
  missed: 'bg-red-100 ring-1 ring-inset ring-red-300',
  current: 'bg-white ring-2 ring-inset ring-amber-400',
  upcoming: 'bg-slate-100',
}

function hhmm(value: string | null) {
  if (!value) return '—'
  const d = new Date(value)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/**
 * 拍照點檢：產線不便貼二維碼，改為選站別後逐項拍照上傳，上傳成功即算點檢。
 * 版面以手機直式為主。站別存在網址（?station=），可做成書籤直接開。
 */
export default function PhotoInspectPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const station = searchParams.get('station') ?? ''
  const [stations, setStations] = useState<string[]>([])
  const [items, setItems] = useState<CheckMonitorRow[]>([])
  const [shift, setShift] = useState<CheckShift | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const body = await api.checkItems(station || undefined)
      setStations(body.stations)
      setItems(body.items)
      setShift(body.shift)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入失敗')
    }
  }, [station])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <AppShell title="拍照點檢">
      <main className="mx-auto max-w-lg space-y-4 px-4 py-5">
        <div>
          <label htmlFor="station" className="mb-1 block text-sm font-medium text-slate-700">
            站別
          </label>
          <select
            id="station"
            value={station}
            onChange={(e) => setSearchParams(e.target.value ? { station: e.target.value } : {})}
            className="w-full rounded-md border border-slate-300 bg-white px-3 py-2.5 text-base"
          >
            <option value="">請選擇站別</option>
            {stations.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          {shift && (
            <p className="mt-1.5 text-xs text-slate-500">
              {shift.label}
              {shift.ended && '（已結束）'}・每 2 小時拍照點檢一次，上傳成功即算完成
            </p>
          )}
        </div>

        {error && (
          <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
        )}

        {station && items.length === 0 && !error && (
          <p className="py-8 text-center text-sm text-slate-400">此站別沒有高風險點檢項目</p>
        )}

        <ul className="space-y-3">
          {items.map((item) => (
            <li key={item.id} className="rounded-lg border border-slate-200 bg-white p-4">
              <p className="text-base text-slate-900">{item.checkContent}</p>
              <p className="mt-0.5 text-xs text-slate-500">
                {item.kpovName} <span className="font-mono">{item.kpovNo}</span> ・{' '}
                {item.frequency ?? `${item.intervalHours}h/次`}
              </p>

              <div className="mt-3 flex items-center gap-2">
                <div className="flex gap-0.5" role="img" aria-label={`本班完成 ${item.progress}%`}>
                  {item.slots.map((slot) => (
                    <span key={slot.start} className={`h-3.5 w-6 rounded-sm ${SLOT_CLASS[slot.state]}`} />
                  ))}
                </div>
                <span className="text-sm font-semibold tabular-nums text-slate-800">{item.progress}%</span>
                <span className="ml-auto text-xs text-slate-500">
                  上次 {hhmm(item.lastInspectedAt)}
                  {item.lastPhotoUrl && (
                    <>
                      {' '}
                      <a href={item.lastPhotoUrl} target="_blank" rel="noreferrer" className="underline">
                        看照片
                      </a>
                    </>
                  )}
                </span>
              </div>

              <div className="mt-3 border-t border-slate-100 pt-3">
                <PhotoCheckButton item={item} onUploaded={() => void load()} />
              </div>
            </li>
          ))}
        </ul>
      </main>
    </AppShell>
  )
}
