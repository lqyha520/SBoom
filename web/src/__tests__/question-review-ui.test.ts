import { afterEach, beforeEach, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, type VueWrapper } from '@vue/test-utils'
import { useExamStore } from '../stores/exam'
import { DEFAULT_LAYOUT } from '../constants'
import QuestionManager from '../components/QuestionManager.vue'
import { isManuallyReviewed, paperQuality } from '../question-quality'
import { uiStubs } from '../../../shared/test/ui-stubs'

let wrapper: VueWrapper
let store: ReturnType<typeof useExamStore>
const button = (label: string) => wrapper.findAll('button').find(item => item.text() === label)!
const question = () => store.papers[0].sections[0].data.questions[0]
beforeEach(() => {
  setActivePinia(createPinia())
  store = useExamStore()
  store.papers = [{ grade: '小学三年级', subject: '数学', keyword: '加法', difficulty: 'medium', title: '练习', sections: [{
    _sid: 'first', type: 'oral_math', layout: { ...DEFAULT_LAYOUT }, warn: '独立复核未完成',
    data: { questions: [{ _qid: 'one', type: 'oral_math', stem: '3+4=', answer: 7, analysis: '3+4=7', quality_status: 'unchecked' }] },
  }] }]
  wrapper = mount(QuestionManager, { props: { paperIndex: 0 }, global: { stubs: { ...uiStubs, UTextarea: true } } })
})
afterEach(() => { wrapper.unmount(); store.$dispose() })

it('确认后退出待核对列表，支持撤销重做和草稿恢复', async () => {
  await wrapper.get('input[type="checkbox"]').setValue(true)
  await button('确认已核对').trigger('click')
  expect(wrapper.text()).toContain('当前大题没有待核对题目')
  expect(question().quality_status).toBe('unchecked')
  expect(paperQuality(store.papers[0])[0].warning).toBe('')
  store.undo()
  expect(isManuallyReviewed(question())).toBe(false)
  store.redo()
  expect(isManuallyReviewed(question())).toBe(true)
  const snapshot = store.captureSnapshot()
  store.applySnapshot(snapshot)
  expect(isManuallyReviewed(question())).toBe(true)
  await wrapper.get('input[type="checkbox"]').setValue(false)
  expect(wrapper.text()).toContain('人工核对完成')
  expect(wrapper.findAll('p').some(item => item.text() === '模型复核通过')).toBe(false)
  await button('撤销人工确认').trigger('click')
  expect(isManuallyReviewed(question())).toBe(false)
  expect(question().quality_status).toBe('unchecked')
})

it('无解析时提示补齐，不产生撤销记录；生成期间不能确认', async () => {
  question().analysis = ''
  await button('确认已核对').trigger('click')
  expect(wrapper.text()).toContain('请先补充解析')
  expect(store.canUndo).toBe(false)
  expect(question()._manualReview).toBeUndefined()
  store.generating = true
  await wrapper.vm.$nextTick()
  expect(button('确认已核对').attributes('disabled')).toBeDefined()
})
