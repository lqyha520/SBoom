import { expect, test, type BrowserContext } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import type { DraftData, MaterialData, PublicationData, WorkflowRecord } from '../src/xhs-workflow'

test.use({ reducedMotion: 'reduce' })

test('发布草稿刷新恢复素材和本机配图，缺失文件保留引用等待处理', async ({ context, page }, info) => {
  await fixture(context)
  const png = Buffer.from(await page.evaluate(() => {
    const canvas = document.createElement('canvas'); canvas.width = 20; canvas.height = 20
    const draw = canvas.getContext('2d')!; draw.fillStyle = '#087955'; draw.fillRect(0, 0, 20, 20)
    return canvas.toDataURL('image/png').split(',')[1]!
  }), 'base64')
  const library = { id: 'library-ref', asset_id: 'library-one', name: '素材.png', media_type: 'image/png', size_bytes: png.length, last_modified: 0 }
  const record: WorkflowRecord<PublicationData> = {
    id: 'pub-recovery', kind: 'publications', parent_id: null, title: '配图恢复草稿', status: 'planned', revision: 1, created_at: '', updated_at: '',
    data: { title: '配图恢复草稿', status: 'planned', source: 'custom', media: [library],
      custom_content: { headline: '每天一道数学题', body: '观察图片里的规律，再动笔练习。', hashtags: '#数学', media_notes: '' },
      account: '数学小课堂', account_id: 'account-one', scheduled_at: null, published_at: null, url: '', notes: '', conclusion: '', next_action: '',
      rights_checked: false, truth_checked: false, privacy_checked: false, media_checked: false, platform_checked: false, review_notes: '' },
  }
  let writes = 0, fileReads = 0
  await context.route('**/xhs-workflow/records/publications/pub-recovery', async route => {
    if (route.request().method() === 'PUT') { record.data = route.request().postDataJSON().data; record.revision++; writes++ }
    await route.fulfill({ json: record })
  })
  await context.route('**/xhs-workspace/assets/library-one**', async route => {
    if (new URL(route.request().url()).pathname.endsWith('/file')) {
      fileReads++; await route.fulfill({ contentType: 'image/png', body: png })
    } else await route.fulfill({ json: { id: 'library-one', media_type: 'image/png', size_bytes: png.length, data: { title: '素材', archived: false, rights: 'original' } } })
  })
  await page.goto('/admin/#xhsPublishing?id=pub-recovery')
  const images = page.locator('.publication-previews img')
  await expect(images).toHaveCount(1)
  await page.getByLabel('选择图文图片', { exact: true }).setInputFiles([
    { name: 'blue.png', mimeType: 'image/png', buffer: png }, { name: 'red.png', mimeType: 'image/png', buffer: png },
  ])
  await expect(page.getByText('配图已暂存到本机；保存草稿后可在本浏览器恢复。', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '前移图片 3', exact: true }).click()
  await page.getByRole('button', { name: '先保存草稿', exact: true }).click()
  await expect.poll(() => record.data.media?.map(item => item.name)).toEqual(['素材.png', 'red.png', 'blue.png'])
  await expect(page.getByText('已保存', { exact: true })).toBeVisible()
  await page.reload()
  await expect(images).toHaveCount(3)
  await expect(page.locator('.publication-previews figcaption span')).toHaveText(['素材.png', 'red.png', 'blue.png'])
  await expect.poll(() => images.evaluateAll(nodes => nodes.every(node => (node as HTMLImageElement).naturalWidth > 0))).toBe(true)
  expect(fileReads).toBe(2); expect(writes).toBe(1)
  await page.setViewportSize({ width: 390, height: 950 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('publication-media-recovered.png'), fullPage: true })
  await page.evaluate(async id => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open('lc-xhs-publication-media', 1)
      request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error)
    })
    try { await new Promise<void>((resolve, reject) => {
      const tx = db.transaction('files', 'readwrite'); tx.objectStore('files').delete('1:' + id)
      tx.oncomplete = () => resolve(); tx.onerror = () => reject(tx.error)
    }) } finally { db.close() }
  }, record.data.media![1]!.id)
  await page.reload()
  await expect(page.getByRole('alert').filter({ hasText: '以下配图暂时无法恢复：red.png' })).toBeVisible()
  await expect(images).toHaveCount(2)
  expect(record.data.media).toHaveLength(3); expect(writes).toBe(1)
  await page.getByRole('button', { name: '移除缺失配图', exact: true }).click()
  await page.getByRole('button', { name: '先保存草稿', exact: true }).click()
  await expect.poll(() => record.data.media?.map(item => item.name)).toEqual(['素材.png', 'blue.png'])
})

