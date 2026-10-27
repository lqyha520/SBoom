import { expect, test, type BrowserContext, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import type { ImageWorksheetParams, WorksheetImage } from '../src/image-generation'

const catalogKeyword = '上册·20 以内加法'

// 真实浏览器、图片解码、IndexedDB 和 PDF；图片为明确标注的离线绘制素材。
async function imageApi(page: Page, context: BrowserContext, options: { holdFirst?: boolean; unknownFirst?: boolean; rejectFirst?: boolean; configured?: boolean } = {}) {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  const b64 = await page.evaluate(() => {
    const canvas = document.createElement('canvas')
    canvas.width = 600; canvas.height = 850
    const draw = canvas.getContext('2d')!
    draw.fillStyle = '#fff'; draw.fillRect(0, 0, 600, 850)
    draw.fillStyle = '#356a5c'; draw.fillRect(0, 0, 600, 12)
    draw.font = 'bold 24px sans-serif'; draw.fillText('OFFLINE WORKSHEET FIXTURE', 40, 70)
    draw.font = '16px sans-serif'; draw.fillText('NOT AI OUTPUT', 40, 102)
    draw.fillStyle = '#343b39'; draw.font = '22px sans-serif'
    for (let row = 0; row < 6; row++) draw.fillText(`${row + 1}.   ${row + 2} + ${row + 3} = __________`, 50, 200 + row * 85)
    return canvas.toDataURL('image/png').split(',')[1]
  })
  const calls: { id: string; params: ImageWorksheetParams }[] = []
  const queries: string[] = []
  const unexpected: string[] = []
  const images = new Map<string, WorksheetImage>()
  let releaseFirst = () => {}
  const firstGate = new Promise<void>(resolve => { releaseFirst = resolve })
  await context.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    let data: unknown
    if (path === '/api/v1/auth/me') data = { id: 7, username: 'teacher', role: 'user' }
    else if (path === '/api/v1/scope/available') data = { available: Object.fromEntries(['一', '二', '三', '四', '五', '六'].map(n => [`小学${n}年级`, ['数学', '语文', '英语']])) }
    else if (path === '/api/v1/scope') data = { allowed: [], books: [{
      id: 'offline-math', semester: '上册', series: '离线浏览器测试教材',
      source_url: 'https://example.test/textbook', verified_on: '2026-10-11',
      units: ['20 以内加法', '20 以内减法', '认识图形', '位置与方向', '认识钟表'].map((title, index) => ({ title, page: index + 1, topics: [] })),
    }] }
    else if (path === '/api/v1/me/templates') data = { templates: [] }
    else if (path === '/api/v1/me/usage') data = { requests: 0 }
    else if (path === '/api/v1/image-generation/options') data = { configured: options.configured !== false }
    else if (path === '/api/v1/generation/options') data = { revision: 'offline-images', timeout_ms: 900000, task_timeout_seconds: 870 }
    else if (path === '/api/v1/image-generation/prompt') data = { prompt: '离线出题说明：根据所选知识点生成练习。' }
    else if (path === '/api/v1/generate-image') {
      const id = route.request().headers()['x-request-id']!
      const params = route.request().postDataJSON() as ImageWorksheetParams
      calls.push({ id, params })
      const image: WorksheetImage = { request_id: id, b64_json: b64, width: 600, height: 850, mime_type: 'image/png', prompt: 'OFFLINE IMAGE FIXTURE - NOT AI OUTPUT' }
      images.set(id, image)
      if (calls.length === 1) {
        if (options.holdFirst) await firstGate
        if (options.unknownFirst || options.rejectFirst) {
          await route.fulfill({ status: options.rejectFirst ? 422 : 504, json: { detail: { error: options.rejectFirst ? '本张生成失败，请调整后重试' : '响应中断，请查询原请求' } } })
          return
        }
      }
      data = image
    } else if (path.startsWith('/api/v1/me/generations/')) {
      const id = path.split('/').at(-1)!
      queries.push(id)
      data = { kind: 'image', status: 'succeeded', result: images.get(id) }
    } else {
      unexpected.push(path)
      await route.fulfill({ status: 404, json: { detail: '浏览器测试未声明的请求' } })
      return
    }
    await route.fulfill({ json: data })
  })
  return { calls, queries, unexpected, releaseFirst }
}

