import JSZip from 'jszip'
import { expect, test, type BrowserContext, type Page } from '@playwright/test'
import { readFile, writeFile } from 'node:fs/promises'
import { DEFAULT_LAYOUT, TEMPLATES } from '../src/constants'
import type { WorkspaceSnapshot } from '../src/persistence'

// 真实生产构建与 IndexedDB；API 固定响应避免依赖付费模型和业务数据库。
async function api(context: BrowserContext) {
  let owner = 7
  await context.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    let data: unknown
    if (path === '/api/v1/auth/me') data = { id: owner, username: `teacher-${owner}`, role: 'user' }
    else if (path === '/api/v1/auth/capabilities') data = { registration_enabled: false }
    else if (path === '/api/v1/scope/available') data = { available: { 小学三年级: ['数学'] } }
    else if (path === '/api/v1/scope') data = { allowed: ['加减法'] }
    else if (path === '/api/v1/me/templates') data = { templates: [] }
    else if (path === '/api/v1/me/usage') data = { requests: 0 }
    else throw new Error(`浏览器用例出现未声明请求：${route.request().method()} ${path}`)
    await route.fulfill({ json: data })
  })
  return {
    switchOwner: (id: number) => {
      owner = id
    },
  }
}

function worksheet(count: number, footer = '认真检查后再交卷'): WorkspaceSnapshot {
  const sections = [
    {
      type: 'quiz',
      _sid: 'choices',
      layout: { ...DEFAULT_LAYOUT, qCols: 1, optCols: 1 },
      data: {
        questions: Array.from({ length: count }, (_, index) => ({
          _qid: `q-${index}`,
          type: 'multiple_choice',
          stem: `第 ${index + 1} 道题：请选择正确答案`,
          options: ['选项甲', '选项乙', '选项丙', '选项丁'],
          answer: 0,
        })),
      },
    },
  ]
  return {
    version: 1,
    grade: '小学三年级',
    subject: '数学',
    keyword: '加减法',
    selectedTags: [],
    title: '分页回归试卷',
    titleHtml: '',
    difficulty: 'medium',
    hiddenElements: [],
    sections: [],
    papers: [
      {
        grade: '小学三年级',
        subject: '数学',
        keyword: '加减法',
        title: '分页回归试卷',
        difficulty: 'medium',
        sections,
        footerOverride: footer,
      },
    ],
    view: 'result',
    paperCount: 1,
    addDayLabel: false,
    templateId: 'exam',
    customTemplate: TEMPLATES.find((item) => item.id === 'custom')!,
    style: {
      bg: 'none',
      bgOpacity: 70,
      banner: false,
      secColor: false,
      frame: 'none',
      encourage: false,
      reward: false,
      kidFont: 'off',
      exportBg: false,
      titleScale: 1,
      titleOffsetY: 0,
    },
    generateWarn: '',
    generateError: '',
    pendingRun: null,
  }
}

async function seed(page: Page, snapshot: WorkspaceSnapshot) {
  await page.goto('/')
  await expect(page.getByRole('button', { name: '小学三年级', exact: true })).toBeVisible()
  await page.evaluate(async (snapshot) => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open('learn-coach-workspaces', 2)
      request.onsuccess = () => resolve(request.result)
      request.onerror = () => reject(request.error)
    })
    try {
      await new Promise<void>((resolve, reject) => {
        const transaction = db.transaction('drafts', 'readwrite')
        transaction.objectStore('drafts').put({ id: '7:browser-fixture', owner: '7', updatedAt: Date.now(), snapshot })
        transaction.oncomplete = () => resolve()
        transaction.onerror = () => reject(transaction.error)
      })
      sessionStorage.setItem('lc_draft_session:7', 'browser-fixture')
    } finally {
      db.close()
    }
  }, snapshot)
  await page.reload()
  await expect(page.locator('.result-view .paper-stack .q')).toHaveCount(
    snapshot.papers[0].sections[0].data.questions.length,
  )
}