async function contentFixture(context: BrowserContext) {
  await fixture(context)
  type Record = WorkflowRecord<MaterialData | DraftData>
  const records = new Map<string, Record>()
  const writes: { kind: string; method: string }[] = []
  const materialData: MaterialData = { title: '一年级口算资料', status: 'draft', grade: '一年级', subject: '数学', keyword: '口算',
    game_type: 'fill_blank', difficulty: 'medium', question_count: 1, instructions: '每天练习一题',
    questions: [{ stem: '1+1=?', options: [], answer: '2', analysis: '一加一等于二', quality_issues: [] }],
    accuracy_checked: false, scope_checked: false, layout_checked: false, review_notes: '', generation_request_id: '' }
  const record = (id: string, kind: 'materials' | 'drafts', parent: string, data: MaterialData | DraftData, revision = 1): Record =>
    ({ id, kind, parent_id: parent, title: data.title, status: data.status, revision, data, created_at: '2026-11-01T02:00:00Z', updated_at: '2026-11-01T02:00:00Z' })
  records.set('material-one', record('material-one', 'materials', 'idea-one', materialData, 2))
  for (const name of ['A', 'B']) records.set(`draft-${name.toLowerCase()}`, record(`draft-${name.toLowerCase()}`, 'drafts', 'material-one', {
    title: `笔记 ${name}`, status: 'draft', audience: '家长', angle: '', headline: `发布标题 ${name}`, title_options: [], body: `这是笔记 ${name} 的正文`, hashtags: '#数学',
    cover_title: `封面 ${name}`, cover_subtitle: '每天一题', theme: 'green', cards: [{ heading: `内页 ${name}`, body: '使用方法' }], notes: '', generation_request_id: 'generated-one', source_material_revision: 1,
  }))
  const enriched = (value: Record) => ({ ...value, children: [...records.values()].filter(child => child.parent_id === value.id).map(child => ({ id: child.id, kind: child.kind, title: child.title, status: child.status })) })
  await context.route('**/api/v1/admin/xhs-workspace/profiles**', route => route.fulfill({ json: { items: [], total: 0 } }))
  await context.route('**/api/v1/admin/xhs-workflow/records/**', async route => {
    const request = route.request(), url = new URL(request.url())
    const match = url.pathname.match(/\/records\/(materials|drafts)(?:\/([^/]+))?(\/versions)?$/)
    if (!match) { await route.fallback(); return }
    const [, kind, id, versions] = match
    if (versions) { await route.fulfill({ json: { items: [], total: 0 } }); return }
    let value: unknown
    if (request.method() === 'POST') {
      const body = request.postDataJSON() as { id: string; parent_id: string; data: MaterialData | DraftData }
      const created = record(body.id, kind as 'materials' | 'drafts', body.parent_id, body.data)
      records.set(created.id, created); writes.push({ kind: kind!, method: 'POST' }); value = enriched(created)
    } else if (id) {
      const current = records.get(id)!
      if (request.method() === 'PUT') {
        const body = request.postDataJSON() as { data: MaterialData | DraftData }
        if (JSON.stringify(current.data) !== JSON.stringify(body.data)) Object.assign(current, { data: body.data, title: body.data.title, status: body.data.status, revision: current.revision + 1 })
        writes.push({ kind: kind!, method: 'PUT' })
      }
      value = enriched(current)
    } else {
      const items = [...records.values()].filter(item => item.kind === kind)
      value = { items, total: items.length, page: 1, page_size: 20 }
    }
    await route.fulfill({ status: request.method() === 'POST' ? 201 : 200, json: value })
  })
  return { records, writes }
}

