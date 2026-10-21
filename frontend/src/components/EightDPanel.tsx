import type { EightD, EightDSide } from '../api/client'
import { LevelChip } from './LevelChip'

type Line = [string, string | number | null | undefined]

function join(...parts: (string | number | null | undefined)[]) {
  const text = parts.filter((p) => p !== null && p !== undefined && p !== '').join('／')
  return text || null
}

function Block({ title, lines, children }: { title: string; lines?: Line[]; children?: React.ReactNode }) {
  return (
    <section className="rounded-md border border-slate-200 bg-white p-3">
      <h4 className="mb-2 text-xs font-semibold text-[#1F5C7A]">{title}</h4>
      {children}
      {lines && (
        <dl className="grid gap-x-4 gap-y-1.5 text-sm sm:grid-cols-2">
          {lines.map(([term, value]) => (
            <div key={term} className="min-w-0">
              <dt className="text-xs text-slate-400">{term}</dt>
              <dd className="whitespace-pre-wrap break-words text-slate-800">{value ?? '—'}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  )
}

function sideLines(side: EightDSide): Line[] {
  return [
    ['Y-CC/SC 檢測項目', side.bigY.item],
    ['Y 偵測方式／偵測度', join(side.bigY.method, side.bigY.score)],
    ['y 產品 KPOV', side.smallY.kpov],
    ['y 偵測方式／偵測度', join(side.smallY.method, side.smallY.score)],
    ['KPIV(x) 因子', side.kpiv.factor],
    ['防呆防錯', join(side.kpiv.foolproof, side.kpiv.foolproofDesc)],
    ['監控方式', join(side.kpiv.monitor, side.kpiv.monitorDesc)],
    ['x 管控等級', side.kpiv.level],
  ]
}

/** 8D：現狀盤查 → 原因 → 改善對策 → 改善後盤查（客訴與維修共用） */
export function EightDPanel({ data }: { data: EightD | null }) {
  if (!data) {
    return <p className="text-sm text-slate-400">這筆紀錄沒有 8D 內容。</p>
  }
  const tech = data.measures.tech
  return (
    <div className="space-y-3">
      <Block title="現狀盤查（品質管控力）" lines={[['製程單元', data.processUnit], ...sideLines(data.before)]}>
        <p className="mb-2 flex items-center gap-2 text-xs text-slate-500">
          品質管控力 <LevelChip level={data.before.level} />
        </p>
      </Block>
      <Block
        title="原因"
        lines={[
          ['發生原因', data.causes.occur],
          ['流出原因', data.causes.escape],
        ]}
      />
      <Block
        title="改善對策"
        lines={[
          ['管理解（流程卡控）', data.measures.mgmt],
          ['技術解・CC/SC 設備攔截', tech.ccscInterception],
          ['技術解・KPOV 設計消除', tech.kpovDesignElimination],
          ['技術解・KPOV 設備攔截', tech.kpovInterception],
          ['技術解・KPIV 防呆防錯', tech.kpivFoolproof],
          ['技術解・KPIV 智能監控', tech.kpivSmart],
          ['對策內容', data.measures.content],
          ['責任人', data.measures.owner],
          ['預計完成時間', data.measures.plannedText],
          ['實際完成時間', data.measures.doneText],
          ['對策有效性判定', data.measures.effectiveness],
        ]}
      />
      <Block title="改善後盤查" lines={[...sideLines(data.after), ['改善判定', data.verdict]]}>
        <p className="mb-2 flex items-center gap-2 text-xs text-slate-500">
          品質管控力 <LevelChip level={data.after.level} />
        </p>
      </Block>
    </div>
  )
}