async function expectContentsFit(page: Page) {
  await expect
    .poll(() =>
      page.locator('.result-view .paper-stack .paper').evaluateAll((papers) =>
        papers.every((paper) => {
          const scale = paper.getBoundingClientRect().width / (paper as HTMLElement).offsetWidth
          const bottom =
            paper.getBoundingClientRect().bottom - parseFloat(getComputedStyle(paper).paddingBottom) * scale
          return [...paper.querySelectorAll('.q, .pv-tail')].every(
            (item) => item.getBoundingClientRect().bottom <= bottom + 2,
          )
        }),
      ),
    )
    .toBe(true)
}

for (const width of [1440, 320]) {
  test(`登录页和工作台不再展示英文品牌 ${width}px`, async ({ page, context }, info) => {
    await api(context)
    await page.setViewportSize({ width, height: width === 320 ? 640 : 1000 })
    await page.route('**/api/v1/auth/me', route => route.fulfill({ status: 401, json: {} }))
    await page.goto('/')
    await expect(page.locator('.auth-form')).toBeVisible()
    await expect(page).toHaveTitle('出题工作台')
    await expect(page.locator('.brand')).toHaveText('出题工作台')
    await expect(page.locator('body')).not.toContainText(/learning\s+coach/i)
    await expect(page.locator('.auth-footer, .brand-caption')).toHaveCount(0)
    await page.screenshot({ path: info.outputPath('login.png') })
    await page.unroute('**/api/v1/auth/me')
    await page.reload()
    await expect(page.locator('.app-shell')).toBeVisible()
    await expect(page.locator('.brand')).toHaveText('出题工作台')
    await expect(page.locator('body')).not.toContainText(/learning\s+coach/i)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: info.outputPath('workspace.png') })
  })
}

test('取消排版恢复删除、顺序和尺寸，导出预览也保持原题目', async ({ page, context }) => {
  await api(context)
  await seed(page, worksheet(6))
  const questions = page.locator('.result-view .paper-stack .q')
  const original = await questions.allTextContents()
  page.once('dialog', dialog => dialog.accept())
  await page.getByRole('button', { name: '排版模式', exact: true }).click()
  await page.locator('.result-view .paper-title').first().press('Alt+ArrowDown')
  await expect(page.locator('.result-view .pv-head').first()).toHaveCSS('margin-top', '3.77953px')
  await questions.first().locator('.q-tools .del').click()
  await expect(questions).toHaveCount(5)
  await questions.first().evaluate(element => {
    const node = element as HTMLElement
    node.style.width = '50px'; node.style.height = '140px'
    node.parentElement!.appendChild(node)
  })
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await expect(questions).toHaveCount(6)
  await expect.poll(() => questions.allTextContents()).toEqual(original)
  expect(await questions.first().evaluate(element => (element as HTMLElement).style.width)).toBe('')
  await expect(page.locator('.result-view .pv-head').first()).toHaveCSS('margin-top', '0px')
  await expectContentsFit(page)
})

test('末页卷尾完整，下载的 PDF 与页面数量一致', async ({ page, context }, info) => {
  await api(context)
  await seed(page, worksheet(6, '检查计算过程与答案。'.repeat(100)))
  await expectContentsFit(page)
  const pages = await page.locator('.result-view .paper-stack .paper').count()
  expect(pages).toBeGreaterThan(1)
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: '下载 PDF', exact: true }).click()
  const saved = await download
  expect(await saved.failure()).toBeNull()
  const filename = info.outputPath('worksheet.pdf')
  await saved.saveAs(filename)
  const content = (await readFile(filename)).toString('latin1')
  expect(content.startsWith('%PDF-')).toBe(true)
  expect(content.match(/\/Type\s*\/Page\b/g)).toHaveLength(pages)
  await page.locator('.result-view .paper-stack .paper').last().screenshot({ path: info.outputPath('worksheet.png') })
})

