import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { reactive } from 'vue'
import QuestionItem from '../components/QuestionItem.vue'
import { DEFAULT_LAYOUT } from '../constants'
import { applyOldSnapshot } from '../stores/exam-local'
import type { Question, SecLayout } from '../types'
import { shortenBlankLines } from '../rich-edit'
import { confirmQuestionReview, isManuallyReviewed } from '../question-quality'

// happy-dom 下 DOMPurify 的遍历不可靠（实测会丢掉 <b>、漏掉 <script>），这里只验证标签的去留与回写；
// 净化本身由浏览器里的 DOMPurify 负责，不在本文件的测试范围内。
vi.mock('../sanitize', () => ({ sanitizeRich: (html: string | null | undefined) => html ?? '' }))

/** 卷面上的一道题；题目用 reactive 包一层，回写后才会像在工作台里一样重新渲染 */
function render(question: Question, no = 1, layout: Partial<SecLayout> = {}) {
  const q = reactive(question)
  const wrapper = mount(QuestionItem, {
    props: { q, no, layout: { ...DEFAULT_LAYOUT, ...layout }, showAnswers: false, editable: true },
  })
  return { q, wrapper }
}
const choice = (): Question => ({ type: 'multiple_choice', stem: '3 + 4 = ？', options: ['6', '7', '8', '9'], answer: 1 })

describe('编辑后的复核状态', () => {
  it('仅调整格式保留状态，改动题干或选项后转为待核对', async () => {
    const { q, wrapper } = render({ ...choice(), quality_status: 'passed', analysis: '3+4=7' })
    confirmQuestionReview(q)
    const option = wrapper.findAll('[data-e="opts"] > div')[1]
    option.element.innerHTML = 'B. <b>7</b>'
    await option.trigger('blur')
    expect(q.quality_status).toBe('passed')
    expect(isManuallyReviewed(q)).toBe(true)
    option.element.innerHTML = 'B. 8'
    await option.trigger('blur')
    expect(q.quality_status).toBe('needs_review')
    expect(q._manualReview).toBeUndefined()
    expect(q.quality_issues).toContain('题目内容已修改，请重新核对答案与解析')
    q.quality_status = 'passed'
    const stem = wrapper.get('[data-e="stem"]')
    stem.element.innerHTML = '① 3 + 5 = ？'
    await stem.trigger('blur')
    expect(q.quality_status).toBe('needs_review')
  })

  it('英文删掉词间空格也属于内容修改', async () => {
    const { q, wrapper } = render({ type: 'fill_blank', stem: 'a long ____', answer: 'road', analysis: '长路', quality_status: 'passed' })
    const stem = wrapper.get('[data-e="stem"]')
    stem.element.innerHTML = '① along ____'
    await stem.trigger('blur')
    expect(q.quality_status).toBe('needs_review')
  })
})

describe('卷面编辑回写：选项', () => {
  it('只点进又离开不改数据，字母保留', async () => {
    const { q, wrapper } = render(choice())
    const option = wrapper.findAll('[data-e="opts"] > div')[1]
    await option.trigger('blur')
    expect(q._optsHtml).toBeUndefined()
    expect(q.options).toEqual(['6', '7', '8', '9'])
    expect(option.text()).toBe('B. 7')
  })

  it('改内容后字母仍在，纯文本同步写回（原来字母会消失、选项文字不更新）', async () => {
    const { q, wrapper } = render(choice())
    const option = wrapper.findAll('[data-e="opts"] > div')[1]
    option.element.innerHTML = 'B. <b>七</b>'
    await option.trigger('blur')
    expect(q._optsHtml?.[1]).toBe('<b>七</b>')
    expect(q.options?.[1]).toBe('七')
    expect(option.text()).toBe('B. 七')
    await option.trigger('blur')
    expect(option.text()).toBe('B. 七')
  })

  it('整项设了格式、字母也包在格式里时，去掉字母并保留格式', async () => {
    const { q, wrapper } = render(choice())
    const option = wrapper.findAll('[data-e="opts"] > div')[2]
    option.element.innerHTML = '<font color="#d0342c">C. 八</font>'
    await option.trigger('blur')
    expect(q._optsHtml?.[2]).toBe('<font color="#d0342c">八</font>')
    expect(q.options?.[2]).toBe('八')
    expect(option.text()).toBe('C. 八')
  })

  it('旧缓存：缺字母的补上字母，已带字母的不重复', () => {
    const { wrapper } = render({ ...choice(), _optsHtml: ['6', '<b>B. 7</b>'] })
    expect(wrapper.findAll('[data-e="opts"] > div').map(option => option.text())).toEqual(['A. 6', 'B. 7', 'C. 8', 'D. 9'])
  })
})

