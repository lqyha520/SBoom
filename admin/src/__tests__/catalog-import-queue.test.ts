import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthError } from '../api'
import { useCatalogImportQueue } from '../catalog-import-queue'
import * as api from '../catalog'
vi.mock('../catalog', async original => ({ ...await original<typeof import('../catalog')>(), importPublication: vi.fn(), attachImportedEdition: vi.fn() }))
const defaults = { grade: '三年级', subject: '数学', category_id: 'math', mode: 'student' as const }
const shared = { description: '练习', view_access: 'free', download_access: 'free' }
const pdf = (name: string, content = name) => new File(['%PDF-1.4\n' + content], name, { type: 'application/pdf' })
const detail = (id: string, title = id) => ({ id, title, revision: 1, status: 'draft' }) as api.CatalogDetail
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(api.importPublication).mockImplementation(async (_user, file, meta) => detail(file.name, meta.title))
  vi.mocked(api.attachImportedEdition).mockResolvedValue({ revision: 2, editions: [] })
})
describe('PDF 导入任务', () => {
  it('逐份保留下载方式，缺少网盘链接的文件不进入导入任务', async () => {
    const queue = useCatalogImportQueue(1, vi.fn())
    await queue.add([pdf('pdf.pdf')], defaults)
    await queue.add([pdf('link.pdf')], { ...defaults, download_mode: 'external' })
    expect(queue.pending).toHaveLength(1)
    queue.rows[1].meta.external_url = 'https://pan.example.com/share?a=1&b=2'
    queue.rows[1].meta.external_code = 'abcd'
    await queue.run(shared)
    expect(vi.mocked(api.importPublication).mock.calls.map(call => call[2].download_mode)).toEqual(['pdf', 'external'])
    expect(vi.mocked(api.importPublication).mock.calls[1][2]).toMatchObject({ external_url: 'https://pan.example.com/share?a=1&b=2', external_code: 'abcd' })
  })
  it('图片合成后只导入指定 PDF，其他待处理文件保持原状', async () => {
    const queue = useCatalogImportQueue(1, vi.fn())
    const existing = pdf('existing.pdf'), generated = pdf('images.pdf')
    await queue.add([existing, generated], defaults)
    queue.rows[1].meta.title = '图片合成习题'
    await queue.run(shared, false, queue.rows[1].id)
    expect(api.importPublication).toHaveBeenCalledTimes(1)
    const uploaded = vi.mocked(api.importPublication).mock.calls[0][1]
    expect(uploaded.name).toBe(generated.name)
    expect(await uploaded.text()).toBe(await generated.text())
    expect(vi.mocked(api.importPublication).mock.calls[0][2].title).toBe('图片合成习题')
    expect(queue.rows[0].state).toBe('queued')
    expect(queue.rows[0].created).toBeUndefined()
    expect(queue.rows[1].state).toBe('succeeded')
  })
  it('选择时拒绝空文件、超大文件、非 PDF 和重复内容，同名不同内容各自保留', async () => {
    const queue = useCatalogImportQueue(1, vi.fn())
    const large = pdf('large.pdf'); Object.defineProperty(large, 'size', { value: 33 * 1024 * 1024 })
    await queue.add([pdf('same.pdf', 'first'), pdf('same.pdf', 'second'), pdf('copy.pdf', 'first'), new File([], 'empty.pdf'), new File(['text'], 'bad.pdf'), large, pdf('bad.txt')], defaults)
    expect(queue.pending).toHaveLength(2)
    expect(new Set(queue.rows.map(row => row.id)).size).toBe(7)
    expect(queue.rows.slice(2).every(row => row.fileError)).toBe(true)
    queue.remove(queue.rows[0].id)
    expect(queue.rows).toHaveLength(6)
    expect(queue.pending).toHaveLength(2)
    expect(queue.rows[0].file.name).toBe('same.pdf')
    expect(api.importPublication).not.toHaveBeenCalled()
  })
  it('只重试失败文件，剩一份仍使用该文件的编辑标题和属性', async () => {
    const queue = useCatalogImportQueue(1, vi.fn())
    await queue.add([pdf('same.pdf', 'first'), pdf('same.pdf', 'second')], defaults)
    queue.rows[0].meta.title = '第一份'
    queue.rows[1].meta.title = '第二份自定义'; queue.rows[1].meta.grade = '四年级'
    vi.mocked(api.importPublication).mockResolvedValueOnce(detail('first')).mockRejectedValueOnce(new Error('网络断开')).mockResolvedValueOnce(detail('second'))
    await queue.run(shared)
    expect(queue.succeeded).toBe(1); expect(queue.failed).toHaveLength(1)
    await queue.run(shared, true)
    expect(api.importPublication).toHaveBeenCalledTimes(3)
    expect(vi.mocked(api.importPublication).mock.calls[2][2]).toMatchObject({ title: '第二份自定义', grade: '四年级' })
    expect(queue.succeeded).toBe(2)
  })
  it('停止后保留当前结果并跳过后续文件，继续时不重传成功项', async () => {
    const queue = useCatalogImportQueue(1, vi.fn())
    await queue.add([pdf('one.pdf'), pdf('two.pdf')], defaults)
    let finish!: (value: api.CatalogDetail) => void
    vi.mocked(api.importPublication).mockImplementationOnce((_user, _file, _meta, progress) => {
      progress?.(35)
      return new Promise(resolve => { finish = resolve })
    })
    const running = queue.run(shared)
    expect(queue.rows[0].progress).toBe(35)
    expect(queue.rows[0].state).toBe('uploading')
    queue.stop(); finish(detail('one')); await running
    expect(api.importPublication).toHaveBeenCalledTimes(1); expect(queue.rows[1].state).toBe('queued')
    await queue.run(shared)
    expect(queue.succeeded).toBe(2); expect(api.importPublication).toHaveBeenCalledTimes(2)
  })
  it('答案失败单独重试，沿用已创建的条目，成功后更新版本号', async () => {
    const created = vi.fn(), queue = useCatalogImportQueue(1, created)
    await queue.add([pdf('one.pdf')], defaults)
    await queue.setAnswer(queue.rows[0].id, pdf('answer.pdf'))
    vi.mocked(api.attachImportedEdition).mockRejectedValueOnce(new Error('附件失败')).mockResolvedValueOnce({ revision: 3, editions: [] })
    await queue.run(shared)
    expect(queue.rows[0].state).toBe('succeeded'); expect(queue.rows[0].answerState).toBe('failed')
    await queue.retryAnswer(queue.rows[0].id)
    expect(api.importPublication).toHaveBeenCalledTimes(1)
    expect(api.attachImportedEdition).toHaveBeenCalledTimes(2)
    expect(queue.rows[0].answerState).toBe('succeeded'); expect(queue.rows[0].created?.revision).toBe(3)
    expect(created).toHaveBeenLastCalledWith(expect.objectContaining({ revision: 3 }))
  })
  it('停止时尚未发送的答案仍可继续关联', async () => {
    const queue = useCatalogImportQueue(1, vi.fn())
    await queue.add([pdf('one.pdf')], defaults); await queue.setAnswer(queue.rows[0].id, pdf('answer.pdf'))
    vi.mocked(api.importPublication).mockImplementationOnce(async () => { queue.stop(); return detail('one') })
    await queue.run(shared)
    expect(api.attachImportedEdition).not.toHaveBeenCalled()
    expect(queue.rows[0].answerState).toBe('queued')
    await queue.retryAnswer(queue.rows[0].id)
    expect(api.attachImportedEdition).toHaveBeenCalledTimes(1)
  })
  it('批量应用不修改已成功的文件，未填必填项不发送请求', async () => {
    const queue = useCatalogImportQueue(1, vi.fn())
    await queue.add([pdf('one.pdf')], defaults); await queue.run(shared)
    await queue.add([pdf('two.pdf')], { ...defaults, grade: '' })
    await queue.run(shared); expect(api.importPublication).toHaveBeenCalledTimes(1)
    queue.apply({ grade: '六年级', category_id: 'other' })
    expect(queue.rows[0].meta.grade).toBe('三年级')
    await queue.run(shared)
    expect(vi.mocked(api.importPublication).mock.calls[1][2]).toMatchObject({ grade: '六年级', category_id: 'other' })
  })
  it('登录失效后停止后续导入，上传完成显示服务端处理阶段', async () => {
    const queue = useCatalogImportQueue(1, vi.fn())
    await queue.add([pdf('one.pdf'), pdf('two.pdf')], defaults)
    vi.mocked(api.importPublication).mockImplementationOnce(async (_u, _f, _m, progress) => {
      progress?.(100); expect(queue.rows[0].state).toBe('processing'); throw new AuthError('登录已过期')
    })
    await queue.run(shared)
    expect(api.importPublication).toHaveBeenCalledTimes(1); expect(queue.stopped).toBe(true)
  })
})