async function openImages(page: Page) {
  await page.goto('/')
  await page.getByRole('button', { name: '图片出题', exact: true }).click()
  await expect(page.getByRole('heading', { name: '设计一份习题图' })).toBeVisible()
}

async function configure(page: Page, count = 1) {
  await page.getByRole('combobox', { name: '图片年级' }).selectOption('小学一年级')
  await page.getByRole('combobox', { name: '图片科目' }).selectOption('数学')
  await page.getByRole('button', { name: catalogKeyword, exact: true }).first().click()
  await page.getByRole('button', { name: /轻量练习 2 类/ }).click()
  if (count !== 1) {
    const input = page.getByRole('spinbutton', { name: '生成张数' })
    await input.fill(String(count)); await input.press('Tab')
  }
}

async function noHorizontalOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
}

test('快速设置、修改原批次设置、复用和下载 PDF，历史图片可在刷新后恢复', async ({ page, context }, info) => {
  const api = await imageApi(page, context)
  await openImages(page)
  await expect(page.getByRole('button', { name: '生成 1 张图片', exact: true })).toBeDisabled()
  await configure(page, 2)
  await expect(page.locator('.image-custom')).toHaveAttribute('open')
  await expect(page.locator('.image-count-value')).toHaveCount(0)
  await expect(page.getByRole('checkbox', { name: '选择题指定题量' })).not.toBeChecked()
  await expect(page.locator('.image-order-summary')).toHaveText('2 张 · 题量自动安排')
  await expect(page.locator('.image-advanced')).not.toHaveAttribute('open')
  await expect(page.locator('.image-paper-exercise')).toHaveCount(2)
  await page.getByRole('button', { name: '黑白打印', exact: true }).click()
  await page.screenshot({ path: info.outputPath('image-settings-desktop.png') })
  await page.getByRole('button', { name: '生成 2 张图片', exact: true }).click()
  await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
  expect(api.calls.map(call => call.params.image_index)).toEqual([1, 2])
  expect(api.calls.every(call => call.params.keyword === catalogKeyword && call.params.style === 'black_white')).toBe(true)
  expect(api.calls.every(call => call.params.items.every(item => item.question_count === null))).toBe(true)
  await expect(page.locator('.image-batch-title')).toContainText('题量自动安排')
  await page.getByRole('button', { name: '上一张图片' }).click()
  await expect(page.locator('.worksheet-image')).toHaveAttribute('alt', /第 1 张/)
  await expect(page.getByRole('button', { name: '上一张图片' })).toBeDisabled()
  await page.getByRole('textbox', { name: '图片知识点' }).fill('乘法练习')
  await expect(page.locator('.image-batch-title h3')).toHaveText(catalogKeyword)
  await expect(page.locator('.image-generate-actions')).toContainText('设置已调整')
  await page.getByRole('button', { name: '复用设置' }).click()
  await expect(page.getByRole('textbox', { name: '图片知识点' })).toHaveValue(catalogKeyword)
  expect(api.calls).toHaveLength(2)
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: '下载 PDF（2 页）' }).click()
  const file = await download
  expect(await file.failure()).toBeNull()
  const pdfPath = info.outputPath('image-worksheet.pdf')
  await file.saveAs(pdfPath)
  const pdf = (await readFile(pdfPath)).toString('latin1')
  expect(pdf.startsWith('%PDF-')).toBe(true)
  expect(pdf.match(/\/Type\s*\/Page\b/g)).toHaveLength(2)
  await page.screenshot({ path: info.outputPath('image-results-desktop.png') })

  await page.getByRole('textbox', { name: '图片知识点' }).fill('乘法练习')
  await page.getByRole('button', { name: '按当前设置新建 2 张', exact: true }).click()
  await expect(page.locator('.image-batch-title h3')).toHaveText('乘法练习')
  await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
  await page.getByRole('button', { name: '历史批次', exact: true }).click()
  await page.getByRole('dialog').getByRole('button', { name: /20 以内加法/ }).click()
  await expect(page.locator('.image-batch-title h3')).toHaveText(catalogKeyword)
  await page.reload()
  await page.getByRole('button', { name: '图片出题', exact: true }).click()
  await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
  await expect(page.locator('.image-batch-title h3')).toHaveText(catalogKeyword)
  await expect(page.getByRole('textbox', { name: '图片知识点' })).toHaveValue('乘法练习')
  expect(api.calls).toHaveLength(4)
  expect(api.queries).toEqual([])
  expect(api.unexpected).toEqual([])
})

