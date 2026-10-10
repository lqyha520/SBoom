import { expect, test, type BrowserContext, type Page } from '@playwright/test'
import { defaultDownloadSettings } from '../src/download-settings'

async function fixture(context: BrowserContext, summaryGate = Promise.resolve()) {
  const writes: { path: string; body: Record<string, unknown> }[] = [], queries: URLSearchParams[] = []
  let summaries = 0
  const paper = { ...defaultDownloadSettings(), id: 'paper', paper_id: 'source', title: '三年级练习', description: '',
    category_id: 'practice', category: '练习', status: 'draft', revision: 1, featured: false,
    grade: '三年级', subject: '数学', version: 1, question_count: 3, page_count: 0, file_status: 'ready',
    thumbnail_url: null, updated_at: 1, view_access: 'free', download_access: 'free',
    required_view: 'free', required_download: 'free', question_types: ['quiz'], assets: [], tags: [], editions: [] }
  const tag = { id: 'term', name: '上学期', kind: 'term', is_visible: true, revision: 1, sort_order: 0, paper_count: 0 }
  const categories = [{ id: 'practice', name: '练习', is_visible: true }]
  await context.route('**/api/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname, method = request.method()
    let data: unknown
    if (method !== 'GET') writes.push({ path, body: request.postDataJSON() })
    if (path === '/api/v1/auth/me') data = { id: 1, username: 'admin', role: 'admin' }
    else if (path === '/api/v1/admin/site/categories') {
      if (method === 'POST') { const item = { id: 'new-category', ...request.postDataJSON() }; categories.push(item); data = item }
      else data = { items: categories }
    } else if (path === '/api/v1/admin/site/dictionary') data = { items: [{ value: url.searchParams.get('kind') === 'grade' ? '三年级' : '数学' }] }
    else if (path === '/api/v1/admin/catalog/summary') { summaries++; await summaryGate; data = { published: 0, draft: 21, withdrawn: 0, favorites: 0, downloads: 0 } }
    else if (path === '/api/v1/admin/catalog/papers') { queries.push(url.searchParams); data = { items: url.searchParams.get('status') === 'published' ? [paper, { ...paper, id: 'second', title: '第二份练习' }] : [paper], total: 21, has_more: true } }
    else if (path === '/api/v1/admin/catalog/papers/paper') {
      if (method === 'PUT') {
        expect(request.postDataJSON().revision).toBe(paper.revision)
        Object.assign(paper, request.postDataJSON(), { revision: paper.revision + 1 })
      }
      data = paper
    } else if (path === '/api/v1/admin/catalog/tags') data = { items: [tag] }
    else if (path === '/api/v1/admin/catalog/sources') data = { items: [{ id: 'revised-source', title: '修订原稿', grade: '三年级', file_status: 'ready' }], has_more: false }
    else if (path === '/api/v1/admin/catalog/papers/paper/edition-sources') data = { items: [{ id: 'answer-source', title: '配套答案', version: 1, mode: 'answersOnly' }] }
    else if (path === '/api/v1/admin/catalog/papers/paper/editions') {
      const body = request.postDataJSON()
      expect(body.revision).toBe(paper.revision)
      Object.assign(paper, { revision: paper.revision + 1, editions: [{ kind: body.kind, paper_id: body.paper_id, label: '配套答案' }] })
      data = paper
    } else if (path === '/api/v1/admin/catalog/papers/paper/revision') {
      const body = request.postDataJSON()
      expect(body.revision).toBe(paper.revision)
      Object.assign(paper, { revision: paper.revision + 1, paper_id: body.paper_id, editions: [], version: 2 })
      data = paper
    }
    else if (path === '/api/v1/admin/catalog/papers/paper/labels') {
      expect(request.postDataJSON().revision).toBe(paper.revision)
      Object.assign(paper, { revision: paper.revision + 1, tags: request.postDataJSON().tag_ids.length ? [tag] : [] })
      data = paper
    } else if (path === '/api/v1/admin/experience/topics') data = method === 'POST' ? { id: 'topic', ...request.postDataJSON() } : { items: [] }
    else if (path === '/api/v1/admin/engagement/requests') data = { items: [{ id: 'request', title: '补充数学资料', username: 'reader', nickname: '读者', grade: '三年级', subject: '数学', status: 'pending', reply: '', revision: 1 }], total: 1, demand: [] }
    else if (path === '/api/v1/admin/engagement/requests/request') data = { ...request.postDataJSON(), revision: 2 }
    else if (path === '/api/v1/admin/stats') { await route.fulfill({ status: 503, json: { detail: '统计维护中' } }); return }
    else if (path === '/api/v1/admin/experience/feedback') data = { items: [], total: 3 }
    else if (path === '/api/v1/admin/commerce/orders') data = { items: [], total: 2, summary: { orders: 2, paid_fen: 0, refunded_fen: 0 } }
    else throw new Error(`未声明的后台请求：${method} ${path}`)
    await route.fulfill({ json: data })
  })
  return { writes, queries, summaries: () => summaries }
}

