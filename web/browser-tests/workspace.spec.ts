import { expect, test, type BrowserContext, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { DEFAULT_LAYOUT, TEMPLATES } from '../src/constants'
import type { WorkspaceSnapshot } from '../src/persistence'

// 真实生产构建与 IndexedDB；API 固定响应避免依赖付费模型和业务数据库。
async function api(context: BrowserContext) {
  let owner = 7
  await context.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    let data: unknown
    if (path === '/api/v1/auth/me') data = { id: owner, username: `teacher-${owner}`, role: 'user' }
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
  let loadWorkspace!: () => void
  const loadingWorkspace = new Promise<void>(resolve => { loadWorkspace = resolve })
  await page.route('**/assets/Workspace-*.js', async route => { await loadingWorkspace; await route.continue() })
  await page.unroute('**/api/v1/auth/me')
  await page.getByRole('button', { name: '重新连接' }).click()
  await expect(page.getByText('正在加载工作台', { exact: true })).toBeVisible()
  loadWorkspace()
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