test('修改选项后重新分页，撤销重做与刷新保留编辑', async ({ page, context }) => {
  await api(context)
  await seed(page, worksheet(5))
  const pagesBefore = await page.locator('.result-view .paper-stack .paper').count()
  const option = page.locator('.result-view .paper-stack .opts [contenteditable="true"]').last()
  const text = '修改后的长选项，用于检查分页是否及时更新。'.repeat(25)
  await option.fill(text)
  await page.getByRole('heading', { name: '生成结果', exact: true }).click()
  await expect.poll(() => page.locator('.result-view .paper-stack .paper').count()).toBeGreaterThan(pagesBefore)
  await expectContentsFit(page)
  await page.getByRole('button', { name: '撤销编辑', exact: true }).click()
  await expect(page.locator('.result-view .paper-stack .opts').last()).not.toContainText(text)
  await page.getByRole('button', { name: '重做编辑', exact: true }).click()
  await expect(page.locator('.result-view .paper-stack .opts').last()).toContainText(text)
  await expect(page.getByText('草稿已保存', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.locator('.result-view .paper-stack .opts').last()).toContainText(text)
  await expectContentsFit(page)
})

test('仅调整富文本字号也会重新分页', async ({ page, context }) => {
  await api(context)
  const snapshot = worksheet(5)
  snapshot.papers[0].sections[0].data.questions[4].options![3] = '保持文字不变，只调整字号以验证行高变化。'.repeat(4)
  await seed(page, snapshot)
  const before = await page.locator('.result-view .paper-stack .paper').count()
  const option = page.locator('.result-view .paper-stack .opts [contenteditable="true"]').last()
  await option.click()
  await option.press('ControlOrMeta+a')
  const slider = page.getByRole('slider', { name: '选中文字字号' })
  await expect(slider).toBeVisible()
  await slider.fill('7')
  await expect.poll(() => page.locator('.result-view .paper-stack .paper').count()).toBeGreaterThan(before)
  await expectContentsFit(page)
})

test('单题超过整页时提示调整内容并阻止裁切导出', async ({ page, context }) => {
  await api(context)
  const snapshot = worksheet(1)
  snapshot.papers[0].sections[0].data.questions[0].stem = '这是一道需要缩短内容的题目。'.repeat(500)
  await seed(page, snapshot)
  await expect(page.getByRole('alert')).toContainText('内容超出 A4 页面')
  const downloads: string[] = []
  page.on('download', download => downloads.push(download.suggestedFilename()))
  await page.getByRole('button', { name: '下载 PDF', exact: true }).click()
  await expect(page.locator('.result-notice')).toContainText('导出失败：内容超出 A4 页面')
  expect(downloads).toEqual([])
})

test('启动请求未完成时显示加载，失败保留账号并可重试', async ({ page, context }) => {
  await api(context)
  await context.addInitScript(() => localStorage.setItem('lc_uid', '7'))
  const workspaceRequests: string[] = []
  page.on('request', request => { if (/assets\/Workspace-.*\.js/.test(request.url())) workspaceRequests.push(request.url()) })
  let release!: () => void
  const pending = new Promise<void>((resolve) => {
    release = resolve
  })
  await page.route('**/api/v1/auth/me', async (route) => {
    await pending
    await route.fulfill({ status: 503, json: { detail: '服务暂不可用' } })
  })
  await page.goto('/')
  await expect(page.getByText('正在加载工作台', { exact: true })).toBeVisible()
  release()
  await expect(page.getByRole('alert')).toContainText('暂时无法连接工作台')
  expect(await page.evaluate(() => localStorage.getItem('lc_uid'))).toBe('7')
  await expect.poll(() => workspaceRequests.length).toBeGreaterThan(0)
  await page.unroute('**/api/v1/auth/me')
  await page.getByRole('button', { name: '重新连接' }).click()
  await expect(page.getByRole('button', { name: '账号菜单：teacher-7' })).toBeVisible()
})

test('新标签页连接失败不干扰旧页，实际切账号保存原草稿并隔离数据', async ({ page, context }) => {
  const accounts = await api(context)
  await seed(page, worksheet(2))
  const other = await context.newPage()
  await other.route('**/api/v1/auth/me', (route) => route.fulfill({ status: 503, json: { detail: '服务暂不可用' } }))
  await other.goto('/')
  await expect(other.getByRole('alert')).toBeVisible()
  await expect(page.locator('.result-view .paper-stack .q')).toHaveCount(2)
  expect(await page.evaluate(() => localStorage.getItem('lc_uid'))).toBe('7')
  accounts.switchOwner(8)
  await other.evaluate(() => localStorage.setItem('lc_uid', '8'))
  await expect(page.getByRole('button', { name: '账号菜单：teacher-8' })).toBeVisible()
  await expect(page.locator('.result-view')).toHaveCount(0)
  const records = await page.evaluate(async () => {
    const request = indexedDB.open('learn-coach-workspaces', 2)
    const db = await new Promise<IDBDatabase>((resolve) => {
      request.onsuccess = () => resolve(request.result)
    })
    try {
      return await new Promise<Array<{ owner: string; snapshot: WorkspaceSnapshot }>>((resolve) => {
        const read = db.transaction('drafts').objectStore('drafts').getAll()
        read.onsuccess = () => resolve(read.result)
      })
    } finally {
      db.close()
    }
  })
  expect(records.some((record) => record.owner === '7' && record.snapshot.papers.length === 1)).toBe(true)
  expect(records.filter((record) => record.owner === '8').every((record) => !record.snapshot.papers.length)).toBe(true)
})


test('标题下移仍保留底部内容，偏移不重建测量卷', async ({ page, context }) => {
  await api(context)
  await seed(page, worksheet(16))
  await expectContentsFit(page)
  const title = page.locator('.result-view .paper-stack .paper-title').first()
  await title.focus()
  for (let index = 0; index < 25; index++) await title.press('Alt+ArrowDown')
  await expectContentsFit(page)
  await expect(page.locator('.result-view .offscreen')).toHaveCount(0)
  await expect(page.locator('.result-view .paper-stack .pv-head').first()).toHaveCSS('margin-top', '94.4882px')
})

test('键盘排序和删除跨页回写，保留其他页题目', async ({ page, context }) => {
  await api(context)
  await seed(page, worksheet(16))
  const questions = page.locator('.result-view .paper-stack .q')
  await page.getByRole('button', { name: '排版模式', exact: true }).click()
  await questions.first().getByRole('button', { name: '下移题目', exact: true }).focus()
  await page.keyboard.press('Enter')
  await expect(questions.first()).toContainText('第 2 道题')
  page.once('dialog', dialog => dialog.accept())
  await questions.last().getByRole('button', { name: '删除题目', exact: true }).focus()
  await page.keyboard.press('Enter')
  await page.getByRole('button', { name: '完成排版', exact: true }).click()
  await expect(questions).toHaveCount(15)
  await expect(questions.first()).toContainText('第 2 道题')
  await expect(questions.last()).toContainText('第 15 道题')
})

test('真实浏览器净化富文本保留字号颜色并移除页面覆盖样式', async ({ page, context }) => {
  await api(context)
  const snapshot = worksheet(1)
  snapshot.papers[0].sections[0].data.questions[0]._stemHtml = '<span class="fixed inset-0" style="color:rgb(255, 0, 0);font-size:18px;position:fixed;z-index:999;background-image:url(https://outside.test/a);width:100vw" onclick="alert(1)">安全富文本</span>'
  await seed(page, snapshot)
  const span = page.locator('.result-view .paper-stack [data-e="stem"] span').filter({ hasText: '安全富文本' }).last()
  await expect(span).toHaveCSS('color', 'rgb(255, 0, 0)')
  await expect(span).toHaveCSS('font-size', '18px')
  const html = await span.evaluate(element => element.outerHTML)
  for (const unsafe of ['class=', 'position:', 'z-index', 'url(', 'onclick', '100vw']) expect(html).not.toContain(unsafe)
})


test('多页 PNG 只下载一个包含全部页面的 ZIP', async ({ page, context }, info) => {
  await api(context)
  await seed(page, worksheet(10))
  const pages = await page.locator('.result-view .paper-stack .paper').count()
  expect(pages).toBeGreaterThan(1)
  const downloads: string[] = []
  page.on('download', download => downloads.push(download.suggestedFilename()))
  await page.getByRole('button', { name: '更多导出方式' }).click()
  const pending = page.waitForEvent('download')
  await page.getByRole('menuitem', { name: '下载 PNG', exact: true }).click()
  const download = await pending
  const file = info.outputPath('pages.zip')
  await download.saveAs(file)
  expect(downloads).toHaveLength(1)
  expect(download.suggestedFilename()).toMatch(/\.zip$/)
  const zip = await JSZip.loadAsync(await readFile(file))
  expect(Object.keys(zip.files).filter(name => name.endsWith('.png'))).toHaveLength(pages)
})

test('退出并清除本机数据删除自己的草稿，保留其他账号', async ({ page, context }) => {
  await api(context)
  await seed(page, worksheet(2))
  await page.evaluate(async () => {
    localStorage.setItem('lc_u7_image_request', 'private')
    localStorage.setItem('lc_u8_image_request', 'keep')
  })
  await page.route('**/api/v1/auth/logout', async route => {
    await page.route('**/api/v1/auth/me', async request => request.fulfill({ status: 401, json: { detail: 'expired' } }))
    await route.fulfill({ status: 204 })
  })
  page.once('dialog', dialog => dialog.accept())
  await page.getByRole('button', { name: '账号菜单：teacher-7' }).click()
  await page.getByRole('menuitem', { name: '退出并清除本机数据', exact: true }).click()
  await expect(page.locator('.auth-form')).toBeVisible()
  const result = await page.evaluate(async () => {
    const request = indexedDB.open('learn-coach-workspaces', 2)
    const db = await new Promise<IDBDatabase>(resolve => { request.onsuccess = () => resolve(request.result) })
    const records = await new Promise<Array<{ owner: string }>>(resolve => { const read = db.transaction('drafts').objectStore('drafts').getAll(); read.onsuccess = () => resolve(read.result) })
    db.close()
    return { records, cleared: localStorage.getItem('lc_u7_image_request'), retained: localStorage.getItem('lc_u8_image_request') }
  })
  expect(result.records.filter(value => value.owner === '7')).toEqual([])
  expect(result.cleared).toBeNull(); expect(result.retained).toBe('keep')
})

test('会话过期保存草稿后在登录页明确提示', async ({ page, context }) => {
  await api(context)
  await seed(page, worksheet(2))
  await page.route('**/api/v1/auth/me', route => route.fulfill({ status: 401, json: { detail: 'expired' } }))
  await page.route('**/api/v1/library/**', route => route.fulfill({ status: 401, json: { detail: 'expired' } }))
  await page.getByRole('button', { name: '云端试卷', exact: true }).click()
  await expect(page.locator('.auth-form')).toContainText('登录已过期，草稿已保存')
})

test('注册关闭时不显示注册页签，开启后才可注册', async ({ page, context }) => {
  await api(context)
  await page.route('**/api/v1/auth/me', route => route.fulfill({ status: 401, json: {} }))
  await page.goto('/')
  await expect(page.getByText('账号由管理员开通', { exact: true })).toBeVisible()
  await expect(page.getByRole('tab', { name: '注册', exact: true })).toHaveCount(0)
  await page.route('**/api/v1/auth/capabilities', route => route.fulfill({ json: { registration_enabled: true } }))
  await page.reload()
  await expect(page.getByRole('tab', { name: '注册', exact: true })).toBeVisible()
})

test('结果页在各宽度自动适宽，中屏搭建为侧栏与预览双栏', async ({ page, context }, info) => {
  await api(context)
  await seed(page, worksheet(2))
  for (const width of [320, 390, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 })
    await expect.poll(() => page.locator('.result-view .paper').first().evaluate(element => {
      const paper = element.getBoundingClientRect(), viewport = document.querySelector('.preview-scroll')!.getBoundingClientRect()
      return paper.width <= viewport.width && paper.left >= viewport.left - 1
    })).toBe(true)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: info.outputPath(`result-${width}.png`) })
  }
  await page.setViewportSize({ width: 1024, height: 900 })
  await page.getByRole('button', { name: '返回搭建', exact: true }).click()
  await expect(page.locator('.workspace-side-tabs')).toBeVisible()
  await expect(page.locator('.preview-panel')).toBeVisible()
  await page.locator('.workspace-side-tabs').getByRole('tab', { name: '试卷结构', exact: true }).click()
  await expect(page.locator('.structure-panel')).toBeVisible()
  await page.screenshot({ path: info.outputPath('build-1024.png') })
})

