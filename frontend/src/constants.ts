// 象限配色與語意 — spec.md §2.2 / §8.2，與 gemini-svg.svg 逐字相符。
// 這裡是前端唯一的色碼來源，其他元件不得自行寫死。

export const LEVEL_COLORS: Record<number, string> = {
  0: '#BFFFDA',
  1: '#C5E9FF',
  2: '#F3EA95',
  3: '#FFCCFF',
}

// spec.md §2.6 嚴重度排序：0 < 1 < 2 < 3
export const LEVEL_SEVERITY: Record<number, number> = { 0: 0, 1: 1, 2: 2, 3: 3 }

export const LEVEL_TEXT: Record<number, { smallY: string; bigY: string }> = {
  0: { smallY: 'y 100%機測', bigY: 'Y 100%機測' },
  1: { smallY: 'y 100%機測', bigY: 'Y 人檢/機測(未證實可靠)' },
  2: { smallY: 'y 人檢/機測(未證實可靠)', bigY: 'Y 100%機測' },
  3: { smallY: 'y 人檢/機測(未證實可靠)', bigY: 'Y 人檢/機測(未證實可靠)' },
}

export const VIEW_LABELS: Record<string, string> = {
  current: '現況',
  baseline: '基準',
  target: '目標',
}
