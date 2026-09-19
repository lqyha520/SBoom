import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import { createFilePool } from '../src/services/file-pool'

function fixture() {
  // Exercise the native document lifecycle; H5 download links use a separate branch.
  const source = readFileSync(new URL('../src/services/assets.ts', import.meta.url), 'utf8').replace(/\/\/ #ifdef H5[\s\S]*?\/\/ #endif/g, '')
  const tasks: { success: (result: { statusCode: number; tempFilePath: string }) => void; fail: () => void; aborted: number }[] = []
  const opened: string[] = [], removed: string[] = []
  const exports: Record<string, any> = {}
  let generation = 0
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText, {
    exports,
    require: (id: string) => id === './file-pool' ? { createFilePool } : {
      ApiError: Error, apiUrl: (path: string) => path, authHeaders: () => ({}), authGeneration: () => generation, handleAuthFailure() {},
    },
    uni: {
      downloadFile(options: (typeof tasks)[number]) {
        const task = { ...options, aborted: 0 }; tasks.push(task)
        return { abort() { task.aborted++; task.fail() }, onProgressUpdate() {} }
      },
      getFileSystemManager: () => ({ unlink({ filePath }: { filePath: string }) { removed.push(filePath) } }),
      openDocument({ filePath, success }: { filePath: string; success: () => void }) { opened.push(filePath); success() },
    },
  })
  return { api: exports, tasks, opened, removed, changeSession() { generation++ } }
}

test('native downloads abort when the last image consumer leaves', async () => {
  const { api, tasks } = fixture()
  const first = api.acquireAsset('/image'), second = api.acquireAsset('/image')
  const rejected = assert.rejects(first.ready)
  await Promise.resolve()
  first.release(); assert.equal(tasks[0]!.aborted, 0)
  second.release(); await rejected
  assert.equal(tasks[0]!.aborted, 1)
})

test('leaving a page cancels its pending PDF and never opens a late document', async () => {
  const { api, tasks, opened, removed } = fixture()
  const pending = api.openPdf({ url: '/pdf' }, '练习')
  const rejected = assert.rejects(pending)
  await Promise.resolve()
  api.cancelPdfDownload(); api.cancelPdfDownload()
  await rejected
  assert.equal(tasks[0]!.aborted, 1); assert.deepEqual(opened, [])
  assert.deepEqual(removed, [])
})

test('opening the native viewer does not cancel or delete its completed PDF', async () => {
  const { api, tasks, opened, removed } = fixture()
  const pending = api.openPdf({ url: '/pdf' }, '练习')
  await Promise.resolve()
  tasks[0]!.success({ statusCode: 200, tempFilePath: '/temporary.pdf' })
  await pending
  api.cancelPdfDownload()
  assert.deepEqual(opened, ['/temporary.pdf']); assert.deepEqual(removed, [])
  assert.equal(tasks[0]!.aborted, 0)
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
