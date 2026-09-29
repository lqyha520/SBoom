import assert from 'node:assert/strict'
import test from 'node:test'
import { createFilePool } from '../src/services/file-pool'

function deferred() {
  let resolve!: (value: string) => void
  let reject!: (reason: Error) => void
  const promise = new Promise<string>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

test('concurrent images share a file until the last consumer releases it', async () => {
  let downloads = 0
  const disposed: string[] = []
  const files = createFilePool(async () => { downloads++; return 'temporary-image' }, file => disposed.push(file))
  const first = files.acquire('image')
  const second = files.acquire('image')
  assert.equal(await first.ready, await second.ready)
  assert.equal(downloads, 1)
  first.release()
  first.release()
  assert.deepEqual(disposed, [])
  second.release()
  assert.deepEqual(disposed, [])
  const next = files.acquire('image')
  await next.ready
  assert.equal(downloads, 1)
  next.release(); files.trim()
  assert.deepEqual(disposed, ['temporary-image'])
})

test('leaving during a download disposes its late file', async () => {
  const pending = deferred()
  const disposed: string[] = []
  const files = createFilePool(() => pending.promise, file => disposed.push(file))
  const handle = files.acquire('image')
  await Promise.resolve()
  handle.release()
  pending.resolve('late-image')
  await assert.rejects(handle.ready, /expired/)
  assert.deepEqual(disposed, ['late-image'])
})

test('logout clears files and stale failures cannot evict a new session download', async () => {
  const old = deferred()
  let downloads = 0
  const disposed: string[] = []
  const files = createFilePool(() => ++downloads === 1 ? old.promise : Promise.resolve('new-image'), file => disposed.push(file))
  const previous = files.acquire('image')
  await Promise.resolve()
  files.clear()
  const current = files.acquire('image')
  old.resolve('old-image')
  await assert.rejects(previous.ready, /expired/)
  assert.equal(await current.ready, 'new-image')
  const shared = files.acquire('image')
  assert.equal(await shared.ready, 'new-image')
  assert.equal(downloads, 2)
  files.clear()
  current.release()
  shared.release()
  assert.deepEqual(disposed, ['old-image', 'new-image'])
})

test('invalid images are evicted so retry downloads a fresh file', async () => {
  let downloads = 0
  const disposed: string[] = []
  const files = createFilePool(async () => 'file-' + ++downloads, file => disposed.push(file))
  const broken = files.acquire('image')
  await broken.ready
  broken.invalidate()
  broken.release()
  const retry = files.acquire('image')
  assert.equal(await retry.ready, 'file-2')
  assert.deepEqual(disposed, ['file-1'])
  retry.release()
})

test('network failures can be retried without retaining a rejected promise', async () => {
  let downloads = 0
  const files = createFilePool(async () => {
    if (++downloads === 1) throw new Error('offline')
    return 'downloaded'
  }, () => {})
  const failed = files.acquire('image')
  await assert.rejects(failed.ready, /offline/)
  const retry = files.acquire('image')
  failed.release()
  assert.equal(await retry.ready, 'downloaded')
  retry.release()
})

test('only the last consumer aborts an in-flight download, once', async () => {
  const pending = deferred()
  let aborted = 0
  const files = createFilePool((_key, _progress, registerCancel) => {
    registerCancel(() => { aborted++; pending.reject(new Error('aborted')) })
    return pending.promise
  }, () => {})
  const first = files.acquire('image'), second = files.acquire('image')
  const rejected = assert.rejects(first.ready, /aborted/)
  await Promise.resolve()
  first.release()
  assert.equal(aborted, 0)
  second.release(); second.release(); files.clear()
  await rejected
  assert.equal(aborted, 1)
})

test('clearing a pending download aborts it without evicting a replacement', async () => {
  const pending = deferred()
  let downloads = 0, aborted = 0
  const files = createFilePool((_key, _progress, registerCancel) => {
    if (++downloads > 1) return Promise.resolve('replacement')
    registerCancel(() => { aborted++; pending.reject(new Error('aborted')) })
    return pending.promise
  }, () => {})
  const previous = files.acquire('image')
  const rejected = assert.rejects(previous.ready, /aborted/)
  await Promise.resolve()
  files.clear()
  const current = files.acquire('image')
  await rejected
  previous.release()
  assert.equal(await current.ready, 'replacement')
  const shared = files.acquire('image')
  assert.equal(await shared.ready, 'replacement')
  assert.equal(downloads, 2); assert.equal(aborted, 1)
  current.release(); shared.release()
})

test('settled downloads are disposed without aborting their completed task', async () => {
  let aborted = 0
  const disposed: string[] = []
  const files = createFilePool(async (_key, _progress, registerCancel) => {
    registerCancel(() => { aborted++ })
    return 'completed'
  }, file => disposed.push(file))
  const handle = files.acquire('image')
  await handle.ready
  handle.release()
  assert.equal(aborted, 0); assert.deepEqual(disposed, [])
  files.trim(); assert.deepEqual(disposed, ['completed'])
})

test('leaving before the download starts avoids all network work', async () => {
  let downloads = 0
  const files = createFilePool(async () => { downloads++; return 'unused' }, () => {})
  const handle = files.acquire('image')
  handle.release()
  await assert.rejects(handle.ready, /expired/)
  assert.equal(downloads, 0)
})

test('invalidating a pending file aborts it and permits retry', async () => {
  const pending = deferred()
  let downloads = 0, aborted = 0
  const files = createFilePool((_key, _progress, registerCancel) => {
    if (++downloads > 1) return Promise.resolve('retry')
    registerCancel(() => { aborted++; pending.reject(new Error('aborted')) })
    return pending.promise
  }, () => {})
  const failed = files.acquire('image')
  const rejected = assert.rejects(failed.ready, /aborted/)
  await Promise.resolve()
  failed.invalidate(); failed.release()
  await rejected
  const retry = files.acquire('image')
  assert.equal(await retry.ready, 'retry'); assert.equal(aborted, 1)
  retry.release()
})

test('宽限期复用已释放文件，LRU 与内存清理不删除仍在显示的文件', async () => {
  const disposed: string[] = []
  const files = createFilePool(async key => key, file => disposed.push(file), { graceMs: 20, maxIdle: 1 })
  const active = files.acquire('active'); await active.ready
  const first = files.acquire('first'); await first.ready; first.release()
  const reused = files.acquire('first'); assert.equal(await reused.ready, 'first'); reused.release()
  const second = files.acquire('second'); await second.ready; second.release()
  assert.deepEqual(disposed, ['first'])
  await new Promise(resolve => setTimeout(resolve, 30))
  assert.deepEqual(disposed, ['first', 'second'])
  files.trim(); assert.equal(await active.ready, 'active')
  active.release(); files.clear(); assert.deepEqual(disposed, ['first', 'second', 'active'])
})
