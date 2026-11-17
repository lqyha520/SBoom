import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import { createFilePool } from '../src/services/file-pool'

function fixture() {
  // Exercise the native document lifecycle; H5 download links use a separate branch.
  const source = readFileSync(new URL('../src/services/assets.ts', import.meta.url), 'utf8').replace(/\/\/ #ifdef H5[\s\S]*?\/\/ #endif/g, '')
  const tasks: { url: string; timeout: number; success: (result: { statusCode: number; tempFilePath: string }) => void; fail: () => void; aborted: number; progress?: (event: { progress: number; totalBytesWritten?: number }) => void }[] = []
  const opened: string[] = [], removed: string[] = []
  const performance: { kind: string; value: number }[] = []
  const exports: Record<string, any> = {}
  let generation = 0
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText, {
    exports,
    require: (id: string) => id === './file-pool' ? { createFilePool } : {
      ApiError: Error, apiUrl: (path: string) => path, authHeaders: () => ({}), authGeneration: () => generation, handleAuthFailure() {},
    },
    uni: {
      $emit(name: string, event: { kind: string; value: number }) { if (name === 'lc-performance') performance.push(event) },
      downloadFile(options: (typeof tasks)[number]) {
        const task = { ...options, aborted: 0 }; tasks.push(task)
        return { abort() { task.aborted++; task.fail() }, onProgressUpdate(callback: NonNullable<typeof task.progress>) { task.progress = callback } }
      },
      getFileSystemManager: () => ({ unlink({ filePath }: { filePath: string }) { removed.push(filePath) } }),
      openDocument({ filePath, success }: { filePath: string; success: () => void }) { opened.push(filePath); success() },
    },
  })
  return { api: exports, tasks, opened, removed, performance, changeSession() { generation++ } }
}

test('装饰图只占三个槽，PDF 使用预留槽并优先于排队预取', async () => {
  const { api, tasks } = fixture()
  const images = Array.from({ length: 7 }, (_, index) => api.acquireAsset('/image-' + index, 0))
  images.forEach(handle => { void handle.ready.catch(() => {}) })
  await Promise.resolve(); assert.equal(tasks.length, 3)
  const first = api.openPdf({ url: '/first-pdf' }, '第一份')
  await Promise.resolve(); assert.equal(tasks[3]!.url, '/first-pdf')
  tasks[3]!.success({ statusCode: 200, tempFilePath: '/first.pdf' }); await first
  const reading = api.acquireAsset('/reading', 2); void reading.ready.catch(() => {})
  await Promise.resolve(); assert.equal(tasks[4]!.url, '/reading')
  const second = api.openPdf({ url: '/second-pdf' }, '第二份')
  await Promise.resolve(); assert.equal(tasks.length, 5)
  tasks[0]!.success({ statusCode: 200, tempFilePath: '/image-0.jpg' })
  assert.equal(tasks[5]!.url, '/second-pdf')
  tasks[5]!.success({ statusCode: 200, tempFilePath: '/second.pdf' }); await second
  images.forEach(handle => handle.release()); reading.release(); api.clearAssetCache()
  assert.equal(api.assetCacheStats().queued, 0)
})

test('排队图片取消立即结束，预取升级为当前页后使用预留槽且不重复下载', async () => {
  const { api, tasks } = fixture()
  const images = Array.from({ length: 5 }, (_, index) => api.acquireAsset('/image-' + index, 0))
  images.forEach(handle => { void handle.ready.catch(() => {}) })
  await Promise.resolve(); assert.equal(tasks.length, 3)
  images[4].release(); await assert.rejects(images[4].ready, /取消/)
  images[3].prioritize(2); assert.equal(tasks[3]!.url, '/image-3')
  const shared = api.acquireAsset('/image-3', 2)
  tasks[3]!.success({ statusCode: 200, tempFilePath: '/image-3.jpg' })
  assert.equal(await shared.ready, await images[3].ready)
  assert.equal(tasks.length, 4)
  images.forEach(handle => handle.release()); shared.release(); api.clearAssetCache()
})

