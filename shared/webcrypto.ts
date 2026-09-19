/**
 * 非安全上下文（http://<公网 IP>）下仍可用的 Web Crypto 兼容层。
 *
 * 背景：`crypto.randomUUID` 与 `crypto.subtle` 都带 [SecureContext] 标记，只有
 * HTTPS、localhost/127.0.0.1、file:// 才会暴露。用「http + 内网 IP」直连部署时它们
 * 是 `undefined`，直接调用会抛 `crypto.randomUUID is not a function`——而且往往发生在
 * 初始化早期，整个前端会连锁失效（工作台空白、草稿卡在「正在恢复」、退出登录被
 * 「草稿未保存」拦下）。
 *
 * 注意 `crypto.getRandomValues` **不受** SecureContext 限制，所以随机数依然取自
 * CSPRNG，不需要降级到 Math.random。
 */

let degradedWarned = false

function warnDegraded(api: string) {
  if (degradedWarned) return
  degradedWarned = true
  // 仅在真正走到回退分支时提示一次，避免刷屏
  console.warn(
    `[lc] 当前不是安全上下文，${api} 不可用，已启用兼容实现（熵源仍为 CSPRNG）。` +
    '改用 HTTPS 访问可避免该降级。',
  )
}

/** 生成 RFC 4122 v4 UUID；优先 `crypto.randomUUID`，非安全上下文回退到 `getRandomValues`。 */
export function randomId(): string {
  const webCrypto = globalThis.crypto
  if (typeof webCrypto?.randomUUID === 'function') return webCrypto.randomUUID()
  warnDegraded('crypto.randomUUID')

  const bytes = new Uint8Array(16)
  if (typeof webCrypto?.getRandomValues === 'function') {
    webCrypto.getRandomValues(bytes)
  } else {
    // 极老浏览器/受限沙箱的兜底；正常路径不会走到这里
    for (let i = 0; i < 16; i += 1) bytes[i] = Math.floor(Math.random() * 256)
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40 // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80 // variant 10
  const hex = Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

const K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
])

/** 纯 JS SHA-256（仅用于 `crypto.subtle` 不可用时的回退，行为与 WebCrypto 完全一致）。 */
function sha256Bytes(data: Uint8Array): Uint8Array {
  const hash = new Uint32Array([
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ])
  const bitLength = data.length * 8
  // 填充：0x80 + 若干 0x00，末尾 8 字节大端比特长度
  const padded = new Uint8Array(((data.length + 9 + 63) >> 6) << 6)
  padded.set(data)
  padded[data.length] = 0x80
  const view = new DataView(padded.buffer)
  view.setUint32(padded.length - 8, Math.floor(bitLength / 0x100000000), false)
  view.setUint32(padded.length - 4, bitLength >>> 0, false)

  const schedule = new Uint32Array(64)
  for (let offset = 0; offset < padded.length; offset += 64) {
    for (let i = 0; i < 16; i += 1) schedule[i] = view.getUint32(offset + i * 4, false)
    for (let i = 16; i < 64; i += 1) {
      const x = schedule[i - 15], y = schedule[i - 2]
      const s0 = ((x >>> 7) | (x << 25)) ^ ((x >>> 18) | (x << 14)) ^ (x >>> 3)
      const s1 = ((y >>> 17) | (y << 15)) ^ ((y >>> 19) | (y << 13)) ^ (y >>> 10)
      schedule[i] = (schedule[i - 16] + s0 + schedule[i - 7] + s1) >>> 0
    }
    let a = hash[0], b = hash[1], c = hash[2], d = hash[3]
    let e = hash[4], f = hash[5], g = hash[6], h = hash[7]
    for (let i = 0; i < 64; i += 1) {
      const S1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7))
      const ch = (e & f) ^ (~e & g)
      const t1 = (h + S1 + ch + K[i] + schedule[i]) >>> 0
      const S0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10))
      const maj = (a & b) ^ (a & c) ^ (b & c)
      const t2 = (S0 + maj) >>> 0
      h = g; g = f; f = e; e = (d + t1) >>> 0
      d = c; c = b; b = a; a = (t1 + t2) >>> 0
    }
    hash[0] = (hash[0] + a) >>> 0; hash[1] = (hash[1] + b) >>> 0
    hash[2] = (hash[2] + c) >>> 0; hash[3] = (hash[3] + d) >>> 0
    hash[4] = (hash[4] + e) >>> 0; hash[5] = (hash[5] + f) >>> 0
    hash[6] = (hash[6] + g) >>> 0; hash[7] = (hash[7] + h) >>> 0
  }

  const out = new Uint8Array(32)
  const outView = new DataView(out.buffer)
  for (let i = 0; i < 8; i += 1) outView.setUint32(i * 4, hash[i], false)
  return out
}

const toHex = (bytes: Uint8Array) =>
  Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('')

/** SHA-256 十六进制摘要；优先 `crypto.subtle`，非安全上下文回退到等价纯 JS 实现。 */
export async function sha256Hex(data: ArrayBuffer | Uint8Array): Promise<string> {
  // 归一化成「由普通 ArrayBuffer 支撑」的视图：TS 6 里裸 Uint8Array 是 Uint8Array<ArrayBufferLike>，
  // 而 subtle.digest 只接受 ArrayBufferView<ArrayBuffer>。入参是 ArrayBuffer 时零拷贝。
  let bytes: Uint8Array<ArrayBuffer>
  if (data instanceof Uint8Array) bytes = new Uint8Array(data)
  else bytes = new Uint8Array(data)
  const subtle = globalThis.crypto?.subtle
  if (subtle) return toHex(new Uint8Array(await subtle.digest('SHA-256', bytes)))
  warnDegraded('crypto.subtle')
  return toHex(sha256Bytes(bytes))
}
