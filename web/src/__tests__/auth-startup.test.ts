import { beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore, UID_KEY } from '../stores/auth'
import { useExamStore } from '../stores/exam'
import * as api from '../api'

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
})
it('认证查询网络失败保留账号，重试后按真实账号恢复工作台', async () => {
  localStorage.setItem(UID_KEY, '7')
  const fetch = vi
    .spyOn(api, 'fetchMe')
    .mockRejectedValueOnce(new Error('网络异常'))
    .mockResolvedValueOnce({ id: 7, username: 'teacher', role: 'user' })
  const auth = useAuthStore()
  await auth.init()
  expect(localStorage.getItem(UID_KEY)).toBe('7')
  expect(auth.bootError).toBe('网络异常')
  expect(auth.ready).toBe(true)
  await auth.init()
  expect(auth.bootError).toBe('')
  expect(useExamStore().ownerId).toBe('7')
  expect(fetch).toHaveBeenCalledTimes(2)
})
it('明确无会话时才清除账号标识', async () => {
  localStorage.setItem(UID_KEY, '7')
  vi.spyOn(api, 'fetchMe').mockResolvedValue(null)
  const auth = useAuthStore()
  await auth.init()
  expect(localStorage.getItem(UID_KEY)).toBeNull()
  expect(auth.bootError).toBe('')
  expect(auth.user).toBeNull()
})