test('预留容量按普通下载计数，PDF 已占槽时仍可并行加载三张图片', async () => {
  const { api, tasks } = fixture()
  const pdf = api.openPdf({ url: '/pdf' }, '原稿')
  const rejected = assert.rejects(pdf)
  await Promise.resolve()
  const images = Array.from({ length: 4 }, (_, index) => api.acquireAsset('/image-' + index))
  images.forEach(handle => { void handle.ready.catch(() => {}) })
  await Promise.resolve()
  assert.equal(tasks.length, 4)
  api.cancelPdfDownload(); await rejected
  assert.equal(tasks.length, 4, '三个普通下载仍占槽，不能挤掉主动操作的预留容量')
  images.forEach(handle => handle.release()); api.clearAssetCache()
})

test('native downloads abort when the last image consumer leaves', async () => {
  const { api, tasks } = fixture()
  const first = api.acquireAsset('/image'), second = api.acquireAsset('/image')
  const rejected = assert.rejects(first.ready)
  await Promise.resolve()
  first.release(); assert.equal(tasks[0]!.aborted, 0)
  second.release(); await rejected
  assert.equal(tasks[0]!.aborted, 1)
})

test('免费观看但需会员下载的资料保留图片，只撤销该资料 PDF，不清除其他资料缓存', async () => {
  const { api, tasks, removed } = fixture()
  const a = '/api/v1/catalog/papers/a/assets/', b = '/api/v1/catalog/papers/b/assets/'
  const imageA = api.acquireAsset(a + 'image'), imageB = api.acquireAsset(b + 'image')
  await Promise.resolve()
  tasks[0]!.success({ statusCode: 200, tempFilePath: '/a.jpg' }); tasks[1]!.success({ statusCode: 200, tempFilePath: '/b.jpg' })
  await Promise.all([imageA.ready, imageB.ready])
  const pdfA = api.openPdf({ url: a + 'pdf', byte_size: 100 }, 'A'); await Promise.resolve()
  tasks[2]!.success({ statusCode: 200, tempFilePath: '/a.pdf' }); await pdfA
  const pdfB = api.openPdf({ url: b + 'pdf', byte_size: 100 }, 'B'); await Promise.resolve()
  tasks[3]!.success({ statusCode: 200, tempFilePath: '/b.pdf' }); await pdfB
  api.revalidateCatalogAssetCache('a', true, false)
  assert.deepEqual(removed, ['/a.pdf'])
  const reused = api.acquireAsset(a + 'image'); assert.equal(await reused.ready, '/a.jpg'); assert.equal(tasks.length, 4)
  api.revalidateCatalogAssetCache('a', false, false)
  assert.deepEqual(removed, ['/a.pdf', '/a.jpg'])
  assert.equal(await imageB.ready, '/b.jpg')
  reused.release(); imageA.release(); imageB.release(); api.clearAssetCache()
})

test('资料观看权限撤销时取消该资料的排队和在途图片，其他资料继续下载', async () => {
  const { api, tasks } = fixture()
  const handles = Array.from({ length: 5 }, (_, index) => api.acquireAsset('/api/v1/catalog/papers/' + (index < 4 ? 'a' : 'b') + '/assets/' + index, 0))
  const rejected = handles.slice(0, 4).map(handle => assert.rejects(handle.ready))
  await Promise.resolve(); assert.equal(tasks.length, 3)
  api.revalidateCatalogAssetCache('a', false, true); await Promise.all(rejected)
  assert.equal(api.assetCacheStats().queued, 0)
  const other = tasks.find(task => task.url.includes('/papers/b/'))!
  assert.ok(other); assert.equal(other.aborted, 0)
  other.success({ statusCode: 200, tempFilePath: '/b.jpg' }); await handles[4].ready
  handles.forEach(handle => handle.release()); api.clearAssetCache()
})

test('下载进度订阅共享在途图片，释放一个订阅者后其进度不再更新', async () => {
  const { api, tasks } = fixture(), first: number[] = [], second: number[] = []
  const a = api.acquireAsset('/shared', 2, (percent: number) => first.push(percent))
  await Promise.resolve(); tasks[0]!.progress!({ progress: 20, totalBytesWritten: 100 })
  const b = api.acquireAsset('/shared', 2, (percent: number) => second.push(percent))
  assert.deepEqual(second, [20]); a.release()
  tasks[0]!.progress!({ progress: 80, totalBytesWritten: 400 })
  assert.deepEqual(first, [20]); assert.deepEqual(second, [20, 80]); assert.equal(tasks.length, 1)
  tasks[0]!.success({ statusCode: 200, tempFilePath: '/shared.jpg' }); await b.ready
  b.release(); api.clearAssetCache()
})

