import type { Due, DueKey, DueStats, FilteredPaged, ListFilter } from '../api/client'
import { MultiSelect } from './MultiSelect'

export const EMPTY_FILTER: ListFilter = {
  occurredFrom: '',
  occurredTo: '',
  groups: [],
  stations: [],
  kpovs: [],
  improvedFrom: '',
  improvedTo: '',
  due: '',
}

// 圓餅的四塊：未到期用藍、逾期依天數由淺到深的紅
const SLICES: { key: Exclude<DueKey, 'overdue' | 'ontime'>; label: string; color: string }[] = [
  { key: 'planned', label: '預計完成（未到期）', color: '#38bdf8' },
  { key: 'lt7', label: '逾期 7 天內', color: '#fca5a5' },
  { key: 'd7_14', label: '逾期 7–14 天', color: '#f87171' },
  { key: 'gt14', label: '逾期 14 天以上', color: '#b91c1c' },
]

export const DUE_LABELS: Record<DueKey, string> = {
  planned: '預計完成（未到期）',
  ontime: '已完成（準時）',
  overdue: '全部逾期',
  lt7: '逾期 7 天內',
  d7_14: '逾期 7–14 天',
  gt14: '逾期 14 天以上',
}

function arc(cx: number, cy: number, r: number, start: number, end: number) {
  const point = (a: number) => [cx + r * Math.sin(a), cy - r * Math.cos(a)]
  const [x1, y1] = point(start)
  const [x2, y2] = point(end)
  return `M ${x1} ${y1} A ${r} ${r} 0 ${end - start > Math.PI ? 1 : 0} 1 ${x2} ${y2}`
}

/**
 * 預計完成數與逾期數的圓餅（spec §17）：依目前篩選（不含完成期限）統計；點一塊或圖例即篩選清單，再點一次取消。
 * 已準時完成的不列入。
 */
export function DuePie({
  stats,
  selected,
  onSelect,
}: {
  stats: DueStats
  selected: DueKey | ''
  onSelect: (key: DueKey | '') => void
}) {
  const total = SLICES.reduce((sum, s) => sum + stats[s.key], 0)
  const toggle = (key: DueKey) => onSelect(selected === key ? '' : key)
  let angle = 0
  const R = 52
  const STROKE = 22

  return (
    <section className="flex flex-col gap-4 rounded-lg border border-slate-200 bg-white p-4 sm:flex-row sm:items-center">
      <svg viewBox="0 0 140 140" className="h-36 w-36 shrink-0" role="img" aria-label="預計完成與逾期圓餅圖">
        {total === 0 ? (
          <circle cx="70" cy="70" r={R} fill="none" stroke="#e2e8f0" strokeWidth={STROKE} />
        ) : (
          SLICES.filter((s) => stats[s.key] > 0).map((s) => {
            const sweep = (stats[s.key] / total) * Math.PI * 2
            const start = angle
            angle += sweep
            const dim = selected && selected !== s.key && !(selected === 'overdue' && s.key !== 'planned')
            const props = {
              fill: 'none',
              stroke: s.color,
              strokeWidth: STROKE,
              opacity: dim ? 0.3 : 1,
              className: 'cursor-pointer',
              onClick: () => toggle(s.key),
            }
            // 只有一塊時 arc 起訖重疊畫不出來，改畫整圈
            return sweep >= Math.PI * 2 - 1e-6 ? (
              <circle key={s.key} cx="70" cy="70" r={R} {...props}>
                <title>{`${s.label}：${stats[s.key]}`}</title>
              </circle>
            ) : (
              <path key={s.key} d={arc(70, 70, R, start, angle)} {...props}>
                <title>{`${s.label}：${stats[s.key]}`}</title>
              </path>
            )
          })
        )}
        <text x="70" y="66" textAnchor="middle" className="fill-red-700 text-[22px] font-semibold tabular-nums">
          {stats.overdue}
        </text>
        <text x="70" y="86" textAnchor="middle" className="fill-slate-500 text-[11px]">
          逾期
        </text>
      </svg>

      <div className="min-w-0 flex-1 space-y-2">
        <div className="flex flex-wrap gap-2 text-sm">
          <button
            type="button"
            onClick={() => toggle('planned')}
            className={`rounded-md border px-3 py-1.5 ${selected === 'planned' ? 'border-sky-500 bg-sky-50' : 'border-slate-200 hover:bg-slate-50'}`}
          >
            預計完成 <b className="tabular-nums text-sky-700">{stats.planned}</b>
          </button>
          <button
            type="button"
            onClick={() => toggle('overdue')}
            className={`rounded-md border px-3 py-1.5 ${selected === 'overdue' ? 'border-red-500 bg-red-50' : 'border-slate-200 hover:bg-slate-50'}`}
          >
            逾期 <b className="tabular-nums text-red-700">{stats.overdue}</b>
          </button>
        </div>
        <ul className="grid gap-1 text-sm sm:grid-cols-2">
          {SLICES.map((s) => (
            <li key={s.key}>
              <button
                type="button"
                onClick={() => toggle(s.key)}
                className={`flex w-full items-center gap-2 rounded px-2 py-1 text-left ${selected === s.key ? 'bg-slate-100 font-medium' : 'hover:bg-slate-50'}`}
              >
                <span className="h-3 w-3 shrink-0 rounded-sm" style={{ backgroundColor: s.color }} />
                <span className="flex-1">{s.label}</span>
                <span className="tabular-nums">{stats[s.key]}</span>
              </button>
            </li>
          ))}
        </ul>
        <p className="text-xs text-slate-400">
          依 8D 預計完成 vs 實際完成：實際晚於預計，或未完成且預計已過，即為逾期；已準時完成的不列入圓餅。點選可篩選下方清單。
        </p>
      </div>
    </section>
  )
}