for (const width of [1440, 320]) {
  test(`清空试卷设置保留结果，可撤销重做并在刷新后保持 ${width}px`, async ({ page, context }, info) => {
    await api(context)
    const snapshot = worksheet(2)
    snapshot.sections = snapshot.papers[0].sections.map(section => ({
      ...section, id: section._sid!, count: section.data.questions.length, status: 'ready',
    }))
    snapshot.selectedTags = ['加减法']; snapshot.paperCount = 3; snapshot.difficulty = 'hard'
    await seed(page, snapshot)
    await page.setViewportSize({ width, height: width === 320 ? 568 : 1000 })
    const clear = page.getByRole('button', { name: '清空设置', exact: true })
    await expect(clear).toBeInViewport()
    page.once('dialog', dialog => dialog.dismiss())
    await clear.click()
    await expect(page.locator('.result-view .paper-stack .q')).toHaveCount(2)
    page.once('dialog', dialog => dialog.accept())
    await clear.click()
    await expect(page.getByRole('heading', { name: '试卷搭建', exact: true })).toBeVisible()
    await expect(page.locator('.conditions-panel')).toBeVisible()
    await expect(page.locator('.conditions-panel [aria-pressed=true]')).toHaveCount(1) // Default difficulty only.
    await expect(page.locator('.conditions-panel textarea')).toHaveValue('')
    await expect(page.locator('.workspace-meta')).toContainText('0 个大题')
    await expect(clear).toBeDisabled()
    await page.screenshot({ path: info.outputPath('cleared-paper-settings.png') })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    for (const action of ['撤销编辑', '重做编辑']) {
      if (width < 621) {
        await page.getByRole('button', { name: '工作台工具' }).click()
        await page.getByRole('menuitem', { name: action, exact: true }).click()
      } else await page.getByRole('button', { name: action, exact: true }).click()
      if (action === '撤销编辑') {
        await expect(page.locator('.result-view .paper-stack .q')).toHaveCount(2)
        await expect(clear).toBeEnabled()
      }
    }
    await expect(clear).toBeDisabled()
    await expect(page.getByText('草稿已保存', { exact: true })).toBeVisible()
    await page.reload()
    await expect(clear).toBeDisabled()
    await expect(page.locator('.conditions-panel textarea')).toHaveValue('')
    await page.getByRole('button', { name: /^生成结果/ }).click()
    await expect(page.locator('.result-view .paper-stack .q')).toHaveCount(2)
    await expect(page.locator('.result-view .paper-title').first()).toContainText(snapshot.title)
  })
}