test('PDF asset IDs get a long timeout without changing the API URL; images retain a short timeout', async () => {
  const { api, tasks } = fixture()
  const url = '/api/v1/catalog/papers/paper/assets/opaque-id'
  const pdf = api.openPdf({ url, kind: 'pdf' }, '原稿')
  await Promise.resolve()
  assert.equal(tasks[0]!.url, url)
  assert.equal(tasks[0]!.timeout, 60000)
  tasks[0]!.success({ statusCode: 200, tempFilePath: '/temporary.pdf' })
  await pdf
  const image = api.acquireAsset('/api/v1/catalog/papers/paper/assets/image-id')
  await Promise.resolve()
  assert.equal(tasks[1]!.timeout, 20000)
  tasks[1]!.success({ statusCode: 200, tempFilePath: '/temporary.jpg' })
  await image.ready
  image.release(); api.clearAssetCache()
})

test('leaving a page cancels its pending PDF and never opens a late document', async () => {
  const { api, tasks, opened, removed, performance } = fixture()
  const pending = api.openPdf({ url: '/pdf' }, '练习')
  const rejected = assert.rejects(pending)
  await Promise.resolve()
  api.cancelPdfDownload(); api.cancelPdfDownload()
  await rejected
  assert.equal(tasks[0]!.aborted, 1); assert.deepEqual(opened, [])
  assert.deepEqual(removed, [])
  assert.equal(performance.filter(item => item.kind === 'pdf_open').length, 0)
})

test('opening the native viewer does not cancel or delete its completed PDF', async () => {
  const { api, tasks, opened, removed, performance } = fixture()
  const pending = api.openPdf({ url: '/pdf' }, '练习')
  await Promise.resolve()
  tasks[0]!.success({ statusCode: 200, tempFilePath: '/temporary.pdf' })
  await pending
  api.cancelPdfDownload()
  assert.deepEqual(opened, ['/temporary.pdf']); assert.deepEqual(removed, [])
  assert.equal(tasks[0]!.aborted, 0)
  const timings = performance.filter(item => item.kind === 'pdf_open')
  assert.equal(timings.length, 1)
  assert.ok(timings[0]!.value >= 0)
  api.clearAssetCache()
  assert.deepEqual(removed, ['/temporary.pdf'])
})

test('a replaced PDF request cannot invalidate the newer shared file', async () => {
  const { api, tasks, opened, removed } = fixture()
  const first = api.openPdf({ url: '/pdf' }, 'old')
  const rejected = assert.rejects(first, /取消/)
  await Promise.resolve()
  const second = api.openPdf({ url: '/pdf' }, 'new')
  tasks[0]!.success({ statusCode: 200, tempFilePath: '/shared.pdf' })
  await rejected; await second
  assert.equal(tasks.length, 1); assert.deepEqual(opened, ['/shared.pdf'])
  assert.deepEqual(removed, [])
  api.clearAssetCache(); assert.deepEqual(removed, ['/shared.pdf'])
})

test('a late download from an old session is discarded before native preview', async () => {
  const { api, tasks, opened, removed, changeSession } = fixture()
  const pending = api.openPdf({ url: '/pdf' }, '练习')
  const rejected = assert.rejects(pending, /登录状态/)
  await Promise.resolve()
  changeSession(); tasks[0]!.success({ statusCode: 200, tempFilePath: '/stale.pdf' })
  await rejected
  assert.deepEqual(opened, []); assert.deepEqual(removed, ['/stale.pdf'])
})

test('32 MiB PDF 在弱网下有足够传输时间且保留原始资源 URL', async () => {
  const { api, tasks } = fixture()
  const pending = api.openPdf({ url: '/large.pdf', byte_size: 32 * 1024 * 1024 }, '大文件')
  await Promise.resolve()
  assert.equal(tasks[0]!.url, '/large.pdf')
  assert.equal(tasks[0]!.timeout, 532000)
  tasks[0]!.success({ statusCode: 200, tempFilePath: '/large.pdf' })
  await pending; api.clearAssetCache()
})
