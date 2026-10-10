import { expect, test, type BrowserContext } from '@playwright/test'
import type { CatalogDetail } from '../src/catalog'
import { defaultDownloadSettings } from '../src/download-settings'

async function catalogApi(context: BrowserContext) {
  let item: CatalogDetail | null = null, conflict = false
  const writes: Record<string, unknown>[] = []
  await context.route('**/api/**', async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname
    let data: unknown
    if (path === '/api/v1/auth/me') data = { id: 1, username: 'admin', role: 'admin' }
    else if (path === '/api/v1/admin/site/categories') data = { items: [{ id: 'practice', name: '随堂练习', is_visible: true }] }
    else if (path === '/api/v1/admin/site/dictionary') data = { items: [{ value: url.searchParams.get('kind') === 'grade' ? '小学三年级' : '数学' }] }
    else if (path === '/api/v1/admin/catalog/sources') data = { items: [{ id: 'source', title: '来源练习', grade: '小学三年级', subject: '数学', version: 1, file_status: 'ready', question_count: 3 }], total: 1, has_more: false }
    else if (path === '/api/v1/admin/catalog/summary') data = { total: item ? 1 : 0, published: item?.status === 'published' ? 1 : 0, draft: item?.status === 'draft' ? 1 : 0, withdrawn: 0, favorites: 0, downloads: 0 }
    else if (path === '/api/v1/admin/catalog/papers' && request.method() === 'POST') {
      item = { ...defaultDownloadSettings(), ...request.postDataJSON(), id: 'created', category: '随堂练习', status: 'draft', revision: 1,
        featured: false, grade: '小学三年级', subject: '数学', version: 1, question_count: 3, page_count: 0,
        file_status: 'ready', thumbnail_url: null, updated_at: 1, required_view: 'free', required_download: 'free',
        question_types: ['fill_blank'], assets: [] }
      data = item
    } else if (path === '/api/v1/admin/catalog/papers') data = { items: item ? [item] : [], total: item ? 1 : 0, has_more: false }
    else if (path === '/api/v1/admin/catalog/papers/created' && request.method() === 'PUT' && item) {
      const body = request.postDataJSON(); writes.push(body)
      if (conflict) {
        conflict = false; item.revision++
        await route.fulfill({ status: 409, json: { detail: { error: '记录已更新，请载入最新版本' } } }); return
      }
      expect(body.revision).toBe(item.revision)
      item = { ...item, ...body, revision: item.revision + 1 }; data = item
    } else if (path === '/api/v1/admin/catalog/papers/created') data = item
    else throw new Error(`浏览器用例出现未声明请求：${request.method()} ${path}`)
    await route.fulfill({ json: data })
  })
  return { writes, conflict: () => { conflict = true } }
}

