import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import sharp from 'sharp'
import lucide from '@iconify-json/lucide/icons.json' with { type: 'json' }

const destination = fileURLToPath(new URL('../src/static/tabs/', import.meta.url))
await mkdir(destination, { recursive: true })
for (const name of ['house', 'files', 'folders', 'star', 'user-round', 'book-open', 'heart']) {
  for (const [suffix, color] of [['', '#637168'], ['-active', '#307e61']]) {
    const body = lucide.icons[name].body.replaceAll('currentColor', color)
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">${body}</svg>`
    await sharp(Buffer.from(svg)).resize(64, 64).png().toFile(`${destination}${name}${suffix}.png`)
  }
}

// Emitted as a Sass partial on purpose: WXSS only resolves `@import` targets that are
// themselves `.wxss`, so a plain `.css` file imported from app.wxss breaks the WeChat
// build with "编译 .wxss 文件错误". `@use`-ing a partial inlines the @font-face directly
// into the bundled app.wxss for both H5 and mp-weixin.
const wotFont = await readFile(fileURLToPath(new URL('../node_modules/@wot-ui/ui/components/wd-icon/iconfont.ttf', import.meta.url)))
await writeFile(fileURLToPath(new URL('../src/wot-font.scss', import.meta.url)),
  `/* Generated from Wot UI's bundled icon font (MIT). Run pnpm assets to rebuild. */\n` +
  `@font-face{font-family:lc-wot-icons;src:url(data:font/truetype;base64,${wotFont.toString('base64')}) format('truetype');font-weight:normal;font-style:normal}\n` +
  `.wd-icon:not(.wd-icon--css):not(.wd-icon--image){font-family:lc-wot-icons!important}\n`)

await writeFile(fileURLToPath(new URL('../src/static/THIRD_PARTY_NOTICES.txt', import.meta.url)),
  await readFile(fileURLToPath(new URL('../THIRD_PARTY_NOTICES.md', import.meta.url)), 'utf8'))
