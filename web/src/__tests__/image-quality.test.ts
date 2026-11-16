import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ImageQualityReview from '../components/ImageQualityReview.vue'
import type { ImageQualityReview as Review } from '../image-generation'

describe('图片质量检查', () => {
  const review: Review = { status: 'passed', human_status: 'pending', issues: [], counts: [], checks: { diagram: 'pass' } }
  it('自动通过和旧图片都不会被标为人工审核通过', () => {
    const passed = mount(ImageQualityReview, { props: { review } })
    expect(passed.text()).toContain('自动检查未发现问题 · 待人工核对')
    expect(mount(ImageQualityReview).text()).toContain('自动检查未完成 · 待人工核对')
  })
  it('显示具体问题和不确定项，模型返回的HTML仅作为文字', () => {
    const wrapper = mount(ImageQualityReview, { props: { review: { ...review, status: 'issues', checks: { diagram: 'uncertain' },
      issues: [{ question: '第2题', message: '<img src=x>数量与算式不一致' }] } } })
    expect(wrapper.text()).toContain('数量与算式不一致')
    expect(wrapper.text()).toContain('图文对应：需核实')
    expect(wrapper.find('img').exists()).toBe(false)
  })
})
