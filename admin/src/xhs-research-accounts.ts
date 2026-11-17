import type { ResearchTask } from './xhs-research'

const bindingsKey = 'xhs-research-account-bindings-v1'
export const selectionKey = 'xhs-research-selected-account'

export function researchBindings(): Record<string, string> {
  const raw = localStorage.getItem(bindingsKey)
  if (!raw) return {}
  const value: unknown = JSON.parse(raw)
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.values(value).some(id => typeof id !== 'string' || !id)) {
    throw new Error('本机任务账号记录无法读取，已停止采集，避免使用错误账号。')
  }
  return value as Record<string, string>
}

export function bindResearchAccounts(tasks: Pick<ResearchTask, 'id'>[], accountId: string) {
  if (!accountId) throw new Error('请先选择采集账号。')
  const bindings = researchBindings()
  for (const task of tasks) {
    if (bindings[task.id] && bindings[task.id] !== accountId) throw new Error('该任务已绑定其他账号，请使用原账号或创建新任务。')
    bindings[task.id] = accountId
  }
  // 保存成功后才启动任务，保证刷新和暂停后仍能找回原账号。
  localStorage.setItem(bindingsKey, JSON.stringify(bindings))
}

export function savedResearchSelection(): string {
  try { return localStorage.getItem(selectionKey) || '' } catch { return '' }
}