test('生成等待后首次结果自动适宽，两个重生成入口取消均不产生新调用', async ({ page, context }) => {
  await api(context)
  const snapshot = worksheet(2)
  snapshot.sections = snapshot.papers[0].sections.map(section => ({
    ...section, id: section._sid!, count: section.data.questions.length, status: 'ready',
  }))
  await seed(page, snapshot)
  let calls = 0, release!: () => void
  const pending = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/v1/generate-batch', async route => {
    calls++
    await pending
    const body = route.request().postDataJSON()
    await route.fulfill({ json: { sections: body.items.map((item: { game_type: string; section_id: string }) => ({
      game_type: item.game_type, section_id: item.section_id, questions: snapshot.papers[0].sections[0].data.questions,
    })) } })
  })
  page.once('dialog', dialog => dialog.dismiss())
  await page.getByRole('button', { name: '重新生成', exact: true }).click()
  expect(calls).toBe(0)
  await page.getByRole('button', { name: '返回搭建', exact: true }).click()
  page.once('dialog', dialog => dialog.dismiss())
  await page.getByRole('button', { name: '生成试卷', exact: true }).click()
  expect(calls).toBe(0)
  page.once('dialog', dialog => dialog.accept())
  await page.getByRole('button', { name: '生成试卷', exact: true }).click()
  await expect.poll(() => calls).toBe(1)
  await expect(page.locator('.result-view .preview-scroll')).toHaveCount(0)
  await page.setViewportSize({ width: 390, height: 844 })
  release()
  await expect(page.locator('.result-view .paper')).toHaveCount(1)
  await expect.poll(() => page.locator('.result-view .paper').evaluate(element =>
    element.getBoundingClientRect().width < 390)).toBe(true)
  expect(calls).toBe(1)
})

