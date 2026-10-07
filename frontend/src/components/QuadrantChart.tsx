import type { LevelCounts } from '../api/client'
import { LEVEL_COLORS, LEVEL_SEVERITY, LEVEL_TEXT } from '../constants'

// 版面座標直接取自 gemini-svg.svg，不得任意調整（spec.md REQ-UI-01）
const RECTS: Record<number, { x: number; y: number }> = {
  2: { x: 140, y: 100 }, // 左上：小y 低、大Y 高
  0: { x: 360, y: 100 }, // 右上：兩軸皆高
  3: { x: 140, y: 250 }, // 左下：兩軸皆低
  1: { x: 360, y: 250 }, // 右下：小y 高、大Y 低
}
const W = 220
const H = 150

const LABEL_POS: Record<number, { x: number; y: number }> = {
  2: { x: 140, y: 85 },
  0: { x: 520, y: 85 },
  3: { x: 140, y: 430 },
  1: { x: 520, y: 430 },
}

type Props = {
  scope: LevelCounts
  plant: LevelCounts
  baseline: LevelCounts
  filtered: boolean
  view: string
  onSelect: (level: number) => void
}

function countOf(counts: LevelCounts, level: number): number {
  return counts[`level${level}` as keyof LevelCounts] as number
}

export function QuadrantChart({ scope, plant, baseline, filtered, view, onSelect }: Props) {
  const rated = scope.total - scope.unrated

  return (
    <svg
      viewBox="0 0 700 550"
      className="w-full h-auto"
      style={{ fontFamily: "'PingFang TC','Microsoft JhengHei',sans-serif" }}
      role="img"
      aria-label="品控力象限圖"
    >
      <rect x="0" y="0" width="700" height="550" fill="#ffffff" />

      {[2, 0, 3, 1].map((level) => {
        const rect = RECTS[level]
        const count = countOf(scope, level)
        const plantCount = countOf(plant, level)
        const baseCount = countOf(baseline, level)
        const pct = rated > 0 ? Math.round((count / rated) * 1000) / 10 : 0
        const delta = view === 'baseline' ? 0 : count - baseCount
        const cx = rect.x + W / 2
        const text = LEVEL_TEXT[level]

        // 依 §2.6 嚴重度：Level 0 是唯一「良好」的格子，其餘皆代表有管控缺口。
        // 因此 Level 0 增加為綠、其他格子增加為紅（反之亦然）。
        const goodBucket = LEVEL_SEVERITY[level] === 0
        const badgeColor = delta === 0 ? '#666' : (delta > 0) === goodBucket ? '#2e7d32' : '#c62828'

        return (
          <g
            key={level}
            onClick={() => onSelect(level)}
            style={{ cursor: 'pointer' }}
            tabIndex={0}
            role="button"
            aria-label={`Level ${level}，${count} 項 KPOV`}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') onSelect(level)
            }}
          >
            <rect x={rect.x} y={rect.y} width={W} height={H} fill={LEVEL_COLORS[level]} />
            <rect
              x={rect.x}
              y={rect.y}
              width={W}
              height={H}
              fill="transparent"
              stroke="#00000022"
              strokeWidth="1"
            />

            <text x={cx} y={rect.y + 24} fontSize="11" fill="#333" textAnchor="middle">
              {text.smallY}
            </text>
            <text x={cx} y={rect.y + 40} fontSize="11" fill="#333" textAnchor="middle">
              {text.bigY}
            </text>

            <text
              x={cx}
              y={rect.y + 92}
              fontSize="40"
              fontWeight="bold"
              fill="#111"
              textAnchor="middle"
            >
              {count}
            </text>
            <text x={cx} y={rect.y + 113} fontSize="12" fill="#444" textAnchor="middle">
              {pct}%
            </text>

            {filtered && (
              <text x={cx} y={rect.y + 133} fontSize="10" fill="#8a8a8a" textAnchor="middle">
                全廠 {plantCount}
              </text>
            )}

            {delta !== 0 && (
              <text
                x={rect.x + W - 10}
                y={rect.y + 18}
                fontSize="12"
                fontWeight="bold"
                fill={badgeColor}
                textAnchor="end"
              >
                {delta > 0 ? `▲+${delta}` : `▼${delta}`}
              </text>
            )}
          </g>
        )
      })}

      {[2, 0, 3, 1].map((level) => (
        <text
          key={`label-${level}`}
          x={LABEL_POS[level].x}
          y={LABEL_POS[level].y}
          fontSize="18"
          fontWeight="bold"
          fill="#222"
        >
          Level {level}
        </text>
      ))}

      {/* 縱軸：大Y 偵測度 */}
      <line x1="360" y1="410" x2="360" y2="70" stroke="#333" strokeWidth="2" />
      <polygon points="360,60 354,72 366,72" fill="#333" />
      <text x="335" y="75" fontSize="18" fontWeight="bold" fill="#333">
        Y
      </text>
      <text x="370" y="90" fontSize="18" fontWeight="bold" fill="#333">
        高
      </text>
      <text x="350" y="440" fontSize="18" fontWeight="bold" fill="#333">
        低
      </text>
      <text x="300" y="465" fontSize="15" fill="#444">
        依偵測度評分
      </text>

      {/* 橫軸：小y 偵測度 */}
      <line x1="120" y1="250" x2="620" y2="250" stroke="#333" strokeWidth="2" />
      <polygon points="630,250 618,244 618,256" fill="#333" />
      <text x="105" y="245" fontSize="18" fontWeight="bold" fill="#333">
        低
      </text>
      <text x="615" y="225" fontSize="18" fontWeight="bold" fill="#333">
        y
      </text>
      <text x="615" y="280" fontSize="18" fontWeight="bold" fill="#333">
        高
      </text>

      {/* 刻度：切點在 5 / 6 之間（spec.md §2.1） */}
      <text x="343" y="118" fontSize="14" fontWeight="bold" fill="#333">
        1
      </text>
      <text x="160" y="243" fontSize="14" fontWeight="bold" fill="#333">
        10
      </text>
      <text x="336" y="243" fontSize="14" fontWeight="bold" fill="#333">
        6
      </text>
      <text x="368" y="243" fontSize="14" fontWeight="bold" fill="#333">
        5
      </text>
      <text x="560" y="243" fontSize="14" fontWeight="bold" fill="#333">
        1
      </text>
      <text x="336" y="388" fontSize="14" fontWeight="bold" fill="#333">
        10
      </text>
    </svg>
  )
}
