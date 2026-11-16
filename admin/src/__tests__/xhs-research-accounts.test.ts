import { beforeEach, expect, it } from 'vitest'
import { bindResearchAccounts, researchBindings } from '../xhs-research-accounts'

beforeEach(() => localStorage.clear())

it('队列的所有任务提前绑定账号，重开页面读取原账号并拒绝覆盖', () => {
  bindResearchAccounts([{ id: 'task-a' }, { id: 'task-b' }], 'account-a')
  expect(researchBindings()).toEqual({ 'task-a': 'account-a', 'task-b': 'account-a' })
  expect(() => bindResearchAccounts([{ id: 'task-b' }], 'account-b')).toThrow('已绑定其他账号')
  expect(researchBindings()['task-b']).toBe('account-a')
})

it('绑定记录损坏时保留原文并停止，不自动重建或换号', () => {
  localStorage.setItem('xhs-research-account-bindings-v1', '{broken')
  expect(() => bindResearchAccounts([{ id: 'task-a' }], 'account-a')).toThrow()
  expect(localStorage.getItem('xhs-research-account-bindings-v1')).toBe('{broken')
})