test('手机可在结果页暂停和继续，只生成剩余图片且操作区不遮挡预览', async ({ page, context }, info) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const api = await imageApi(page, context, { holdFirst: true })
  try {
    await openImages(page)
    await configure(page, 3)
    await page.screenshot({ path: info.outputPath('image-settings-mobile.png') })
    await expect(page.getByRole('button', { name: '生成 3 张图片' })).toBeInViewport()
    await page.getByRole('button', { name: '生成 3 张图片' }).click()
    await expect(page.locator('.image-workbench')).toHaveAttribute('data-mobile-panel', 'preview')
    await expect(page.getByRole('button', { name: '暂停后续生成' })).toBeInViewport()
    await expect(page.locator('.image-controls')).not.toBeVisible()
    await page.getByRole('button', { name: '暂停后续生成' }).click()
    await expect(page.locator('.image-batch-status')).toContainText('本张完成后暂停')
    api.releaseFirst()
    await expect(page.locator('.image-batch-status')).toContainText('本批次已暂停')
    expect(api.calls).toHaveLength(1)
    await page.getByRole('button', { name: '继续生成剩余 2 张' }).click()
    await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
    expect(api.calls.map(call => call.params.image_index)).toEqual([1, 2, 3])
    const download = page.waitForEvent('download')
    await page.getByRole('button', { name: '下载本张' }).click()
    expect((await download).suggestedFilename()).toMatch(/第3张\.png$/)
    await page.screenshot({ path: info.outputPath('image-results-mobile.png') })
    await noHorizontalOverflow(page)
    await page.getByRole('button', { name: '返回出题设置' }).click()
    await expect(page.getByRole('button', { name: '按当前设置新建 3 张' })).toBeInViewport()
    await page.reload()
    await page.getByRole('button', { name: '图片出题', exact: true }).click()
    await expect(page.locator('.image-workbench')).toHaveAttribute('data-mobile-panel', 'preview')
    await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
    expect(api.calls).toHaveLength(3)
    expect(api.queries).toEqual([])
    expect(api.unexpected).toEqual([])
  } finally { api.releaseFirst() }
})

test('手机网络异常后直接查询原请求，成功找回图片且不重复生成', async ({ page, context }) => {
  await page.setViewportSize({ width: 360, height: 740 })
  const api = await imageApi(page, context, { unknownFirst: true })
  await openImages(page)
  await configure(page)
  await page.getByRole('button', { name: '生成 1 张图片' }).click()
  await expect(page.locator('.image-batch-status')).toContainText('生成结果待确认')
  await expect(page.getByRole('button', { name: '查询本次结果' })).toBeInViewport()
  await expect(page.getByRole('button', { name: /继续生成剩余/ })).toHaveCount(0)
  expect(api.calls).toHaveLength(1)
  await page.getByRole('button', { name: '查询本次结果' }).click()
  await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
  expect(api.queries).toEqual([api.calls[0].id])
  expect(api.calls).toHaveLength(1)
  await noHorizontalOverflow(page)
  expect(api.unexpected).toEqual([])
})

test('断线后自动查询找回图片，剩余页面仍需用户点击继续', async ({ page, context }) => {
  const api = await imageApi(page, context, { unknownFirst: true })
  await openImages(page)
  await configure(page, 2)
  await page.getByRole('button', { name: '生成 2 张图片' }).click()
  await expect(page.locator('.image-batch-status')).toContainText('生成结果待确认')
  await expect(page.getByRole('button', { name: '继续生成剩余 1 张' })).toBeVisible({ timeout: 15_000 })
  expect(api.calls).toHaveLength(1)
  expect(api.queries).toEqual([api.calls[0].id])
  await expect(page.getByRole('button', { name: '下载本张' })).toBeEnabled()
  expect(api.unexpected).toEqual([])
})

