import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import {
  arApi,
  markerImageSrc,
  MAX_MARKER_ID,
  type ArDevice,
  type DeviceQuality,
  type EquipmentOption,
} from '../api/arClient'
import { AppShell } from '../components/AppShell'
import { LEVEL_COLORS } from '../constants'

type FormState = {
  markerId: string
  name: string
  description: string
  workInstruction: string
  equipmentCode: string
}

const EMPTY: FormState = { markerId: '', name: '', description: '', workInstruction: '', equipmentCode: '' }

/** 設備卡上的品控力狀態：兩個系統在這裡真正接上 */
function QualityBadge({ markerId }: { markerId: number }) {
  const [data, setData] = useState<DeviceQuality | null>(null)

  useEffect(() => {
    let alive = true
    arApi
      .deviceQuality(markerId)
      .then((d) => alive && setData(d))
      .catch(() => alive && setData(null))
    return () => {
      alive = false
    }
  }, [markerId])

  if (!data) return null

  if (!data.linked) {
    return <p className="mt-2 text-xs text-amber-700">{data.reason}</p>
  }

  return (
    <div className="mt-2 rounded-md bg-slate-50 p-2">
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <span className="text-slate-500">{data.station}</span>
        <span className="text-slate-400">·</span>
        <span className="text-slate-500">{data.kpovCount} 個 KPOV</span>
        {[0, 1, 2, 3].map((level) => {
          const n = data.levelCounts[String(level)] ?? 0
          if (!n) return null
          return (
            <span
              key={level}
              className="inline-flex h-4 items-center rounded px-1 text-[10px] font-semibold text-slate-800 ring-1 ring-black/10"
              style={{ backgroundColor: LEVEL_COLORS[level] }}
            >
              L{level} {n}
            </span>
          )
        })}
      </div>
      {data.escalatedOpen > 0 && (
        <p className="mt-1 text-xs font-medium text-red-700">
          {data.escalatedOpen} 項 KPOV 惡化中
        </p>
      )}
    </div>
  )
}