// Exercise real UI components against isolated data, without touching local accounts or posting content.
async function fixture(context: BrowserContext) {
  const queries: URLSearchParams[] = [], writes: unknown[] = [], openedNotes: unknown[] = []
  const record = { id: 'idea-one', kind: 'ideas', parent_id: null, title: '一年级口算分层练习', status: 'inbox', revision: 1,
    data: { title: '一年级口算分层练习', status: 'inbox', grade: '一年级', subject: '数学', keyword: '口算', audience: '一年级家长',
      problem: '孩子计算正确，但速度不稳定', angle: '每天十题，按难度分层', format: '分层练习', priority: 'normal', due_date: null, source_note_id: '', notes: '' },
    created_at: '2026-10-30T02:00:00Z', updated_at: '2026-10-30T02:00:00Z' }
  const records = [record, { ...record, id: 'idea-two', title: '找规律方法卡', status: 'planned', data: { ...record.data, title: '找规律方法卡', keyword: '找规律' } },
    { ...record, id: 'idea-three', title: '加减混合运算易错点', status: 'creating', data: { ...record.data, keyword: '混合运算' } }]
  await context.route('http://127.0.0.1:17632/**', route => {
    if (new URL(route.request().url()).pathname === '/accounts/open-note') openedNotes.push(route.request().postDataJSON())
    return route.fulfill({ json: { enabled: true, busy: false, version: 11, items: [{ id: 'account-one', name: '数学小课堂', archived: false, busy: false }] } })
  })
  await context.route('**/api/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname
    let data: unknown
    if (path === '/api/v1/auth/me') data = { id: 1, username: 'admin', role: 'admin', is_super_admin: true }
    else if (path === '/api/v1/local-access/issue') data = { token: 'browser-fixture-capability' }
    else if (path === '/api/v1/admin/xhs-workflow/records/ideas') {
      queries.push(url.searchParams)
      const q = url.searchParams.get('q') || '', status = url.searchParams.get('status') || ''
      const items = records.filter(item => (!q || item.title.includes(q)) && (!status || item.status === status))
      data = { items, total: q || status ? items.length : 41, page: Number(url.searchParams.get('page') || 1), page_size: 20 }
    } else if (path === '/api/v1/admin/xhs-workflow/records/ideas/idea-one') {
      if (request.method() === 'PUT') { const body = request.postDataJSON(); writes.push(body); Object.assign(record, { data: body.data, title: body.data.title, revision: record.revision + 1 }) }
      data = record
    } else if (/\/xhs-workflow\/records\/(materials|drafts|publications)$/.test(path)) data = { items: [], total: 0, page: 1, page_size: 20 }
    else if (path === '/api/v1/admin/xhs-research/tasks') data = { items: [{ id: 'task-one', grade: '一年级', subject: '数学', keyword: '口算', period: 'week', sort_by: 'popular',
      note_limit: 30, status: 'completed', note_count: 1, created_at: '2026-10-30T02:00:00Z' }], total: 1 }
    else if (path === '/api/v1/admin/xhs-research/batches') data = { items: [] }
    else if (path === '/api/v1/admin/xhs-research/notes') data = { items: [{ note_id: 'note-one', title: '一年级口算，这三个步骤值得练习', author: '数学老师',
      published_text: '2026-10-29', likes_text: '1200', likes_count: 1200, captured_at: '2026-10-30T02:00:00Z', favorite: false, mark_status: 'reference', remark: '可以改为分层练习',
      revision: 1, seen_count: 1, seen_before: false, grade: '一年级', subject: '数学', keyword: '口算', url: 'https://www.xiaohongshu.com/explore/note-one?xsec_token=fixture-token&xsec_source=pc_search' }], total: 1 }
    else if (path === '/api/v1/admin/xhs-workspace/today') data = { items: [], total: 0, page: 1 }
    else if (path === '/api/v1/admin/xhs-workspace/calendar') {
      const time = new Date(url.searchParams.get('start')!); time.setHours(10)
      const item = { id: 'publication-one', kind: 'publications', title: '口算练习发布', status: 'ready', data: { account: '数学小课堂' },
        account_key: 'account-one', calendar_at: time.toISOString(), conflicts: ['another-publication'] }
      data = { items: [item], unscheduled: [{ ...item, id: 'publication-two', title: '找规律待排期', calendar_at: null }],
        accounts: [{ id: 'account-one', name: '数学小课堂', last_published_at: new Date().toISOString() }] }
    }
    else { await route.fulfill({ status: 404, json: { detail: `未声明的测试请求：${path}` } }); return }
    await route.fulfill({ json: data })
  })
  return { queries, writes, openedNotes }
}