test('明确失败后提示重试费用，修改下一批条件不会改变本批次的继续生成', async ({ page, context }) => {
  const api = await imageApi(page, context, { rejectFirst: true })
  await openImages(page)
  await configure(page)
  await page.getByRole('button', { name: '生成 1 张图片' }).click()
  await expect(page.locator('.image-batch-status')).toContainText('可能产生新的费用')
  await page.getByRole('textbox', { name: '图片知识点' }).fill('新的知识点')
  await page.getByRole('button', { name: '继续生成剩余 1 张' }).click()
  await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
  expect(api.calls).toHaveLength(2)
  expect(api.calls[0].id).not.toBe(api.calls[1].id)
  expect(api.calls[1].params.keyword).toBe(catalogKeyword)
  expect(api.unexpected).toEqual([])
})

test('小屏幕可选自动或指定题量，题量限制与免费说明预览有效', async ({ page, context }, info) => {
  await page.setViewportSize({ width: 320, height: 568 })
  const api = await imageApi(page, context)
  await openImages(page)
  await configure(page)
  await expect(page.getByRole('spinbutton', { name: '选择题题量' })).toHaveCount(0)
  await page.getByRole('checkbox', { name: '选择题指定题量' }).check()
  const count = page.getByRole('spinbutton', { name: '选择题题量' })
  await count.fill('20'); await count.press('Tab')
  await expect(page.locator('.image-order-summary')).toHaveText('1 张 · 已指定 20 题，其余自动')
  await page.getByRole('checkbox', { name: '填空题指定题量' }).check()
  const fillCount = page.getByRole('spinbutton', { name: '填空题题量' })
  await expect(fillCount).toHaveValue('4')
  await expect(page.locator('.image-order-summary')).toHaveText('1 张 × 24 题')
  await expect(page.locator('.image-type-grid').getByRole('button', { name: '判断题', exact: true })).toBeDisabled()
  await page.screenshot({ path: info.outputPath('image-counts-320.png') })
  await page.getByRole('checkbox', { name: '选择题指定题量' }).uncheck()
  await fillCount.fill(''); await fillCount.press('Tab')
  await expect(page.locator('.image-count-value')).toHaveCount(0)
  await expect(page.locator('.image-order-summary')).toHaveText('1 张 · 题量自动安排')
  await page.reload()
  await page.getByRole('button', { name: '图片出题', exact: true }).click()
  await expect(page.locator('.image-order-summary')).toHaveText('1 张 · 题量自动安排')
  await expect(page.getByRole('checkbox', { name: '填空题指定题量' })).not.toBeChecked()
  await page.locator('.image-advanced summary').click()
  await page.getByRole('textbox', { name: '补充要求' }).fill('每题多留一点书写空间')
  await page.getByRole('button', { name: '查看生成说明', exact: true }).click()
  await expect(page.getByRole('dialog')).toContainText('离线出题说明')
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: '生成 1 张图片', exact: true })).toBeInViewport()
  expect(api.calls).toEqual([])
  await noHorizontalOverflow(page)
  expect(api.unexpected).toEqual([])
})

test('只选题型即可生成，也支持部分题型指定数量并在刷新后保留', async ({ page, context }, info) => {
  const api = await imageApi(page, context)
  await openImages(page)
  await page.getByRole('combobox', { name: '图片年级' }).selectOption('小学一年级')
  await page.getByRole('combobox', { name: '图片科目' }).selectOption('数学')
  await page.getByRole('textbox', { name: '图片知识点' }).fill('20 以内加法')
  await page.locator('.image-type-grid').getByRole('button', { name: '选择题', exact: true }).click()
  await expect(page.getByRole('button', { name: '生成 1 张图片', exact: true })).toBeEnabled()
  await expect(page.locator('.image-count-value')).toHaveCount(0)
  await page.getByRole('button', { name: '生成 1 张图片', exact: true }).click()
  await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
  expect(api.calls[0].params.items).toEqual([{ game_type: 'quiz', question_count: null }])
  await page.locator('.image-type-grid').getByRole('button', { name: '填空题', exact: true }).click()
  await page.getByRole('checkbox', { name: '选择题指定题量' }).check()
  const count = page.getByRole('spinbutton', { name: '选择题题量' })
  await count.fill('6'); await count.press('Tab')
  await page.reload()
  await page.getByRole('button', { name: '图片出题', exact: true }).click()
  await expect(count).toHaveValue('6')
  await expect(page.getByRole('checkbox', { name: '填空题指定题量' })).not.toBeChecked()
  await expect(page.locator('.image-order-summary')).toHaveText('1 张 · 已指定 6 题，其余自动')
  await page.getByRole('button', { name: '按当前设置新建 1 张', exact: true }).click()
  await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
  expect(api.calls[1].params.items).toEqual([{ game_type: 'quiz', question_count: 6 }, { game_type: 'fill_blank', question_count: null }])
  await expect(page.locator('.image-batch-title')).toContainText('已指定 6 题，其余自动')
  await page.getByRole('button', { name: '复用设置' }).click()
  await expect(page.locator('.image-generate-actions')).not.toContainText('设置已调整')
  await page.screenshot({ path: info.outputPath('image-counts-mixed-desktop.png') })
  await noHorizontalOverflow(page)
  expect(api.unexpected).toEqual([])
})