for (const width of [1440, 320]) {
  test(`公共资料创建、预览、确认发布与冲突恢复保留修改 ${width}px`, async ({ page, context }, info) => {
    const server = await catalogApi(context), errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    await page.setViewportSize({ width, height: width === 320 ? 640 : 1000 })
    await page.goto('/admin/#papers')
    await page.getByRole('button', { name: '添加习题', exact: true }).click()
    let editor = page.getByRole('dialog', { name: '添加习题草稿', exact: true })
    await editor.getByRole('combobox').filter({ hasText: '选择习题' }).click()
    await page.getByRole('option', { name: '来源练习 · 小学三年级 · v1', exact: true }).click()
    await expect(editor.getByRole('textbox', { name: '公开标题' })).toHaveValue('来源练习')
    await editor.getByRole('textbox', { name: '公开标题' }).fill('浏览器回归练习')
    await expect(editor).toHaveCSS('opacity', '1')
    await page.screenshot({ path: info.outputPath('publication-form.png') })
    await editor.getByRole('button', { name: '创建草稿', exact: true }).click()
    editor = page.getByRole('dialog', { name: '编辑公共习题', exact: true })
    const created = page.getByRole('region', { name: '本次新建习题' })
    const preview = editor.getByRole('complementary', { name: '已保存资料预览' })
    await expect(preview.getByRole('button', { name: '管理员', exact: true })).toBeVisible()
    await page.screenshot({ path: info.outputPath('publication-preview.png') })
    await preview.getByRole('button', { name: '核对后设置发布', exact: true }).click()
    const publish = editor.getByRole('button', { name: '确认发布', exact: true })
    await expect(publish).toBeDisabled()
    await editor.getByRole('checkbox', { name: '已核对内容，确认公开发布', exact: true }).check()
    await publish.click()
    await expect(editor).toContainText('公共习题已更新')
    await page.screenshot({ path: info.outputPath('publication-published.png') })
    expect(server.writes[0]).toMatchObject({ revision: 1, status: 'published', confirm_publication: true })
    server.conflict()
    await editor.getByRole('textbox', { name: '公开标题' }).fill('保留我的标题')
    await editor.getByRole('button', { name: '保存更改', exact: true }).click()
    await editor.getByRole('button', { name: '载入最新并保留我的修改', exact: true }).click()
    await expect(editor).toContainText('您的修改已保留')
    await expect(editor.getByRole('textbox', { name: '公开标题' })).toHaveValue('保留我的标题')
    await editor.getByRole('button', { name: '保存更改', exact: true }).click()
    await expect.poll(() => server.writes.length).toBe(3)
    expect(server.writes[2]).toMatchObject({ revision: 3, title: '保留我的标题' })
    await editor.getByRole('button', { name: '关闭', exact: true }).last().click()
    await expect(page.locator('.catalog-table tbody')).toContainText('保留我的标题')
    await created.getByRole('button', { name: '本次新建 1 份习题 · 展开', exact: true }).click()
    await expect(created.getByRole('button', { name: '查看资料', exact: true })).toBeVisible()
    await expect(created.getByRole('button', { name: '预览并发布', exact: true })).toHaveCount(0)
    await expect(created.getByRole('listitem')).toHaveCount(1)
    if (width === 320) {
      const row = page.locator('.catalog-table tbody tr').first()
      await row.scrollIntoViewIfNeeded()
      await expect(row.getByRole('button', { name: '编辑 保留我的标题', exact: true })).toBeInViewport()
      expect(await page.locator('.data-scroll').evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
      await row.getByRole('button', { name: '更多操作 保留我的标题', exact: true }).click()
      for (const action of ['教学标签', '打印版本', '更新修订稿', '删除公共条目']) await expect(page.getByRole('menuitem', { name: action, exact: true })).toBeVisible()
      await page.keyboard.press('Escape')
      await expect(page.getByRole('menu')).toBeHidden()
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: info.outputPath('publication-saved.png') })
    expect(errors).toEqual([])
  })
}

test('资料未保存时关闭、Esc 和页面切换均可取消，放弃后重新添加为空', async ({ page, context }) => {
  await catalogApi(context)
  await page.goto('/admin/#papers')
  await page.getByRole('button', { name: '添加习题', exact: true }).click()
  const editor = page.getByRole('dialog', { name: '添加习题草稿', exact: true })
  const title = editor.getByRole('textbox', { name: '公开标题' })
  await title.fill('不能丢失的草稿')
  await expect(editor).toContainText('有未保存的修改')
  expect(await page.evaluate(() => {
    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    return event.defaultPrevented
  })).toBe(true)
  const dismiss = async (action: () => Promise<unknown>) => {
    page.once('dialog', async dialog => {
      expect(dialog.message()).toContain('未保存')
      await dialog.dismiss()
    })
    await action()
    await expect(editor).toBeVisible()
    await expect(title).toHaveValue('不能丢失的草稿')
  }
  await dismiss(() => editor.getByRole('button', { name: '关闭', exact: true }).last().click())
  await dismiss(() => page.keyboard.press('Escape'))
  await dismiss(() => page.evaluate(() => { location.hash = '#users' }))
  await expect(page).toHaveURL(/#papers$/)
  page.once('dialog', dialog => dialog.accept())
  await editor.getByRole('button', { name: '关闭', exact: true }).last().click()
  await expect(editor).toBeHidden()
  await page.getByRole('button', { name: '添加习题', exact: true }).click()
  await expect(title).toHaveValue('')
  await expect(editor).not.toContainText('有未保存的修改')
  expect(await page.evaluate(() => {
    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    return event.defaultPrevented
  })).toBe(false)
})