test('内容列表搜索回到第一页，空结果可清空筛选恢复', async ({ context, page }, info) => {
  const data = await fixture(context)
  await page.goto('/admin/#xhsIdeas')
  await expect(page.locator('.workflow-list-item')).toHaveCount(3)
  await expect(page.locator('.workflow-item-summary').first()).toContainText('一年级 · 数学 · 口算')
  await page.locator('.workflow-pagination button').filter({ hasText: /^2$/ }).click()
  await expect.poll(() => data.queries.at(-1)?.get('page')).toBe('2')
  const before = data.queries.length
  await page.getByRole('textbox', { name: '搜索标题' }).fill('口算')
  await page.getByRole('textbox', { name: '搜索标题' }).press('Enter')
  await expect(page.locator('.workflow-list-item')).toHaveCount(1)
  expect(data.queries).toHaveLength(before + 1)
  expect(data.queries.at(-1)?.get('page')).toBe('1')
  await page.getByRole('textbox', { name: '搜索标题' }).fill('不存在的内容')
  await page.getByRole('textbox', { name: '搜索标题' }).press('Enter')
  await expect(page.getByText('没有找到匹配的内容')).toBeVisible()
  await page.locator('.workflow-empty-state').getByRole('button', { name: '清空筛选' }).click()
  await expect(page.locator('.workflow-list-item')).toHaveCount(3)
  await page.screenshot({ path: info.outputPath('workbench-desktop.png'), fullPage: true })
})

test('编辑页快捷保存，手机端长表单仍可看到保存操作', async ({ context, page }, info) => {
  const data = await fixture(context)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/admin/#xhsIdeas?id=idea-one')
  await page.getByRole('textbox', { name: '选题名称' }).fill('每日十题口算练习')
  await expect(page.getByText('有未保存的修改')).toBeVisible()
  await page.getByRole('textbox', { name: '选题名称' }).press('Control+s')
  await expect.poll(() => data.writes.length).toBe(1)
  await expect(page.getByText('已保存', { exact: true })).toBeVisible()
  await page.locator('.admin-main').evaluate(element => { element.scrollTop = 600 })
  await expect(page.getByRole('button', { name: '保存', exact: true })).toBeInViewport()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('workbench-mobile-editor.png'), fullPage: true })
})

