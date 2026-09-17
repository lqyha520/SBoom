import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

function fixture(options: { compressFails?: boolean; encoded?: unknown; readFails?: boolean } = {}) {
  const source = readFileSync(new URL('../src/services/profile-photo.ts', import.meta.url), 'utf8')
  let include = true
  const code = source.split('\n').filter(line => {
    const marker = /\/\/ #ifdef (.*)/.exec(line)
    if (marker) { include = marker[1]!.trim() === 'MP-WEIXIN'; return false }
    if (line.includes('// #endif')) { include = true; return false }
    return include
  }).join('\n')
  const events: string[] = []
  const exports: Record<string, any> = {}
  vm.runInNewContext(ts.transpileModule(code, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText, {
    exports, require: () => ({ ApiError: Error }),
    uni: {
      getImageInfo(input: any) { events.push('inspect:' + input.src); input.success({ path: 'wxfile://selected-avatar', width: 3000, height: 2400 }) },
      compressImage(input: any) {
        events.push('compress')
        assert.equal(input.compressedWidth, 512)
        assert.equal(input.compressedHeight, 410)
        assert.equal(input.src, 'wxfile://selected-avatar')
        if (options.compressFails) input.fail({ errMsg: 'unavailable' })
        else input.success({ tempFilePath: 'wxfile://compressed-avatar' })
      },
      getFileSystemManager: () => ({ readFile(input: any) {
        events.push('read:' + input.filePath)
        assert.equal(input.encoding, 'base64')
        if (options.readFails) input.fail({})
        else input.success({ data: options.encoded ?? 'aW1hZ2U=' })
      } }),
    },
  })
  return { prepare: exports.prepareProfilePhoto as (path: string) => Promise<{ path: string; image: string }>, events }
}

test('native avatar selection compresses before reading and previews the uploaded file', async () => {
  const app = fixture()
  const photo = await app.prepare('http://tmp/selected')
  assert.equal(photo.path, 'wxfile://compressed-avatar')
  assert.equal(photo.image, 'aW1hZ2U=')
  assert.deepEqual(app.events, ['inspect:http://tmp/selected', 'compress', 'read:wxfile://compressed-avatar'])
})

test('unavailable native compression falls back to the explicitly selected image', async () => {
  const app = fixture({ compressFails: true })
  assert.equal((await app.prepare('wxfile://selected-avatar')).path, 'wxfile://selected-avatar')
  assert.equal(app.events[app.events.length - 1], 'read:wxfile://selected-avatar')
})

test('unreadable, empty and oversized native images fail without submitting invalid data', async () => {
  await assert.rejects(fixture({ readFails: true }).prepare('wxfile://selected'), /头像读取失败/)
  await assert.rejects(fixture({ encoded: '' }).prepare('wxfile://selected'), /头像读取失败/)
  await assert.rejects(fixture({ encoded: new ArrayBuffer(8) }).prepare('wxfile://selected'), /头像读取失败/)
  await assert.rejects(fixture({ encoded: 'A'.repeat(3 * 1024 * 1024) }).prepare('wxfile://selected'), /超过 2 MB/)
})
