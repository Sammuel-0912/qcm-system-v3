import type { ChangeKind, ChangeWindow, LevelChangeItem, LevelChangesResponse } from '../api/client'
import { MeasureTable } from './MeasureTable'

type Props = {
  data: LevelChangesResponse | null
  /** 期間由上方篩選列的天／週／月／年決定，這裡只顯示說明 */
  window: ChangeWindow
  kind: ChangeKind
  onKindChange: (kind: ChangeKind) => void
  onPageChange: (page: number) => void
  /** 點列開明細側欄（8D 明細／等級歷程） */
  onOpen: (row: LevelChangeItem) => void
}

const WINDOW_HINT: Record<ChangeWindow, string> = {
  day: '近 1 天',
  week: '近 7 天',
  month: '近 30 天',
  year: '近 365 天',
}

export function DeviationPanel({ data, window, kind, onKindChange, onPageChange, onOpen }: Props) {
  const windowHint = WINDOW_HINT[window]
  const cards: { value: ChangeKind; label: string; tone: string; active: string }[] = [
    {
      value: 'escalated',
      label: '高風險',
      tone: 'border-red-200 bg-red-50 text-red-700',
      active: 'ring-2 ring-red-500',
    },
    {
      value: 'improved',
      label: '已改善',
      tone: 'border-emerald-200 bg-emerald-50 text-emerald-700',
      active: 'ring-2 ring-emerald-500',
    },
  ]

  return (
    <div className="flex h-full flex-col">
      <div className="mb-3 flex flex-wrap items-baseline gap-2">
        <h2 className="text-base font-semibold text-slate-800">等級異動總覽</h2>
        <span className="text-sm text-slate-500">{windowHint}</span>
      </div>

      <div className="mb-3 grid grid-cols-2 gap-3">
        {cards.map((card) => (
          <button
            key={card.value}
            type="button"
            aria-pressed={kind === card.value}
            onClick={() => onKindChange(card.value)}
            className={`rounded-lg border p-3 text-left transition hover:brightness-95 ${card.tone} ${
              kind === card.value ? card.active : ''
            }`}
          >
            <div className="text-2xl font-bold">{data ? data.counts[card.value] : '—'}</div>
            <div className="text-xs underline underline-offset-2">
              {card.label}
              <span className="ml-1 opacity-70">· {windowHint}</span>
            </div>
          </button>
        ))}
      </div>

      <div className="flex-1">
        <MeasureTable
          data={data}
          onPageChange={onPageChange}
          onOpen={onOpen}
          emptyText={`${windowHint}沒有${kind === 'escalated' ? '高風險' : '改善'}的項目。`}
        />
      </div>
    </div>
  )
}
