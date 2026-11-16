import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { bindWorkspaceOwner } from '../api'
import { useAuthStore } from '../stores/auth'
import CloudLibraryDialog from '../components/CloudLibraryDialog.vue'
import { deleteArchives, fetchArchives, fetchArchiveFolders, fetchLibraryCapacity, previewArchiveDeletion, type ArchiveSummary } from '../library'

vi.mock('../library', async original => ({ ...await original<typeof import('../library')>(),
  deleteArchives: vi.fn(), fetchArchives: vi.fn(), fetchArchiveFolders: vi.fn(), fetchLibraryCapacity: vi.fn(), previewArchiveDeletion: vi.fn(),
}))
const input = defineComponent({ props: ['modelValue'], emits: ['update:modelValue'], setup: (props, { emit }) => () => h('input', { value: props.modelValue, onInput: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).value) }) })
const stubs = {
  UModal: defineComponent({ props: ['open', 'title'], setup: (props, { slots }) => () => props.open ? h('div', { role: 'dialog' }, [props.title, slots.body?.(), slots.footer?.()]) : null }),
  UButton: defineComponent({ props: ['label', 'disabled', 'loading'], setup: (props, { slots }) => () => h('button', { disabled: props.disabled || props.loading }, props.label || slots.default?.()) }),
  UInput: input, USelect: input,
  UCheckbox: defineComponent({ props: ['modelValue', 'disabled'], emits: ['update:modelValue'], setup: (props, { emit }) => () => h('input', { type: 'checkbox', checked: props.modelValue, disabled: props.disabled, onChange: (event: Event) => emit('update:modelValue', (event.target as HTMLInputElement).checked) }) }),
  UAlert: defineComponent({ props: ['title'], setup: props => () => h('p', props.title) }),
  UTooltip: defineComponent({ setup: (_, { slots }) => () => h('span', slots.default?.()) }),
  UIcon: true, UBadge: true, UDropdownMenu: true,
}
function row(id: string): ArchiveSummary {
  return { id, title: '试卷 ' + id, grade: '三年级', subject: '数学', version: 1, question_count: 4, folder_id: null, folder_name: null, group_name: '', favorite: false, file_status: 'ready', file_error: '', page_count: 1, created_at: 1, thumbnail_url: null }
}
const preview = { items: [{ id: 'a', title: '试卷 a', reason: null, storage_bytes: 1024 }, { id: 'b', title: '试卷 b', reason: '已关联公共库', storage_bytes: 2048 }], deletable_count: 1, reclaimable_bytes: 1024 }
let wrapper: VueWrapper
beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear(); setActivePinia(createPinia())
  useAuthStore().user = { id: 17, role: 'admin', username: 'admin' }; bindWorkspaceOwner('17')
  vi.mocked(fetchArchives).mockResolvedValue({ items: [row('a'), row('b')], total: 2, has_more: false })
  vi.mocked(fetchArchiveFolders).mockResolvedValue({ items: [] })
  vi.mocked(fetchLibraryCapacity).mockResolvedValue({ storage_bytes: 1024, storage_limit_bytes: 5 * 1024 ** 3 })
  vi.mocked(previewArchiveDeletion).mockResolvedValue(structuredClone(preview))
  vi.mocked(deleteArchives).mockResolvedValue({ deleted_ids: ['a'], skipped: [preview.items[1]], released_bytes: 1024 })
})
afterEach(() => { wrapper?.unmount(); bindWorkspaceOwner(''); vi.useRealTimers() })
async function open() {
  wrapper = mount(CloudLibraryDialog, { props: { open: true }, global: { stubs } })
  await flushPromises()
}
function button(label: string) { return wrapper.findAll('button').find(button => button.text() === label)! }
async function select() {
  await button('批量管理').trigger('click')
  await button('全选已加载（最多 50 份）').trigger('click')
}
async function confirmPreview() {
  await select(); await button('删除所选（2）').trigger('click'); await flushPromises()
}

it('shows capacity and requires a preview then explicit confirmation', async () => {
  await open(); expect(wrapper.text()).toContain('已用 1 KB / 5 GB')
  await confirmPreview()
  expect(previewArchiveDeletion).toHaveBeenCalledWith(['a', 'b'])
  expect(deleteArchives).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain('保留：已关联公共库')
  await button('确认删除 1 份').trigger('click'); await flushPromises()
  expect(deleteArchives).toHaveBeenCalledWith(['a', 'b'])
  expect(wrapper.text()).toContain('已删除 1 份，释放 1 KB；保留 1 份')
  expect(wrapper.text()).toContain('试卷 b：已关联公共库')
})
it('canceling the preview never deletes anything', async () => {
  await open(); await confirmPreview(); await button('取消').trigger('click')
  expect(deleteArchives).not.toHaveBeenCalled()
  expect(button('删除所选（2）')).toBeDefined()
})
it('cannot confirm when all selected papers are protected', async () => {
  vi.mocked(previewArchiveDeletion).mockResolvedValue({ ...preview, deletable_count: 0, reclaimable_bytes: 0 })
  await open(); await confirmPreview()
  expect(button('确认删除 0 份').attributes('disabled')).toBeDefined()
  await button('确认删除 0 份').trigger('click'); expect(deleteArchives).not.toHaveBeenCalled()
})
it('clears selection when filters change and caps select-loaded at 50', async () => {
  vi.mocked(fetchArchives).mockResolvedValue({ items: Array.from({ length: 60 }, (_, index) => row(String(index))), total: 60, has_more: false })
  await open(); await select()
  expect(button('删除所选（50）')).toBeDefined()
  expect(wrapper.findAll('input[type="checkbox"]').filter(input => input.attributes('disabled') !== undefined)).toHaveLength(10)
  await wrapper.get('[aria-label="搜索云端试卷"]').setValue('新搜索')
  expect(button('删除所选（0）').attributes('disabled')).toBeDefined()
})
it('rejects a changed account before sending any delete request', async () => {
  await open(); await confirmPreview(); bindWorkspaceOwner('other')
  await button('确认删除 1 份').trigger('click'); await flushPromises()
  expect(deleteArchives).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain('登录账号已变化')
})
it('locks confirmation during a request and preserves feedback after a disconnect', async () => {
  let reject!: (reason: Error) => void
  vi.mocked(deleteArchives).mockReturnValue(new Promise((_resolve, fail) => { reject = fail }))
  await open(); await confirmPreview(); await button('确认删除 1 份').trigger('click')
  expect(button('确认删除 1 份').attributes('disabled')).toBeDefined()
  await button('确认删除 1 份').trigger('click'); expect(deleteArchives).toHaveBeenCalledTimes(1)
  reject(new Error('连接中断')); await flushPromises()
  expect(wrapper.text()).toContain('先刷新列表核对结果')
  expect(wrapper.text()).toContain('试卷 a')
})
