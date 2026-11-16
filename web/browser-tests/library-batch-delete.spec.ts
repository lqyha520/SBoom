import { expect, test } from '@playwright/test'

for (const width of [1440, 390]) {
  test(`云端批量删除预览、取消和保护结果 ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 950 })
    const records = ['旧版练习卷', '已发布的单元练习', '参考答案历史版本'].map((title, index) => ({
      id: 'paper-' + index, title, grade: '小学三年级', subject: '数学', version: 1, question_count: 10,
      folder_id: null, folder_name: null, group_name: '', favorite: false, file_status: 'ready', file_error: '',
      page_count: 2, created_at: 1, thumbnail_url: null, publication_id: index === 1 ? 'published' : null,
    }))
    let deleted = false, deleteCalls = 0
    await page.route('**/api/**', async route => {
      const path = new URL(route.request().url()).pathname
      let data: unknown
      if (path === '/api/v1/auth/me') data = { id: 7, username: 'teacher', role: 'admin' }
      else if (path === '/api/v1/auth/capabilities') data = { registration_enabled: false }
      else if (path === '/api/v1/scope/available') data = { available: { 小学三年级: ['数学'] } }
      else if (path === '/api/v1/scope') data = { allowed: ['加减法'], forbidden: [] }
      else if (path === '/api/v1/me/templates') data = { templates: [] }
      else if (path === '/api/v1/me/usage') data = { requests: 0, daily_limit: 0 }
      else if (path === '/api/v1/generation/options') data = { revision: 'fixture', timeout_ms: 900000, task_timeout_seconds: 870 }
      else if (path === '/api/v1/library/papers') data = { items: deleted ? records.slice(1) : records, total: deleted ? 2 : 3, has_more: false }
      else if (path === '/api/v1/library/folders') data = { items: [] }
      else if (path === '/api/v1/library/summary') data = { storage_bytes: (deleted ? 4 : 6) * 1024 ** 2, storage_limit_bytes: 5 * 1024 ** 3 }
      else if (path === '/api/v1/library/papers/batch-delete/preview') {
        expect(route.request().postDataJSON()).toEqual({ ids: records.map(row => row.id) })
        data = { items: records.map((row, index) => ({ id: row.id, title: row.title, storage_bytes: 2 * 1024 ** 2, reason: index === 1 ? '已关联公共库（含草稿或下架条目）' : index === 2 ? '被公共资料的打印版本历史引用' : null })), deletable_count: 1, reclaimable_bytes: 2 * 1024 ** 2 }
      } else if (path === '/api/v1/library/papers/batch-delete') {
        expect(route.request().postDataJSON()).toEqual({ ids: records.map(row => row.id), confirmed: true })
        deleteCalls++; deleted = true
        data = { deleted_ids: ['paper-0'], skipped: records.slice(1).map(row => ({ id: row.id, title: row.title, reason: '被公共库引用，已保留', storage_bytes: 2 * 1024 ** 2 })), released_bytes: 2 * 1024 ** 2 }
      } else throw new Error('未声明请求：' + path)
      await route.fulfill({ json: data })
    })
    await page.goto('/')
    if (width < 600) {
      await page.getByRole('button', { name: '工作台工具', exact: true }).click()
      await page.getByRole('menuitem', { name: '云端试卷' }).click()
    } else await page.getByRole('button', { name: '云端试卷', exact: true }).click()
    await expect(page.getByLabel('试卷库容量')).toContainText('/ 5 GB')
    await page.getByRole('button', { name: '批量管理', exact: true }).click()
    await page.getByRole('button', { name: '全选已加载（最多 50 份）', exact: true }).click()
    await page.getByRole('button', { name: '删除所选（3）', exact: true }).click()
    await expect(page.getByRole('dialog', { name: '确认批量删除' })).toBeVisible()
    await expect(page.getByLabel('批量删除预览')).toContainText('打印版本历史引用')
    expect(deleteCalls).toBe(0)
    await expect(page.getByRole('dialog', { name: '云端试卷', exact: true })).toBeHidden()
    await page.screenshot({ path: info.outputPath(`delete-preview-${width}.png`), fullPage: true, animations: 'disabled' })
    await page.getByRole('button', { name: '取消', exact: true }).click()
    await expect(page.locator('.archive-row')).toHaveCount(3)
    expect(deleteCalls).toBe(0)
    await page.getByRole('button', { name: '删除所选（3）', exact: true }).click()
    await page.getByRole('button', { name: '确认删除 1 份', exact: true }).click()
    await expect(page.locator('.archive-row')).toHaveCount(2)
    await expect(page.getByText('已删除 1 份，释放 2.0 MB；保留 2 份')).toBeVisible()
    await expect(page.getByLabel('试卷库容量')).toContainText('已用 4.0 MB')
    expect(deleteCalls).toBe(1)
    await page.screenshot({ path: info.outputPath(`delete-result-${width}.png`), fullPage: true, animations: 'disabled' })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}
