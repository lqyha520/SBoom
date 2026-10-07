/** Full Banner editing -> anonymous home journey against a disposable UI fixture. */
const assert = require('node:assert/strict')
const { mkdir, writeFile } = require('node:fs/promises')
const path = require('node:path')
const { createRequire } = require('node:module')
const { chromium, request } = createRequire(path.resolve(__dirname, '../web/package.json'))('@playwright/test')
const sharp = createRequire(path.resolve(__dirname, '../miniprogram/package.json'))('sharp')

const base = process.env.HOME_UI_BASE || 'http://127.0.0.1:8361'
const output = path.resolve(__dirname, '../artifacts/home-redesign')
const checks = [], screenshots = [], errors = []
const check = (name, result = true) => { assert.ok(result, name); checks.push(name); console.log('PASS ' + name) }
const settle = page => page.waitForLoadState('networkidle')
async function shot(page, name, fullPage = false) {
  await page.waitForTimeout(350) // Let the bottom sheet and card transitions finish before visual capture.
  await page.screenshot({ path: path.join(output, name + '.png'), fullPage })
  screenshots.push(name + '.png')
}
async function noOverflow(page) {
  const size = await page.evaluate(() => ({ content: document.documentElement.scrollWidth, screen: innerWidth }))
  assert.ok(size.content <= size.screen + 1, JSON.stringify(size))
}
async function bannerLoaded(page, width) {
  await page.waitForFunction(width => {
    const frame = document.querySelector('.banner-photo')
    const img = frame?.querySelector('img')
    return img?.complete && img.naturalWidth === width && frame.getBoundingClientRect().height > 100
  }, width)
}
async function main() {
  assert.ok(['127.0.0.1', 'localhost'].includes(new URL(base).hostname))
  await mkdir(output, { recursive: true })
  const api = await request.newContext({ baseURL: base })
  assert.equal((await (await api.get('/health')).json()).fixture, true, 'Never mutate a real database')
  assert.equal((await api.post('/api/v1/auth/login', { data: { username: 'admin_console', password: 'admin-pass-123' } })).status(), 200)
  const list = async () => (await (await api.get('/api/v1/admin/site/banners')).json()).items
  const home = async () => (await (await api.get('/api/v1/site/home')).json()).banners
  async function updateBanner(item, changes) {
    const fields = ['revision', 'kicker', 'title', 'subtitle', 'action_label', 'target_type', 'target_value', 'image_fit', 'sort_order', 'is_visible']
    const response = await api.put('/api/v1/admin/site/banners/' + item.id, { data: Object.fromEntries(fields.map(key => [key, Object.hasOwn(changes, key) ? changes[key] : item[key]])) })
    assert.equal(response.status(), 200); return response.json()
  }
  for (const item of await list()) assert.equal((await api.delete('/api/v1/admin/site/banners/' + item.id, { params: { revision: item.revision } })).status(), 204)
  const papers = (await (await api.get('/api/v1/catalog/papers?limit=12')).json()).items
  const site = await (await api.get('/api/v1/site/home')).json()
  assert.ok(papers.length > 2)
  const existingCategories = (await (await api.get('/api/v1/admin/site/categories')).json()).items
  const categories = []
  for (const [name, description, icon] of [['同步练习', '跟上每一课的进度', 'book'], ['专项提升', '把重要的知识点练扎实', 'edit']]) {
    let category = existingCategories.find(item => item.name === name)
    if (!category) {
      const response = await api.post('/api/v1/admin/site/categories', { data: { name, description, icon, is_visible: true } })
      assert.equal(response.status(), 201); category = await response.json()
    }
    categories.push(category)
  }
  for (const [index, paper] of papers.slice(0, 6).entries()) {
    const item = await (await api.get('/api/v1/admin/catalog/papers/' + paper.id)).json()
    const result = await api.put('/api/v1/admin/catalog/papers/' + paper.id, { data: {
      revision: item.revision, title: item.title, description: item.description, status: item.status,
      featured: item.featured, view_access: item.view_access, download_access: item.download_access,
      category_id: categories[index % categories.length].id, confirm_publication: true,
    } })
    assert.equal(result.status(), 200)
  }
  const existingTopics = (await (await api.get('/api/v1/admin/experience/topics')).json()).items
  if (!existingTopics.length) {
    for (const [title, description, ids] of [
      ['新学期同步练习', '跟着课堂进度，把基础练扎实', papers.slice(0, 4).map(item => item.id)],
      ['阅读与表达', '读懂一段文字，也学会表达想法', papers.slice(4, 8).map(item => item.id)],
    ]) assert.equal((await api.post('/api/v1/admin/experience/topics', { data: { title, description, paper_ids: ids, is_visible: true } })).status(), 201)
  }
  const photo = path.join(output, 'sample-landscape.jpg')
  await sharp(path.resolve(__dirname, '../miniprogram/src/static/banners/study.jpg')).resize(1200, 500).jpeg({ quality: 88 }).toFile(photo)
  const portrait = path.join(output, 'sample-portrait.png')
  // Deliberately different dimensions and warm colors to exercise full-image rendering.
  await sharp({ create: { width: 900, height: 1200, channels: 3, background: '#e7b276' } }).composite([
    { input: Buffer.from('<svg width="900" height="1200"><rect x="45" y="45" width="810" height="1110" rx="24" fill="#fff1d9" stroke="#8b622f" stroke-width="6"/><text x="450" y="180" text-anchor="middle" font-size="60" fill="#835b2d">READING</text><path d="M180 360H720M180 440H720M180 520H720M180 600H720" stroke="#c3a174" stroke-width="12"/><text x="450" y="1060" text-anchor="middle" font-size="42" fill="#835b2d">FULL POSTER</text></svg>') },
  ]).png().toFile(portrait)

  const browser = await chromium.launch({ headless: true })
  const adminContext = await browser.newContext({ viewport: { width: 1365, height: 950 }, storageState: await api.storageState() })
  const readerContext = await browser.newContext({ viewport: { width: 375, height: 812 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true })
  await readerContext.tracing.start({ screenshots: true, snapshots: true })
  // 真实浏览器验收只允许访问当前一次性服务，防止本机构建的生产地址误发请求。
  for (const context of [adminContext, readerContext]) await context.route('**/*', route => {
    const url = new URL(route.request().url())
    return ['data:', 'blob:'].includes(url.protocol) || url.origin === new URL(base).origin ? route.continue() : route.abort()
  })
  const admin = await adminContext.newPage(), reader = await readerContext.newPage()
  await reader.clock.install()
  for (const page of [admin, reader]) { page.setDefaultTimeout(12000); page.on('pageerror', error => errors.push(error.message)) }
  const goHome = async () => {
    if (await reader.locator('.home-page').isVisible()) {
      await reader.getByRole('button', { name: '习题库', exact: true }).click()
      await reader.waitForURL('**/pages/library/index'); await settle(reader)
    }
    // TTL 内返回首页应命中缓存；推进墙钟验证发布更新，避免实际等待一分钟。
    await reader.clock.fastForward(65_000)
    const refreshed = reader.waitForResponse(response => response.url().endsWith('/api/v1/site/home'))
    await reader.getByRole('button', { name: '首页', exact: true }).click()
    await reader.waitForURL(url => url.hash === '#/' || url.hash.startsWith('#/pages/home/index'))
    await refreshed; await settle(reader)
  }
  const dialog = () => admin.getByRole('dialog', { name: /新建 Banner|编辑 Banner/ })
  async function setTarget(label) {
    await admin.getByRole('combobox', { name: 'Banner 跳转方式' }).click()
    await admin.getByRole('option', { name: label, exact: true }).click()
  }
  async function save() {
    await admin.getByRole('button', { name: '保存 Banner', exact: true }).click()
    await dialog().waitFor({ state: 'hidden' }); await settle(admin)
  }
  async function edit(title) {
    await admin.getByRole('button', { name: '编辑 ' + title, exact: true }).click()
    await dialog().waitFor()
  }
  try {
    await admin.goto(base + '/admin/'); await admin.getByRole('button', { name: '首页 Banner', exact: true }).click(); await settle(admin)
    await admin.getByRole('button', { name: '新建 Banner', exact: true }).click()
    check('New banners expose image selection before the first save', await admin.getByRole('button', { name: '选择图片', exact: true }).isVisible())
    await admin.getByLabel('选择 Banner 图片', { exact: true }).setInputFiles(photo)
    await admin.locator('.phone-preview img[src^="blob:"]').waitFor()
    await admin.getByRole('textbox', { name: 'Banner 标题', exact: true }).fill('新学期，练好每一课')
    await admin.getByRole('textbox', { name: 'Banner 副标题', exact: true }).fill('同步巩固，把每天的小进步留下来')
    await admin.getByRole('textbox', { name: 'Banner 上方小字', exact: true }).fill('新学期精选')
    await admin.getByRole('radio', { name: /居中裁切/ }).check()
    await setTarget('按关键词找习题')
    await admin.getByRole('textbox', { name: 'Banner 搜索关键词', exact: true }).fill('数学')
    await admin.getByRole('textbox', { name: 'Banner 按钮文案', exact: true }).fill('开始练习')
    check('Selecting a photo only changes the local preview until save', (await list()).length === 0)
    await admin.locator('.upload-area').scrollIntoViewIfNeeded(); await shot(admin, '01-admin-upload-preview')
    await save()
    let banner = (await list())[0]
    assert.equal(banner.image_fit, 'cover'); assert.ok(banner.image_url)
    check('Save publishes the chosen file, copy, fit and destination', (await home())[0].image_url === banner.image_url)
    await shot(admin, '02-admin-gallery')

    const imageRequests = []
    reader.on('request', request => { if (/\/site\/banners\/.*\/image/.test(request.url())) imageRequests.push(request.url()) })
    await reader.goto(base + '/#/pages/home/index'); await reader.locator('.paper-card').nth(1).waitFor(); await settle(reader)
    check('Welcome mode retains published banners without downloading hidden artwork', await reader.locator('.home-welcome').isVisible() && imageRequests.length === 0)
    check('The admin identifies published banners awaiting operations mode', await admin.getByText('待启用运营模式', { exact: true }).isVisible())
    await shot(reader, '00-home-welcome-375')
    await admin.getByRole('switch', { name: '启用运营 Banner', exact: true }).click()
    await expectMode()
    await goHome(); await bannerLoaded(reader, 1200)
    check('Visitors see the uploaded banner and real recommended papers', await reader.locator('.paper-card').count() === 2)
    const bounds = await reader.evaluate(() => {
      const image = document.querySelector('.banner-media').getBoundingClientRect(), copy = document.querySelector('.banner-body').getBoundingClientRect(), slide = document.querySelector('.banner-slide').getBoundingClientRect()
      return { imageBottom: image.bottom, imageWidth: image.width, imageHeight: image.height, copyTop: copy.top, copyLeft: copy.left, copyRight: copy.right, copyBottom: copy.bottom, slideLeft: slide.left, slideRight: slide.right, slideBottom: slide.bottom, slideWidth: slide.width }
    })
    check('Artwork fills its own row and readable copy stays below without overlap',
      Math.abs(bounds.imageWidth - bounds.slideWidth) < 2 && bounds.imageHeight === 150 &&
      bounds.copyTop >= bounds.imageBottom &&
      bounds.copyLeft >= bounds.slideLeft && bounds.copyRight <= bounds.slideRight && bounds.copyBottom <= bounds.slideBottom)
    await noOverflow(reader); await shot(reader, '03-home-photo-375')
    await reader.setViewportSize({ width: 320, height: 640 }); await noOverflow(reader); await shot(reader, '04-home-photo-320')
    await reader.setViewportSize({ width: 375, height: 812 })
    await reader.locator('.home-collections').scrollIntoViewIfNeeded(); await shot(reader, '05-home-collections')
    await reader.locator('.home-search-row').scrollIntoViewIfNeeded()
    const [navigation] = await Promise.all([
      reader.waitForResponse(response => response.url().includes('/api/v1/catalog/papers?') && new URL(response.url()).searchParams.get('q') === '数学'),
      reader.getByRole('button', { name: '新学期，练好每一课，开始练习', exact: true }).click(),
    ])
    assert.equal(navigation.status(), 200)
    check('Tapping anywhere on a configured banner opens the intended keyword results', reader.url().includes('/pages/library/index'))
    await goHome()
    const before = await reader.locator('.paper-card-open').first().getAttribute('aria-label')
    await reader.getByRole('button', { name: '换一组习题', exact: true }).click()
    check('Change-group selects different real papers', await reader.locator('.paper-card-open').first().getAttribute('aria-label') !== before)
    let contentReads = 0
    const countContent = req => { if (req.url().endsWith('/api/v1/site/home')) contentReads++ }
    reader.on('request', countContent)
    const latest = reader.waitForResponse(response => response.url().includes('/api/v1/catalog/papers?') && new URL(response.url()).searchParams.get('sort') === 'latest')
    await reader.getByRole('button', { name: '最近上新', exact: true }).click(); await latest; await settle(reader)
    check('Switching recommendation tabs leaves the banner and other home content intact', contentReads === 0 && await reader.locator('.banner-photo').count() === 1)
    reader.off('request', countContent)
    await reader.getByRole('button', { name: '选择年级', exact: true }).click()
    await reader.getByRole('dialog', { name: '选择年级', exact: true }).waitFor()
    check('The grade chooser shows every configured grade as a direct choice', await reader.locator('.grade-choice').count() === new Set(site.dictionaries.grades).size + 1)
    await shot(reader, '09-home-grade-chooser')
    const gradeLoad = reader.waitForResponse(response => response.url().includes('/api/v1/catalog/papers?') && new URL(response.url()).searchParams.get('grade') === papers[0].grade)
    await reader.getByRole('button', { name: papers[0].grade, exact: true }).click(); await gradeLoad; await settle(reader)
    assert.equal((await reader.locator('.search-grade-choice').innerText()).trim(), papers[0].grade.replace(/^小学/, ''))
    await goHome()
    check('A guest grade selection filters papers and survives leaving and returning home', (await reader.locator('.search-grade-choice').innerText()).trim() === papers[0].grade.replace(/^小学/, ''))
    await reader.getByRole('button', { name: '选择年级', exact: true }).click()
    await reader.getByRole('button', { name: '全部年级', exact: true }).click(); await settle(reader)
    await reader.getByRole('button', { name: '收藏习题', exact: true }).first().click()
    await reader.waitForURL('**/pages/login/index?**')
    check('Guest favorites ask for login while browsing stays public', reader.url().includes('returnTo='))
    await reader.goto(base + '/#/pages/home/index'); await bannerLoaded(reader, 1200)

    await edit(banner.title)
    await admin.getByLabel('选择 Banner 图片', { exact: true }).setInputFiles(portrait)
    await admin.locator('.phone-preview img[src^="blob:"]').waitFor()
    await admin.getByRole('radio', { name: /完整展示/ }).check()
    await shot(admin, '06-admin-portrait-preview')
    const oldUrl = banner.image_url
    await save(); banner = (await list())[0]
    assert.notEqual(banner.image_url, oldUrl)
    await goHome(); await bannerLoaded(reader, 900)
    check('Replacing the same banner id refreshes the image on returning home', banner.image_fit === 'contain')
    check('Portrait artwork uses full-image rendering without a fixed green overlay', await reader.locator('.banner-photo').evaluate(element => getComputedStyle(element.firstElementChild).backgroundSize === 'contain'))
    await shot(reader, '07-home-portrait-375')

    await edit(banner.title)
    await setTarget('不跳转（纯展示）'); await save(); await goHome()
    check('A pure-display banner has no misleading button or navigation', await reader.locator('.banner-hit, .banner-cta').count() === 0)
    const secondResult = await api.post('/api/v1/admin/site/banners', { data: { title: '阅读，从一小步开始', subtitle: '把每次阅读变成积累', target_type: 'subject', target_value: '语文', sort_order: 30 } })
    assert.equal(secondResult.status(), 201)
    const second = await secondResult.json()
    await goHome(); await reader.getByRole('button', { name: '下一张 Banner', exact: true }).click()
    await reader.waitForFunction(() => document.querySelectorAll('.banner-dot')[1]?.getAttribute('aria-pressed') === 'true')
    check('Manual carousel controls select the next configured banner', await reader.locator('.banner-dot').count() === 2)
    const subjectNav = reader.waitForResponse(response => response.url().includes('/api/v1/catalog/papers?') && new URL(response.url()).searchParams.get('subject') === '语文')
    await reader.getByRole('button', { name: '阅读，从一小步开始，去看看', exact: true }).click(); await subjectNav
    check('A subject banner opens the correct subject results')
    assert.equal((await api.delete('/api/v1/admin/site/banners/' + second.id, { params: { revision: second.revision } })).status(), 204)

    await reader.route('**/api/v1/site/topics', route => route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":{"error":"Fixture unavailable"}}' }))
    await goHome(); await reader.locator('.home-status').waitFor(); await reader.locator('.paper-card').nth(1).waitFor()
    check('Optional topic failures leave search, banners and papers usable', await reader.locator('.paper-card:visible').count() === 2 && await reader.locator('.home-status').isVisible())
    await reader.unroute('**/api/v1/site/topics')
    await reader.locator('.home-status').getByText('重试', { exact: true }).click(); await reader.locator('.home-status').waitFor({ state: 'hidden' })
    check('Retry restores the failed home section', await reader.locator('.collection-card').count() >= 2)
    const categoryNav = reader.waitForResponse(response => response.url().includes('/api/v1/catalog/papers?') && new URL(response.url()).searchParams.get('category') === categories[0].id)
    await reader.locator('.category-entry').filter({ hasText: categories[0].name }).click(); await categoryNav
    check('Category cards open the configured category with real published papers')
    await goHome()
    await reader.locator('.collection-card').first().click()
    await reader.waitForURL('**/pages/topic/index?**')
    check('Curated collections open their own topic page')
    await reader.goto(base + '/?home-ui=errors#/pages/home/index'); await bannerLoaded(reader, 900)
    await reader.route('**/api/v1/site/banners/*/image?v=*', route => route.fulfill({ status: 503, body: 'fixture image unavailable' }))
    await reader.reload(); await reader.locator('.banner-image-placeholder').waitFor(); await settle(reader)
    check('Image download failures retain readable copy without broken images', await reader.locator('.banner-photo').count() === 0 && await reader.locator('.banner-title').innerText() === banner.title)
    await reader.unroute('**/api/v1/site/banners/*/image?v=*'); await goHome(); await bannerLoaded(reader, 900)
    await reader.route('**/api/v1/site/home', route => route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":{"error":"Fixture home unavailable"}}' }))
    await reader.reload(); await reader.locator('.home-status').waitFor(); await reader.locator('.paper-card').nth(1).waitFor()
    check('Unavailable banner configuration still permits browsing the catalog', await reader.locator('.home-welcome').isVisible() && await reader.locator('.paper-card').count() === 2)
    await reader.unroute('**/api/v1/site/home'); await reader.locator('.home-status').getByText('重试', { exact: true }).click(); await reader.locator('.home-status').waitFor({ state: 'hidden' })

    await admin.getByRole('button', { name: '刷新 Banner', exact: true }).click(); await settle(admin)
    banner = (await list())[0]
    await edit(banner.title)
    await admin.getByLabel('选择 Banner 图片', { exact: true }).setInputFiles(photo)
    await admin.locator('.phone-preview img[src^="blob:"]').waitFor()
    await dialog().getByRole('button', { name: '取消', exact: true }).click()
    check('Cancel discards a selected replacement without uploading it', (await list())[0].revision === banner.revision)

    const originalCopy = banner
    banner = await updateBanner(banner, { title: '长标题'.repeat(13), kicker: '上方小字'.repeat(6), subtitle: '副标题说明'.repeat(12), target_type: 'keyword', target_value: '数学', action_label: '去看看'.repeat(4) })
    await goHome(); await bannerLoaded(reader, 900); await reader.setViewportSize({ width: 320, height: 640 })
    const copyBounds = await reader.locator('.banner-body').evaluate(element => ({ content: element.scrollHeight, frame: element.clientHeight }))
    check('Maximum-length copy stays inside the banner at 320 px', copyBounds.content <= copyBounds.frame + 1)
    await noOverflow(reader); await shot(reader, '10-home-long-copy-320')
    await reader.setViewportSize({ width: 375, height: 812 })
    banner = await updateBanner(banner, { ...originalCopy, revision: banner.revision })
    await admin.getByRole('button', { name: '刷新 Banner', exact: true }).click(); await settle(admin)
    await edit(banner.title)
    await admin.getByLabel('选择 Banner 图片', { exact: true }).setInputFiles(photo)
    await admin.locator('.phone-preview img[src^="blob:"]').waitFor()
    banner = await updateBanner(banner, { subtitle: '另一位管理员已更新文案' })
    await admin.getByRole('button', { name: '保存 Banner', exact: true }).click(); await admin.locator('.editor-error').waitFor()
    check('A stale editor cannot overwrite a newer update or upload its pending photo', (await list())[0].revision === banner.revision && await admin.locator('.phone-preview img[src^="blob:"]').count() === 1)
    await dialog().getByRole('button', { name: '取消', exact: true }).click()
    await admin.getByRole('button', { name: '刷新 Banner', exact: true }).click(); await settle(admin)

    await admin.getByRole('button', { name: '新建 Banner', exact: true }).click()
    await admin.getByRole('textbox', { name: 'Banner 标题', exact: true }).fill('打开一份好练习')
    await setTarget('打开指定习题')
    await admin.locator('.paper-choice').first().click(); await save()
    const linked = (await list()).find(item => item.title === '打开一份好练习')
    assert.ok(linked.target_value)
    await goHome(); await reader.getByRole('button', { name: /查看第2张：打开一份好练习/ }).click()
    await reader.getByRole('button', { name: '打开一份好练习，去看看', exact: true }).click()
    await reader.waitForURL(url => url.hash.includes('/pages/paper/index?id=' + linked.target_value))
    check('The admin can choose a published paper without copying an id, and its banner opens that paper')
    await api.delete('/api/v1/admin/site/banners/' + linked.id, { params: { revision: linked.revision } })
    await reader.goto(base + '/?home-ui=after-paper#/pages/home/index'); await bannerLoaded(reader, 900)
    await admin.getByRole('button', { name: '刷新 Banner', exact: true }).click(); await settle(admin)

    await admin.getByRole('button', { name: '新建 Banner', exact: true }).click()
    await admin.getByRole('textbox', { name: 'Banner 标题', exact: true }).fill('上传失败后可重试')
    await admin.getByLabel('选择 Banner 图片', { exact: true }).setInputFiles(photo)
    await admin.locator('.phone-preview img[src^="blob:"]').waitFor()
    await admin.route('**/api/v1/admin/site/banners/*/image?revision=*', route => route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":{"error":"Fixture upload failed"}}' }))
    await admin.getByRole('button', { name: '保存 Banner', exact: true }).click()
    await admin.locator('.editor-error').waitFor()
    check('Failed first upload keeps the file selected and the new banner hidden', await admin.locator('.phone-preview img[src^="blob:"]').count() === 1 && !(await home()).some(item => item.title === '上传失败后可重试'))
    await admin.unroute('**/api/v1/admin/site/banners/*/image?revision=*')
    await save()
    check('Retry publishes only after the retained photo successfully uploads', (await home()).some(item => item.title === '上传失败后可重试' && item.image_url))

    await edit(banner.title)
    await admin.getByRole('button', { name: '移除图片', exact: true }).click()
    check('Removing an image is previewed before save', await admin.locator('.phone-preview .copy-preview').isVisible())
    await save()
    await goHome()
    check('Removing a photo clears the cached image in the existing home component', await reader.locator('.banner-slide').first().getAttribute('class').then(value => value.includes('text-banner')))
    for (const item of await list()) assert.equal((await api.delete('/api/v1/admin/site/banners/' + item.id, { params: { revision: item.revision } })).status(), 204)
    assert.deepEqual(await home(), [])
    await goHome()
    await reader.locator('.home-welcome').waitFor()
    check('An unconfigured homepage has one honest entry point and no fixed fake carousel', await reader.locator('.home-welcome').isVisible() && await reader.locator('.banner-swiper').count() === 0)
    await noOverflow(reader); await shot(reader, '08-home-without-banner')
    check('Both applications finish without unhandled browser errors', errors.length === 0)
  } catch (error) {
    console.error(JSON.stringify({ adminUrl: admin.url(), readerUrl: reader.url() }))
    await shot(admin, 'failure-admin').catch(() => {})
    await shot(reader, 'failure-home').catch(() => {})
    throw error
  } finally {
    await writeFile(path.join(output, 'checks.json'), JSON.stringify({ checks, errors, screenshots }, null, 2))
    await readerContext.tracing.stop({ path: path.join(output, 'trace.zip') })
    await browser.close(); await api.dispose()
  }
  async function expectMode() {
    await admin.getByText('运营 Banner 已启用', { exact: true }).waitFor()
    assert.equal((await (await api.get('/api/v1/site/home')).json()).banner_mode, 'operations')
  }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
