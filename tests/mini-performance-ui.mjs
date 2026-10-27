/** Bounded rendering and resource loading in the built H5 app; no production traffic. */
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { mkdirSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const { chromium, expect } = createRequire(new URL('../web/package.json', import.meta.url))('@playwright/test')
const sharp = createRequire(new URL('../miniprogram/package.json', import.meta.url))('sharp')
const base = process.env.MINI_UI_BASE || 'http://127.0.0.1:8365'
assert.ok(['127.0.0.1', 'localhost'].includes(new URL(base).hostname))
const directory = new URL('../artifacts/mini-performance/', import.meta.url)
mkdirSync(directory, { recursive: true })
const output = name => fileURLToPath(new URL(name, directory))
const original = await sharp(Buffer.from(`<svg width="1200" height="1700"><rect width="1200" height="1700" fill="white"/><text x="180" y="150" font-size="52">Math practice · 40 pages</text>${Array.from({ length: 24 }, (_, i) => `<text x="160" y="${240 + i * 53}" font-size="34">${i + 1}.    ${17 + i} + ${4 + i} = ________</text>`).join('')}</svg>`)).jpeg({ quality: 90 }).toBuffer()
const thumbnail = await sharp(original).resize({ width: 320, height: 480, fit: 'inside' }).jpeg({ quality: 82 }).toBuffer()
const report = { checks: [], requests: [], errors: [], originalBytes: original.length, thumbnailBytes: thumbnail.length }
const browser = await chromium.launch({ headless: true })
const context = await browser.newContext({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true })
const page = await context.newPage()
page.on('pageerror', error => report.errors.push(error.message))
let releaseSession
const sessionGate = new Promise(resolve => { releaseSession = resolve })
const rows = Array.from({ length: 125 }, (_, i) => ({
  id: 'paper-' + i, title: '四十页口算练习 ' + (i + 1), grade: '小学三年级', subject: '数学', revision: 1,
  can_view: true, can_download: true, required_view: 'free', required_download: 'free', view_access: 'free', download_access: 'free',
  question_count: 960, page_count: 40, favorite: false, keyword: '加减法', answer_readiness: 'included', file_status: 'ready',
  thumbnail_url: '/api/v1/catalog/assets/cover-' + i, release_number: 1, download_mode: 'pdf', created_at: 1720000000, updated_at: 1720000000,
}))
await context.addInitScript(() => localStorage.setItem('lc-consumer-session-v2', 'local-performance-fixture'))
await context.route('**/*', route => {
  const url = new URL(route.request().url())
  return ['data:', 'blob:'].includes(url.protocol) || url.origin === new URL(base).origin ? route.continue() : route.abort()
})
await context.route('**/api/v1/**', async route => {
  const request = route.request(), url = new URL(request.url()), path = url.pathname
  report.requests.push({ path, query: url.search, authenticated: !!request.headers().authorization })
  if (path.startsWith('/api/v1/catalog/assets/') || path.startsWith('/api/v1/site/banners/')) {
    await new Promise(resolve => setTimeout(resolve, 50))
    return route.fulfill({ contentType: 'image/jpeg', body: path.includes('/original-') ? original : thumbnail })
  }
  let body
  if (path === '/api/v1/mini/me') {
    await sessionGate
    body = { id: 'reader', username: 'reader', avatar: '', has_password: true, membership: 'regular', is_vip: false }
  } else if (path === '/api/v1/site/home') body = {
    banner_mode: 'operations', banners: Array.from({ length: 8 }, (_, i) => ({ id: String(i), image_url: '/api/v1/site/banners/' + i + '/image', title: '每日练习 ' + (i + 1), target_type: 'none' })),
    notices: { banner: [], popup: [] }, dictionaries: { grades: ['小学三年级'], subjects: ['语文', '数学', '英语'] }, categories: [],
  }
  else if (path === '/api/v1/catalog/summary') body = { papers: 125, favorites: 0, downloads: 0, grades: ['小学三年级'], subjects: ['数学'], categories: [] }
  else if (path === '/api/v1/site/topics' || path === '/api/v1/site/catalog-tags') body = { items: [] }
  else if (path === '/api/v1/mini/messages') body = { items: [], total: 0, unread: 0, has_more: false }
  else if (path === '/api/v1/mini/events' || path.startsWith('/api/v1/mini/history/')) body = {}
  else if (path === '/api/v1/catalog/papers') {
    const start = Number((url.searchParams.get('cursor') || '').replace('page-', '') || url.searchParams.get('offset') || 0)
    const limit = Number(url.searchParams.get('limit') || 20)
    body = { items: rows.slice(start, start + limit), total: url.searchParams.get('pagination') === 'cursor' && url.searchParams.get('include_total') !== 'true' ? null : rows.length, has_more: start + limit < rows.length, next_cursor: start + limit < rows.length ? 'page-' + (start + limit) : null }
  } else if (path === '/api/v1/catalog/window') body = { items: request.postDataJSON().ids.map(id => rows.find(row => row.id === id)) }
  else if (path === '/api/v1/catalog/papers/paper-0') body = { ...rows[0], difficulty: 'medium', description: '原稿与选页缩略图分开加载。', assets: Array.from({ length: 40 }, (_, i) => ({ id: 'page-' + i, kind: 'page', page_number: i + 1, byte_size: original.length, mime_type: 'image/jpeg', url: '/api/v1/catalog/assets/original-' + i, thumbnail_url: '/api/v1/catalog/assets/thumb-' + i })) }
  else throw Error('Unhandled fixture request ' + path)
  await route.fulfill({ json: body })
})
try {
  await page.goto(base + '/#/pages/home/index')
  await expect(page.locator('.home-cards .paper-card')).toHaveCount(2)
  await expect(page.locator('.banner-photo')).toHaveCount(2)
  assert.equal(report.requests.filter(item => item.path.startsWith('/api/v1/site/banners/')).length, 2)
  releaseSession()
  await expect.poll(() => report.requests.some(item => item.path === '/api/v1/catalog/papers' && item.authenticated)).toBe(true)
  assert.equal(report.requests.filter(item => item.path === '/api/v1/site/home').length, 1)
  assert.equal(report.requests.filter(item => item.path === '/api/v1/site/topics').length, 1)
  report.checks.push('8 banners acquire only current and next; session restoration shares public home/topics')

  const changePapers = page.getByRole('button', { name: '换一组习题', exact: true })
  await expect(changePapers).toBeEnabled()
  const catalogReads = () => report.requests.filter(item => item.path === '/api/v1/catalog/papers')
  const beforeChange = catalogReads().length
  await changePapers.click()
  await expect(page.locator('.home-cards .paper-card').first()).toContainText(rows[2].title)
  assert.equal(catalogReads().length, beforeChange, 'second pair must reuse the first four rows')
  await changePapers.click()
  await expect(page.locator('.home-cards .paper-card').first()).toContainText(rows[4].title)
  await expect(page.locator('.home-cards .paper-card')).toHaveCount(2)
  const nextGroup = new URLSearchParams(catalogReads().at(-1).query)
  assert.equal(nextGroup.get('limit'), '4')
  assert.equal(nextGroup.get('cursor'), 'page-4')
  assert.equal(nextGroup.get('include_total'), 'false')
  await changePapers.click()
  await expect(page.locator('.home-cards .paper-card').first()).toContainText(rows[6].title)
  assert.equal(catalogReads().length, beforeChange + 1)
  report.checks.push('home pairs reuse four-row batches and fetch the next cursor only when exhausted')

  await page.goto(base + '/#/pages/paper/index?id=paper-0')
  await expect(page.locator('.detail-meta')).toContainText('进阶')
  await page.getByRole('button', { name: '查看完整习题预览' }).click()
  await expect(page.locator('.paper-reader')).toBeVisible()
  await expect(page.locator('.reader-pages uni-swiper-item')).toHaveCount(5)
  await expect(page.locator('.reader-image')).toHaveCount(2)
  await expect(page.locator('.reader-image image, .reader-image img').first()).toBeVisible()
  await page.getByRole('button', { name: '选择预览页码' }).click()
  await expect(page.locator('.reader-page-option')).toHaveCount(12)
  await expect(page.locator('.reader-thumb img').first()).toBeVisible()
  const originalRequests = report.requests.filter(item => item.path.includes('/original-'))
  assert.ok(new Set(originalRequests.map(item => item.path)).size <= 2, 'chooser must not request original pages')
  await page.locator('.chooser-controls').getByRole('button', { name: '下一组' }).click()
  await expect(page.locator('.reader-page-option')).toHaveCount(12)
  await page.locator('.reader-page-option').first().click()
  await expect(page.locator('.reader-jump')).toContainText('13 / 40')
  await expect(page.locator('.reader-pages uni-swiper-item')).toHaveCount(5)
  await expect(page.locator('.reader-image')).toHaveCount(3)
  for (let i = 14; i <= 20; i++) {
    await page.locator('.reader-controls').getByRole('button', { name: '下一页', exact: true }).click()
    await expect(page.locator('.reader-jump')).toContainText(i + ' / 40')
    await page.waitForTimeout(320)
  }
  // Native touch input exercises swiper change + animationfinish, including rebasing.
  const cdp = await context.newCDPSession(page)
  const swipe = async () => {
    const box = await page.locator('.reader-pages').boundingBox()
    const x = box.x + box.width * .8, y = box.y + box.height * .5
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] })
    for (let step = 1; step <= 8; step++) {
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: x - box.width * .65 * step / 8, y }] })
      await page.waitForTimeout(20)
    }
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
  }
  for (let i = 21; i <= 27; i++) {
    await swipe(); await expect(page.locator('.reader-jump')).toContainText(i + ' / 40')
    await page.waitForTimeout(650) // uni-swiper 默认动画为 500ms，等待 animationfinish 后再发下一次手势。
    await expect(page.locator('.reader-pages uni-swiper-item')).toHaveCount(5)
  }
  await page.screenshot({ path: output('reader-40-pages.png') })
  await page.getByRole('button', { name: '选择预览页码' }).click()
  await page.screenshot({ path: output('chooser-40-pages.png') })
  report.checks.push('40 pages: <=5 swiper containers, <=3 reading images, 12 thumbnails; cross-group jump, 7 button turns and 7 touch turns')

  const beforeCatalog = report.requests.length
  await page.goto(base + '/#/pages/library/index')
  await expect(page.locator('.paper-row')).toHaveCount(20)
  for (const count of [40, 60]) {
    await page.getByRole('button', { name: /加载更多/ }).click()
    await expect(page.locator('.paper-row')).toHaveCount(count)
  }
  await page.locator('.window-controls uni-button').filter({ hasText: '下一组' }).click()
  await expect(page.locator('.paper-row')).toHaveCount(20)
  await expect(page.locator('.paper-row').first()).toContainText('四十页口算练习 61')
  const pages = report.requests.slice(beforeCatalog).filter(item => item.path === '/api/v1/catalog/papers')
  const params = pages.map(item => new URLSearchParams(item.query))
  assert.deepEqual(params.map(item => item.get('cursor') || ''), ['', 'page-20', 'page-40', 'page-60'])
  assert.deepEqual(params.map(item => item.get('include_total')), ['true', 'false', 'false', 'true'])
  assert.ok(params.every(item => item.get('pagination') === 'cursor'))
  report.checks.push('125 catalog entries use cursor pages, count only group refreshes and retain at most 60 rows')
  assert.deepEqual(report.errors, [])
  writeFileSync(output('result.json'), JSON.stringify(report, null, 2))
  console.log(JSON.stringify({ checks: report.checks, originalBytes: original.length, thumbnailBytes: thumbnail.length, errors: report.errors }, null, 2))
} catch (error) {
  await page.screenshot({ path: output('failure.png') })
  writeFileSync(output('failure.json'), JSON.stringify({ error: String(error), ...report, text: await page.locator('body').innerText() }, null, 2))
  throw error
} finally { releaseSession(); await context.close(); await browser.close() }
