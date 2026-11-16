import { expect, test, type BrowserContext, type Page } from '@playwright/test'
import { defaultDownloadSettings } from '../src/download-settings'

async function fixture(context: BrowserContext, gate = Promise.resolve()) {
  let detailReads = 0
  const paper = { ...defaultDownloadSettings(), id: 'paper', paper_id: 'source', title: '导航回归习题',
    description: '', category_id: 'practice', category: '练习', status: 'draft', revision: 1,
    featured: false, grade: '三年级', subject: '数学', version: 1, question_count: 3,
    page_count: 0, file_status: 'ready', thumbnail_url: null, updated_at: 1,
    view_access: 'free', download_access: 'free', required_view: 'free', required_download: 'free',
    question_types: ['quiz'], assets: [], tags: [], editions: [] }
  await context.route('**/api/**', async route => {
    const url = new URL(route.request().url()), path = url.pathname
    expect(route.request().method()).toBe('GET')
    let data: unknown
    if (path === '/api/v1/auth/me') data = { id: 1, username: 'admin', role: 'admin', is_super_admin: true }
    else if (path === '/api/v1/admin/site/categories') data = { items: [{ id: 'practice', name: '练习', is_visible: true }] }
    else if (path === '/api/v1/admin/site/dictionary') data = { items: [{ value: url.searchParams.get('kind') === 'grade' ? '三年级' : '数学' }] }
    else if (path === '/api/v1/admin/catalog/summary') data = { draft: 60, published: 0, withdrawn: 0, favorites: 0, downloads: 0 }
    else if (path === '/api/v1/admin/catalog/papers') data = { items: [paper], total: 60, has_more: false }
    else if (path === '/api/v1/admin/catalog/papers/paper') { detailReads++; await gate; data = paper }
    else if (path === '/api/v1/admin/experience/topics') data = { items: [] }
    else throw new Error(`Unexpected request: ${path}`)
    await route.fulfill({ json: data })
  })
  return { detailReads: () => detailReads }
}

async function menu(page: Page, tab: string, label: string, width: number) {
  if (width < 800) await page.getByRole('combobox', { name: '选择管理页面', exact: true }).selectOption(tab)
  else await page.getByRole('navigation', { name: '管理后台导航', exact: true }).getByRole('button', { name: label, exact: true }).click()
}

for (const width of [1440, 390]) {
  test(`直达预览关闭后返回公共习题不再弹出，筛选与手动预览正常 ${width}px`, async ({ page, context }) => {
    const server = await fixture(context)
    await page.setViewportSize({ width, height: 1000 })
    await page.goto('/admin/#papers?paper=paper&q=math&status=draft&page=3')
    const preview = page.getByRole('dialog', { name: '导航回归习题', exact: true })
    await expect(preview).toBeVisible()
    await expect(page).not.toHaveURL(/paper=/)
    expect(server.detailReads()).toBe(1)
    await preview.getByRole('button', { name: '关闭', exact: true }).last().click()
    await menu(page, 'topics', '专题合集', width)
    await menu(page, 'papers', '公共习题', width)
    await expect(page.getByRole('button', { name: '刷新公共习题' })).toBeVisible()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await expect(page).toHaveURL(/#papers\?q=math&status=draft&page=3$/)
    expect(server.detailReads()).toBe(1)
    await page.reload()
    await expect(page.getByRole('button', { name: '刷新公共习题' })).toBeVisible()
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await page.getByRole('button', { name: '预览 导航回归习题', exact: true }).click()
    await expect(preview).toBeVisible()
    expect(server.detailReads()).toBe(2)
  })
}

test('直达预览加载期间关闭，响应返回后不会重新弹出', async ({ page, context }) => {
  let release!: () => void
  await fixture(context, new Promise<void>(resolve => { release = resolve }))
  try {
    await page.goto('/admin/#papers?paper=paper')
    const preview = page.getByRole('dialog', { name: '习题预览', exact: true })
    await expect(preview).toBeVisible()
    await preview.getByRole('button', { name: '关闭', exact: true }).last().click()
    const response = page.waitForResponse('**/api/v1/admin/catalog/papers/paper')
    release()
    await response
    await expect(page.getByRole('button', { name: '刷新公共习题' })).toBeVisible()
    await expect(page.getByRole('dialog')).toHaveCount(0)
  } finally { release() }
})
