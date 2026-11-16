import { createRequire } from 'node:module'
import { createServer } from 'node:http'
import { spawn } from 'node:child_process'
import { readFile } from 'node:fs/promises'
import { mkdirSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { extname, resolve, sep } from 'node:path'
import assert from 'node:assert/strict'

const require = createRequire(new URL('../web/package.json', import.meta.url))
const { chromium, expect } = require('@playwright/test')
const root = resolve(fileURLToPath(new URL('../miniprogram/dist/build/h5/', import.meta.url)))
const directory = fileURLToPath(new URL('../artifacts/mini-optimization-20261113/', import.meta.url))
mkdirSync(directory, { recursive: true })
const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.png': 'image/png', '.jpg': 'image/jpeg', '.svg': 'image/svg+xml' }
const server = createServer(async (request, response) => {
  try {
    const file = resolve(root, '.' + decodeURIComponent(new URL(request.url, 'http://localhost').pathname))
    if (!file.startsWith(root + sep) && file !== root) { response.writeHead(403); response.end(); return }
    const target = file === root ? resolve(root, 'index.html') : file
    response.setHeader('Content-Type', types[extname(target)] || 'application/octet-stream')
    response.end(await readFile(target))
  } catch { response.writeHead(404); response.end() }
})
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
const base = process.env.MINI_UI_BASE || 'http://127.0.0.1:' + server.address().port
const browser = await chromium.launch({ headless: true })
const report = { flows: [], errors: [], requests: [] }
const now = Date.now() / 1000
const detail = { id: 'paper', title: '三年级数学单元练习', description: '先看到资料说明，再确认账号权益。', category: '数学', grade: '三年级', subject: '数学',
  required_view: 'free', required_download: 'vip', can_view: false, can_download: false, favorite: false,
  assets: [], editions: [], file_status: 'ready', created_at: now, updated_at: now, release_number: 1, answer_readiness: 'included', question_count: 12, page_count: 2 }
function deferred() { let resolve; const promise = new Promise(done => { resolve = done }); return { promise, resolve } }
async function fixture({ reader = false } = {}) {
  const context = await browser.newContext({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true })
  await context.addInitScript(() => localStorage.setItem('lc-consumer-session-v2', 'isolated-test-token'))
  // 使用 online/offline 通知模拟微信连接变化；Chrome 的 connection.type 不随离线模式改变。
  if (reader) await context.addInitScript(() => Object.defineProperty(navigator, 'connection', { get: () => undefined }))
  const state = { owner: 'reader-a', memberGate: Promise.resolve(), supportFail: false, referralDelay: 0, referralFinished: false, feedback: [], imageGates: new Map(), imageFailures: new Map(), imageRequests: [] }
  await context.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname, method = request.method()
    report.requests.push({ path, method, anonymous: !request.headers().authorization })
    if (path.startsWith('/api/v1/catalog/papers/paper/assets/')) {
      state.imageRequests.push(path)
      if (state.imageFailures.get(path) > 0) { state.imageFailures.set(path, state.imageFailures.get(path) - 1); await route.abort('failed'); return }
      await state.imageGates.get(path)?.promise
      const number = Number(path.split('-').at(-1)) + 1
      await route.fulfill({ status: 200, contentType: 'image/svg+xml', body: `<svg xmlns="http://www.w3.org/2000/svg" width="320" height="452"><rect width="320" height="452" fill="white"/><text x="30" y="80" font-size="26">Page ${number}</text><path d="M30 110h260M30 160h260M30 210h260M30 260h260" stroke="#888"/></svg>` })
      return
    }
    let body = {}, status = 200
    if (path === '/api/v1/mini/me') {
      await state.memberGate
      body = { id: state.owner, username: state.owner, nickname: '测试读者', avatar: '', has_password: true, has_wechat: true, is_vip: false, membership_status: 'regular' }
    } else if (path === '/api/v1/catalog/papers/paper') body = reader ? { ...detail, can_view: true, page_count: 6,
      thumbnail_url: '/api/v1/catalog/papers/paper/assets/thumb-0', assets: Array.from({ length: 6 }, (_, index) => ({
        id: 'page-' + index, kind: 'page', page_number: index + 1, byte_size: 262144,
        url: '/api/v1/catalog/papers/paper/assets/page-' + index, thumbnail_url: '/api/v1/catalog/papers/paper/assets/thumb-' + index,
      })) } : detail
    else if (path === '/api/v1/site/home') body = { banner_mode: 'welcome', banners: [], notices: { banner: [], popup: [] }, dictionaries: { grades: ['三年级'], subjects: ['数学'] }, categories: [] }
    else if (path === '/api/v1/catalog/summary') body = { papers: 1, favorites: 0, downloads: 0, unread: 0, grades: ['三年级'], subjects: ['数学'], categories: [] }
    else if (path === '/api/v1/catalog/papers') body = { items: [detail], total: 1, has_more: false }
    else if (path === '/api/v1/site/topics' || path === '/api/v1/site/catalog-tags') body = { items: [] }
    else if (path === '/api/v1/site/support') {
      if (state.supportFail) { status = 503; body = { detail: { error: '客服信息暂时不可用' } } }
      else body = { revision: 1, benefits: '完整原稿与PDF', wechat: 'test-support', phone: '', email: '', hours: '' }
    } else if (path === '/api/v1/mini/membership/plans') body = { items: [], checkout_enabled: false, ios_enabled: true }
    else if (path === '/api/v1/mini/feedback') {
      if (method === 'POST') { body = { id: 'feedback-1', ...request.postDataJSON(), status: 'pending', created_at: now, updated_at: now }; state.feedback.push(body) }
      else body = { items: state.feedback, total: state.feedback.length, has_more: false }
    } else if (path === '/api/v1/mini/referral-entry') {
      await new Promise(resolve => setTimeout(resolve, state.referralDelay))
      body = { visit_id: 'a'.repeat(32), destination: '/pages/paper/index?id=paper', tracked: true }
      state.referralFinished = true
    } else if (path === '/api/v1/mini/messages') body = { items: [], unread: 0, total: 0, has_more: false }
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  })
  const page = await context.newPage()
  page.on('pageerror', error => report.errors.push(error.message))
  return { context, page, state, go: path => page.goto(base + '/#' + path) }
}
try {
  const cold = await fixture(), gate = deferred()
  cold.state.memberGate = gate.promise
  try {
    await cold.go('/pages/paper/index?id=paper')
    await expect(cold.page.getByText('三年级数学单元练习', { exact: true })).toBeVisible()
    await expect(cold.page.getByText('正在恢复登录，稍后可收藏或下载。')).toBeVisible()
    assert.equal(report.requests.find(item => item.path === '/api/v1/catalog/papers/paper').anonymous, true)
    await cold.page.screenshot({ path: resolve(directory, 'detail-restoring-375.png'), fullPage: true })
    gate.resolve()
    await expect(cold.page.getByText('完整内容仅对有效 VIP 会员开放')).toHaveCount(0)
    await expect(cold.page.getByRole('button', { name: '收藏习题', exact: true })).toBeEnabled()
    cold.state.supportFail = true
    await cold.page.locator('.download-button .wd-button').click()
    await expect(cold.page.getByRole('button', { name: '会员套餐与卡密', exact: true })).toBeVisible()
    await expect(cold.page.getByRole('button', { name: '重试客服信息', exact: true })).toBeVisible()
    cold.state.supportFail = false
    await cold.page.getByRole('button', { name: '重试客服信息', exact: true }).click()
    await expect(cold.page.getByRole('button', { name: '重试客服信息', exact: true })).toHaveCount(0)
    await cold.page.screenshot({ path: resolve(directory, 'membership-recovered-375.png'), fullPage: true })
    report.flows.push('公开详情先于登录、恢复后核验、会员弹层客服独立重试')
  } finally { gate.resolve(); await cold.context.close() }

  const reader = await fixture({ reader: true }), imageGate = deferred()
  const slowPage = '/api/v1/catalog/papers/paper/assets/page-3'
  reader.state.imageGates.set(slowPage, imageGate)
  try {
    await reader.go('/pages/paper/index?id=paper')
    await reader.page.getByRole('button', { name: '查看完整习题预览', exact: true }).click()
    const view = reader.page.locator('.paper-reader')
    await expect(view).toBeVisible()
    await expect.poll(() => reader.state.imageRequests.includes('/api/v1/catalog/papers/paper/assets/page-2')).toBe(true)
    const next = view.locator('.reader-controls .wd-button').filter({ hasText: '下一页' })
    for (let index = 1; index <= 3; index++) {
      await next.click()
      await expect(view.locator('.reader-jump')).toContainText((index + 1) + ' / 6')
    }
    const current = view.locator('.private-image[aria-label="第 4 页原稿"]')
    await expect(current.locator('.image-status')).toHaveText('正在加载清晰原图…')
    await expect(current.locator('.image-status')).toBeInViewport({ ratio: 1 })
    await expect.poll(() => current.locator('.placeholder-image img').evaluate(image => image.naturalWidth)).toBeGreaterThan(0)
    await reader.page.screenshot({ path: resolve(directory, 'reader-thumbnail-wait-375.png'), fullPage: true })
    imageGate.resolve()
    await expect(current.locator('.image.is-loaded')).toBeVisible()
    await expect(current.locator('.image-status')).toHaveCount(0)
    await view.locator('.reader-controls .wd-button').filter({ hasText: '上一页' }).click()
    await expect(view.locator('.reader-jump')).toContainText('3 / 6')
    await next.click(); await expect(view.locator('.reader-jump')).toContainText('4 / 6')
    assert.equal(reader.state.imageRequests.filter(path => path === slowPage).length, 1, '重复翻页复用原图')
    report.flows.push('阅读器提前准备后两页、慢原图先显示缩略图、解码后替换、重复翻页复用')
    await view.getByRole('button', { name: '返回习题详情', exact: true }).click()
    await expect(view).toHaveCount(0)
    await reader.page.getByRole('button', { name: '查看完整习题预览', exact: true }).click()
    await expect(view.locator('.reader-jump')).toContainText('4 / 6')
    await expect(view.locator('.reader-resume')).toContainText('已继续上次第 4 页')
    await expect(view.locator('.reader-resume')).toBeInViewport({ ratio: 1 })
    await expect.poll(async () => Math.abs((await view.boundingBox()).y)).toBeLessThan(1)
    await reader.page.screenshot({ path: resolve(directory, 'reader-resumed-375.png'), fullPage: true })
    await view.getByRole('button', { name: '从第一页开始', exact: true }).click()
    await expect(view.locator('.reader-jump')).toContainText('1 / 6'); await expect(view.locator('.reader-resume')).toHaveCount(0)
    report.flows.push('续读页码提示与从第一页开始')
  } finally { imageGate.resolve(); await reader.context.close() }

  const recovery = await fixture({ reader: true })
  const failedImage = '/api/v1/catalog/papers/paper/assets/page-1'
  recovery.state.imageFailures.set(failedImage, 1)
  try {
    await recovery.go('/pages/paper/index?id=paper')
    await recovery.page.getByRole('button', { name: '查看完整习题预览', exact: true }).click()
    const view = recovery.page.locator('.paper-reader')
    await expect.poll(() => recovery.state.imageRequests.includes(failedImage)).toBe(true)
    await view.locator('.reader-controls .wd-button').filter({ hasText: '下一页' }).click()
    await expect(view.locator('.image-status').filter({ hasText: '图片加载失败，点击重试' })).toBeInViewport({ ratio: 1 })
    const reads = report.requests.filter(item => item.path === '/api/v1/catalog/papers/paper').length
    await recovery.context.setOffline(true)
    await expect(recovery.page.locator('.offline-notice')).toBeVisible()
    await recovery.context.setOffline(false)
    await expect(view.locator('.private-image[aria-label="第 2 页原稿"] .image.is-loaded')).toBeVisible()
    await expect(view.locator('.reader-jump')).toContainText('2 / 6')
    assert.equal(report.requests.filter(item => item.path === '/api/v1/catalog/papers/paper').length, reads, '网络恢复不重建阅读器')
    await view.getByRole('button', { name: '返回习题详情', exact: true }).click()
    await expect.poll(() => report.requests.filter(item => item.path === '/api/v1/catalog/papers/paper').length).toBe(reads + 1)
    report.flows.push('断网恢复重试当前页，保留阅读位置，关闭后补核验')
  } finally { await recovery.context.setOffline(false); await recovery.context.close() }

  const feedback = await fixture()
  try {
    await feedback.go('/subpages/support/index?paper=paper&kind=download')
    await feedback.page.locator('.feedback-input textarea').fill('下载后打开PDF显示空白页面')
    await expect(feedback.page.getByText('草稿已保存，仅保留在本机七天')).toBeVisible()
    await feedback.page.reload()
    await expect(feedback.page.locator('.feedback-input textarea')).toHaveValue('下载后打开PDF显示空白页面')
    await feedback.page.screenshot({ path: resolve(directory, 'feedback-restored-375.png'), fullPage: true })
    feedback.state.owner = 'reader-b'; await feedback.page.reload()
    await expect(feedback.page.locator('.feedback-input textarea')).toHaveValue('')
    feedback.state.owner = 'reader-a'; await feedback.page.reload()
    await expect(feedback.page.locator('.feedback-input textarea')).toHaveValue('下载后打开PDF显示空白页面')
    await feedback.page.getByRole('button', { name: '提交反馈', exact: true }).click()
    await expect(feedback.page.getByText('已提交，可在我的反馈中查看处理结果')).toBeVisible()
    await feedback.page.reload()
    await expect(feedback.page.locator('.feedback-input textarea')).toHaveValue('')
    report.flows.push('反馈草稿重启恢复、账号隔离、成功提交清理')
  } finally { await feedback.context.close() }

  for (const mode of ['normal', 'timeout', 'interaction']) {
    const referral = await fixture()
    referral.state.referralDelay = mode === 'normal' ? 0 : mode === 'timeout' ? 2000 : 900
    try {
      await referral.go('/pages/home/index?ref=a_' + 'b'.repeat(20))
      if (mode === 'interaction') await referral.page.locator('.home-search-row input').fill('口算')
      await expect.poll(() => referral.state.referralFinished).toBe(true)
      if (mode === 'normal') await expect(referral.page).toHaveURL(/pages\/paper\/index\?id=paper/)
      else await expect(referral.page).toHaveURL(/pages\/home\/index/)
      report.flows.push('推广落地：' + mode)
    } finally { await referral.context.close() }
  }
  assert.deepEqual(report.errors, [])
  if (process.argv.includes('--baseline')) {
    await new Promise((resolve, reject) => {
      const child = spawn(process.execPath, [fileURLToPath(new URL('mini-optimization-ui.mjs', import.meta.url))], {
        env: { ...process.env, MINI_UI_BASE: base }, stdio: 'inherit',
      })
      child.once('error', reject)
      child.once('exit', code => code === 0 ? resolve() : reject(new Error('原有浏览器回归未通过：' + code)))
    })
    report.flows.push('原有小屏、收藏整理、阅读器、需求草稿和客服回归')
  }
  report.passed = true
} catch (error) {
  report.passed = false; report.failure = error.stack
  throw error
} finally {
  writeFileSync(resolve(directory, 'browser-result.json'), JSON.stringify(report, null, 2))
  await browser.close(); await new Promise(resolve => server.close(resolve))
}
console.log(JSON.stringify({ passed: report.passed, flows: report.flows, errors: report.errors }, null, 2))
