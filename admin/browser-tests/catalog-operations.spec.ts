import { expect, test } from '@playwright/test'
for (const width of [1440, 390]) {
  test(`资料体检、发布排期和取消 ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 950 })
    const paper = { id: 'paper-1', title: '教材同步练习', grade: '小学一年级', subject: '数学', status: 'draft', revision: 3, featured: false, required_view: 'free', required_download: 'vip', answer_readiness: 'separate', download_mode: 'pdf', category: '', category_id: '', description: '', assets: [], question_types: ['oral_math'], thumbnail_url: null }
    let scheduled: Record<string, unknown> | null = null, writes = 0
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    await page.route('**/api/**', async route => {
      const request = route.request(), path = new URL(request.url()).pathname
      let data: unknown
      if (path === '/api/v1/auth/me') data = { id: 1, username: 'admin', role: 'admin', is_super_admin: true }
      else if (path === '/api/v1/admin/site/categories' || path === '/api/v1/admin/site/dictionary') data = { items: [] }
      else if (path === '/api/v1/admin/catalog/summary') data = { total: 1, draft: 1, published: 0, withdrawn: 0, favorites: 0, downloads: 0 }
      else if (path === '/api/v1/admin/catalog/papers') data = { items: [paper], total: 1, has_more: false }
      else if (path === '/api/v1/admin/catalog/papers/paper-1') data = paper
      else if (path === '/api/v1/admin/catalog/health') data = { items: [{ catalog_id: paper.id, title: paper.title, revision: 3, status: 'draft', external: false, link_check: null, issues: [{ code: 'textbook_missing', severity: 'warning', message: '未关联可见教材标签，无法参与教材精准推荐' }] }], total: 1, has_more: false, checked_at: 1 }
      else if (path === '/api/v1/admin/catalog/schedules') data = { items: scheduled ? [scheduled] : [], total: scheduled ? 1 : 0, has_more: false }
      else if (path === '/api/v1/admin/catalog/schedules/paper-1') {
        if (request.method() === 'PUT') {
          const body = request.postDataJSON(); expect(body).toMatchObject({ catalog_revision: 3, schedule_revision: 0, confirm_publication: true })
          expect(body.scheduled_at).toBeGreaterThan(Date.now() / 1000); writes++
          scheduled = { ...body, catalog_id: paper.id, title: paper.title, revision: 1, status: 'pending', message: '', updated_at: 1 }
        } else if (request.method() === 'DELETE') {
          expect(new URL(request.url()).searchParams.get('revision')).toBe('1'); writes++
          scheduled = { ...scheduled, revision: 2, status: 'cancelled', message: '已取消排期' }
          await route.fulfill({ status: 204 }); return
        }
        data = scheduled
      } else throw new Error('未声明请求：' + path)
      await route.fulfill({ json: data })
    })
    await page.goto('/admin/#papers')
    await page.getByRole('button', { name: '资料体检', exact: true }).click()
    await expect(page.getByRole('dialog', { name: '资料体检', exact: true })).toContainText('未关联可见教材标签')
    await page.screenshot({ path: info.outputPath(`catalog-health-${width}.png`), fullPage: true })
    await page.getByRole('button', { name: '完成', exact: true }).click()
    await page.getByRole('button', { name: '发布排期', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: '资料发布排期', exact: true })
    await dialog.getByRole('button', { name: '选择草稿并安排发布', exact: true }).click()
    await dialog.getByRole('button', { name: '选择', exact: true }).click()
    await expect(dialog.getByRole('button', { name: '保存排期', exact: true })).toBeDisabled()
    expect(writes).toBe(0)
    await dialog.getByRole('checkbox', { name: '我已核对当前资料、答案、文件及会员权限，确认到时公开发布', exact: true }).check()
    await page.screenshot({ path: info.outputPath(`catalog-schedule-${width}.png`), fullPage: true })
    await dialog.getByRole('button', { name: '保存排期', exact: true }).click()
    await expect(dialog).toContainText('待发布')
    page.once('dialog', dialog => dialog.accept())
    await dialog.getByRole('button', { name: '取消排期', exact: true }).click()
    await expect(dialog).toContainText('已取消')
    expect(writes).toBe(2)
    expect(errors).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}


for (const width of [1440, 390]) {
  test(`全库体检分类、跨页异常与排期状态筛选 ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 950 })
    const paper = { id: 'paper', title: '公共资料', grade: '小学一年级', subject: '数学', status: 'draft', revision: 1, download_mode: 'external', category: '', category_id: '' }
    const health = Array.from({ length: 25 }, (_, index) => ({ catalog_id: 'health-' + index, title: '体检资料 ' + index, revision: 1, status: 'draft', external: false, link_check: null,
      issues: index === 24 ? [{ code: 'asset_unavailable', severity: 'error', message: '文件缺失或大小异常' }] : [] }))
    const schedules = [
      { catalog_id: 'failed', title: '需要处理的排期', scheduled_at: 1, catalog_revision: 1, revision: 1, status: 'failed', message: '资料版本已变化', updated_at: 1 },
      { catalog_id: 'pending', title: '等待发布的资料', scheduled_at: 2, catalog_revision: 1, revision: 1, status: 'pending', message: '', updated_at: 1 },
      { catalog_id: 'published', title: '已发布的资料', scheduled_at: 3, catalog_revision: 1, revision: 1, status: 'published', message: '', updated_at: 1 },
    ]
    await page.route('**/api/**', async route => {
      const url = new URL(route.request().url()), path = url.pathname
      let data: unknown
      if (path === '/api/v1/auth/me') data = { id: 1, username: 'admin', role: 'admin', is_super_admin: true }
      else if (path === '/api/v1/admin/site/categories' || path === '/api/v1/admin/site/dictionary') data = { items: [] }
      else if (path === '/api/v1/admin/catalog/summary') data = { total: 1, draft: 1, published: 0, withdrawn: 0, favorites: 0, downloads: 0 }
      else if (path === '/api/v1/admin/catalog/papers') data = { items: [paper], total: 1, has_more: false }
      else if (path === '/api/v1/admin/catalog/health') {
        let matched = health
        if (url.searchParams.get('only_issues') === 'true') matched = matched.filter(item => item.issues.length)
        if (url.searchParams.get('category')) { expect(url.searchParams.get('category')).toBe('file'); matched = matched.filter(item => item.issues.length) }
        const offset = Number(url.searchParams.get('offset'))
        data = { items: matched.slice(offset, offset + 20), total: matched.length, has_more: offset + 20 < matched.length, checked_at: 1, counts: { all: 25, issues: 1, file: 1 } }
      } else if (path === '/api/v1/admin/catalog/schedules') {
        const status = url.searchParams.get('status')
        const matched = schedules.filter(item => !status || item.status === status)
        data = { items: matched, total: matched.length, has_more: false, counts: { all: 3, failed: 1, pending: 1, published: 1, cancelled: 0 } }
      } else throw new Error('未声明请求：' + path)
      await route.fulfill({ json: data })
    })
    await page.goto('/admin/#papers')
    await page.getByRole('button', { name: '资料体检', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: '资料体检', exact: true })
    await expect(dialog).toContainText('25 份 · 1 份有提示')
    await expect(dialog.locator('.ops-card')).toHaveCount(20)
    await dialog.getByRole('button', { name: '下一页', exact: true }).click()
    await expect(dialog.locator('.ops-card')).toHaveCount(5)
    await dialog.getByRole('checkbox', { name: '仅显示异常资料（全部页面）', exact: true }).check()
    await expect(dialog.locator('.ops-card')).toHaveCount(1)
    await expect(dialog).toContainText('第 1 页 · 共 1 条')
    await expect(dialog).toContainText('文件缺失或大小异常')
    await dialog.getByRole('button', { name: '文件异常（1）', exact: true }).click()
    await expect(dialog.getByRole('button', { name: '文件异常（1）', exact: true })).toHaveAttribute('aria-pressed', 'true')
    await expect(dialog.getByRole('button', { name: '下一页', exact: true })).toBeDisabled()
    await dialog.getByRole('button', { name: '完成', exact: true }).click()
    await page.getByRole('button', { name: '发布排期', exact: true }).click()
    const scheduleDialog = page.getByRole('dialog', { name: '资料发布排期', exact: true })
    await expect(scheduleDialog.locator('.ops-card')).toHaveCount(3)
    await scheduleDialog.getByRole('button', { name: '失败待处理（1）', exact: true }).click()
    await expect(scheduleDialog.locator('.ops-card')).toHaveCount(1)
    await expect(scheduleDialog.locator('.ops-card')).toContainText('资料版本已变化')
    await scheduleDialog.getByRole('button', { name: '待发布（1）', exact: true }).click()
    await expect(scheduleDialog.locator('.ops-card')).toContainText('等待发布的资料')
    await scheduleDialog.getByRole('button', { name: '已发布（1）', exact: true }).click()
    await expect(scheduleDialog.locator('.ops-card')).toContainText('已发布的资料')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}
