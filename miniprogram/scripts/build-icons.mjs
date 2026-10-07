import { mkdir, readFile, writeFile, readdir } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import subsetFont from 'subset-font'
import sharp from 'sharp'
import lucide from '@iconify-json/lucide/icons.json' with { type: 'json' }

const destination = fileURLToPath(new URL('../src/static/tabs/', import.meta.url))
await mkdir(destination, { recursive: true })
const tabIcons = new Set(['house', 'book-open', 'heart', 'user-round'])
for (const name of tabIcons) {
  const variants = [['', '#637168'], ['-active', '#307e61']]
  if (tabIcons.has(name)) variants.push(['-selected', '#ffffff'])
  for (const [suffix, color] of variants) {
    const body = lucide.icons[name].body.replaceAll('currentColor', color)
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">${body}</svg>`
    await sharp(Buffer.from(svg)).resize(64, 64).png().toFile(`${destination}${name}${suffix}.png`)
  }
}

// Emitted as a Sass partial on purpose: WXSS only resolves `@import` targets that are
// themselves `.wxss`, so a plain `.css` file imported from app.wxss breaks the WeChat
// build with "编译 .wxss 文件错误". `@use`-ing a partial inlines the @font-face directly
// into the bundled app.wxss for both H5 and mp-weixin.
const wotRoot = fileURLToPath(new URL('../node_modules/@wot-ui/ui/components/', import.meta.url))
const iconCss = await readFile(path.join(wotRoot, 'wd-icon/iconfont.scss'), 'utf8')
const glyphs = new Map([...iconCss.matchAll(/\.wd-icon-([\w-]+):before\s*\{\s*content:\s*["']\\([\da-f]+)["']/gi)].map(match => [match[1], String.fromCodePoint(parseInt(match[2], 16))]))
async function sources(directory) {
  let text = ''
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const file = path.join(directory, entry.name)
    if (entry.isDirectory()) text += await sources(file)
    else if (/\.(vue|ts|scss)$/.test(entry.name) && entry.name !== 'wot-font.scss') text += '\n' + await readFile(file, 'utf8')
  }
  return text
}
let source = await sources(fileURLToPath(new URL('../src/', import.meta.url)))
const components = new Set()
for (;;) {
  const names = [...source.matchAll(/wd-([a-z][a-z-]+)/g)].map(match => match[1]).filter(name => !components.has(name))
  if (!names.length) break
  for (const name of names) { components.add(name); try { source += await sources(path.join(wotRoot, 'wd-' + name)) } catch { /* 样式类不一定是组件。 */ } }
}
const used = [...glyphs.keys()].filter(name => new RegExp(`["'\x60]${name}["'\x60]`).test(source)).sort()
const completeFont = await readFile(path.join(wotRoot, 'wd-icon/iconfont.ttf'))
const wotFont = await subsetFont(completeFont, used.map(name => glyphs.get(name)).join(''), { targetFormat: 'sfnt' })
console.log(`Wot 图标子集：${used.length}/${glyphs.size}，${completeFont.length} → ${wotFont.length} bytes`)
await writeFile(fileURLToPath(new URL('../src/static/icon-subset.json', import.meta.url)), JSON.stringify(used, null, 2) + '\n')
await writeFile(fileURLToPath(new URL('../src/wot-font.scss', import.meta.url)),
  `/* Generated from Wot UI's bundled icon font (MIT). Run pnpm assets to rebuild. */\n` +
  `@font-face{font-family:lc-wot-icons;src:url(data:font/truetype;base64,${wotFont.toString('base64')}) format('truetype');font-weight:normal;font-style:normal}\n` +
  `.wd-icon:not(.wd-icon--css):not(.wd-icon--image){font-family:lc-wot-icons!important}\n`)

await writeFile(fileURLToPath(new URL('../src/static/THIRD_PARTY_NOTICES.txt', import.meta.url)),
  await readFile(fileURLToPath(new URL('../THIRD_PARTY_NOTICES.md', import.meta.url)), 'utf8'))
