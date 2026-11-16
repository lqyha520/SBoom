import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import XhsPublishAssist from '../components/XhsPublishAssist.vue'
import { uiStubs } from '../../../shared/test/ui-stubs'
import { newPublication, type PublicationData, type WorkflowRecord } from '../xhs-workflow'
import { validateMedia } from '../xhs-publish-assist'

const mocks = vi.hoisted(() => ({ request: vi.fn(), get: vi.fn(), check: vi.fn() }))
vi.mock('../xhs-publish-assist', async original => ({ ...await original<typeof import('../xhs-publish-assist')>(), assistRequest: mocks.request, mediaBase64: async (file: File) => file.name }))
vi.mock('../xhs-workflow', async original => ({ ...await original<typeof import('../xhs-workflow')>(), getWorkflow: mocks.get }))
vi.mock('../xhs-publication', async original => ({ ...await original<typeof import('../xhs-publication')>(), checkPublication: mocks.check }))
let wrapper: VueWrapper, record: WorkflowRecord<PublicationData>
const button = (name: string) => wrapper.findAll('button').find(item => item.text() === name)!
const files = [new File(['one'], 'one.png', { type: 'image/png' }), new File(['two'], 'two.jpg', { type: 'image/jpeg' })]
const session = { account_id: 'account-test-1', token: 'token-123', record_id: 'publication-123', revision: 2, status: 'waiting', message: '请登录', browser_open: true, touched: false }
beforeEach(() => {
  vi.resetAllMocks()
  vi.spyOn(URL, 'createObjectURL').mockImplementation(file => 'blob:' + (file as File).name)
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  record = { id: 'publication-123', revision: 2, kind: 'publications', parent_id: null, title: '练习', status: 'ready', created_at: '', updated_at: '', data: { ...newPublication(), title: '练习', account: '学习账号', status: 'ready', rights_checked: true, truth_checked: true, privacy_checked: true, media_checked: true, platform_checked: true, custom_content: { headline: '练习标题', body: '练习正文', hashtags: '#数学', media_notes: '' } } }
  mocks.get.mockResolvedValue(record)
  mocks.check.mockResolvedValue({ blockers: [] })
  mocks.request.mockImplementation(async route => route === '/accounts' ? { items: [{id:'account-test-1',name:'学习账号',note:'',archived:false}] } : route === '/health' ? { version: 4 } : { available: true, busy: false, session: { ...session, ...(route === '/publisher/prepare' ? { touched: true, status: 'prepared' } : {}) } })
  wrapper = mount(XhsPublishAssist, { props: { record, dirty: false }, global: { stubs: uiStubs } })
})
afterEach(() => wrapper.unmount())
async function select() {
  const input = wrapper.get('input[type="file"]')
  Object.defineProperty(input.element, 'files', { value: files, configurable: true })
  await input.trigger('change'); await flushPromises()
}
async function confirm() { for (const input of wrapper.findAll('input[type="checkbox"]')) await input.setValue(true) }
it('支持图片和单视频，拒绝混用、空文件和超出数量', () => {
  expect(() => validateMedia(files)).not.toThrow()
  expect(() => validateMedia([new File(['mp4'], 'x.mp4', { type: 'video/mp4' })])).not.toThrow()
  expect(() => validateMedia([...files, new File(['mp4'], 'x.mp4', { type: 'video/mp4' })])).toThrow('混用')
  expect(() => validateMedia([new File([], 'x.png', { type: 'image/png' })])).toThrow('空文件')
  expect(() => validateMedia(Array(10).fill(files[0]))).toThrow('1–9')
})
it('先确认账号与素材，排序后重新确认；仅发送已保存文案且不登记已发布', async () => {
  await flushPromises(); await select()
  expect(button('填入文案与素材').attributes('disabled')).toBeDefined()
  await confirm()
  await wrapper.get('button[aria-label="前移素材 2"]').trigger('click')
  expect(button('填入文案与素材').attributes('disabled')).toBeDefined()
  await confirm(); await button('填入文案与素材').trigger('click'); await flushPromises()
  expect(mocks.request).toHaveBeenCalledWith('/publisher/prepare', expect.objectContaining({ record_id: record.id, revision: 2, headline: '练习标题', body: '练习正文\n\n#数学', media: [{ type: 'image/jpeg', base64: 'two.jpg' }, { type: 'image/png', base64: 'one.png' }] }))
  expect(record.status).toBe('ready')
  expect(wrapper.text()).toContain('已辅助填入，尚未发布')
  expect(button('填入文案与素材').attributes('disabled')).toBeDefined()
})
it.each(['revision', 'status', 'blockers'])('服务端 %s 已变化时不向本机发送素材', async field => {
  await flushPromises(); await select(); await confirm()
  if (field === 'revision') mocks.get.mockResolvedValue({ ...record, revision: 3 })
  if (field === 'status') mocks.get.mockResolvedValue({ ...record, status: 'published' })
  if (field === 'blockers') mocks.check.mockResolvedValue({ blockers: ['请复核'] })
  await button('填入文案与素材').trigger('click'); await flushPromises()
  expect(mocks.request.mock.calls.some(call => call[0] === '/publisher/prepare')).toBe(false)
})
it('未保存变动会清空临时素材和确认，未复核、已发布记录禁用入口', async () => {
  await flushPromises(); await select(); await confirm()
  await wrapper.setProps({ dirty: true })
  expect(wrapper.findAll('img')).toHaveLength(0)
  expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2)
  expect(button('打开辅助发布窗口').attributes('disabled')).toBeDefined()
  await wrapper.setProps({ dirty: false, record: { ...record, status: 'published' } })
  expect(button('打开辅助发布窗口').attributes('disabled')).toBeDefined()
})

it('切换账号必须重新确认，不能携带上一个账号的确认直接上传', async () => {
  await flushPromises(); await select(); await confirm()
  mocks.request.mockImplementation(async route => route === '/accounts' ? { items: [
    { id:'account-test-1',name:'学习账号',archived:false }, { id:'account-test-2',name:'第二个账号',archived:false },
  ] } : { available:true,busy:false,session:{...session,account_id:route.includes('account-test-2')?'account-test-2':'account-test-1'} })
  await button('刷新账号列表').trigger('click'); await flushPromises()
  await wrapper.get('select[aria-label="辅助发布账号"]').setValue('account-test-2'); await flushPromises()
  for (const input of wrapper.findAll('input[type="checkbox"]')) expect((input.element as HTMLInputElement).checked).toBe(false)
  expect(button('填入文案与素材').attributes('disabled')).toBeDefined()
  expect(mocks.request.mock.calls.some(call=>call[0]==='/publisher/prepare')).toBe(false)
})

it('第一步传入的图片在文案编辑和重新保存时保留，但发布确认必须重做', async () => {
  await flushPromises()
  const selectedMedia = files.map(file => ({ file, url: 'blob:' + file.name }))
  await wrapper.setProps({ selectedMedia }); await confirm()
  await wrapper.setProps({ dirty: true })
  expect(wrapper.findAll('img')).toHaveLength(2)
  expect(URL.revokeObjectURL).not.toHaveBeenCalled()
  expect(button('填入文案与素材').attributes('disabled')).toBeDefined()
  for (const input of wrapper.findAll('input[type="checkbox"]')) expect((input.element as HTMLInputElement).checked).toBe(false)
  await wrapper.setProps({ dirty: false, record: { ...record, revision: 3 } })
  expect(wrapper.findAll('img')).toHaveLength(2)
  expect(wrapper.find('input[type="file"]').exists()).toBe(false)
  expect(button('填入文案与素材').attributes('disabled')).toBeDefined()
})
