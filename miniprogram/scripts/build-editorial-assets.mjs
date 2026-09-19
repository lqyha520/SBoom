import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import sharp from 'sharp'

// Recompose existing licensed artwork. No remote downloads or image API calls.
const output = fileURLToPath(new URL('../marketing/study-collection/', import.meta.url))
const notebook = await readFile(new URL('../src/static/illustrations/notebook.png', import.meta.url))
const photograph = await readFile(new URL('../src/static/banners/study.jpg', import.meta.url))
const notebookUri = `data:image/png;base64,${notebook.toString('base64')}`
const photoUri = `data:image/jpeg;base64,${photograph.toString('base64')}`
await mkdir(output, { recursive: true })

const campaigns = [
  { key: 'daily', kicker: '每日练习', headline: ['每天', '练一点'], caption: '把基础练熟，让进步发生',
    title: '口算练习，随时开始', subtitle: '先选年级，再挑一份合适的练习', action_label: '去练习', category: '每日口算',
    background: '#e8f2ed', ink: '#285743', muted: '#527b64', accent: '#cddfd3', symbol: '+',
    topic: '每日口算', description: '按年级挑选一份，练熟基础计算' },
  { key: 'reading', kicker: '阅读与积累', headline: ['读一读', '想一想'], caption: '从词句出发，发现文字的意思',
    title: '读懂文字，也学会表达', subtitle: '阅读理解与词句积累，慢慢练扎实', action_label: '去阅读', category: '阅读与积累',
    background: '#9ccded', ink: '#244e71', muted: '#396384', accent: '#cce2f2', symbol: 'Aa',
    topic: '阅读与积累', description: '读一段文字，积累词句与表达' },
  { key: 'unit', kicker: '单元巩固', headline: ['学一课', '练一练'], caption: '回顾一个单元，巩固每个知识点',
    title: '学过的知识，再巩固一次', subtitle: '按年级查找单元练习，跟上学习进度', action_label: '去巩固', category: '单元练习',
    background: '#f8efdf', ink: '#725733', muted: '#8a6b43', accent: '#edddc0', symbol: '✓',
    topic: '单元巩固', description: '按年级回顾单元知识，查漏补缺' },
]

function svg(campaign, width, height, cover = false) {
  const artX = cover ? 455 : 706, artY = cover ? 156 : 35, artSize = cover ? 355 : 420
  const title = cover ? `<text x="64" y="216" font-size="64" font-weight="700">${campaign.topic}</text>`
    : campaign.headline.map((line, index) => `<text x="76" y="207" transform="translate(0 ${index * 106})" font-size="92" font-weight="700">${line}</text>`).join('')
  const background = campaign.key === 'reading' && !cover
    ? `<image href="${photoUri}" width="1200" height="624" y="-62" preserveAspectRatio="xMidYMid slice"/>`
    : `<rect width="${width}" height="${height}" fill="${campaign.background}"/>
      <circle cx="${cover ? 688 : 955}" cy="${cover ? 348 : 242}" r="${cover ? 250 : 228}" fill="${campaign.accent}"/>
      <path d="M ${cover ? 492 : 732} ${cover ? 474 : 395} Q ${cover ? 550 : 774} ${cover ? 468 : 376} ${cover ? 630 : 820} ${cover ? 452 : 394}" stroke="${campaign.muted}" stroke-width="3" fill="none" opacity=".35"/>
      <image href="${notebookUri}" x="${artX}" y="${artY}" width="${artSize}" height="${artSize}"/>
      <g transform="translate(${cover ? 734 : 1052} ${cover ? 122 : 61}) rotate(12)"><rect width="74" height="74" rx="22" fill="#ffffff"/><text x="37" y="50" font-size="36" text-anchor="middle" fill="${campaign.ink}">${campaign.symbol}</text></g>`
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
    ${background}<g font-family="Microsoft YaHei, sans-serif" fill="${campaign.ink}">
    ${cover ? `<rect x="64" y="58" width="160" height="44" rx="22" fill="#ffffff" fill-opacity=".72"/><text x="144" y="88" font-size="24" text-anchor="middle">学习专题</text>` : ''}
    ${title}${cover ? `<text x="64" y="273" font-size="25" fill="${campaign.muted}">${campaign.description}</text>` : ''}
    <path d="M ${cover ? 66 : 80} ${cover ? 320 : 378} h 68" stroke="${campaign.ink}" stroke-width="4" stroke-linecap="round"/>
    </g></svg>`
}

for (const campaign of campaigns) {
  for (const [suffix, width, height, cover] of [['banner', 1200, 500, false], ['topic', 900, 600, true]]) {
    const source = svg(campaign, width, height, cover)
    const name = `${campaign.key}-${suffix}`
    await writeFile(`${output}/${name}.svg`, source)
    const result = await sharp(Buffer.from(source)).jpeg({ quality: 90, mozjpeg: true }).toFile(`${output}/${name}.jpg`)
    console.log(`${name}.jpg: ${width} × ${height}, ${(result.size / 1024).toFixed(1)} KiB`)
  }
}
await writeFile(`${output}/campaigns.json`, JSON.stringify(campaigns.map(({ key, title, subtitle, action_label, category, topic, description, kicker }) => ({
  key, kicker, title, subtitle, action_label, target_type: 'category', category,
  image: `${key}-banner.jpg`, image_fit: 'contain', topic, description, cover: `${key}-topic.jpg`,
  publish_initially: key === 'daily',
})), null, 2) + '\n')