test('调研条件说明、笔记整理和窄屏滚动入口可用', async ({ context, page }, info) => {
  const data = await fixture(context)
  await page.goto('/admin/#xhsResearch')
  await expect(page.getByText('将搜索：一年级 数学 全部知识点')).toBeVisible()
  await expect(page.getByText('请选择一个采集账号')).toBeVisible()
  expect((await page.locator('.research-form').boundingBox())!.height).toBeLessThan(220)
  await page.getByRole('combobox', { name: '采集账号', exact: true }).click()
  await page.getByRole('option', { name: '数学小课堂', exact: true }).click()
  await expect(page.getByText('一年级口算，这三个步骤值得练习', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '查看笔记', exact: true }).click()
  await expect.poll(() => data.openedNotes.length).toBe(1)
  expect(data.openedNotes[0]).toEqual({ account_id: 'account-one', url: 'https://www.xiaohongshu.com/explore/note-one?xsec_token=fixture-token&xsec_source=pc_search' })
  expect(context.pages()).toHaveLength(1)
  await page.getByRole('button', { name: '更多条件', exact: true }).click()
  await expect(page.getByRole('textbox', { name: '筛选作者', exact: true })).toBeVisible()
  await page.getByRole('textbox', { name: '筛选作者', exact: true }).fill('数学老师')
  await page.getByRole('button', { name: '筛选', exact: true }).click()
  await page.getByRole('button', { name: '收起条件', exact: true }).click()
  await expect(page.getByLabel('已应用的笔记筛选')).toContainText('作者：数学老师')
  await page.getByRole('button', { name: '编辑标记和备注：一年级口算，这三个步骤值得练习' }).click()
  await page.getByRole('textbox', { name: '笔记备注' }).fill('继续保留这条改编思路')
  await page.getByRole('button', { name: '取消', exact: true }).click()
  await expect(page.getByRole('dialog', { name: '放弃未保存的备注？' })).toBeVisible()
  await page.getByRole('button', { name: '继续编辑', exact: true }).click()
  await expect(page.getByRole('textbox', { name: '笔记备注' })).toHaveValue('继续保留这条改编思路')
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: '放弃修改', exact: true }).click()
  await expect(page.getByRole('dialog')).toBeHidden()
  await page.getByRole('button', { name: '今日待办' }).click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toBeHidden()
  await page.screenshot({ path: info.outputPath('research-desktop.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByText('左右滑动查看完整笔记和整理操作')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('research-mobile.png'), fullPage: true })
  await page.locator('.research-results').scrollIntoViewIfNeeded()
  await page.screenshot({ path: info.outputPath('research-mobile-results.png'), fullPage: true })
})

test('关联选择和发布日历在桌面及手机上可用', async ({ context, page }, info) => {
  await fixture(context)
  await page.goto('/admin/#xhsMaterials?new=1')
  await expect(page.getByRole('heading', { name: '选择关联选题库' })).toBeVisible()
  await expect(page.locator('.parent-picker .workflow-item-summary').first()).toContainText('一年级 · 数学 · 口算')
  await page.getByRole('textbox', { name: '搜索关联内容' }).fill('口算')
  await page.getByRole('textbox', { name: '搜索关联内容' }).press('Enter')
  await expect(page.locator('.parent-picker .workflow-list-item')).toHaveCount(1)
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.locator('.parent-picker').scrollIntoViewIfNeeded()
  await page.screenshot({ path: info.outputPath('parent-picker-mobile.png'), fullPage: true })
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto('/admin/#xhsPublishing')
  await page.getByRole('button', { name: '发布日历', exact: true }).click()
  await expect(page.getByRole('button', { name: /口算练习发布/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /找规律待排期/ })).toBeVisible()
  await expect(page.getByText('本周 1 项 · 未排期 1 项')).toBeVisible()
  await page.screenshot({ path: info.outputPath('calendar-desktop.png'), fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole('button', { name: '下一周', exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.locator('.publication-calendar').scrollIntoViewIfNeeded()
  await page.screenshot({ path: info.outputPath('calendar-mobile.png'), fullPage: true })
})

test('资料手动制作可逐步保存、复核并带入笔记', async ({ context, page }, info) => {
  const data = await contentFixture(context)
  await page.goto('/admin/#xhsMaterials?new=1')
  await expect(page.getByRole('button', { name: '保存', exact: true })).toBeDisabled()
  await expect(page.getByText('请先选择关联选题', { exact: true })).toBeVisible()
  await page.locator('.parent-picker .workflow-list-item').first().click()
  await expect(page.getByRole('textbox', { name: '资料名称', exact: true })).toHaveValue('一年级口算分层练习')
  await page.getByRole('button', { name: '手动编写', exact: true }).click()
  await expect(page.getByRole('button', { name: '保存并制作笔记', exact: true })).toBeDisabled()
  await page.getByRole('textbox', { name: '第1题题干', exact: true }).fill('2+3=?')
  await page.getByRole('textbox', { name: '第1题答案', exact: true }).fill('5')
  await page.getByRole('textbox', { name: '第1题讲解', exact: true }).fill('两个和三个合起来是五个。')
  await page.getByRole('button', { name: '保存并复核资料', exact: true }).click()
  await expect(page.getByRole('checkbox', { name: '已逐题核对答案与讲解', exact: true })).toBeEnabled()
  await page.getByRole('checkbox', { name: '已逐题核对答案与讲解', exact: true }).check()
  await page.getByRole('checkbox', { name: '已检查适用年级与知识范围', exact: true }).check()
  await page.getByRole('checkbox', { name: '已检查导出排版与留白', exact: true }).check()
  await page.getByRole('button', { name: '1 · 出题设置', exact: true }).click()
  await page.getByText('题型', { exact: true }).locator('..').getByRole('combobox').click()
  await page.getByRole('option', { name: '选择题', exact: true }).click()
  await page.getByRole('button', { name: '3 · 复核与导出', exact: true }).click()
  await expect(page.getByRole('checkbox', { name: '已逐题核对答案与讲解', exact: true })).not.toBeChecked()
  await expect(page.getByRole('checkbox', { name: '已逐题核对答案与讲解', exact: true })).toBeDisabled()
  await expect(page.getByText('请先保存当前内容，再完成复核。', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '保存当前内容', exact: true }).click()
  await page.getByRole('button', { name: '保存并制作笔记', exact: true }).click()
  await expect(page.getByRole('textbox', { name: '笔记内部名称', exact: true })).toHaveValue('一年级口算分层练习 · 笔记')
  expect(data.writes.filter(write => write.kind === 'materials' && write.method === 'POST')).toHaveLength(1)
  await page.screenshot({ path: info.outputPath('material-to-draft.png'), fullPage: true })
})

test('配图编辑与切换笔记清除旧预览，并保持清楚的步骤入口', async ({ context, page }, info) => {
  await contentFixture(context)
  await page.goto('/admin/#xhsDrafts?id=draft-a')
  await page.getByRole('button', { name: '下一步：封面与内页', exact: true }).click()
  await page.getByRole('button', { name: '下一步：预览与导出', exact: true }).click()
  await page.getByRole('button', { name: '预览全部配图', exact: true }).click()
  await expect(page.getByRole('img', { name: '封面预览', exact: true })).toBeVisible()
  const oldImage = await page.getByRole('img', { name: '封面预览', exact: true }).getAttribute('src')
  await page.getByRole('button', { name: '2 · 封面与内页', exact: true }).click()
  await page.getByRole('textbox', { name: '封面主标题', exact: true }).fill('更新后的封面')
  await page.getByRole('button', { name: '下一步：预览与导出', exact: true }).click()
  await expect(page.getByRole('img', { name: '封面预览', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '预览全部配图', exact: true }).click()
  await expect(page.getByRole('img', { name: '封面预览', exact: true })).not.toHaveAttribute('src', oldImage!)
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByRole('button', { name: '3 · 预览与导出', exact: true })).toHaveAttribute('aria-current', 'step')
  await page.getByRole('navigation', { name: '内容制作阶段' }).getByRole('button', { name: /资料制作/ }).click()
  await page.getByRole('navigation', { name: '内容制作阶段' }).getByRole('button', { name: /笔记制作/ }).click()
  await expect(page).toHaveURL(/#xhsDrafts$/)
  await page.locator('.workflow-list-item').filter({ hasText: '笔记 B' }).click()
  await expect(page.getByRole('textbox', { name: '发布标题', exact: true })).toHaveValue('发布标题 B')
  await expect(page.getByRole('button', { name: '1 · 标题与正文', exact: true })).toHaveAttribute('aria-current', 'step')
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('draft-mobile-steps.png'), fullPage: true })
})

test('继续已有笔记保留资料版本提示，另建入口明确创建新方案', async ({ context, page }) => {
  const data = await contentFixture(context)
  await page.goto('/admin/#xhsMaterials?id=material-one')
  await page.getByRole('button', { name: '保存并继续笔记', exact: true }).click()
  await expect(page).toHaveURL(/#xhsDrafts\?id=draft-a$/)
  await expect(page.getByText('关联资料已有更新，当前文案仍基于旧版本。请核对题目与描述，或根据最新资料重新生成文案。', { exact: true })).toBeVisible()
  data.records.get('material-one')!.revision++
  await page.getByRole('button', { name: '刷新关联资料', exact: true }).click()
  await expect(page.getByText(/关联资料当前为第 3 版/)).toBeVisible()
  await expect(page.getByRole('textbox', { name: '笔记正文', exact: true })).toHaveValue('这是笔记 A 的正文')
  await page.getByRole('button', { name: '一年级口算资料', exact: true }).click()
  await page.getByRole('button', { name: '另建一篇笔记', exact: true }).click()
  await expect(page).toHaveURL(/#xhsDrafts\?new=1&parent=material-one$/)
  await expect(page.getByRole('textbox', { name: '笔记内部名称', exact: true })).toHaveValue('一年级口算资料 · 笔记')
  expect(data.writes.filter(write => write.kind === 'drafts' && write.method === 'POST')).toHaveLength(0)
})

test('资料 PDF 可在页面核对学生卷和答案卷，并下载当前预览', async ({ context, page }, info) => {
  await contentFixture(context)
  await page.goto('/admin/#xhsMaterials?id=material-one')
  await page.getByRole('button', { name: '3 · 复核与导出', exact: true }).click()
  await page.getByRole('button', { name: '预览资料 PDF', exact: true }).click()
  const modal = page.getByRole('dialog', { name: '资料 PDF 预览' })
  const student = modal.getByRole('img', { name: '学生卷第1页预览', exact: true })
  await expect(student).toBeVisible()
  await expect.poll(() => student.evaluate(element => (element as HTMLImageElement).naturalWidth)).toBe(1240)
  const studentImage = await student.getAttribute('src')
  await modal.getByRole('button', { name: '答案与讲解', exact: true }).click()
  await expect(modal.getByRole('img', { name: '答案讲解第1页预览', exact: true })).not.toHaveAttribute('src', studentImage!)
  const download = page.waitForEvent('download')
  await modal.getByRole('button', { name: '下载当前预览', exact: true }).click()
  const file = await download
  expect(file.suggestedFilename()).toBe('一年级口算资料-答案讲解.pdf')
  expect((await readFile((await file.path())!)).subarray(0, 8).toString()).toMatch(/^%PDF-/)
  await page.setViewportSize({ width: 390, height: 844 })
  await modal.getByRole('button', { name: '放大预览', exact: true }).click()
  await modal.getByRole('button', { name: '放大预览', exact: true }).click()
  const image = await modal.getByRole('img', { name: '答案讲解第1页预览', exact: true }).boundingBox()
  const viewport = await modal.locator('.pdf-preview').boundingBox()
  expect(image!.width).toBeGreaterThan(viewport!.width)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('material-pdf-mobile.png'), fullPage: true })
})

test('笔记可展开关联资料核对题目，缩小窗口后当前阶段仍完整可见', async ({ context, page }, info) => {
  const data = await contentFixture(context)
  const material = data.records.get('material-one')!.data as MaterialData
  material.questions = [...material.questions, ...[2, 3, 4].map(value => ({ stem: `${value}+1=?`, options: [], answer: String(value + 1), analysis: '在原数上增加一', quality_issues: [] }))]
  await page.goto('/admin/#xhsDrafts?id=draft-a')
  await page.locator('.workflow-source summary').click()
  await expect(page.locator('.workflow-source-question')).toHaveCount(3)
  await expect(page.locator('.workflow-source')).toContainText('1+1=?')
  await expect(page.locator('.workflow-source')).toContainText('完整内容请打开资料查看')
  await page.setViewportSize({ width: 390, height: 844 })
  await expect.poll(async () => {
    const nav = await page.getByRole('navigation', { name: '内容制作阶段' }).boundingBox()
    const active = await page.locator('nav[aria-label="内容制作阶段"] [aria-current="page"]').boundingBox()
    return !!nav && !!active && active.x >= nav.x && active.x + active.width <= nav.x + nav.width
  }).toBe(true)
  await page.locator('.workflow-source').scrollIntoViewIfNeeded()
  await page.screenshot({ path: info.outputPath('draft-source-mobile.png'), fullPage: true })
  await page.getByRole('button', { name: '打开资料完整内容', exact: true }).click()
  await expect(page).toHaveURL(/#xhsMaterials\?id=material-one$/)
})

test('历史版本先对比未保存正文，取消覆盖后保留当前内容', async ({ context, page }, info) => {
  const data = await contentFixture(context)
  const old = { ...data.records.get('draft-a')!.data, body: '历史版本的正文' }
  await context.route('**/xhs-workflow/records/drafts/draft-a/versions**', route => route.fulfill({ json: { items: [{ revision: 1, data: old, created_at: '2026-10-30T02:00:00Z' }], total: 1 } }))
  await page.goto('/admin/#xhsDrafts?id=draft-a')
  await page.getByRole('textbox', { name: '笔记正文', exact: true }).fill('当前还没保存的新正文')
  await page.getByRole('button', { name: '版本历史', exact: true }).click()
  const modal = page.getByRole('dialog', { name: '版本历史' })
  await modal.getByRole('button', { name: '带入编辑', exact: true }).click()
  await expect(modal).toContainText('当前还没保存的新正文')
  await expect(modal).toContainText('历史版本的正文')
  page.once('dialog', dialog => dialog.dismiss())
  await modal.getByRole('button', { name: '确认带入编辑', exact: true }).click()
  await expect(modal).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: info.outputPath('version-comparison-mobile.png'), fullPage: true })
  await page.keyboard.press('Escape')
  await expect(page.getByRole('textbox', { name: '笔记正文', exact: true })).toHaveValue('当前还没保存的新正文')
  expect(data.writes).toHaveLength(0)
})

test('新建笔记保存响应中断后恢复原记录，继续保存沿用同一记录', async ({ context, page }) => {
  const data = await contentFixture(context)
  let createdId = '', creates = 0
  await context.route('**/xhs-workflow/records/drafts', async route => {
    if (route.request().method() !== 'POST') { await route.fallback(); return }
    const body = route.request().postDataJSON() as { id: string; parent_id: string; data: DraftData }
    creates++; createdId = body.id
    data.records.set(body.id, { id: body.id, kind: 'drafts', parent_id: body.parent_id, title: body.data.title, status: body.data.status, revision: 1, data: body.data, created_at: '', updated_at: '' })
    await route.abort('failed')
  })
  await page.goto('/admin/#xhsDrafts?new=1&parent=material-one')
  await page.getByRole('textbox', { name: '笔记正文', exact: true }).fill('原提交内容')
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByText('已查询确认原提交保存成功。', { exact: true })).toBeVisible()
  await expect.poll(() => new URL(page.url()).hash).toBe('#xhsDrafts?id=' + createdId)
  await page.getByRole('textbox', { name: '笔记正文', exact: true }).fill('恢复后继续编辑')
  await page.getByRole('button', { name: '保存', exact: true }).click()
  await expect(page.getByText('已保存', { exact: true })).toBeVisible()
  expect(creates).toBe(1)
  expect((data.records.get(createdId)!.data as DraftData).body).toBe('恢复后继续编辑')
})

test('复盘数据和结论一次保存，返回版本同步到页面', async ({ context, page }) => {
  await fixture(context)
  const writes: string[] = []
  let metrics: unknown[] = []
  const record = { id: 'pub-review', kind: 'publications', title: '练习发布复盘', status: 'published', parent_id: null, revision: 1,
    data: { title: '练习发布复盘', status: 'published', account: '数学账号', url: 'https://xhslink.com/a/review', published_at: '2026-10-25T00:00:00Z', conclusion: '', next_action: '' } }
  await context.route('**/api/v1/admin/xhs-workflow/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path.endsWith('/reviews/pub-review')) {
      writes.push(path); const body = route.request().postDataJSON()
      Object.assign(record, { revision: 2, data: { ...record.data, conclusion: body.conclusion, next_action: body.next_action } })
      metrics = [{ ...body.metric, revision: 1 }]
      await route.fulfill({ json: { record, items: metrics } })
    } else if (path.endsWith('/metrics/pub-review')) await route.fulfill({ json: { items: metrics } })
    else if (path.endsWith('/records/publications/pub-review')) await route.fulfill({ json: record })
    else await route.fallback()
  })
  await page.goto('/admin/#xhsAnalytics?id=pub-review&checkpoint=7')
  await page.getByRole('spinbutton', { name: '浏览量', exact: true }).fill('300')
  await page.getByRole('textbox', { name: '复盘结论', exact: true }).fill('分层练习获得了反馈')
  await page.getByRole('button', { name: '保存复盘', exact: true }).click()
  await expect(page.getByText('数据和复盘已保存', { exact: true })).toBeVisible()
  expect(writes).toEqual(['/api/v1/admin/xhs-workflow/reviews/pub-review'])
  await expect(page.getByRole('spinbutton', { name: '浏览量', exact: true })).toHaveValue('300')
  await expect(page.getByRole('textbox', { name: '复盘结论', exact: true })).toHaveValue('分层练习获得了反馈')
})
