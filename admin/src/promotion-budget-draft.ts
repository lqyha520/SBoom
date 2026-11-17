export interface MonthlyBudgetDraft { value: string; saved: string; revision: number }
const key = (actor: number, owner: string) => `lc-promotion-budget-v1:${actor}:${owner}`

/** 当前标签页内按登录账号和预算所属管理员隔离，不保存收款信息。 */
export function readBudgetDraft(actor: number, owner: string): MonthlyBudgetDraft | null {
  const raw = sessionStorage.getItem(key(actor, owner))
  if (!raw) return null
  try {
    const draft = JSON.parse(raw)
    if (draft?.version !== 1 || typeof draft.value !== 'string' || typeof draft.saved !== 'string'
      || draft.value.length > 80 || draft.saved.length > 80 || !Number.isSafeInteger(draft.revision)
      || draft.revision < 0 || draft.value === draft.saved) return null
    return { value: draft.value, saved: draft.saved, revision: draft.revision }
  } catch { return null }
}

export function storeBudgetDraft(actor: number, owner: string, draft?: MonthlyBudgetDraft) {
  if (!draft || draft.value === draft.saved) sessionStorage.removeItem(key(actor, owner))
  else sessionStorage.setItem(key(actor, owner), JSON.stringify({ version: 1, value: draft.value, saved: draft.saved, revision: draft.revision }))
}
