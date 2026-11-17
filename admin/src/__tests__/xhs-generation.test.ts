import { defineComponent, h, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { generationGrade, useXhsGeneration } from '../xhs-generation'
const mocks = vi.hoisted(() => ({ request: vi.fn() }))
vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), request: mocks.request }))
let wrapper: ReturnType<typeof mount>
let generation: ReturnType<typeof useXhsGeneration<{ value: string }>>
const currentId = ref('material-one')
beforeEach(() => {
  localStorage.clear(); vi.resetAllMocks(); currentId.value = 'material-one'
  wrapper = mount(defineComponent({ setup() { generation = useXhsGeneration(7, () => currentId.value, 'material'); return () => h('div') } }))
})
afterEach(() => wrapper.unmount())
it('采集年级映射到实际教材名称，未核实科目不会进入模型', () => {
  const available = { '小学一年级': ['数学', '语文'] }
  expect(generationGrade('一年级','数学',available)).toBe('小学一年级')
  expect(generationGrade('小学一年级','数学',available)).toBe('小学一年级')
  expect(generationGrade('一年级','英语',available)).toBeUndefined()
  expect(generationGrade('高一','数学',available)).toBeUndefined()
})
it('先持久保存请求编号，再按文本模型时限发起一次生成', async () => {
  mocks.request.mockImplementation(async path => {
    expect(JSON.parse(localStorage.getItem('lc-xhs-generation:7:material:material-one')!)).toHaveProperty('id')
    if (path === '/api/v1/generation/options?kind=text') return { timeout_ms: 450000, revision: 'config-v1' }
    return { value: 'result' }
  })
  expect(await generation.generate('/api/v1/generate', { keyword: '找规律' })).toEqual({ value: 'result' })
  expect(mocks.request).toHaveBeenLastCalledWith('/api/v1/generate', expect.objectContaining({ method: 'POST', headers: expect.objectContaining({ 'X-Request-ID': expect.any(String), 'X-Model-Config-Revision': 'config-v1' }) }), 'json', 450000)
  await generation.generate('/api/v1/generate', {})
  expect(mocks.request).toHaveBeenCalledTimes(2)
})
it('网络中断保留编号，恢复只查询原请求，不再次发起生成', async () => {
  mocks.request.mockResolvedValueOnce({ timeout_ms: 300000, revision: '1' }).mockRejectedValueOnce(new Error('网络中断'))
  expect(await generation.generate('/api/v1/generate', {})).toBeNull()
  const id = generation.pending.value!.id
  mocks.request.mockResolvedValueOnce({ status: 'succeeded', result: { value: 'saved' }, cache_expired: false })
  expect(await generation.recover()).toEqual({ value: 'saved' })
  expect(mocks.request).toHaveBeenLastCalledWith(`/api/v1/me/generations/${id}`)
  expect(generation.pending.value).not.toBeNull()
  generation.finish()
  expect(localStorage.getItem('lc-xhs-generation:7:material:material-one')).toBeNull()
})
it('本地请求记录无法保存时不会发出付费请求', async () => {
  vi.stubGlobal('localStorage', { getItem: vi.fn(), setItem: () => { throw new Error('storage unavailable') }, removeItem: vi.fn() })
  try { await generation.generate('/api/v1/generate', {}); expect(mocks.request).not.toHaveBeenCalled() }
  finally { vi.unstubAllGlobals() }
})
it('切换资料后迟到的生成结果不会串入新资料，原请求仍能恢复', async () => {
  let complete!: (value: { value: string }) => void
  mocks.request.mockResolvedValueOnce({ timeout_ms: 300000, revision: '1' }).mockImplementationOnce(() => new Promise(resolve => { complete = resolve }))
  const running = generation.generate('/api/v1/generate', {})
  await nextTick()
  currentId.value = 'material-two'; await nextTick()
  complete({ value: 'first material result' })
  expect(await running).toBeNull()
  expect(generation.result.value).toBeNull()
  expect(generation.pending.value).toBeNull()
  currentId.value = 'material-one'; await nextTick()
  expect(generation.pending.value?.id).toBeTruthy()
})

it('版本与编辑快照随请求持久保存，重开后仍拒绝把旧结果当成当前输入', async () => {
  mocks.request.mockResolvedValueOnce({ timeout_ms: 300000, revision: '1' }).mockResolvedValueOnce({ value: '旧输入结果' })
  const editor = { body: '原正文', audience: '家长' }
  await generation.generate('/api/v1/generate', {}, 3, editor)
  expect(generation.matches(3, editor)).toBe(true)
  expect(generation.matches(4, editor)).toBe(false)
  expect(generation.matches(3, { ...editor, body: '已编辑的新正文' })).toBe(false)
  wrapper.unmount()
  wrapper = mount(defineComponent({ setup() { generation = useXhsGeneration(7, () => currentId.value, 'material'); return () => h('div') } }))
  expect(generation.matches(3, editor)).toBe(true)
  expect(generation.matches(4, editor)).toBe(false)
})

it('历史请求缺少输入版本时必须人工核对', async () => {
  mocks.request.mockResolvedValueOnce({ timeout_ms: 300000, revision: '1' }).mockResolvedValueOnce({ value: '历史结果' })
  await generation.generate('/api/v1/generate', {})
  expect(generation.matches(1, {})).toBe(false)
})
