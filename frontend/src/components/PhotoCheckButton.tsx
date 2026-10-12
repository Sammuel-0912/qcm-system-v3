import { useRef, useState } from 'react'

import { api, type CheckMonitorRow } from '../api/client'

type Props = {
  item: Pick<CheckMonitorRow, 'equipmentCode' | 'kpovNo' | 'checkContent'>
  onUploaded: () => void
  /** compact：表格內的小按鈕；預設為手機頁的大按鈕＋異常勾選 */
  compact?: boolean
}

const MAX_EDGE = 1600

/** 手機原圖常有 3–8 MB，縮到長邊 1600px 再上傳；失敗就傳原檔 */
async function shrink(file: File): Promise<File> {
  if (!file.type.startsWith('image/')) return file
  try {
    const bitmap = await createImageBitmap(file)
    const scale = Math.min(1, MAX_EDGE / Math.max(bitmap.width, bitmap.height))
    if (scale === 1 && file.size < 1.5 * 1024 * 1024) return file
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(bitmap.width * scale)
    canvas.height = Math.round(bitmap.height * scale)
    canvas.getContext('2d')?.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.85))
    return blob ? new File([blob], 'check.jpg', { type: 'image/jpeg' }) : file
  } catch {
    return file
  }
}

/** 拍照點檢：選／拍一張照片，上傳成功即記一次點檢（預設正常，可回報異常） */
export function PhotoCheckButton({ item, onUploaded, compact = false }: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [abnormal, setAbnormal] = useState(false)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  // 表格版沒有勾選框，按「異常」時才帶入異常狀態
  const pending = useRef<{ status: 'ok' | 'warn'; note?: string }>({ status: 'ok' })

  function pick(status: 'ok' | 'warn', withNote?: string) {
    pending.current = { status, note: withNote }
    inputRef.current?.click()
  }

  async function upload(file: File) {
    setBusy(true)
    setMessage(null)
    try {
      await api.checkInspect({
        item,
        file: await shrink(file),
        status: pending.current.status,
        note: pending.current.note,
      })
      setMessage({ ok: true, text: pending.current.status === 'warn' ? '已上傳：異常' : '已上傳：正常' })
      setAbnormal(false)
      setNote('')
      onUploaded()
    } catch (err) {
      setMessage({ ok: false, text: err instanceof Error ? err.message : '上傳失敗，請再試一次' })
    } finally {
      setBusy(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  const input = (
    <input
      ref={inputRef}
      type="file"
      accept="image/*"
      capture="environment"
      className="hidden"
      onChange={(e) => {
        const file = e.target.files?.[0]
        if (file) void upload(file)
      }}
    />
  )

  if (compact) {
    return (
      <span className="inline-flex flex-col items-start gap-1">
        {input}
        <span className="inline-flex gap-1">
          <button
            type="button"
            disabled={busy}
            onClick={() => pick('ok')}
            className="rounded border border-slate-300 px-1.5 py-0.5 text-xs text-slate-700 hover:bg-slate-50 disabled:opacity-40"
            title="上傳照片，記為正常"
          >
            {busy ? '上傳中…' : '📷 拍照'}
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              const text = window.prompt('異常說明（可留空）')
              if (text !== null) pick('warn', text)
            }}
            className="rounded border border-red-200 px-1.5 py-0.5 text-xs text-red-700 hover:bg-red-50 disabled:opacity-40"
            title="上傳照片，記為異常"
          >
            異常
          </button>
        </span>
        {message && (
          <span className={`text-xs ${message.ok ? 'text-emerald-700' : 'text-red-700'}`}>{message.text}</span>
        )}
      </span>
    )
  }

  return (
    <div>
      {input}
      <label className="flex items-center gap-2 text-sm text-slate-700">
        <input
          type="checkbox"
          checked={abnormal}
          onChange={(e) => setAbnormal(e.target.checked)}
          className="h-4 w-4 accent-red-600"
        />
        回報異常
      </label>
      {abnormal && (
        <input
          type="text"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="異常說明（可留空）"
          className="mt-2 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
      )}
      <button
        type="button"
        disabled={busy}
        onClick={() => pick(abnormal ? 'warn' : 'ok', abnormal ? note : undefined)}
        className={`mt-2 w-full rounded-md py-3 text-sm font-semibold text-white transition disabled:opacity-40 ${
          abnormal ? 'bg-red-600 hover:bg-red-700' : 'bg-slate-900 hover:bg-slate-700'
        }`}
      >
        {busy ? '上傳中…' : abnormal ? '📷 拍照上傳（異常）' : '📷 拍照上傳'}
      </button>
      {message && (
        <p className={`mt-2 text-sm ${message.ok ? 'text-emerald-700' : 'text-red-700'}`}>{message.text}</p>
      )}
    </div>
  )
}
