import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, shallowMount, type VueWrapper } from '@vue/test-utils'
import { uiStubs } from '../../../shared/test/ui-stubs'
import { useExamStore } from '../stores/exam'
import { DEFAULT_LAYOUT } from '../constants'
import { confirmQuestionReview } from '../question-quality'
import StepResult from '../components/StepResult.vue'
import * as exporter from '../exporter'
import * as wordExporter from '../word-export'

vi.mock('../exporter', () => ({ exportPDF: vi.fn(), exportPNG: vi.fn(), exportBatch: vi.fn(), printStack: vi.fn() }))
vi.mock('../word-export', () => ({ exportWord: vi.fn() }))
const dropdown = defineComponent({ props: ['items'], setup: (props, { slots }) => () => h('div', [slots.default?.(),
  props.items.flat().map((item: { label: string; onSelect: () => void }) => h('button', { onClick: item.onSelect }, item.label))]) })
let wrapper: VueWrapper
beforeEach(() => {
  vi.clearAllMocks(); setActivePinia(createPinia())
  useExamStore().papers = [1, 2].map(day => ({ day, title: '练习', grade: '小学三年级', subject: '数学', keyword: '加法', difficulty: 'medium', sections: [{
    _sid: 'section', type: 'oral_math', layout: { ...DEFAULT_LAYOUT }, data: { questions: [{ stem: '3+4=', answer: 7, analysis: '3+4=7', quality_status: 'unchecked' }] },
  }] }))
  wrapper = shallowMount(StepResult, { global: { stubs: { ...uiStubs, UDropdownMenu: dropdown, UButtonGroup: defineComponent({ setup: (_, { slots }) => () => h('div', slots.default?.()) }) } } })
})
afterEach(() => { wrapper.unmount(); useExamStore().$dispose() })
async function click(label: string) { await wrapper.findAll('button').find(button => button.text() === label)!.trigger('click'); await flushPromises() }

it('待核对题目阻止 PDF、PNG、打印及整批导出，人工核对后可导出当前试卷', async () => {
  for (const label of ['下载学生卷', '下载 PNG', '打印试卷', '全部试卷 ZIP', '合并全部 PDF']) await click(label)
  expect(wrapper.text()).toContain('请先补齐题目、答案与解析')
  for (const fn of Object.values(exporter)) expect(fn).not.toHaveBeenCalled()
  confirmQuestionReview(useExamStore().papers[0].sections[0].data.questions[0])
  await click('下载学生卷')
  expect(exporter.exportPDF).toHaveBeenCalledOnce()
  await click('合并全部 PDF')
  expect(exporter.exportBatch).not.toHaveBeenCalled()
})

it('缺题或空答案不能被通过状态绕过，数值零答案可以导出', async () => {
  const section = useExamStore().papers[0].sections[0], question = section.data.questions[0]
  question.quality_status = 'passed'; question.answer = ''
  await click('下载学生卷'); expect(exporter.exportPDF).not.toHaveBeenCalled()
  question.answer = 0; section.data.missing_count = 1
  await click('下载学生卷'); expect(exporter.exportPDF).not.toHaveBeenCalled()
  section.data.missing_count = 0
  await click('下载学生卷'); expect(exporter.exportPDF).toHaveBeenCalledOnce()
})

it('Word 导出同样要求题目完成核对，默认只导出当前学生卷', async () => {
  await click('可编辑 Word'); await click('下载 Word 文件')
  expect(wordExporter.exportWord).not.toHaveBeenCalled()
  confirmQuestionReview(useExamStore().papers[0].sections[0].data.questions[0])
  await click('可编辑 Word'); await click('下载 Word 文件')
  expect(wordExporter.exportWord).toHaveBeenCalledWith([useExamStore().papers[0]], expect.anything(), expect.anything(), expect.objectContaining({ mode: 'student' }))
})
