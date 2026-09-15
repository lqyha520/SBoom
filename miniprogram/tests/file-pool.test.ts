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
  assert.deepEqual(disposed, ['temporary-image'])
  const next = files.acquire('image')
  await next.ready
  assert.equal(downloads, 2)
  next.release()
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
