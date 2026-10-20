/** KPIV(x) 管控等級標籤：「A: 防呆防錯+智能」→ 字母上色＋說明；A 為最佳（綠），其餘依序轉暖色 */
const TONES: Record<string, string> = {
  A: 'bg-emerald-100 text-emerald-800 ring-emerald-200',
  B: 'bg-sky-100 text-sky-800 ring-sky-200',
  C: 'bg-amber-100 text-amber-800 ring-amber-200',
  D: 'bg-orange-100 text-orange-800 ring-orange-200',
  E: 'bg-rose-100 text-rose-800 ring-rose-200',
}

export function KpivLevelBadge({ value }: { value: string }) {
  const match = value.match(/^\s*([A-Z])\s*[:：]\s*(.*)$/)
  const grade = match?.[1] ?? null
  const desc = match ? match[2] : value
  return (
    <span
      title="KPIV(x) 管控等級"
      className={`mt-1 inline-flex w-fit items-center gap-1 rounded px-1.5 py-0.5 text-[11px] ring-1 ring-inset ${
        (grade && TONES[grade]) || 'bg-slate-100 text-slate-700 ring-slate-200'
      }`}
    >
      {grade && <span className="font-bold">{grade}</span>}
      <span>{desc}</span>
    </span>
  )
}
