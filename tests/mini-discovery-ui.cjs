/** 小程序检索与加载状态回归；仅运行于一次性 UI fixture，截取 320 / 390px 页面。 */
const assert = require('node:assert/strict')
const { mkdir, writeFile } = require('node:fs/promises')
const path = require('node:path')
const { createRequire } = require('node:module')
const { chromium, request, expect } = createRequire(path.resolve(__dirname, '../web/package.json'))('@playwright/test')

const base = process.env.DISCOVERY_UI_BASE || 'http://127.0.0.1:8364'
const output = process.env.DISCOVERY_UI_OUTPUT || path.resolve(__dirname, '../artifacts/mini-discovery')
const checks = []
const check = name => { checks.push(name); console.log('PASS ' + name) }

async function main() {
  assert.ok(['127.0.0.1', 'localhost'].includes(new URL(base).hostname))
  await mkdir(output, { recursive: true })
  const api = await request.newContext({ baseURL: base })
  assert.equal((await (await api.get('/health')).json()).fixture, true)
  assert.equal((await api.post('/api/v1/auth/login', { data: { username: 'admin_console', password: 'admin-pass-123' } })).status(), 200)
  const papers = (await (await api.get('/api/v1/catalog/papers')).json()).items
  assert.ok(papers.length >= 4, 'Start profile_ui_fixture with LC_SEED_MINI_FIXTURE=1')
  const tags = (await (await api.get('/api/v1/admin/catalog/tags')).json()).items
  const tag = tags.find(item => item.name === 'UI进位运算') || await (await api.post('/api/v1/admin/catalog/tags', { data: { kind: 'knowledge', name: 'UI进位运算' } })).json()
  assert.ok(tag.id)
  for (const paper of papers.slice(0, 2)) {
    const current = await (await api.get('/api/v1/admin/catalog/papers/' + paper.id)).json()
    assert.equal((await api.put('/api/v1/admin/catalog/papers/' + paper.id + '/labels', { data: { revision: current.revision, tag_ids: [tag.id] } })).status(), 200)
  }
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  let fail = true, hold = true, release
  const gate = new Promise(resolve => { release = resolve })
  const states = ['included', 'separate', 'missing', 'unknown']
  await context.route('**/*', async route => {
    const url = new URL(route.request().url())
    if (['data:', 'blob:'].includes(url.protocol)) return route.continue()
    if (url.origin !== new URL(base).origin) return route.abort()
    if (url.pathname === '/api/v1/catalog/papers') {
      if (hold) await gate
      if (fail) return route.fulfill({ status: 503, json: { detail: { error: '模拟网络暂时不可用' } } })
      const response = await route.fetch(), data = await response.json()
      data.items = data.items.map(item => ({ ...item, answer_readiness: states[papers.findIndex(p => p.id === item.id) % 4] }))
      return route.fulfill({ response, json: data })
    }
    if (url.pathname === '/api/v1/catalog/papers/' + papers[0].id) {
      const response = await route.fetch(), data = await response.json()
      // 覆盖版本选择的界面状态；实际版本匹配、下载权限由后端契约测试验证。
      data.answer_readiness = 'separate'
      data.editions = [{ kind: 'original', label: '练习版', byte_size: 1024, mode: 'student' }, { kind: 'answers', label: '答案解析版', byte_size: 2048, mode: 'answersOnly' }]
      return route.fulfill({ response, json: data })
    }
    return route.continue()
  })
  const noOverflow = async () => {
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1))
  }
  const shot = async name => {
    await page.waitForTimeout(350) // 等弹层和页面切换动画结束后截图。
    await noOverflow()
    await page.screenshot({ path: path.join(output, name + '.png'), fullPage: true })
  }
  try {
    await page.goto(base + '/#/pages/home/index')
    await expect(page.locator('.feed-caption')).toContainText('正在加载习题')
    hold = false; release()
    await expect(page.locator('.feed-caption')).toContainText('加载失败，请重试', { timeout: 15000 })
    await expect(page.locator('.home-empty')).toHaveCount(0)
    assert.ok(!(await page.locator('.feed-caption').innerText()).includes('0 份'))
    await shot('home-error-390')
    fail = false
    await page.getByRole('button', { name: '重试加载习题', exact: true }).click()
    await expect(page.locator('.home-cards .paper-card')).toHaveCount(2)
    await expect(page.locator('.home-cards .paper-answer').first()).toHaveText('含答案')
    await expect(page.locator('.home-cards .paper-answer').nth(1)).toHaveText('配套答案')
    await expect(page.locator('.home-more')).toHaveCount(0)
    await page.getByRole('button', { name: '选择适合的年级' }).click()
    await expect(page.getByRole('button', { name: '小学三年级', exact: true })).toBeVisible()
    await page.getByRole('button', { name: '小学三年级', exact: true }).click()
    await expect(page.locator('.feed-caption')).toContainText('小学三年级 · 共 4 份习题')
    await shot('home-390')
    check('首页首次加载、失败、重试、答案标识和年级入口')

    await page.locator('.paper-card-open').first().click()
    await page.locator('.edition-summary').click()
    await expect(page.locator('.edition-options [role="radio"]')).toHaveCount(2)
    await page.getByRole('radio', { name: /答案解析版/ }).click()
    await expect(page.locator('.edition-summary')).toContainText('答案解析版')
    await expect(page.locator('.edition-summary')).toContainText('预览为原稿')
    await expect(page.locator('.preview-pill')).toContainText('原稿预览')
    await expect(page.locator('.detail-heading')).toContainText('配套答案')
    await shot('detail-edition-390')
    await page.setViewportSize({ width: 320, height: 740 })
    await shot('detail-edition-320')
    check('详情答案状态和非原稿下载版本说明，320px 无横向溢出')

    fail = true
    await page.goBack()
    await expect(page.locator('.feed-caption')).toContainText('更新失败 · 上次共 4 份', { timeout: 15000 })
    await expect(page.locator('.home-cards .paper-card')).toHaveCount(2)
    await shot('home-retained-320')
    fail = false
    await page.getByRole('button', { name: '重试加载习题', exact: true }).click()
    await expect(page.locator('.feed-caption')).toContainText('共 4 份习题')
    check('返回首页刷新失败保留旧资料，并标明旧数量')

    fail = true
    await page.goto(base + '/#/pages/library/index')
    await expect(page.locator('.result-count')).toHaveText('加载失败，请重试', { timeout: 15000 })
    await expect(page.locator('.catalog-empty')).toHaveCount(0)
    fail = false
    await page.getByRole('button', { name: '重试加载', exact: true }).click()
    await expect(page.locator('.paper-row')).toHaveCount(4)
    assert.deepEqual(await page.locator('.paper-row .paper-answer').allTextContents(), ['含答案', '配套答案', '暂无答案', '答案待核对'])
    await shot('library-320')
    await page.locator('.paper-main').first().click()
    await expect(page.locator('.detail-title')).toBeVisible()
    fail = true
    await page.goBack()
    await expect(page.locator('.result-count')).toHaveText('更新失败 · 上次共 4 份', { timeout: 15000 })
    await expect(page.locator('.paper-row')).toHaveCount(4)
    fail = false
    await page.getByRole('button', { name: '重试加载', exact: true }).click()
    await expect(page.locator('.result-count')).toHaveText('共 4 份习题')
    // 排序改为选择器后，确认选择会发起新请求，免费筛选不会丢失排序。
    await page.getByRole('button', { name: '排序：精选', exact: true }).click()
    await page.locator('.uni-picker-content:visible').waitFor()
    await page.waitForTimeout(700) // 等待弹出动画及滚轮尺寸初始化。
    const latestResponse = page.waitForResponse(response => {
      const url = new URL(response.url())
      return url.pathname === '/api/v1/catalog/papers' && url.searchParams.get('sort') === 'latest' && response.ok()
    })
    const wheel = page.locator('.uni-picker-view-group:visible')
    if (await wheel.count()) {
      await wheel.dispatchEvent('wheel', { deltaY: 40 })
      await page.waitForTimeout(350) // 滚轮完成吸附后提交。
    } else await page.locator('.uni-picker-item:visible').filter({ hasText: /^最新$/ }).click()
    const confirmSort = page.locator('.uni-picker-action-confirm:visible')
    if (await confirmSort.count()) await confirmSort.click()
    await latestResponse
    await expect(page.getByRole('button', { name: '排序：最新', exact: true })).toBeVisible()
    await expect(page.locator('.paper-row')).toHaveCount(4)
    const freeResponse = page.waitForResponse(response => {
      const url = new URL(response.url())
      return url.pathname === '/api/v1/catalog/papers' && url.searchParams.get('sort') === 'latest' && url.searchParams.get('only_free') === 'true' && response.ok()
    })
    await page.getByRole('button', { name: '仅免费', exact: true }).click()
    await freeResponse
    await expect(page.getByRole('button', { name: '仅免费', exact: true })).toHaveAttribute('aria-pressed', 'true')
    await expect(page.locator('.result-count')).toHaveText('共 4 份习题')
    await shot('library-sorted-free-320')
    check('切换最新排序并叠加免费筛选，保留排序和列表结果')
    const input = page.locator('.search-field input')
    await input.fill('三年级 数学 UI进位运算')
    await input.press('Enter')
    await expect(page.locator('.result-count')).toHaveText('共 2 份习题')
    await expect(page.locator('.paper-row')).toHaveCount(2)
    await input.fill('没有这个知识点')
    await input.press('Enter')
    await expect(page.locator('.result-count')).toHaveText('共 0 份习题')
    await expect(page.locator('.catalog-empty')).toBeVisible()
    check('列表首次失败、重试、四种答案状态、真实跨字段标签搜索与空结果')

    // Exercise the real password-login return path; only the disposable fixture is mutated.
    await page.goto(base + '/#/pages/paper/index?id=' + papers[0].id)
    await page.locator('.edition-summary').click()
    await shot('edition-sheet-320')
    await page.getByRole('radio', { name: /答案解析版/ }).click()
    await page.locator('.download-button').getByRole('button').click()
    await expect(page.locator('.login-title')).toBeVisible()
    await page.locator('.consent-checkbox').click()
    await page.locator('.login-primary').click()
    await page.locator('.login-input input').nth(0).fill('ui_reader')
    await page.locator('.login-input input').nth(1).fill('reader-pass-123')
    await page.locator('.login-submit').getByRole('button').click()
    await expect(page.locator('.edition-summary')).toContainText('答案解析版')
    await expect(page.locator('.download-button')).toContainText(/继续下载\s*答案解析版/)
    assert.ok((await page.locator('.detail-dock').boundingBox()).height < 150, 'idle download dock stays compact')
    await shot('login-return-answers-320')
    const downloadRequests = []
    await context.route('**/api/v1/catalog/papers/*/download?*', route => {
      downloadRequests.push(new URL(route.request().url()).searchParams.get('edition'))
      return route.fulfill({ status: 503, json: { detail: { error: '模拟下载暂时不可用' } } })
    })
    await page.locator('.download-button').getByRole('button').click()
    await expect(page.locator('.download-button')).toContainText('重试下载')
    assert.deepEqual(downloadRequests, ['answers'])
    await page.locator('.download-button').getByRole('button').click()
    await expect.poll(() => downloadRequests.length).toBe(2)
    assert.deepEqual(downloadRequests, ['answers', 'answers'])
    check('真实登录返回保留答案版，继续下载与失败重试都请求答案版；底栏小于150px')

    await page.goto(base + '/#/pages/library/index')
    await page.locator('.search-field input').fill('')
    await page.locator('.search-field input').press('Enter')
    await expect(page.locator('.paper-row')).toHaveCount(4)
    await expect(page.locator('.search-history')).toHaveCount(0)
    await page.locator('.search-field input').fill('三年级 数学 UI进位运算')
    await page.locator('.search-field input').press('Enter')
    await expect(page.locator('.paper-row')).toHaveCount(2)
    await page.locator('.search-submit').tap()
    await page.locator('.search-field input').fill('')
    await page.locator('.search-field input').press('Enter')
    await expect(page.locator('.search-history')).toHaveCount(0)
    await page.locator('.search-field input').blur()
    await page.waitForTimeout(350) // Wot 的 blur 会延迟 150ms 发出，等这一轮失焦完成后重新点入。
    await page.locator('.search-field input').tap()
    await expect(page.locator('.history-track').getByRole('button')).toHaveCount(1)
    await expect(page.locator('.search-example')).toContainText('三年级 数学 进位')
    await shot('search-help-320')
    await page.locator('.history-track').getByRole('button').tap()
    await expect(page.locator('.paper-row')).toHaveCount(2)
    await expect(page.locator('.search-history')).toHaveCount(0)
    await page.getByRole('button', { name: '选择年级', exact: true }).click()
    await page.getByRole('button', { name: '小学三年级', exact: true }).click()
    await page.getByRole('button', { name: '清除其他条件', exact: true }).click()
    await expect(page.locator('.search-grade-choice')).toContainText('三年级')
    await expect(page.locator('.search-field input')).toHaveValue('')
    await expect(page.locator('.paper-row')).toHaveCount(4)
    await page.getByRole('button', { name: '更多筛选', exact: true }).click()
    await shot('filter-sheet-320')
    await page.getByRole('button', { name: /重置全部条件/ }).click()
    await expect(page.locator('.search-grade-choice')).toContainText('全部年级')
    await expect(page.locator('.catalog-sheet')).not.toBeVisible()
    check('历史仅聚焦展开，触屏点击搜索生效；快捷清除保留年级，面板全重置清除年级')

    // A fresh guest session taps favorite in the list and returns from login to that paper.
    await page.evaluate(() => localStorage.clear())
    await page.reload()
    await expect(page.locator('.paper-row')).toHaveCount(4)
    await page.locator('.paper-row .favorite-control').nth(2).tap()
    await expect(page.locator('.login-title')).toBeVisible()
    await page.locator('.consent-checkbox').click()
    await page.locator('.login-primary').click()
    await page.locator('.login-input input').nth(0).fill('ui_reader')
    await page.locator('.login-input input').nth(1).fill('reader-pass-123')
    await page.locator('.login-submit').getByRole('button').click()
    await expect(page.locator('.detail-favorite')).toContainText('已收藏')
    await page.reload()
    await expect(page.locator('.detail-favorite')).toContainText('已收藏')
    check('游客在列表收藏后登录自动完成收藏，刷新不会重复取消')
    assert.deepEqual(errors, [])
    await writeFile(path.join(output, 'ui-result.json'), JSON.stringify({ checks, errors }, null, 2))
  } catch (error) {
    await page.screenshot({ path: path.join(output, 'failure.png') })
    await writeFile(path.join(output, 'failure.json'), JSON.stringify({ error: String(error), errors, url: page.url(), text: await page.locator('body').innerText(), preferences: await page.evaluate(() => Object.keys(localStorage).filter(key => key.includes('preferences')).map(key => localStorage.getItem(key))) }, null, 2))
    throw error
  } finally {
    release(); await context.close(); await browser.close(); await api.dispose()
  }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
