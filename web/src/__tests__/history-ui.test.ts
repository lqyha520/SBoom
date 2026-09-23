import 'fake-indexeddb/auto'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { useAuthStore } from '../stores/auth'
import { useExamStore } from '../stores/exam'
import * as persistence from '../persistence'
import HistoryDialog from '../components/HistoryDialog.vue'
import DraftManager from '../components/DraftManager.vue'
import { uiStubs } from '../../../shared/test/ui-stubs'

let wrapper: VueWrapper | undefined
let store: ReturnType<typeof useExamStore>
beforeEach(async () => {
  await new Promise<void>((resolve, reject) => {
    const request = indexedDB.deleteDatabase('learn-coach-workspaces')
    request.onsuccess = () => resolve(); request.onerror = () => reject(request.error)
  })
  setActivePinia(createPinia()); useAuthStore().user = { id: 1, username: 'fixture', role: 'user' }
  store = useExamStore()
  await store.initPersistence()
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined; store.disposePersistence(); store.$dispose() })

it('历史对话框只渲染当前页，翻页和跨页搜索可用', async () => {
  const value = store.captureSnapshot()
  for (let i = 0; i < 25; i++) await persistence.addHistory('1', { ...value, title: `试卷-${i}-独立` }, 'manual')
  wrapper = mount(HistoryDialog, { props: { open: true }, global: { stubs: uiStubs } })
  await vi.waitFor(() => expect(wrapper!.findAll('article')).toHaveLength(20))
  await wrapper.findAll('button').find(item => item.text() === '下一页')!.trigger('click')
  await vi.waitFor(() => expect(wrapper!.findAll('article')).toHaveLength(5))
  const target = (await persistence.listHistory('1'))[0].title
  await wrapper.get('input').setValue(target)
  await vi.waitFor(() => expect(wrapper!.findAll('article')).toHaveLength(1))
  expect(wrapper.text()).toContain(target)
  expect(wrapper.text()).toContain('第 1 页')
})

it('整理草稿保留当前页面，仅在确认后删除所选旧副本', async () => {
  await store.flushDraft()
  await persistence.saveDraft('1', 'old', { ...store.captureSnapshot(), title: '旧副本' })
  wrapper = mount(DraftManager, { props: { open: true }, global: { stubs: uiStubs } })
  await vi.waitFor(() => expect(wrapper!.text()).toContain('旧副本'))
  expect(wrapper.text()).toContain('当前页面')
  const buttons = wrapper.findAll('button').filter(item => item.text() === '删除')
  expect(buttons).toHaveLength(1)
  await buttons[0].trigger('click')
  expect(await persistence.listDrafts('1')).toHaveLength(2)
  await wrapper.findAll('button').find(item => item.text() === '确认删除')!.trigger('click')
  await flushPromises()
  await vi.waitFor(async () => expect(await persistence.listDrafts('1')).toHaveLength(1))
  expect((await persistence.listDrafts('1'))[0].id).toBe('1:' + store.draftId)
})

it('历史读取失败显示错误而非空列表，重试成功后清除提示', async () => {
  await persistence.addHistory('1', { ...store.captureSnapshot(), title: '保留版本' }, 'manual')
  vi.spyOn(persistence, 'listHistory').mockRejectedValueOnce(new Error('磁盘暂不可用'))
  wrapper = mount(HistoryDialog, { props: { open: true }, global: { stubs: uiStubs } })
  await vi.waitFor(() => expect(wrapper!.text()).toContain('历史记录读取失败'))
  expect(wrapper.text()).not.toContain('还没有历史版本')
  await wrapper.findAll('button').find(item => item.text() === '重新加载')!.trigger('click')
  await vi.waitFor(() => expect(wrapper!.findAll('article')).toHaveLength(1))
  expect(wrapper.text()).toContain('保留版本')
  expect(wrapper.text()).not.toContain('历史记录读取失败')
  expect(store.storageError).toBe('')
})
