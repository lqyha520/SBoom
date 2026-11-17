import 'fake-indexeddb/auto'
import { File as NativeFile } from 'node:buffer'
import { beforeEach, expect, it, vi } from 'vitest'
import { cachePublicationFile, readPublicationFile, type PublicationMedia } from '../xhs-media-cache'

const reference: PublicationMedia = { id: 'local-file', asset_id: '', name: '练习.png', media_type: 'image/png', size_bytes: 3, last_modified: 12345 }
beforeEach(() => { vi.stubGlobal('File', NativeFile) })

it('恢复本机文件时保留原字节、名称及时间，并隔离管理员', async () => {
  const file = new File(['abc'], reference.name, { type: reference.media_type, lastModified: reference.last_modified })
  await cachePublicationFile(7, reference, file, [reference.id])
  const restored = await readPublicationFile(7, reference)
  expect(await restored?.text()).toBe('abc')
  expect(restored).toMatchObject({ name: reference.name, lastModified: 12345, type: 'image/png' })
  expect(await readPublicationFile(8, reference)).toBeNull()
  expect(await readPublicationFile(7, { ...reference, size_bytes: 4 })).toBeNull()
})