function DateRange({
  label,
  from,
  to,
  onChange,
}: {
  label: string
  from: string
  to: string
  onChange: (from: string, to: string) => void
}) {
  const input = 'w-[9.5rem] rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm'
  return (
    <div>
      <span className="mb-1 block text-xs font-medium text-slate-500">{label}</span>
      <div className="flex items-center gap-1">
        <input type="date" value={from} max={to || undefined} onChange={(e) => onChange(e.target.value, to)} aria-label={`${label}起`} className={input} />
        <span className="text-slate-400">～</span>
        <input type="date" value={to} min={from || undefined} onChange={(e) => onChange(from, e.target.value)} aria-label={`${label}迄`} className={input} />
      </div>
    </div>
  )
}

/** 清單篩選列：發生時間、機種（客訴為客戶）、站別、KPOV、改善時間、完成期限 */
export function ListFilterBar({
  value,
  onChange,
  options,
  occurredLabel,
  groupLabel,
}: {
  value: ListFilter
  onChange: (next: ListFilter) => void
  options: FilteredPaged<unknown>['options'] | undefined
  occurredLabel: string
  groupLabel: string
}) {
  const set = (patch: Partial<ListFilter>) => onChange({ ...value, ...patch })
  const dirty = JSON.stringify(value) !== JSON.stringify(EMPTY_FILTER)
  return (
    <section className="flex flex-wrap items-end gap-4 rounded-lg border border-slate-200 bg-white p-4">
      <DateRange label={occurredLabel} from={value.occurredFrom} to={value.occurredTo} onChange={(f, t) => set({ occurredFrom: f, occurredTo: t })} />
      <div className="w-44">
        <MultiSelect
          label={groupLabel}
          options={(options?.groups ?? []).map((g) => ({ value: g, label: g }))}
          selected={value.groups}
          onChange={(groups) => set({ groups })}
        />
      </div>
      <div className="w-44">
        <MultiSelect
          label="站別"
          options={(options?.stations ?? []).map((s) => ({ value: s, label: s }))}
          selected={value.stations}
          onChange={(stations) => set({ stations })}
        />
      </div>
      <div className="w-52">
        <MultiSelect
          label="KPOV"
          options={(options?.kpovs ?? []).map((k) => ({ value: k.value, label: k.label, hint: k.value }))}
          selected={value.kpovs}
          onChange={(kpovs) => set({ kpovs })}
        />
      </div>
      <DateRange label="改善時間" from={value.improvedFrom} to={value.improvedTo} onChange={(f, t) => set({ improvedFrom: f, improvedTo: t })} />
      <label>
        <span className="mb-1 block text-xs font-medium text-slate-500">完成期限</span>
        <select
          value={value.due}
          onChange={(e) => set({ due: e.target.value as DueKey | '' })}
          className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm"
        >
          <option value="">全部</option>
          {(Object.keys(DUE_LABELS) as DueKey[]).map((k) => (
            <option key={k} value={k}>
              {DUE_LABELS[k]}
            </option>
          ))}
        </select>
      </label>
      {dirty && (
        <button type="button" onClick={() => onChange(EMPTY_FILTER)} className="px-1 py-1.5 text-sm text-[#0086DB] hover:underline">
          清除篩選
        </button>
      )}
    </section>
  )
}

/**
 * 完成期限標記：逾期為紅色「逾期 N 天」；準時完成為綠色「已完成」；下方註明 8D 預計／實際完成。
 * 未到期（預計完成）不另加標記。
 */
export function DueBadge({ due }: { due: Due | null | undefined }) {
  if (!due) return null
  if (due.status === 'ontime') {
    return (
      <span className="mt-0.5 block" title={`8D 預計完成 ${due.plannedAt}・實際完成 ${due.doneAt}`}>
        <span className="block w-fit rounded bg-emerald-600 px-1 text-[10px] font-medium text-white">已完成</span>
        <span className="block text-[10px] text-emerald-700">實際 {due.doneAt}</span>
      </span>
    )
  }
  if (due.status !== 'overdue') return null
  return (
    <span className="mt-0.5 block" title={`8D 預計完成 ${due.plannedAt}・實際完成 ${due.doneAt ?? '未完成'}`}>
      <span className="block w-fit rounded bg-red-600 px-1 text-[10px] font-medium text-white">逾期 {due.overdueDays} 天</span>
      <span className="block text-[10px] text-red-600">
        預計 {due.plannedAt}
        {due.doneAt ? `・實際 ${due.doneAt}` : '・未完成'}
      </span>
    </span>
  )
}
