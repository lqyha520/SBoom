import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { bindWorkspaceOwner } from '../api'
import { useExamStore } from '../stores/exam'
import { DEFAULT_LAYOUT } from '../constants'
import { completeArchive, createArchive, fetchArchiveFolders, type ArchiveDetail } from '../library'
import CloudSaveDialog from '../components/CloudSaveDialog.vue'

vi.mock('../library', async original => ({ ...await original<typeof import('../library')>(),
  createArchive: vi.fn(), completeArchive: vi.fn(), fetchArchiveFolders: vi.fn() }))
const slot = defineComponent({ setup: (_, { slots }) => () => h('div', slots.default?.()) })
const radio = defineComponent({ props: ['modelValue', 'items', 'disabled'], emits: ['update:modelValue'],
  setup: (props, { emit }) => () => h('select', { disabled: props.disabled, value: props.modelValue,
    onChange: (event: Event) => emit('update:modelValue', (event.target as HTMLSelectElement).value) },
  props.items.map((item: { value: string; label: string }) => h('option', { value: item.value }, item.label))) })
const stubs = {
  UModal: defineComponent({ setup: (_, { slots }) => () => h('div', [slots.body?.(), slots.footer?.()]) }),
  UButton: defineComponent({ props: ['label', 'disabled', 'loading'], setup: props => () => h('button', { disabled: props.disabled || props.loading }, props.label) }),
  URadioGroup: radio, USelect: radio, UFormField: slot, UTooltip: slot,
  UAlert: defineComponent({ props: ['title'], setup: props => () => h('p', props.title) }), UIcon: true, UInput: true,
}
let wrapper: VueWrapper
beforeEach(() => {
  vi.resetAllMocks(); setActivePinia(createPinia()); bindWorkspaceOwner('teacher')
  useExamStore().papers = Array.from({ length: 20 }, (_, index) => ({ title: '练习' + index, grade: '小学一年级', subject: '数学', keyword: '进位加法', difficulty: 'medium',
    sections: [{ type: 'quiz', layout: { ...DEFAULT_LAYOUT }, data: { questions: [{ stem: '8 + 7', answer: 15 }] } }] }))
  vi.mocked(fetchArchiveFolders).mockResolvedValue({ items: [] })
  vi.mocked(createArchive).mockImplementation(async body => ({ id: body.source_id, version: 1, file_status: 'pending', snapshot: body.snapshot } as ArchiveDetail))
  vi.mocked(completeArchive).mockImplementation(async record => ({ ...record, file_status: 'ready' }))
})
afterEach(() => { wrapper?.unmount(); bindWorkspaceOwner('') })
async function open() { wrapper = mount(CloudSaveDialog, { props: { open: true, selected: 3 }, global: { stubs } }); await flushPromises() }
async function click(label: string) { await wrapper.findAll('button').find(button => button.text() === label)!.trigger('click'); await flushPromises() }

it('默认二十份只创建一条，上传失败复用同一记录和完整快照', async () => {
  await open()
  vi.mocked(completeArchive).mockRejectedValueOnce(new Error('模拟上传中断'))
  await click('保存试卷')
  // 等待整个保存流程的可见结果，包含原生 Web Crypto 摘要与上传失败处理。
  await vi.waitFor(() => expect(wrapper.text()).toContain('模拟上传中断'))
  expect(createArchive).toHaveBeenCalledOnce()
  const first = vi.mocked(createArchive).mock.calls[0][0]
  expect(first.snapshot.schema_version).toBe(2)
  expect(first.snapshot.additional_papers).toHaveLength(19)
  expect(first.snapshot.export_options).toMatchObject({ mode: 'withAnswers', separate_answers: true })
  expect(wrapper.text()).toContain('模拟上传中断')
  await click('重试未完成项')
  await vi.waitFor(() => expect(wrapper.text()).toContain('已归档'))
  expect(createArchive).toHaveBeenCalledOnce()
  expect(completeArchive).toHaveBeenCalledTimes(2)
  expect(vi.mocked(completeArchive).mock.calls[1][0].id).toBe(first.source_id)
  expect(wrapper.text()).toContain('已归档')
})

it('可以改为逐份保存，仍生成二十条独立记录', async () => {
  await open()
  await wrapper.findAll('select')[1].setValue('separate')
  await click('保存试卷')
  await vi.waitFor(() => expect(wrapper.findAll('.save-job').filter(job => job.text().includes('已归档'))).toHaveLength(20))
  expect(completeArchive).toHaveBeenCalledTimes(20)
  expect(createArchive).toHaveBeenCalledTimes(20)
  expect(vi.mocked(createArchive).mock.calls.every(([body]) => body.snapshot.schema_version === 1)).toBe(true)
})

it('当前试卷只保存当前选中的一份', async () => {
  await open()
  await wrapper.findAll('select')[0].setValue('current')
  await click('保存试卷')
  await vi.waitFor(() => expect(wrapper.text()).toContain('已归档'))
  expect(createArchive).toHaveBeenCalledOnce()
  expect(vi.mocked(createArchive).mock.calls[0][0].snapshot.paper.title).toBe('练习3')
  expect(vi.mocked(createArchive).mock.calls[0][0].snapshot.export_options.separate_answers).toBe(true)
})

it('仅学生卷不携带分开保存答案选项', async () => {
  await open()
  await wrapper.find('[aria-label="归档 PDF 内容"]').setValue('student')
  await click('保存试卷')
  // 合并快照的 Web Crypto 摘要可能在下个任务轮次完成。
  await vi.waitFor(() => expect(wrapper.text()).toContain('已归档'))
  expect(createArchive).toHaveBeenCalledOnce()
  expect(vi.mocked(createArchive).mock.calls[0][0].snapshot.export_options).toMatchObject({ mode: 'student' })
  expect(vi.mocked(createArchive).mock.calls[0][0].snapshot.export_options.separate_answers).toBeUndefined()
})