describe('卷面编辑回写：题干与连线', () => {
  it('填空横线缩为三个下划线，预览和只聚焦不改写原题', async () => {
    const { q, wrapper } = render({ type: 'fill_blank', stem: '____ + ______ = 10\n___ + __ = 5' })
    const stem = wrapper.get('[data-e="stem"]')
    expect(stem.text()).toBe('① ___ + ___ = 10\n___ + __ = 5')
    await stem.trigger('blur')
    expect(q.stem).toBe('____ + ______ = 10\n___ + __ = 5')
    expect(q._stemHtml).toBeUndefined()
  })

  it('富文本填空缩短横线但保留格式、属性和其他题型', async () => {
    const html = '<b title="____">____</b> + 2 = 5'
    expect(shortenBlankLines(html)).toBe('<b title="____">___</b> + 2 = 5')
    const { q, wrapper } = render({ type: 'fill_blank', stem: '____ + 2 = 5', _stemHtml: html })
    expect(wrapper.get('[data-e="stem"] b').text()).toBe('___')
    await wrapper.get('[data-e="stem"]').trigger('blur')
    expect(q._stemHtml).toBe(html)
    const other = render({ type: 'reading', stem: '____' })
    expect(other.wrapper.get('[data-e="stem"]').text()).toBe('① ____')
  })

  it('关闭题号时，开头的 □、《 不会被当成题号删掉', async () => {
    const { q, wrapper } = render({ type: 'fill_blank', stem: '□ + 5 = 12' }, 1, { showNo: false })
    const stem = wrapper.get('[data-e="stem"]')
    stem.element.innerHTML = '□ + 5 = 13'
    await stem.trigger('blur')
    expect(q.stem).toBe('□ + 5 = 13')
    expect(stem.text()).toBe('□ + 5 = 13')
    stem.element.innerHTML = '《静夜思》的作者是（ ）'
    await stem.trigger('blur')
    expect(q.stem).toBe('《静夜思》的作者是（ ）')
  })

  it('显示题号时只去掉题号，关卡标记留在卷面、不进纯文本', async () => {
    const { q, wrapper } = render({ type: 'fill_blank', stem: '3 + 5 = ____', difficulty_level: 2 }, 3)
    const stem = wrapper.get('[data-e="stem"]')
    expect(stem.text()).toBe('③ [第2关] 3 + 5 = ___')
    stem.element.innerHTML = '③ [第2关] 3 + 6 = ____'
    await stem.trigger('blur')
    expect(q._stemHtml).toBe('[第2关] 3 + 6 = ____')
    expect(q.stem).toBe('3 + 6 = ____')
    expect(stem.text()).toBe('③ [第2关] 3 + 6 = ___')
  })

  it('第 51 题起题号是「51.」，反复编辑不会越积越多', async () => {
    const { q, wrapper } = render({ type: 'fill_blank', stem: '8 + 9 = ____' }, 51)
    const stem = wrapper.get('[data-e="stem"]')
    stem.element.innerHTML = '51. 8 + 9 = __'
    await stem.trigger('blur')
    await stem.trigger('blur')
    expect(q.stem).toBe('8 + 9 = __')
    expect(stem.text()).toBe('51. 8 + 9 = __')
  })

  it('只点进又离开不写缓存，原始题干保持不变', async () => {
    const { q, wrapper } = render({ type: 'oral_math', stem: '3+5=' })
    await wrapper.get('[data-e="stem"]').trigger('blur')
    expect(q._stemHtml).toBeUndefined()
    expect(q.stem).toBe('3+5=')
  })

  it('排版模式注入的拖拽手柄不会写进题目', async () => {
    const { q, wrapper } = render({ type: 'fill_blank', stem: '旧题干' })
    const stem = wrapper.get('[data-e="stem"]')
    stem.element.innerHTML = '① 新题干<span class="sort-handle">⠿</span>'
    await stem.trigger('blur')
    expect(q._stemHtml).toBe('新题干')
    expect(q.stem).toBe('新题干')
  })

  it('连线题：改动写回数据（原来会报错，改动在重新渲染后丢失）', async () => {
    const { q, wrapper } = render({ type: 'match_pair', stem: '连一连。', left_items: ['2+3', '4+1'], right_items: ['5', '5'], answer: [[0, 0], [1, 1]] })
    const cells = wrapper.findAll('[data-e="match"] td')
    cells[2].element.textContent = '（2）4 + 2'
    await cells[2].trigger('blur')
    await cells[0].trigger('blur')
    expect(q.left_items).toEqual(['2+3', '4 + 2'])
    expect(q.right_items).toEqual(['5', '5'])
  })

  it('旧模板迁移：题干去掉圈号和关卡标记，正文首字保留', () => {
    const cards = [{ type: 'fill_blank', count: 2, data: { questions: [{ stem: '' }, { stem: '' }] as Question[] } }]
    applyOldSnapshot(cards, '<div class="sec-block"><div class="q"><div data-e="stem">① [第1关] 《静夜思》的作者是（ ）</div></div>'
      + '<div class="q"><div data-e="stem">□ + 5 = 12</div></div></div>')
    expect(cards[0].data.questions.map(question => question.stem)).toEqual(['《静夜思》的作者是（ ）', '□ + 5 = 12'])
  })
})