test('长卷PDF导出记录耗时和浏览器堆内存，页数完整', async ({ page, context }, info) => {
  test.setTimeout(120_000)
  await api(context)
  const snapshot = worksheet(25)
  snapshot.papers = Array.from({ length: 10 }, (_, index) => ({ ...structuredClone(snapshot.papers[0]), day: index + 1 }))
  snapshot.paperCount = 10
  await seed(page, snapshot)
  const pages = (await page.locator('.result-view .paper-stack .paper').count()) * snapshot.papers.length
  expect(pages).toBeGreaterThanOrEqual(50)
  const cdp = await context.newCDPSession(page)
  await cdp.send('Performance.enable')
  const heap = async () => (await cdp.send('Performance.getMetrics')).metrics.find(metric => metric.name === 'JSHeapUsedSize')!.value
  const before = await heap()
  let peak = before, active = true
  const sampling = (async () => {
    while (active) {
      peak = Math.max(peak, await heap())
      await new Promise(resolve => setTimeout(resolve, 100))
    }
  })()
  const started = Date.now()
  try {
    const pending = page.waitForEvent('download')
    await page.getByRole('button', { name: '更多导出方式', exact: true }).click()
    await page.getByRole('menuitem', { name: '合并全部 PDF', exact: true }).click()
    const download = await pending
    const file = info.outputPath('long-worksheet.pdf')
    await download.saveAs(file)
    const content = await readFile(file)
    expect(content.toString('latin1').match(/\/Type\s*\/Page\b/g)).toHaveLength(pages)
    await writeFile(info.outputPath('performance.json'), JSON.stringify({
      pages, durationMs: Date.now() - started, pdfBytes: content.length, beforeHeapBytes: before, sampledPeakHeapBytes: peak,
      note: 'Local Chromium JS heap sampling; not process RSS or a production capacity claim.',
    }, null, 2))
  } finally { active = false; await sampling; await cdp.detach() }
})

