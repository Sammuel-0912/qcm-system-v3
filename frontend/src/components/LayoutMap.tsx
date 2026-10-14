import { HOTSPOTS, LAYOUT_ASPECT, LAYOUT_IMAGE, type Hotspot } from '../layoutConfig'
import { LEVEL_COLORS } from '../constants'

type Props = {
  selected: string | null
  onSelect: (targetId: string | null) => void
  /** targetId -> 該站最嚴重等級，用來替熱區上色 */
  worstLevels?: Record<string, number | null>
  showGuesses?: boolean
}

function hotspotFill(hotspot: Hotspot, selected: boolean, level: number | null | undefined) {
  if (selected) return 'rgba(15,23,42,0.18)'
  if (level !== null && level !== undefined) return `${LEVEL_COLORS[level]}99`
  return hotspot.kind === 'CTP' ? 'rgba(56,153,236,0.14)' : 'rgba(120,120,120,0.14)'
}

export function LayoutMap({ selected, onSelect, worstLevels = {}, showGuesses = true }: Props) {
  const aspect = (LAYOUT_ASPECT.height / LAYOUT_ASPECT.width) * 100
  // 全部定位完成後，「待確認」的圖例與註腳就沒有意義，自動隱藏

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <h2 className="text-base font-semibold text-slate-800">PM1 整線 Layout</h2>
        <span className="text-sm text-slate-500">點站點查看下方趨勢與現狀</span>
        {selected && (
          <button
            onClick={() => onSelect(null)}
            className="ml-auto rounded-md border border-slate-300 px-2.5 py-1 text-sm text-slate-600 hover:bg-slate-50"
          >
            取消選取
          </button>
        )}
      </div>

      <div
        className="relative w-full overflow-hidden rounded-md border border-slate-200 bg-white"
        style={{ paddingBottom: `${aspect}%` }}
      >
        <img
          src={LAYOUT_IMAGE}
          alt="PM1 整線設備 layout"
          className="absolute inset-0 h-full w-full object-contain"
          draggable={false}
        />

        <svg
          viewBox={`0 0 ${LAYOUT_ASPECT.width} ${LAYOUT_ASPECT.height}`}
          className="absolute inset-0 h-full w-full"
          preserveAspectRatio="xMidYMid meet"
        >
          {HOTSPOTS.map((hotspot, index) => {
            const isSelected = selected === hotspot.targetId
            const x = (hotspot.rect.x / 100) * LAYOUT_ASPECT.width
            const y = (hotspot.rect.y / 100) * LAYOUT_ASPECT.height
            const w = (hotspot.rect.w / 100) * LAYOUT_ASPECT.width
            const h = (hotspot.rect.h / 100) * LAYOUT_ASPECT.height
            const level = worstLevels[hotspot.targetId]

            return (
              <g
                key={hotspot.targetId}
                onClick={() => onSelect(isSelected ? null : hotspot.targetId)}
                style={{ cursor: 'pointer' }}
                role="button"
                tabIndex={0}
                aria-label={`${hotspot.displayName}（${hotspot.kind}）`}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') onSelect(isSelected ? null : hotspot.targetId)
                }}
              >
                <rect
                  x={x}
                  y={y}
                  width={w}
                  height={h}
                  rx={3}
                  fill={hotspotFill(hotspot, isSelected, level)}
                  stroke={isSelected ? '#0f172a' : hotspot.kind === 'CTP' ? '#2b8fd6' : '#8a8a8a'}
                  strokeWidth={isSelected ? 3 : 1.5}
                  strokeDasharray={showGuesses && hotspot.confidence === 'guess' ? '4 3' : undefined}
                />
                {/* 編號徽章：方便現場指認「第 N 個熱區位置要改」 */}
                <circle cx={x + 7} cy={y + 7} r={6.5} fill="#0f172a" opacity={isSelected ? 1 : 0.75} />
                <text
                  x={x + 7}
                  y={y + 9.5}
                  fontSize="8"
                  fontWeight="bold"
                  fill="#ffffff"
                  textAnchor="middle"
                >
                  {index + 1}
                </text>
                <title>
                  {index + 1}. {hotspot.displayName}
                  {hotspot.kpovStation !== hotspot.displayName ? `（KPOV 庫：${hotspot.kpovStation}）` : ''}
                  {hotspot.confidence === 'guess' ? ' — 位置待確認' : ''}
                </title>
              </g>
            )
          })}
        </svg>
      </div>

    </div>
  )
}