for (const viewport of [{ width: 1440, height: 1000 }, { width: 320, height: 568 }]) {
  test(`仅选小学一年级数学即可出图，自动题型可恢复且批次可复用 ${viewport.width}px`, async ({ page, context }, info) => {
    await page.setViewportSize(viewport)
    const api = await imageApi(page, context)
    await openImages(page)
    const generate = page.getByRole('button', { name: '生成 1 张图片', exact: true })
    await expect(generate).toBeDisabled()
    await page.getByRole('combobox', { name: '图片年级' }).selectOption('小学一年级')
    await expect(generate).toBeDisabled()
    await page.getByRole('combobox', { name: '图片科目' }).selectOption('数学')
    await expect(generate).toBeEnabled()
    await expect(page.getByRole('textbox', { name: '图片知识点' })).toHaveValue('')
    await expect(page.locator('.image-order-summary')).toHaveText('1 张 · 题型、题量自动安排')
    await expect(page.locator('.image-type-grid button[aria-pressed=true]')).toHaveCount(0)
    await page.screenshot({ path: info.outputPath('automatic-settings.png') })
    await noHorizontalOverflow(page)
    await generate.click()
    await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
    expect(api.calls[0].params).toMatchObject({ grade: '小学一年级', subject: '数学', keyword: '', items: [] })
    await expect(page.locator('.image-batch-title h3')).toHaveText('小学一年级数学·年级知识练习')
    await page.getByRole('button', { name: '复用设置', exact: true }).click()
    await expect(page.locator('.image-generate-actions')).not.toContainText('设置已调整')
    await page.locator('.image-type-grid').getByRole('button', { name: '选择题', exact: true }).click()
    await expect(page.locator('.image-counts')).toBeVisible()
    await page.getByRole('button', { name: '恢复自动题型' }).click()
    await expect(page.locator('.image-counts')).toHaveCount(0)
    await page.reload()
    await page.getByRole('button', { name: '图片出题', exact: true }).click()
    await page.getByRole('button', { name: '复用设置', exact: true }).click()
    await expect(page.locator('.image-order-summary')).toHaveText('1 张 · 题型、题量自动安排')
    await page.getByRole('button', { name: '按当前设置新建 1 张', exact: true }).click()
    await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
    expect(api.calls).toHaveLength(2)
    expect(api.calls[1].params.items).toEqual([])
    expect(api.calls[1].params.keyword).toBe('')
    await page.getByRole('button', { name: '历史批次', exact: true }).click()
    await expect(page.getByRole('dialog')).toContainText('小学一年级数学·年级知识练习')
    await page.getByRole('dialog').getByRole('button', { name: /小学一年级数学·年级知识练习/ }).click()
    await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
    expect(api.calls).toHaveLength(2)
    await page.screenshot({ path: info.outputPath('automatic-results.png') })
    await noHorizontalOverflow(page)
    expect(api.unexpected).toEqual([])
  })
}