test('慢网络冷启动记录首屏且不提前下载重型导出依赖', async ({ page, context }, info) => {
  test.setTimeout(60_000)
  await api(context)
  const cdp = await context.newCDPSession(page)
  await cdp.send('Network.enable')
  await cdp.send('Network.setCacheDisabled', { cacheDisabled: true })
  await cdp.send('Network.emulateNetworkConditions', {
    offline: false, latency: 150, downloadThroughput: 200_000, uploadThroughput: 93_750,
  })
  const requested: string[] = []
  page.on('request', request => requested.push(request.url()))
  const started = Date.now()
  await page.goto('/')
  await expect(page.getByRole('button', { name: '小学三年级', exact: true })).toBeVisible({ timeout: 45_000 })
  const readyMs = Date.now() - started
  expect(requested.some(url => /\/(jspdf|html2canvas|jszip)[^/]*\.js/.test(url))).toBe(false)
  const timing = await page.evaluate(() => ({
    paints: performance.getEntriesByType('paint').map(entry => ({ name: entry.name, startTime: entry.startTime })),
    transferredBytes: performance.getEntriesByType('resource').reduce((size, entry) => size + (entry as PerformanceResourceTiming).transferSize, 0),
  }))
  await writeFile(info.outputPath('cold-start.json'), JSON.stringify({
    readyMs, ...timing, network: { latencyMs: 150, downloadBytesPerSecond: 200_000 },
    note: 'Mocked API, real production JS/CSS, local Chromium. Not an end-user Core Web Vitals claim.',
  }, null, 2))
  await cdp.detach()
})