async function select(page: Page, label: string, option: string) {
  await page.getByRole('combobox', { name: label, exact: true }).click()
  await page.getByRole('option', { name: option, exact: true }).click()
}

test('菜单搜索与固定入口持久化，原有链接保持可用', async ({ page, context }) => {
  await fixture(context)
  await page.goto('/admin/#papers')
  await page.getByRole('textbox', { name: '搜索管理菜单' }).fill('专题')
  const nav = page.getByRole('navigation', { name: '管理后台导航' })
  await expect(nav.getByRole('button', { name: '专题合集', exact: true })).toBeVisible()
  await expect(nav.getByRole('button', { name: '系统日志', exact: true })).toHaveCount(0)
  await nav.getByRole('button', { name: '加入常用：专题合集' }).click()
  await page.getByRole('button', { name: '清除搜索' }).click()
  await page.getByRole('button', { name: '常用：专题合集', exact: true }).click()
  await expect(page).toHaveURL(/#topics$/)
  await page.reload()
  await expect(page.getByRole('button', { name: '常用：专题合集', exact: true })).toBeVisible()
})

test('列表不等待统计，筛选和页码刷新后保留，翻页不重取统计', async ({ page, context }) => {
  let release!: () => void
  const server = await fixture(context, new Promise<void>(resolve => { release = resolve }))
  try {
    await page.goto('/admin/#papers')
    await expect(page.getByRole('button', { name: '编辑 三年级练习' })).toBeVisible()
    await expect(page.getByRole('button', { name: '刷新公共习题' })).toBeEnabled()
    await select(page, '年级筛选', '三年级')
    await select(page, '学科筛选', '数学')
    await select(page, '分类筛选', '练习')
    await select(page, '权限筛选', '免费预览 · VIP 下载')
    await expect.poll(() => server.queries.at(-1)?.get('access')).toBe('vip_download')
    await page.getByRole('button', { name: 'Page 2', exact: true }).click()
    await expect.poll(() => server.queries.at(-1)?.get('offset')).toBe('20')
    expect(server.summaries()).toBe(1)
    release()
    await page.reload()
    await expect(page.getByRole('combobox', { name: '年级筛选' })).toContainText('三年级')
    await expect.poll(() => server.queries.at(-1)?.get('offset')).toBe('20')
    expect(server.queries.at(-1)?.get('category')).toBe('practice')
  } finally { release() }
})

test('专题与需求回复的 Esc 和页面切换可以取消，不丢输入', async ({ page, context }) => {
  const server = await fixture(context)
  await page.goto('/admin/#topics')
  await page.getByRole('button', { name: '新建专题', exact: true }).click()
  const topic = page.getByRole('dialog', { name: '新建专题', exact: true })
  await topic.getByRole('textbox', { name: '专题名称' }).fill('单元复习')
  await topic.getByRole('checkbox', { name: '三年级练习 · 三年级 · 数学' }).check()
  await topic.getByRole('checkbox', { name: '第二份练习 · 三年级 · 数学' }).check()
  await topic.getByRole('button', { name: '拖动排序：第二份练习' }).dragTo(topic.locator('.selected-paper').first())
  await expect(topic.locator('.selected-paper').first()).toContainText('第二份练习')
  await topic.locator('.selected-paper').first().getByRole('button', { name: '下移' }).click()
  await expect(topic.locator('.selected-paper').first()).toContainText('三年级练习')
  page.once('dialog', dialog => dialog.dismiss())
  await page.keyboard.press('Escape')
  await expect(topic.getByRole('textbox', { name: '专题名称' })).toHaveValue('单元复习')
  page.once('dialog', dialog => dialog.dismiss())
  await page.evaluate(() => { location.hash = '#resourceRequests' })
  await expect(page).toHaveURL(/#topics$/)
  await topic.getByRole('button', { name: '保存专题' }).click()
  await expect(topic).toBeHidden()
  expect(server.writes.at(-1)?.body).toMatchObject({ title: '单元复习', paper_ids: ['paper', 'second'] })
  await page.goto('/admin/#resourceRequests')
  await page.getByRole('button', { name: '处理需求' }).click()
  const request = page.getByRole('dialog', { name: '处理资料需求' })
  await request.getByRole('textbox', { name: '回复用户' }).fill('正在整理，明天补齐')
  page.once('dialog', dialog => dialog.dismiss())
  await page.keyboard.press('Escape')
  await expect(request.getByRole('textbox', { name: '回复用户' })).toHaveValue('正在整理，明天补齐')
  await request.getByRole('button', { name: '保存处理结果' }).click()
  await expect(request).toBeHidden()
  expect(server.writes.at(-1)?.body.reply).toBe('正在整理，明天补齐')
})

test('统一编辑保留各面板草稿并同步保存版本，可就地创建分类', async ({ page, context }, info) => {
  const server = await fixture(context)
  await page.goto('/admin/#papers')
  await page.getByRole('button', { name: '编辑 三年级练习' }).click()
  const editor = page.getByRole('dialog', { name: '编辑公共习题' })
  await editor.getByRole('textbox', { name: '公开标题' }).fill('尚未保存的标题')
  await editor.getByRole('tab', { name: '教学标签' }).click()
  await select(page, '学期', '上学期')
  await editor.getByRole('tab', { name: '基本与发布' }).click()
  await expect(editor.getByRole('textbox', { name: '公开标题' })).toHaveValue('尚未保存的标题')
  await editor.getByRole('tab', { name: '教学标签' }).click()
  await expect(editor.getByRole('combobox', { name: '学期' })).toContainText('上学期')
  page.once('dialog', dialog => dialog.dismiss())
  await page.keyboard.press('Escape')
  await expect(editor).toBeVisible()
  await editor.getByRole('button', { name: '保存资料标签' }).click()
  await expect(editor).toContainText('资料标签已保存')
  await editor.getByRole('tab', { name: '基本与发布' }).click()
  await editor.getByText('新建分类', { exact: true }).click()
  await editor.getByRole('textbox', { name: '新分类名称' }).fill('期末复习')
  await editor.getByRole('button', { name: '创建并选中' }).click()
  await expect(editor.getByRole('combobox', { name: '分类*', exact: true })).toContainText('期末复习')
  await expect(editor.getByRole('textbox', { name: '公开标题' })).toHaveValue('尚未保存的标题')
  await editor.getByRole('button', { name: '保存更改' }).click()
  await expect(editor).toContainText('公共习题已更新')
  expect(server.writes.find(write => write.path.endsWith('/paper'))?.body).toMatchObject({ revision: 2, title: '尚未保存的标题', category_id: 'new-category' })
  await editor.getByRole('tab', { name: '教学标签' }).click()
  await select(page, '学期', '未设置')
  await editor.getByRole('button', { name: '保存资料标签' }).click()
  await expect.poll(() => server.writes.filter(write => write.path.endsWith('/labels')).length).toBe(2)
  expect(server.writes.at(-1)?.body.revision).toBe(3)
  await page.screenshot({ path: info.outputPath('unified-editor.png') })
})

test('首页待办独立于平台统计，可直接进入对应筛选列表', async ({ page, context }, info) => {
  await fixture(context)
  await page.goto('/admin/#overview')
  await expect(page.getByRole('button', { name: '待处理资料需求 1 前往处理 →' })).toBeVisible()
  await expect(page.getByRole('button', { name: '待审核退款 2 前往处理 →' })).toBeVisible()
  await page.screenshot({ path: info.outputPath('admin-home.png') })
  await page.getByRole('button', { name: '待处理资料需求 1 前往处理 →' }).click()
  await expect(page).toHaveURL(/#resourceRequests\?status=pending$/)
  await expect(page.getByRole('button', { name: '处理需求' })).toBeVisible()
})

test('保存其他面板时保留修订和打印版本草稿，后续使用最新版本号', async ({ page, context }) => {
  const server = await fixture(context)
  await page.goto('/admin/#papers')
  await page.getByRole('button', { name: '编辑 三年级练习' }).click()
  const editor = page.getByRole('dialog', { name: '编辑公共习题' })
  await editor.getByRole('tab', { name: '修订稿' }).click()
  await select(page, '修订稿*', '修订原稿 · 三年级 · 文件就绪')
  await editor.getByRole('textbox', { name: '向用户说明本次更新' }).fill('补充第三题解析')
  await editor.getByRole('tab', { name: '教学标签' }).click()
  await select(page, '学期', '上学期')
  await editor.getByRole('button', { name: '保存资料标签' }).click()
  await expect(editor).toContainText('资料标签已保存')
  await editor.getByRole('tab', { name: '修订稿' }).click()
  await expect(editor.getByRole('textbox', { name: '向用户说明本次更新' })).toHaveValue('补充第三题解析')
  await editor.getByRole('tab', { name: '打印版本' }).click()
  await select(page, '关联打印文件', '配套答案 · v1 · 答案版')
  page.once('dialog', dialog => dialog.dismiss())
  await select(page, '要配置的版本', '练习版')
  await expect(editor.getByRole('combobox', { name: '要配置的版本' })).toContainText('答案解析版')
  await editor.getByRole('button', { name: '查找文件' }).click()
  await expect(editor.getByRole('combobox', { name: '关联打印文件' })).toContainText('配套答案')
  await editor.getByRole('tab', { name: '基本与发布' }).click()
  await editor.getByRole('textbox', { name: '公开标题' }).fill('保存主信息')
  await editor.getByRole('button', { name: '保存更改' }).click()
  await expect(editor).toContainText('公共习题已更新')
  await expect(editor.getByRole('status')).toContainText('有未保存的修改')
  await editor.getByRole('tab', { name: '打印版本' }).click()
  await expect(editor.getByRole('combobox', { name: '关联打印文件' })).toContainText('配套答案')
  await editor.getByRole('button', { name: '保存打印版本' }).click()
  await expect(editor).toContainText('打印版本已保存')
  expect(server.writes.at(-1)?.body).toMatchObject({ revision: 3, kind: 'answers', paper_id: 'answer-source' })
  await editor.getByRole('tab', { name: '修订稿' }).click()
  await expect(editor.getByRole('textbox', { name: '向用户说明本次更新' })).toHaveValue('补充第三题解析')
  await editor.getByRole('button', { name: '保存修订版' }).click()
  await expect.poll(() => server.writes.at(-1)?.path).toContain('/revision')
  expect(server.writes.at(-1)?.body).toMatchObject({ revision: 4, paper_id: 'revised-source', note: '补充第三题解析' })
  await expect(editor.getByRole('tab', { name: '基本与发布' })).toHaveAttribute('aria-selected', 'true')
  await expect(editor.getByRole('status')).not.toContainText('有未保存的修改')
})