test('服务未配置时两种手机面板均保留提示，禁止发起生成', async ({ page, context }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const api = await imageApi(page, context, { configured: false })
  await openImages(page)
  await configure(page)
  await expect(page.getByText('生图服务尚未配置', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '生成 1 张图片', exact: true })).toBeDisabled()
  await page.locator('.image-mobile-tabs').getByRole('button', { name: '效果预览' }).click()
  await expect(page.getByText('生图服务尚未配置', { exact: true })).toBeVisible()
  expect(api.calls).toEqual([])
  await noHorizontalOverflow(page)
})

for (const width of [1440, 320]) {
  test(`清空图片设置后可换年级科目，新旧结果与历史各自保留 ${width}px`, async ({ page, context }, info) => {
    await page.setViewportSize({ width, height: width === 320 ? 568 : 1000 })
    const api = await imageApi(page, context)
    await openImages(page)
    const clear = page.getByRole('button', { name: '清空设置', exact: true })
    await expect(clear).toBeDisabled()
    await configure(page, 2)
    await page.getByRole('combobox', { name: '图片难度' }).selectOption('hard')
    await page.getByRole('button', { name: '黑白打印', exact: true }).click()
    await page.locator('.image-advanced summary').click()
    await page.getByRole('textbox', { name: '补充要求' }).fill('多留书写空间')
    await page.getByRole('checkbox', { name: '选择题指定题量' }).check()
    await page.getByRole('button', { name: '生成 2 张图片', exact: true }).click()
    await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
    if (width < 768) await page.getByRole('button', { name: '返回出题设置', exact: true }).click()
    await expect(clear).toBeInViewport()
    page.once('dialog', dialog => dialog.dismiss())
    await clear.click()
    await expect(page.getByRole('textbox', { name: '图片知识点' })).toHaveValue(catalogKeyword)
    page.once('dialog', dialog => dialog.accept())
    await clear.click()
    await expect(page.getByRole('combobox', { name: '图片年级' })).toHaveValue('')
    await expect(page.getByRole('combobox', { name: '图片年级' })).toBeFocused()
    await expect(page.getByRole('combobox', { name: '图片科目' })).toHaveValue('')
    await expect(page.getByRole('combobox', { name: '图片科目' }).locator('option:checked')).toHaveText('先选年级')
    await expect(page.getByRole('textbox', { name: '图片知识点' })).toHaveValue('')
    await expect(page.getByRole('textbox', { name: '补充要求', includeHidden: true })).toHaveValue('')
    await expect(page.getByRole('combobox', { name: '图片难度' })).toHaveValue('medium')
    await expect(page.getByRole('button', { name: '黑白打印', exact: true })).toHaveAttribute('aria-pressed', 'true')
    await expect(page.locator('.image-order-summary')).toHaveText('1 张 · 题型、题量自动安排')
    await expect(clear).toBeDisabled()
    await expect(page.getByRole('button', { name: '按当前设置新建 1 张' })).toBeDisabled()
    await page.screenshot({ path: info.outputPath('cleared-image-settings.png') })
    await noHorizontalOverflow(page)
    await page.reload()
    await page.getByRole('button', { name: '图片出题', exact: true }).click()
    await expect(page.locator('.image-batch-title h3')).toHaveText(catalogKeyword)
    await expect(page.locator('.image-pages button')).toHaveCount(2)
    await expect(page.locator('.worksheet-image')).toBeVisible()
    expect(api.calls).toHaveLength(2)
    if (width < 768) await page.getByRole('button', { name: '返回出题设置', exact: true }).click()
    await expect(page.getByRole('combobox', { name: '图片年级' })).toHaveValue('')
    await page.getByRole('combobox', { name: '图片年级' }).selectOption('小学二年级')
    await page.getByRole('combobox', { name: '图片科目' }).selectOption('语文')
    await page.getByRole('button', { name: '按当前设置新建 1 张' }).click()
    await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
    expect(api.calls).toHaveLength(3)
    expect(api.calls[2].params).toMatchObject({ grade: '小学二年级', subject: '语文', keyword: '', items: [],
      difficulty: 'medium', requirements: '', style: 'black_white', image_count: 1 })
    await page.getByRole('button', { name: '历史批次', exact: true }).click()
    await expect(page.getByRole('dialog')).toContainText('20 以内加法')
    expect(api.unexpected).toEqual([])
  })
}
