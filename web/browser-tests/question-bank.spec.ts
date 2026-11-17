import { expect, test } from '@playwright/test'

for (const width of [1440, 390]) {
  test(`题库选择、组卷和待核对提示 ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 950 })
    const record = { id: 'bank-1', title: '进位加法好题', grade: '小学一年级', subject: '数学', topic: '进位加法', difficulty: 'easy', section_type: 'oral_math', passage: '', revision: 1, created_at: 1, updated_at: 1,
      questions: [{ stem: '8 + 7 = __', answer: 15, analysis: '8 加 2 得 10，再加 5 得 15', quality_status: 'unchecked' }] }
    let selections = 0
    const errors: string[] = []
    page.on('pageerror', e => errors.push(e.message))
    await page.route('**/api/**', async route => {
      const path = new URL(route.request().url()).pathname
      let data: unknown
      if (path === '/api/v1/auth/me') data = { id: 7, username: 'teacher', role: 'user' }
      else if (path === '/api/v1/auth/capabilities') data = { registration_enabled: false }
      else if (path === '/api/v1/scope/available') data = { available: { 小学一年级: ['数学'] } }
      else if (path === '/api/v1/scope') data = { allowed: ['进位加法'], forbidden: [] }
      else if (path === '/api/v1/me/templates') data = { templates: [] }
      else if (path === '/api/v1/me/usage') data = { requests: 0, daily_limit: 0 }
      else if (path === '/api/v1/generation/options') data = { revision: 'fixture', timeout_ms: 900000, task_timeout_seconds: 870 }
      else if (path === '/api/v1/question-bank') data = { items: [record], total: 1, has_more: false }
      else if (path === '/api/v1/question-bank/selection') {
        expect(route.request().postDataJSON()).toEqual({ ids: ['bank-1'] }); selections++
        data = { items: [record], total: 1, has_more: false }
      } else throw new Error('未声明请求：' + path)
      await route.fulfill({ json: data })
    })
    await page.goto('/')
    if (width < 600) {
      await page.getByRole('button', { name: '工作台工具', exact: true }).click()
      await page.getByRole('menuitem', { name: '我的题库 保存好题，以后直接组卷', exact: true }).click()
    } else await page.getByRole('button', { name: '我的题库', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: '我的题库', exact: true })
    await expect(dialog).toBeVisible()
    await dialog.getByRole('checkbox', { name: '进位加法好题', exact: true }).check()
    await dialog.getByRole('textbox', { name: '组卷标题' }).fill('题库拼成的练习')
    await expect(dialog.getByText('已选择 1 条', { exact: false })).toBeVisible()
    await page.screenshot({ path: info.outputPath(`question-bank-${width}.png`), fullPage: true })
    await dialog.getByRole('button', { name: '用所选题目组卷（1 道）', exact: true }).click()
    await expect(dialog).toBeHidden()
    await expect(page.locator('.paper-stack')).toContainText('题库拼成的练习')
    await expect(page.getByText('1 个大题待核对', { exact: false }).first()).toBeVisible()
    expect(selections).toBe(1)
    expect(errors).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.screenshot({ path: info.outputPath(`question-bank-paper-${width}.png`), fullPage: true })
  })
}


for (const width of [1440, 390]) {
  test(`跨页选题、清空筛选与删除末页最后一条 ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 950 })
    const records = Array.from({ length: 21 }, (_, index) => ({ id: 'bank-' + index, title: '收藏题目 ' + index, grade: '小学一年级', subject: '数学', topic: '加法', difficulty: 'easy', section_type: index === 0 ? 'reading' : 'oral_math', passage: index === 0 ? '阅读文章' : '', revision: 1, created_at: 1, updated_at: 1,
      questions: Array.from({ length: index === 0 ? 3 : 1 }, () => ({ stem: '2 加 3 等于几？', answer: 5, analysis: '2 + 3 = 5' })) }))
    await page.route('**/api/**', async route => {
      const url = new URL(route.request().url()), path = url.pathname
      let data: unknown
      if (path === '/api/v1/auth/me') data = { id: 7, username: 'teacher', role: 'user' }
      else if (path === '/api/v1/auth/capabilities') data = { registration_enabled: false }
      else if (path === '/api/v1/scope/available') data = { available: { 小学一年级: ['数学'] } }
      else if (path === '/api/v1/scope') data = { allowed: ['加法'], forbidden: [] }
      else if (path === '/api/v1/me/templates') data = { templates: [] }
      else if (path === '/api/v1/me/usage') data = { requests: 0, daily_limit: 0 }
      else if (path === '/api/v1/generation/options') data = { revision: 'fixture', timeout_ms: 900000, task_timeout_seconds: 870 }
      else if (path === '/api/v1/question-bank') {
        const matched = records.filter(item => !url.searchParams.get('q') || item.title.includes(url.searchParams.get('q')!))
        const offset = Number(url.searchParams.get('offset') || 0)
        data = { items: matched.slice(offset, offset + 20), total: matched.length, has_more: offset + 20 < matched.length, bank_total: records.length, available: { 小学一年级: ['数学'] } }
      } else if (route.request().method() === 'DELETE' && path === '/api/v1/question-bank/bank-20') {
        records.splice(20, 1); await route.fulfill({ status: 204 }); return
      } else throw new Error('未声明请求：' + path)
      await route.fulfill({ json: data })
    })
    await page.goto('/')
    if (width < 600) { await page.getByRole('button', { name: '工作台工具', exact: true }).click(); await page.getByRole('menuitem', { name: '我的题库 保存好题，以后直接组卷', exact: true }).click() }
    else await page.getByRole('button', { name: '我的题库', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: '我的题库', exact: true })
    await dialog.getByRole('checkbox', { name: '收藏题目 0', exact: true }).check()
    await expect(dialog.locator('.bank-selection')).toContainText('共 3 道题')
    await dialog.getByRole('button', { name: '下一页', exact: true }).click()
    await dialog.getByRole('checkbox', { name: '收藏题目 20', exact: true }).check()
    await expect(dialog.locator('.bank-selection')).toContainText('共 4 道题')
    await dialog.locator('.bank-selection summary').click()
    await expect(dialog.locator('.bank-selected-row')).toHaveCount(2)
    await dialog.getByRole('textbox', { name: '搜索个人题库' }).fill('没有这样的题目')
    await dialog.getByRole('button', { name: '筛选', exact: true }).click()
    await expect(dialog.locator('.bank-empty')).toContainText('没有符合筛选条件的题目')
    await expect(dialog.locator('.bank-selection')).toContainText('共 4 道题')
    await dialog.getByRole('button', { name: '清空筛选查看全部', exact: true }).click()
    await dialog.getByRole('button', { name: '下一页', exact: true }).click()
    page.once('dialog', prompt => prompt.accept())
    await dialog.locator('.bank-item').getByRole('button', { name: '删除', exact: true }).click()
    await expect(dialog.getByText('第 1 页', { exact: true })).toBeVisible()
    await expect(dialog.getByRole('checkbox', { name: '收藏题目 0', exact: true })).toBeChecked()
    await expect(dialog.locator('.bank-selection')).toContainText('共 3 道题')
    await expect(dialog.getByRole('button', { name: '下一页', exact: true })).toBeDisabled()
    await expect(page.locator('html')).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  })
}

test('空题库提供保存指引和生成入口', async ({ page }) => {
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    const data = path === '/api/v1/auth/me' ? { id: 7, username: 'teacher', role: 'user' }
      : path === '/api/v1/scope/available' ? { available: {} }
        : path === '/api/v1/me/templates' ? { templates: [] }
          : path === '/api/v1/generation/options' ? { revision: 'fixture', timeout_ms: 900000, task_timeout_seconds: 870 }
            : path === '/api/v1/question-bank' ? { items: [], total: 0, bank_total: 0, has_more: false, available: {} } : {}
    await route.fulfill({ json: data })
  })
  await page.goto('/')
  await page.getByRole('button', { name: '我的题库', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '我的题库', exact: true })
  await expect(dialog).toContainText('保存好题，以后直接组卷')
  await expect(dialog.locator('.bank-empty')).toContainText('还没有保存题目')
  await dialog.getByRole('button', { name: '如何保存题目', exact: true }).click()
  await expect(dialog.locator('.bank-guide')).toContainText('存入题库')
  await dialog.getByRole('button', { name: '去生成题目', exact: true }).click()
  await expect(dialog).toBeHidden()
})
