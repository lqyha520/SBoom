import { createRequire } from 'node:module'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'
const require = createRequire(new URL('../web/package.json', import.meta.url))
const { chromium, expect } = require('@playwright/test')
const base = process.env.MINI_UI_BASE || 'http://127.0.0.1:5181'
const directory = new URL('../artifacts/mini-optimization/', import.meta.url)
mkdirSync(directory, { recursive: true })
const output = name => fileURLToPath(new URL(name, directory))
const report = { flows: [], screenshots: [], errors: [], requests: [] }
const browser = await chromium.launch({ headless: true })
let currentPage
try {
  const artwork = await browser.newPage({ viewport: { width: 595, height: 842 }, deviceScaleFactor: 1 })
  await artwork.setContent(`<html lang="zh"><style>body{margin:0;padding:40px;color:#222;font-family:Arial,"Microsoft YaHei",sans-serif}h1{font-size:24px;text-align:center;margin:10px 0 30px}.meta{border-bottom:2px solid #444;padding-bottom:18px;font-size:14px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:50px 25px;margin-top:40px;font-size:23px}footer{position:absolute;bottom:32px;text-align:center;width:515px;font-size:13px}</style><h1>小学一年级数学 · 加减法练习</h1><div class="meta">姓名：____________　日期：____________</div><h3>一、算一算</h3><div class="grid">${Array.from({ length: 12 }, (_, i) => `<div>${i + 3} + ${i % 5 + 1} = ____</div>`).join('')}</div><footer>第 1 页</footer></html>`)
  await artwork.screenshot({ path: output('worksheet.png') })
  await artwork.close()
  const image = readFileSync(output('worksheet.png'))
  const context = await browser.newContext({ viewport: { width: 375, height: 812 }, deviceScaleFactor: 1 })
  const now = Math.floor(Date.now() / 1000)
  let favorites = new Set(Array.from({ length: 24 }, (_, i) => 'paper-' + i))
  const groups = [{ id: 'g1', name: '期末复习', revision: 1, paper_count: 0 }]
  const assigned = new Map()
  let messageFailure = false, batchFailure = false
  let recentEnabled = true, homeEmpty = false
  let sessionGate = Promise.resolve()
  let sessionReleased = true
  let submitted = []
  const rows = Array.from({ length: 24 }, (_, i) => ({
    id: 'paper-' + i, revision: 1, title: `20 以内加减法练习 ${i + 1}`,
    grade: '小学一年级', subject: '数学', can_view: true, can_download: true,
    required_view: 'free', required_download: 'free', view_access: 'free', download_access: 'free',
    question_count: 12, page_count: 4, keyword: i === 1 ? '' : '20 以内加减法', answer_readiness: i % 2 ? 'separate' : 'included', created_at: now, updated_at: now,
    thumbnail_url: '/api/v1/catalog/assets/image-' + i, file_status: 'ready',
    category: '口算练习', download_mode: 'pdf', release_number: 1,
  }))
  const user = { id: 'audit-reader', username: 'audit-reader', nickname: '测试读者', avatar: '', has_password: true, has_wechat: true, membership: 'regular', is_vip: false, vip_expires_at: null, membership_status: 'regular' }
  await context.route('**/api/v1/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname
    const method = request.method(), data = request.postDataJSON?.()
    report.requests.push({ path, method, query: url.search, authorization: request.headers().authorization || '' })
    let body, status = 200
    if (path.startsWith('/api/v1/catalog/assets/')) {
      await route.fulfill({ status, contentType: 'image/png', body: image }); return
    }
    if (path === '/api/v1/mini/me') { await sessionGate; body = user }
    else if (path === '/api/v1/site/home') body = { banner_mode: 'welcome', banners: [], notices: { banner: [], popup: [] }, dictionaries: { grades: ['小学一年级', '小学二年级'], subjects: ['语文', '数学', '英语'] }, categories: [] }
    else if (path === '/api/v1/catalog/summary') body = { papers: rows.length, favorites: favorites.size, downloads: 8, unread: 0, grades: ['小学一年级', '小学二年级'], subjects: ['语文', '数学', '英语'], categories: [{ id: 'daily', name: '口算练习' }] }
    else if (path === '/api/v1/site/topics' || path === '/api/v1/site/catalog-tags') body = { items: [] }
    else if (path === '/api/v1/catalog/papers') {
      let result = rows
      if (homeEmpty || (!recentEnabled && url.searchParams.get('recent') === 'true')) result = []
      if (url.searchParams.get('favorite') === 'true') result = result.filter(row => favorites.has(row.id))
      if (url.searchParams.get('ungrouped') === 'true') result = result.filter(row => !assigned.has(row.id))
      if (url.searchParams.get('favorite_group')) result = result.filter(row => assigned.get(row.id) === url.searchParams.get('favorite_group'))
      const offset = Number(url.searchParams.get('offset') || 0), limit = Number(url.searchParams.get('limit') || 20)
      body = { items: result.slice(offset, offset + limit).map(row => ({ ...row, favorite: favorites.has(row.id), activity_at: now - 3600 })), total: result.length, has_more: offset + limit < result.length }
    } else if (path === '/api/v1/catalog/window') body = { items: rows.filter(row => data.ids.includes(row.id)).map(row => ({ ...row, favorite: favorites.has(row.id) })) }
    else if (/^\/api\/v1\/catalog\/papers\/paper-\d+$/.test(path)) {
      const row = rows.find(row => row.id === path.split('/').at(-1))
      body = { ...row, favorite: favorites.has(row.id), description: '20 以内加减法巩固练习，含学生版与答案版。', assets: [
        ...Array.from({ length: 4 }, (_, i) => ({ id: 'page-' + i, kind: 'page', page_number: i + 1, url: '/api/v1/catalog/assets/page-' + i, byte_size: image.length })),
        { id: 'pdf', kind: 'pdf', byte_size: 102400, url: '/api/v1/catalog/assets/file' },
      ], editions: [{ kind: 'original', label: '原稿', byte_size: 102400 }, { kind: 'student', label: '学生版', byte_size: 102400 }, { kind: 'answers', label: '答案版', byte_size: 51200 }] }
    } else if (path === '/api/v1/mini/favorite-groups') body = { items: groups }
    else if (path === '/api/v1/mini/favorites/batch') {
      if (batchFailure) { status = 503; body = { detail: { error: '模拟网络失败，请重试' } } }
      else {
        for (const id of data.ids) {
          if (data.action === 'remove') { favorites.delete(id); assigned.delete(id) }
          else if (data.group_id) assigned.set(id, data.group_id)
          else assigned.delete(id)
        }
        body = { count: data.ids.length }
      }
    } else if (path === '/api/v1/mini/requests') {
      if (method === 'POST') { submitted.push({ ...data, id: 'request-1', status: 'pending', created_at: now }); body = submitted.at(-1) }
      else body = { items: submitted, total: submitted.length, has_more: false }
    } else if (path === '/api/v1/mini/messages') {
      if (messageFailure) { status = 503; body = { detail: { error: '消息暂不可用' } } }
      else body = { items: [], total: 0, has_more: false, unread: 0 }
    } else if (path === '/api/v1/site/support') body = { revision: 1, wechat: 'study-support', phone: '', email: '', hours: '09:00 - 18:00', benefits: '会员资料服务' }
    else if (path === '/api/v1/mini/membership/plans') body = { items: [], checkout_enabled: false, ios_enabled: false }
    else if (path === '/api/v1/mini/events' || path.startsWith('/api/v1/mini/history/')) body = {}
    else { throw Error('Unhandled mock route: ' + method + ' ' + path) }
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  })
  const page = await context.newPage()
  currentPage = page
  page.on('pageerror', error => report.errors.push(error.message))
  await page.goto(base + '/')
  await page.evaluate(() => localStorage.setItem('lc-consumer-session-v2', 'isolated-test-token'))
  let releaseSession
  sessionGate = new Promise(resolve => { releaseSession = resolve })
  sessionReleased = false
  const coldRequests = report.requests.length
  await page.reload()
  await expect(page.locator('.paper-card-title').first()).toBeVisible()
  assert.equal(sessionReleased, false)
  await page.getByRole('button', { name: '最近上新', exact: true }).click()
  await expect.poll(() => report.requests.slice(coldRequests).some(item => item.path === '/api/v1/catalog/papers' && item.query.includes('sort=latest'))).toBe(true)
  assert.ok(report.requests.slice(coldRequests).filter(item => item.path === '/api/v1/catalog/papers').every(item => !item.authorization), 'Cold public reads must not carry a session token')
  sessionReleased = true
  releaseSession()
  await expect.poll(() => report.requests.slice(coldRequests).some(item => item.path === '/api/v1/catalog/papers' && item.authorization)).toBe(true)
  await page.getByRole('button', { name: '为你精选', exact: true }).click()
  report.flows.push('public home renders and sort remains usable while session recovery is pending')
  const go = async path => { await page.goto(base + '/#' + path); await page.waitForTimeout(350) }
  const screenshot = async name => {
    await page.waitForTimeout(350)
    await page.screenshot({ path: output(name + '.png'), fullPage: false })
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, name + ' overflow')
    report.screenshots.push(name)
  }
  for (const [width, height] of [[320, 568], [375, 812], [430, 932], [1024, 900]]) {
    await page.setViewportSize({ width, height })
    await go('/pages/home/index')
    await expect(page.locator('.paper-card-title').first()).toBeVisible()
    await page.locator('.home-search-row').scrollIntoViewIfNeeded()
    await page.mouse.move(0, 0)
    await expect(page.locator('.home-heading')).toHaveCount(0)
    await expect(page.locator('.home-banner')).toBeInViewport()
    await expect(page.locator('.welcome-art')).toBeVisible()
    const title = await page.locator('.paper-card-title').first().boundingBox()
    assert.ok(title.y + title.height < height - 68, 'Home first title should fit above tabbar: ' + JSON.stringify(title))
    const first = page.locator('.paper-card').first()
    await expect(first.locator('.paper-card-keyword')).toHaveCount(0)
    await expect(first.locator('.paper-card-meta')).toContainText('12 题 · 4 页')
    await expect(first.locator('.paper-answer')).toHaveText('含答案')
    assert.ok((await first.boundingBox()).height <= (height <= 680 ? 270 : 360), 'Featured cards must fit the responsive cover and metadata')
    assert.equal(await first.locator('.cover-sheet').evaluate(element => getComputedStyle(element).transform), 'none')
    assert.equal(await first.locator('.cover-sheet').evaluate(element => {
      const sheet = element.getBoundingClientRect(), cover = element.closest('.paper-cover').getBoundingClientRect()
      return sheet.left >= cover.left && sheet.right <= cover.right && sheet.top >= cover.top && sheet.bottom <= cover.bottom
    }), true, 'Full cover must fit without clipping')
    await expect.poll(() => page.locator('.home-cards .paper-cover').evaluateAll(elements => {
      const boxes = elements.map(element => element.getBoundingClientRect())
      return Math.max(Math.abs(boxes[0].left - boxes[1].left), Math.abs(boxes[0].width - boxes[1].width))
    }), { message: 'Cards with and without keywords must share cover geometry' }).toBeLessThan(1)
    await screenshot('home-' + width)
    await first.evaluate(element => element.scrollIntoView({ block: 'center' }))
    await expect(first.locator('.paper-card-meta')).toBeInViewport()
    await first.screenshot({ path: output('paper-card-' + width + '.png') })
  }
  report.flows.push('home first title and consistent stacked-cover geometry at 320/375/430/1024')
  await page.setViewportSize({ width: 375, height: 812 })
  await go('/pages/home/index')
  await page.getByRole('button', { name: '换一组习题', exact: true }).click()
  const selectedTitle = await page.locator('.paper-card-title').first().textContent()
  await page.locator('.paper-card-open').first().evaluate(element => element.scrollIntoView({ block: 'start' }))
  await page.mouse.move(0, 0)
  const cardTop = (await page.locator('.paper-card-open').first().boundingBox()).y
  await page.locator('.paper-card-open').first().click()
  await expect(page.locator('.detail-title')).toBeVisible()
  await page.goBack()
  await expect(page.locator('.paper-card-title').first()).toHaveText(selectedTitle)
  await expect(page.locator('.paper-card-open').first()).toBeInViewport()
  await expect.poll(async () => Math.abs((await page.locator('.paper-card-open').first().boundingBox()).y - cardTop)).toBeLessThan(3)
  report.flows.push('home selected group and card position survive detail return')
  recentEnabled = false
  await page.setViewportSize({ width: 375, height: 812 })
  await page.reload()
  await expect(page.locator('.paper-card-title').first()).toBeVisible()
  await expect(page.locator('.home-banner')).toBeVisible()
  await expect(page.locator('.welcome-title')).toHaveText('每天一份好练习')
  await page.locator('.home-search-row').scrollIntoViewIfNeeded()
  await screenshot('home-no-recent-375')
  homeEmpty = true
  await page.reload()
  await expect(page.locator('.empty-title')).toHaveText('新的练习正在准备中')
  await expect(page.getByRole('button', { name: /^进入习题库/ })).toBeVisible()
  await screenshot('home-empty-375')
  homeEmpty = false
  report.flows.push('home without browsing history and empty catalog retain navigation')
  await page.setViewportSize({ width: 320, height: 568 })
  await go('/pages/favorites/index')
  await expect(page.locator('.paper-row')).toHaveCount(20)
  const firstDate = await page.locator('.paper-topic').first().textContent()
  await page.locator('.paper-main').first().click()
  await expect(page.locator('.detail-title')).toBeVisible()
  await page.goBack()
  await expect(page.locator('.paper-topic').first()).toHaveText(firstDate)
  await page.mouse.wheel(0, -2000)
  await page.waitForTimeout(350)
  report.flows.push('activity date retained after detail return')
  await page.getByRole('button', { name: '批量整理', exact: true }).click()
  await page.locator('.paper-main').nth(0).click()
  await page.locator('.paper-main').nth(1).click()
  await expect(page.getByText('已选 2 份', { exact: true })).toBeVisible()
  await screenshot('batch-select-320')
  await page.getByRole('button', { name: '移至分组', exact: true }).click()
  await expect(page.locator('.batch-group').filter({ hasText: '期末复习' })).toBeVisible()
  await screenshot('batch-groups-320')
  await page.locator('.batch-group').filter({ hasText: '期末复习' }).click()
  await expect(page.getByText('批量整理', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '未分组', exact: true }).click()
  await expect(page.getByText('共 22 份习题', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '批量整理', exact: true }).click()
  await page.locator('.paper-main').first().click()
  batchFailure = true
  await page.locator('.batch-commands').getByRole('button', { name: '取消收藏', exact: true }).click()
  await page.getByText('确认', { exact: true }).click()
  await expect(page.locator('.batch-error')).toContainText('模拟网络失败')
  await expect(page.getByText('已选 1 份', { exact: true })).toBeVisible()
  await screenshot('batch-error-320')
  batchFailure = false
  await page.locator('.batch-commands').getByRole('button', { name: '取消收藏', exact: true }).click()
  await page.getByText('确认', { exact: true }).click()
  await expect(page.getByText('批量整理', { exact: true })).toBeVisible()
  assert.equal(favorites.size, 23)
  report.flows.push('batch assign, ungrouped filter, removal failure and retry')
  await go('/pages/library/index')
  await expect(page.locator('.sort-buttons')).toBeVisible()
  const touchSizes = await page.locator('.sort-choice, .filter-free, .topic-choice').evaluateAll(elements => elements.map(element => element.getBoundingClientRect().height))
  assert.ok(touchSizes.length && touchSizes.every(height => height >= 44), 'Catalog touch targets must be at least 44px high')
  await page.getByRole('button', { name: '选择年级', exact: true }).click()
  await page.getByRole('button', { name: '小学一年级', exact: true }).click()
  await page.getByText('数学', { exact: true }).first().click()
  await page.locator('input').first().fill('口算')
  await page.waitForTimeout(500)
  await page.getByRole('button', { name: '清除其他条件', exact: true }).click()
  await expect(page.locator('.search-grade-choice')).toContainText('一年级')
  await expect(page.locator('input').first()).toHaveValue('')
  await page.getByRole('button', { name: '更多筛选', exact: true }).click()
  await page.getByRole('button', { name: /重置全部条件/ }).click()
  await expect(page.locator('.search-grade-choice')).toContainText('全部年级')
  await screenshot('filters-reset-320')
  report.flows.push('temporary filter reset preserves scope, full reset clears scope')
  await go('/pages/paper/index?id=paper-0')
  await page.locator('.edition-summary').click()
  await page.getByRole('radio').filter({ hasText: '答案版' }).click()
  await expect(page.locator('.edition-summary')).toContainText('答案版')
  await expect(page.locator('.preview-pill')).toContainText('原稿预览')
  await expect(page.locator('.detail-dock')).toContainText(/下载\s*答案版/)
  await expect(page.locator('.file-guidance')).toContainText('可免费预览和下载')
  const previewButton = await page.locator('.preview-pill').boundingBox()
  const downloadDock = await page.locator('.detail-dock').boundingBox()
  assert.ok(previewButton.y + previewButton.height <= downloadDock.y, 'Preview action must fit above the download dock')
  await screenshot('detail-editions-320')
  await page.getByRole('button', { name: '查看完整习题预览' }).click()
  await expect(page.locator('.paper-reader')).toBeVisible()
  await page.getByRole('button', { name: '选择预览页码' }).click()
  await expect(page.locator('.reader-page-option')).toHaveCount(4)
  await screenshot('reader-thumbnails-320')
  await page.locator('.reader-page-option').nth(2).click()
  await expect(page.locator('.reader-jump')).toContainText('3 / 4')
  await page.getByRole('button', { name: '恢复适宽' }).click()
  await expect(page.locator('.reader-hint')).toHaveText('100%')
  await screenshot('reader-320')
  report.flows.push('edition selection, thumbnail page navigation and fit control')
  await go('/subpages/requests/index')
  await expect(page.locator('.request-form')).toBeVisible()
  await page.locator('.request-form input').first().fill('一年级看图列式')
  await page.locator('.request-form textarea').fill('需要带图片的加减法练习')
  await page.waitForTimeout(550)
  await screenshot('request-draft-320')
  await go('/pages/account/index')
  await go('/subpages/requests/index')
  await expect(page.locator('.request-form input').first()).toHaveValue('一年级看图列式')
  await expect(page.locator('.request-form textarea')).toHaveValue('需要带图片的加减法练习')
  await page.getByText('提交资料需求', { exact: true }).click()
  await expect(page.getByText('一年级看图列式', { exact: true })).toBeVisible()
  await go('/pages/account/index')
  await go('/subpages/requests/index')
  await page.getByRole('button', { name: '提交需求', exact: true }).click()
  await expect(page.locator('.request-form input').first()).toHaveValue('')
  assert.equal(submitted.length, 1)
  report.flows.push('request draft survives navigation and is cleared after successful submission')
  await go('/subpages/membership/index?contact=1')
  await expect(page.locator('.contact-sheet')).toBeVisible()
  await expect(page.getByText('study-support', { exact: true })).toBeVisible()
  await screenshot('contact-direct-320')
  report.flows.push('contact deep link opens contact sheet directly')
  messageFailure = true
  await go('/pages/account/index')
  await page.reload()
  await expect(page.locator('.quick-value').first()).toHaveText('23')
  await expect(page.getByRole('button', { name: '重试消息提醒' })).toBeVisible({ timeout: 10000 })
  await screenshot('account-partial-error-320')
  const beforeRetry = report.requests.length
  messageFailure = false
  await page.getByRole('button', { name: '重试消息提醒' }).click()
  await expect(page.getByRole('button', { name: '重试消息提醒' })).toHaveCount(0)
  assert.ok(report.requests.slice(beforeRetry).every(item => item.path === '/api/v1/mini/messages'))
  report.flows.push('account independent results and section-only retry')
  assert.deepEqual(report.errors, [])
  await context.close()
} catch (error) {
  report.failure = error.stack
  if (currentPage) await currentPage.screenshot({ path: output('failure.png'), fullPage: true }).catch(() => {})
  throw error
} finally {
  writeFileSync(output('browser-result.json'), JSON.stringify(report, null, 2))
  await browser.close()
}
console.log(JSON.stringify({ flows: report.flows, screenshots: report.screenshots, errors: report.errors }, null, 2))
