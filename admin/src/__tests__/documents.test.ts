import { afterEach, expect, it, vi } from 'vitest'
import { defineComponent, h, KeepAlive, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import DocumentManager from '../components/DocumentManager.vue'
import { ApiError } from '../api'
import { uiStubs } from '../../../shared/test/ui-stubs'
const mocks = vi.hoisted(() => ({ list: vi.fn(), save: vi.fn() }))
vi.mock('../site', () => ({ siteDocuments: mocks.list, updateDocument: mocks.save }))
afterEach(() => vi.restoreAllMocks())
it('切换文档和菜单保留草稿，冲突恢复仅更新基线并保留文字', async () => {
  let revision = 1
  mocks.list.mockImplementation(async () => ({ items: ['agreement', 'privacy'].map(key => ({ key, title: key, body: '原正文', revision, updated_at: 1 })) }))
  mocks.save.mockRejectedValueOnce(new ApiError('版本已变化', 409))
  const visible = ref(true)
  const wrapper = mount(defineComponent({ setup: () => () => h(KeepAlive, () => visible.value ? h(DocumentManager, { user: { id: 1, username: 'admin', role: 'admin' } }) : h('div')) }), { global: { stubs: uiStubs } })
  try {
    await flushPromises()
    await wrapper.get('#doc-body').setValue('我的协议草稿')
    const click = async (label: string) => { await wrapper.findAll('button').find(item => item.text() === label)!.trigger('click'); await flushPromises() }
    await click('隐私政策'); await wrapper.get('#doc-body').setValue('我的隐私草稿')
    await click('用户协议'); expect((wrapper.get('#doc-body').element as HTMLTextAreaElement).value).toBe('我的协议草稿')
    visible.value = false; await flushPromises(); revision = 2; visible.value = true; await flushPromises()
    expect((wrapper.get('#doc-body').element as HTMLTextAreaElement).value).toBe('我的协议草稿')
    await click('保存'); await click('载入最新并保留我的修改')
    expect((wrapper.get('#doc-body').element as HTMLTextAreaElement).value).toBe('我的协议草稿')
    mocks.save.mockImplementation(async (_id, key, body) => ({ key, ...body, revision: 3, updated_at: 1 }))
    await click('保存')
    expect(mocks.save).toHaveBeenLastCalledWith(1, 'agreement', { title: 'agreement', body: '我的协议草稿', revision: 2 })
  } finally { wrapper.unmount() }
})
