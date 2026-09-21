import { useEffect, useRef, useState } from 'react'

type Option = { value: string; label: string; hint?: string }

type Props = {
  label: string
  options: Option[]
  selected: string[]
  onChange: (next: string[]) => void
  allLabel?: string
}

export function MultiSelect({ label, options, selected, onChange, allLabel = '全部' }: Props) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onClickOutside(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  const summary =
    selected.length === 0
      ? allLabel
      : selected.length === 1
        ? (options.find((o) => o.value === selected[0])?.label ?? selected[0])
        : `已選 ${selected.length} 項`

  function toggle(value: string) {
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value])
  }

  return (
    <div className="relative" ref={ref}>
      <label className="mb-1 block text-xs font-medium text-slate-500">{label}</label>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex min-w-[180px] items-center justify-between gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 transition hover:border-slate-400"
        aria-expanded={open}
      >
        <span className={selected.length === 0 ? 'text-slate-400' : ''}>{summary}</span>
        <span className="text-slate-400">▾</span>
      </button>

      {open && (
        <div className="absolute z-20 mt-1 max-h-72 w-full min-w-[220px] overflow-y-auto rounded-md border border-slate-200 bg-white p-1 shadow-lg">
          <button
            type="button"
            onClick={() => onChange([])}
            className="w-full rounded px-2 py-1.5 text-left text-sm text-slate-600 hover:bg-slate-100"
          >
            {allLabel}
          </button>
          <div className="my-1 border-t border-slate-100" />
          {options.map((option) => (
            <label
              key={option.value}
              className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-slate-100"
            >
              <input
                type="checkbox"
                checked={selected.includes(option.value)}
                onChange={() => toggle(option.value)}
                className="h-3.5 w-3.5 accent-slate-700"
              />
              <span className="flex-1 text-slate-800">{option.label}</span>
              {option.hint && <span className="text-xs text-slate-400">{option.hint}</span>}
            </label>
          ))}
        </div>
      )}
    </div>
  )
}