function DeviceModal({
  initial,
  options,
  onClose,
  onSaved,
}: {
  initial: ArDevice | null
  options: EquipmentOption[]
  onClose: () => void
  onSaved: () => void
}) {
  const isEdit = initial !== null
  const [form, setForm] = useState<FormState>(
    initial
      ? {
          markerId: String(initial.markerId),
          name: initial.name,
          description: initial.description ?? '',
          workInstruction: initial.workInstruction ?? '',
          equipmentCode: initial.equipmentCode ?? '',
        }
      : EMPTY,
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const set = (key: keyof FormState) => (value: string) => setForm((f) => ({ ...f, [key]: value }))

  async function save() {
    setError(null)
    const markerId = Number(form.markerId)
    if (!Number.isInteger(markerId) || markerId < 0 || markerId > MAX_MARKER_ID) {
      setError(`Marker ID 必須是 0 ~ ${MAX_MARKER_ID} 的整數（AR.js 3×3 barcode 的有效範圍）`)
      return
    }
    if (!form.name.trim()) {
      setError('請填寫設備名稱')
      return
    }
    setSaving(true)
    try {
      const payload = {
        name: form.name.trim(),
        description: form.description.trim() || null,
        workInstruction: form.workInstruction.trim() || null,
        equipmentCode: form.equipmentCode || null,
      }
      if (isEdit) await arApi.updateDevice(markerId, payload)
      else await arApi.createDevice({ markerId, ...payload, name: payload.name })
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : '儲存失敗')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-lg bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900">{isEdit ? '編輯設備' : '新增設備'}</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700" aria-label="關閉">
            ✕
          </button>
        </div>

        <div className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-500">
              Marker ID（0 ~ {MAX_MARKER_ID}）
            </span>
            <input
              type="number"
              min={0}
              max={MAX_MARKER_ID}
              value={form.markerId}
              disabled={isEdit}
              onChange={(e) => set('markerId')(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-100 disabled:text-slate-500"
              placeholder="例：5"
            />
            {isEdit && (
              <span className="mt-1 block text-xs text-slate-400">
                Marker ID 是主鍵，不可修改；要換號請刪除後重建
              </span>
            )}
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-500">設備名稱</span>
            <input
              value={form.name}
              onChange={(e) => set('name')(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              placeholder="例：鎖銅排1 日常點檢"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-500">設備描述</span>
            <input
              value={form.description}
              onChange={(e) => set('description')(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              placeholder="例：DCS-PM1 主線"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-500">
              對應品控力設備代碼
            </span>
            <select
              value={form.equipmentCode}
              onChange={(e) => set('equipmentCode')(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">不綁定</option>
              {options.map((o) => (
                <option key={o.equipmentCode} value={o.equipmentCode}>
                  {o.station}（{o.equipmentCode}）· {o.kpovCount} 個 KPOV
                </option>
              ))}
            </select>
            <span className="mt-1 block text-xs text-slate-400">
              綁定後，點檢時看得到這台機器的品控力等級
            </span>
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-500">作業指引</span>
            <textarea
              rows={5}
              value={form.workInstruction}
              onChange={(e) => set('workInstruction')(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              placeholder={'1. 確認螺絲無浮鎖\n2. 檢查銅排無變形\n3. 確認鎖付扭力值正常'}
            />
          </label>

          {error && (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              onClick={onClose}
              className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
            >
              取消
            </button>
            <button
              onClick={() => void save()}
              disabled={saving}
              className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
            >
              {saving ? '儲存中…' : '儲存'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function ArDevicesPage() {
  const [devices, setDevices] = useState<ArDevice[]>([])
  const [options, setOptions] = useState<EquipmentOption[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [modal, setModal] = useState<{ device: ArDevice | null } | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [d, o] = await Promise.all([arApi.devices(), arApi.equipmentOptions()])
      setDevices(d)
      setOptions(o.options)
    } catch (err) {
      setError(err instanceof Error ? err.message : '載入失敗')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  function flash(msg: string) {
    setNotice(msg)
    setTimeout(() => setNotice(null), 2500)
  }

  async function remove(device: ArDevice) {
    if (
      !window.confirm(
        `確定刪除 Marker ${device.markerId}「${device.name}」？\n該設備的所有點檢紀錄會一併刪除，無法復原。`,
      )
    )
      return
    try {
      await arApi.deleteDevice(device.markerId)
      flash(`已刪除 Marker ${device.markerId}`)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : '刪除失敗')
    }
  }

  async function upload(markerId: number, file: File) {
    try {
      await arApi.uploadImage(markerId, file)
      flash('圖片已上傳')
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : '上傳失敗')
    }
  }

  function downloadMarker(device: ArDevice) {
    const src = markerImageSrc(device.markerId)
    if (!src) return
    const link = document.createElement('a')
    link.download = `marker_${device.markerId}.png`
    link.href = src
    link.click()
  }

  const actions = (
    <>
      <button
        onClick={() => setModal({ device: null })}
        className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700"
      >
        新增設備
      </button>
      <Link
        to="/ar/dashboard"
        className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 transition hover:border-slate-400 hover:bg-slate-50"
      >
        儀表板
      </Link>
    </>
  )

  return (
    <AppShell title="AR 設備管理" actions={actions}>
      <main className="mx-auto max-w-7xl space-y-4 px-6 py-6">
        {error && (
          <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}
        {notice && (
          <div className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
            {notice}
          </div>
        )}

        {loading ? (
          <p className="py-10 text-center text-sm text-slate-500">載入中…</p>
        ) : devices.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-200 bg-white py-14 text-center">
            <p className="text-sm text-slate-500">尚未建立任何設備</p>
            <p className="mt-1 text-xs text-slate-400">
              每個設備對應一個 AR marker（0 ~ {MAX_MARKER_ID}），列印後貼在機台上供相機掃描
            </p>
            <button
              onClick={() => setModal({ device: null })}
              className="mt-5 rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
            >
              新增第一台設備
            </button>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {devices.map((device) => {
              const marker = markerImageSrc(device.markerId)
              return (
                <div
                  key={device.markerId}
                  className="flex flex-col rounded-lg border border-slate-200 bg-white p-4"
                >
                  <div className="flex items-start gap-3">
                    {marker ? (
                      <img
                        src={marker}
                        alt={`Marker ${device.markerId}`}
                        className="h-20 w-20 shrink-0 rounded border border-slate-200"
                        style={{ imageRendering: 'pixelated' }}
                      />
                    ) : (
                      <div className="flex h-20 w-20 shrink-0 items-center justify-center rounded border border-dashed border-red-300 text-center text-[10px] text-red-600">
                        超出 0~{MAX_MARKER_ID}
                      </div>
                    )}
                    <div className="min-w-0 flex-1">
                      <h3 className="truncate font-semibold text-slate-900">{device.name}</h3>
                      <p className="font-mono text-xs text-slate-400">Marker {device.markerId}</p>
                      {device.description && (
                        <p className="mt-1 truncate text-sm text-slate-600">{device.description}</p>
                      )}
                    </div>
                  </div>

                  <QualityBadge markerId={device.markerId} />

                  {device.imageUrl && (
                    <img
                      src={device.imageUrl}
                      alt="作業圖"
                      className="mt-3 max-h-40 w-full rounded border border-slate-200 object-contain"
                    />
                  )}

                  {device.workInstruction && (
                    <pre className="mt-3 whitespace-pre-wrap rounded bg-slate-50 p-2 text-xs leading-relaxed text-slate-700">
                      {device.workInstruction}
                    </pre>
                  )}

                  <div className="mt-3 flex flex-wrap gap-1.5 border-t border-slate-100 pt-3">
                    <button
                      onClick={() => setModal({ device })}
                      className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50"
                    >
                      編輯
                    </button>
                    <button
                      onClick={() => downloadMarker(device)}
                      disabled={!marker}
                      className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                    >
                      下載 Marker
                    </button>
                    <label className="cursor-pointer rounded border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-50">
                      上傳圖片
                      <input
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={(e) => {
                          const file = e.target.files?.[0]
                          if (file) void upload(device.markerId, file)
                          e.target.value = ''
                        }}
                      />
                    </label>
                    <button
                      onClick={() => void remove(device)}
                      className="ml-auto rounded px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                    >
                      刪除
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </main>

      {modal && (
        <DeviceModal
          initial={modal.device}
          options={options}
          onClose={() => setModal(null)}
          onSaved={() => {
            setModal(null)
            flash('已儲存')
            void load()
          }}
        />
      )}
    </AppShell>
  )
}
