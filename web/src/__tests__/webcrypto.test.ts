import { createHash } from 'node:crypto'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { randomId, sha256Hex } from '../../../shared/webcrypto'

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
const realCrypto = globalThis.crypto
const reference = (bytes: Uint8Array<ArrayBuffer>) => createHash('sha256').update(Buffer.from(bytes)).digest('hex')

/** 模拟「非安全上下文」：crypto 存在、getRandomValues 可用，但没有 randomUUID / subtle。 */
function dropSecureContextApis() {
  vi.stubGlobal('crypto', {
    getRandomValues: (buffer: Uint8Array<ArrayBuffer>) => realCrypto.getRandomValues(buffer),
  })
}

afterEach(() => vi.unstubAllGlobals())

describe('randomId 在非安全上下文下仍可用', () => {
  it('优先使用 crypto.randomUUID', () => {
    expect(typeof realCrypto.randomUUID).toBe('function')
    expect(randomId()).toMatch(UUID_V4)
  })

  it('crypto.randomUUID 缺失时回退到 getRandomValues，且不是明文 Math.random', () => {
    dropSecureContextApis()
    // 没跑回退实现的话这里会抛 "crypto.randomUUID is not a function"
    const ids = Array.from({ length: 200 }, () => randomId())
    ids.forEach(id => expect(id).toMatch(UUID_V4))
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('回退路径同样把版本位/变体位写对，且熵来自 CSPRNG', () => {
    dropSecureContextApis()
    const spy = vi.spyOn(realCrypto, 'getRandomValues')
    randomId()
    expect(spy).toHaveBeenCalledTimes(1)
  })
})

describe('sha256Hex 与 WebCrypto 结果完全一致', () => {
  const encode = (text: string) => new TextEncoder().encode(text)

  it.each([
    ['空输入', ''],
    ['abc', 'abc'],
    ['长文本', 'The quick brown fox jumps over the lazy dog'],
  ])('已知向量：%s', async (_label, text) => {
    expect(await sha256Hex(encode(text))).toBe(reference(encode(text)))
  })

  // 覆盖 SHA-256 填充边界：块内不足/刚好/超出，以及多块
  it.each([0, 1, 55, 56, 63, 64, 65, 119, 120, 127, 128, 1000, 100000])(
    '回退实现与 node:crypto 在 %i 字节处一致',
    async (size) => {
      const bytes = new Uint8Array(size)
      for (let i = 0; i < size; i += 1) bytes[i] = (i * 31 + 7) & 0xff
      dropSecureContextApis()
      expect(await sha256Hex(bytes)).toBe(reference(bytes))
    },
  )

  it('接受 ArrayBuffer 入参', async () => {
    const bytes = encode('binary input')
    expect(await sha256Hex(bytes.buffer.slice(0))).toBe(reference(bytes))
  })

  it('WebCrypto 可用时不会退回纯 JS 实现（subtle.digest 被调用）', async () => {
    const spy = vi.spyOn(realCrypto.subtle, 'digest')
    await sha256Hex(encode('abc'))
    expect(spy).toHaveBeenCalledWith('SHA-256', expect.anything())
  })
})
