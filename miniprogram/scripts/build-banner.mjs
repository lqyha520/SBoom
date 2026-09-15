import { mkdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import sharp from 'sharp'

// Cinthya Gonzalez, Unsplash License. Attribution and source: THIRD_PARTY_NOTICES.md.
const source = 'https://images.unsplash.com/photo-1647559709298-c0e3dcb47092?fm=jpg&q=85&w=1400&fit=max'
const response = await fetch(source)
if (!response.ok) throw new Error(`Banner source returned ${response.status}`)
const original = Buffer.from(await response.arrayBuffer())
const { data, info } = await sharp(original).resize({ height: 520 }).modulate({ brightness: 1.08 }).ensureAlpha().raw().toBuffer({ resolveWithObject: true })
// Blend the photo's empty left edge into a flat backdrop without stretching its texture.
for (let y = 0; y < info.height; y++) {
  for (let x = 0; x < 100; x++) data[(y * info.width + x) * 4 + 3] = Math.round(255 * x / 100)
}
const photo = await sharp(data, { raw: info }).png().toBuffer()
const destination = fileURLToPath(new URL('../src/static/banners/', import.meta.url))
await mkdir(destination, { recursive: true })
await sharp({ create: { width: 1000, height: 520, channels: 3, background: '#9ccded' } })
  .composite([{ input: photo, left: 1000 - info.width, top: 0 }])
  .jpeg({ quality: 84, mozjpeg: true })
  .toFile(`${destination}study.jpg`)
console.log('Created static/banners/study.jpg (1000 x 520).')
