import { expect, test, type BrowserContext, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import JSZip from 'jszip'
import type { ImageWorksheetParams, WorksheetImage } from '../src/image-generation'

const catalogKeyword = '上册·20 以内加法'

for (const width of [390, 1440]) {
  test(`自定义水印的五个位置、预览与下载一致，关闭恢复原图 ${width}px`, async ({ page, context }, info) => {
    await page.setViewportSize({ width, height: 950 })
    const api = await imageApi(page, context)
    await openImages(page); await configure(page, 3)
    await page.getByRole('button', { name: '生成 3 张图片', exact: true }).click()
    await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
    const original = [...api.images.values()][0]!.b64_json!
    const toggle = page.getByRole('switch', { name: '下载时添加文字水印' })
    const single = page.getByRole('button', { name: '下载本张', exact: true })
    await expect(toggle).not.toBeChecked()
    await toggle.check()
    await expect(page.getByText('请填写水印文字', { exact: true })).toBeVisible()
    await expect(single).toBeDisabled()
    await expect(page.getByRole('button', { name: '批量下载图片（3 张）', exact: true })).toBeDisabled()
    await expect(page.getByRole('button', { name: '下载 PDF（3 页）', exact: true })).toBeDisabled()
    const label = page.getByRole('textbox', { name: '水印文字', exact: true })
    await label.fill('王老师 · 数学课堂')
    await expect(page.getByText('下方为水印效果预览，可放大查看。', { exact: true })).toBeVisible()
    const preview = page.locator('.worksheet-image')
    let previous = ''
    for (const position of ['bottom-right', 'bottom-left', 'top-right', 'top-left', 'center']) {
      await page.getByRole('combobox', { name: '水印位置' }).selectOption(position)
      await expect.poll(() => preview.getAttribute('src')).not.toBe(previous)
      await expect(page.getByText('下方为水印效果预览，可放大查看。', { exact: true })).toBeVisible()
      previous = (await preview.getAttribute('src'))!
      const png = await preview.evaluate(async (element: HTMLImageElement) => {
        const data = await (await fetch(element.src)).blob()
        return new Promise<string>(resolve => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]!); reader.readAsDataURL(data) })
      })
      const bounds = await changedPixels(page, original, png)
      expect(bounds.width).toBe(600); expect(bounds.height).toBe(850)
      expect(bounds.count).toBeGreaterThan(100)
      if (position.startsWith('top')) expect(bounds.maxY).toBeLessThan(85)
      if (position.startsWith('bottom')) expect(bounds.minY).toBeGreaterThan(765)
      if (position.endsWith('left')) expect(bounds.minX).toBeLessThan(30)
      if (position.endsWith('right')) expect(bounds.maxX).toBeGreaterThan(570)
      if (position === 'center') {
        expect(Math.abs((bounds.minX + bounds.maxX) / 2 - 300)).toBeLessThan(12)
        expect(Math.abs((bounds.minY + bounds.maxY) / 2 - 425)).toBeLessThan(12)
      }
      const pending = page.waitForEvent('download'); await single.click()
      const file = await pending, path = info.outputPath(position + '.png')
      await file.saveAs(path)
      expect((await readFile(path)).toString('base64')).toBe(png)
    }
    const priorPreview = previous
    await label.fill('李老师的练习')
    await expect.poll(() => preview.getAttribute('src')).not.toBe(priorPreview)
    await expect(page.getByText('下方为水印效果预览，可放大查看。', { exact: true })).toBeVisible()
    const pending = page.waitForEvent('download'); await single.click()
    const customPath = info.outputPath('custom.png'); await (await pending).saveAs(customPath)
    const custom = await readFile(customPath)
    expect(custom.equals(await readFile(info.outputPath('center.png')))).toBe(false)
    const start = page.getByRole('spinbutton', { name: '范围起始张数' })
    await start.fill('2'); await start.press('Tab')
    const archive = page.waitForEvent('download')
    await page.getByRole('button', { name: '批量下载图片（2 张）', exact: true }).click()
    const zipPath = info.outputPath('watermarked.zip'); await (await archive).saveAs(zipPath)
    const zip = await JSZip.loadAsync(await readFile(zipPath))
    expect(Object.keys(zip.files)).toEqual(['习题图片-第02张.png', '习题图片-第03张.png'])
    for (const file of Object.values(zip.files)) expect(await file.async('base64')).toBe(custom.toString('base64'))
    const pdfDownload = page.waitForEvent('download')
    await page.getByRole('button', { name: '下载 PDF（2 页）', exact: true }).click()
    const pdfPath = info.outputPath('watermarked.pdf'); await (await pdfDownload).saveAs(pdfPath)
    const pdf = (await readFile(pdfPath)).toString('latin1')
    expect(pdf.match(/\/Type\s*\/Page\b/g)).toHaveLength(2)
    // 云端依旧保存原始图片，PDF 内的实际图片流与带水印下载不同。
    await page.getByRole('button', { name: '保存到云端', exact: true }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByRole('button', { name: '保存到云端', exact: true }).click()
    await expect(dialog).toContainText('已保存到云端')
    const streams = (value: string) => [...value.matchAll(/\/Subtype \/Image\b[\s\S]*?stream\r?\n([\s\S]*?)\r?\nendstream/g)].map(match => match[1])
    expect(streams(pdf)).toHaveLength(2)
    expect(streams(pdf)).not.toEqual(streams(api.cloudUploads[0]!.pdf.toString('latin1')))
    await dialog.getByRole('button', { name: '完成', exact: true }).click()
    await page.reload(); await page.getByRole('button', { name: '图片出题', exact: true }).click()
    await expect(toggle).toBeChecked(); await expect(label).toHaveValue('李老师的练习')
    await expect(page.getByRole('combobox', { name: '水印位置' })).toHaveValue('center')
    await expect(page.getByText('下方为水印效果预览，可放大查看。', { exact: true })).toBeVisible()
    await page.screenshot({ path: info.outputPath('watermark-controls.png') })
    await toggle.uncheck()
    await downloadImages(page, info.outputPath('originals.zip'), [...api.images.values()])
    expect(api.calls).toHaveLength(3); expect(api.unexpected).toEqual([])
    await noHorizontalOverflow(page)
    // 切换账号后，不继承上一个账号的文字和位置偏好。
    await toggle.check()
    await context.route('**/api/v1/auth/me', route => route.fulfill({ json: { id: 8, username: 'another', role: 'user' } }))
    await page.reload(); await page.getByRole('button', { name: '图片出题', exact: true }).click()
    await configure(page); await page.getByRole('button', { name: '生成 1 张图片', exact: true }).click()
    await expect(toggle).not.toBeChecked(); await toggle.check(); await expect(label).toHaveValue('')
    await expect(page.getByRole('combobox', { name: '水印布局' })).toHaveValue('single')
    await expect(page.getByRole('slider', { name: /水印透明度/ })).toHaveValue('45')
  })
}

for (const width of [390, 1440]) {
  test(`水印透明度、多行与平铺布局写入下载文件，兼容旧设置 ${width}px`, async ({ page, context }, info) => {
    await page.setViewportSize({ width, height: 950 })
    const api = await imageApi(page, context)
    await context.addInitScript(() => {
      const key = 'lc_u7_image_request_watermark'
      if (!localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify({ enabled: true, text: '旧版水印', position: 'bottom-left' }))
    })
    await openImages(page); await configure(page, 2)
    await page.getByRole('button', { name: '生成 2 张图片', exact: true }).click()
    await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
    const original = [...api.images.values()][0]!.b64_json!
    const label = page.getByRole('textbox', { name: '水印文字', exact: true })
    const layout = page.getByRole('combobox', { name: '水印布局' })
    const position = page.getByRole('combobox', { name: '水印位置' })
    const slider = page.getByRole('slider', { name: /水印透明度/ })
    const preview = page.locator('.worksheet-image')
    const single = page.getByRole('button', { name: '下载本张', exact: true })
    await expect(label).toHaveValue('旧版水印'); await expect(position).toHaveValue('bottom-left')
    await expect(layout).toHaveValue('single'); await expect(slider).toHaveValue('45')
    const previewPng = async () => {
      await expect(page.getByText('下方为水印效果预览，可放大查看。', { exact: true })).toBeVisible()
      return preview.evaluate(async (element: HTMLImageElement) => {
        const data = await (await fetch(element.src)).blob()
        return new Promise<string>(resolve => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]!); reader.readAsDataURL(data) })
      })
    }
    const transparency = async (value: number) => {
      const previous = await preview.getAttribute('src')
      await slider.evaluate((input: HTMLInputElement, next) => {
        input.value = String(next); input.dispatchEvent(new Event('input', { bubbles: true }))
      }, value)
      await expect(slider).toHaveValue(String(value))
      await expect.poll(() => preview.getAttribute('src')).not.toBe(previous)
      return previewPng()
    }
    const savePng = async (name: string) => {
      const pending = page.waitForEvent('download'); await single.click()
      const path = info.outputPath(name); await (await pending).saveAs(path)
      return (await readFile(path)).toString('base64')
    }
    const savePdf = async (name: string) => {
      const pending = page.waitForEvent('download')
      await page.getByRole('button', { name: '下载 PDF（2 页）', exact: true }).click()
      const path = info.outputPath(name); await (await pending).saveAs(path)
      const text = (await readFile(path)).toString('latin1')
      expect(text.match(/\/Type\s*\/Page\b/g)).toHaveLength(2)
      return [...text.matchAll(/\/Subtype \/Image\b[\s\S]*?stream\r?\n([\s\S]*?)\r?\nendstream/g)].map(match => match[1])
    }
    await label.fill('AAAA\nBBBB\nCCCC'); await position.selectOption('bottom-right')
    const strong = await transparency(20)
    const strongPixels = await changedPixels(page, original, strong)
    expect(strongPixels.bands).toBe(3)
    expect(strongPixels.minY).toBeGreaterThan(700)
    expect(strongPixels.maxY).toBeLessThan(850)
    const faint = await transparency(80)
    const faintPixels = await changedPixels(page, original, faint)
    expect(faintPixels.bands).toBe(3)
    expect(faintPixels.difference).toBeGreaterThan(0)
    expect(faintPixels.difference).toBeLessThan(strongPixels.difference * 0.4)
    expect(await savePng('multiline-faint.png')).toBe(faint)
    await label.fill('王老师的课堂\n仅供学习使用'); await transparency(70)
    let tiledPng = ''
    for (const value of ['tiled', 'diagonal']) {
      const before = await preview.getAttribute('src')
      await layout.selectOption(value)
      await expect.poll(() => preview.getAttribute('src')).not.toBe(before)
      const png = await previewPng()
      const pixels = await changedPixels(page, original, png)
      expect(pixels.cells).toBe(9)
      expect(pixels.minX).toBeLessThan(200); expect(pixels.maxX).toBeGreaterThan(400)
      expect(pixels.minY).toBeLessThan(200); expect(pixels.maxY).toBeGreaterThan(650)
      expect(await savePng(value + '.png')).toBe(png)
      if (value === 'diagonal') expect(png).not.toBe(tiledPng)
      tiledPng = png
      await expect(position).toHaveCount(0)
    }
    const pending = page.waitForEvent('download')
    await page.getByRole('button', { name: '批量下载图片（2 张）', exact: true }).click()
    const zipPath = info.outputPath('diagonal.zip'); await (await pending).saveAs(zipPath)
    const zip = await JSZip.loadAsync(await readFile(zipPath))
    expect(Object.keys(zip.files)).toHaveLength(2)
    for (const file of Object.values(zip.files)) expect(await file.async('base64')).toBe(tiledPng)
    const markedPdf = await savePdf('diagonal.pdf')
    await page.reload(); await page.getByRole('button', { name: '图片出题', exact: true }).click()
    await expect(label).toHaveValue('王老师的课堂\n仅供学习使用')
    await expect(layout).toHaveValue('diagonal'); await expect(slider).toHaveValue('70')
    expect(await previewPng()).toBe(tiledPng)
    await page.screenshot({ path: info.outputPath('watermark-layout-controls.png') })
    const invisible = await transparency(100)
    expect(invisible).toBe(original)
    await expect(page.getByText(/当前下载不显示水印/)).toBeVisible()
    expect(await savePng('transparent.png')).toBe(original)
    await downloadImages(page, info.outputPath('transparent.zip'), [...api.images.values()])
    expect(await savePdf('transparent.pdf')).not.toEqual(markedPdf)
    const before = await preview.getAttribute('src')
    await slider.focus(); await slider.press('Home')
    await expect(slider).toHaveValue('0')
    await expect.poll(() => preview.getAttribute('src')).not.toBe(before)
    expect((await changedPixels(page, original, await previewPng())).count).toBeGreaterThan(100)
    await layout.selectOption('single'); await expect(position).toHaveValue('bottom-right')
    await label.fill('字'.repeat(41)); await expect(page.getByRole('alert').filter({ hasText: '每行最多 40' })).toBeVisible()
    await expect(single).toBeDisabled()
    await label.fill('一\n二\n三\n四'); await expect(page.getByText('水印文字最多 3 行', { exact: true })).toBeVisible()
    await expect(single).toBeDisabled()
    expect(api.calls).toHaveLength(2); expect(api.unexpected).toEqual([])
    await noHorizontalOverflow(page)
  })
}

async function changedPixels(page: Page, original: string, output: string) {
  return page.evaluate(async ({ original, output }) => {
    const pixels = async (png: string) => {
      const image = new Image(); image.src = 'data:image/png;base64,' + png; await image.decode()
      const canvas = document.createElement('canvas'); canvas.width = image.naturalWidth; canvas.height = image.naturalHeight
      const draw = canvas.getContext('2d')!; draw.drawImage(image, 0, 0)
      return draw.getImageData(0, 0, canvas.width, canvas.height)
    }
    const a = await pixels(original), b = await pixels(output)
    let minX = b.width, maxX = -1, minY = b.height, maxY = -1, count = 0, difference = 0
    const rows = new Set<number>(), cells = new Set<number>()
    for (let y = 0; y < b.height; y++) for (let x = 0; x < b.width; x++) {
      const i = (y * b.width + x) * 4
      if ([0, 1, 2, 3].some(c => a.data[i + c] !== b.data[i + c])) {
        count++; minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y)
        difference += [0, 1, 2, 3].reduce((sum, c) => sum + Math.abs(a.data[i + c]! - b.data[i + c]!), 0)
        rows.add(y); cells.add(Math.floor(y / b.height * 3) * 3 + Math.floor(x / b.width * 3))
      }
    }
    const bands = [...rows].filter(y => !rows.has(y - 1)).length
    return { width: b.width, height: b.height, count, minX, maxX, minY, maxY, difference, bands, cells: cells.size }
  }, { original, output })
}

test('缓存用量与手动清理保留当前图片和历史请求，刷新不重复生成', async ({ page, context }) => {
  const api = await imageApi(page, context)
  await openImages(page); await configure(page, 2)
  const generate = page.getByRole('button', { name: '生成 2 张图片', exact: true })
  await generate.click()
  await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
  await page.getByRole('button', { name: '按当前设置新建 2 张', exact: true }).click()
  await expect.poll(() => api.calls.length).toBe(4)
  await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
  const cachedKeys = () => page.evaluate(async () => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open('lc-worksheet-images', 1)
      request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error)
    })
    try { return await new Promise<IDBValidKey[]>((resolve, reject) => {
      const request = db.transaction('images').objectStore('images').getAllKeys()
      request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error)
    }) } finally { db.close() }
  })
  await expect.poll(cachedKeys).toHaveLength(4)
  await expect(page.locator('.image-cache-settings summary')).toContainText('/ 256 MiB')
  await page.locator('.image-cache-settings summary').click()
  page.once('dialog', dialog => dialog.accept())
  await page.getByRole('button', { name: '清理历史图片缓存', exact: true }).click()
  await expect(page.getByText('已清理 2 张历史图片缓存；当前批次和请求记录保留。', { exact: true })).toBeVisible()
  await expect.poll(cachedKeys).toEqual(api.calls.slice(2).map(item => 'lc_u7_image_request:' + item.id).sort())
  const history = await page.evaluate(() => JSON.parse(localStorage.getItem('lc_u7_image_request_history') || '[]'))
  expect(history).toHaveLength(1)
  expect(JSON.parse(history[0].snapshot).pages.map((item: { id: string }) => item.id)).toEqual(api.calls.slice(0, 2).map(item => item.id))
  await page.reload()
  await page.getByRole('button', { name: '图片出题', exact: true }).click()
  await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
  expect(api.calls).toHaveLength(4); expect(api.queries).toHaveLength(0); expect(api.unexpected).toEqual([])
})

for (const width of [390, 1440]) {
  test(`十二张图片分段下载和保存云端，刷新可恢复 ${width}px`, async ({ page, context }, info) => {
    await page.setViewportSize({ width, height: 950 })
    const api = await imageApi(page, context)
    await openImages(page)
    await configure(page, 12)
    await page.getByRole('button', { name: '生成 12 张图片', exact: true }).click()
    await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
    expect(api.calls).toHaveLength(12)
    expect(api.calls[11]!.params).toMatchObject({ image_count: 12, image_index: 12 })
    const start = page.getByRole('spinbutton', { name: '范围起始张数' })
    await start.fill('11'); await start.press('Tab')
    await expect(page.locator('.image-export-range')).toContainText('已选 2 张成品')
    const download = page.waitForEvent('download')
    await page.getByRole('button', { name: '批量下载图片（2 张）', exact: true }).click()
    const file = await download
    const path = info.outputPath('range.zip')
    await file.saveAs(path)
    const zip = await JSZip.loadAsync(await readFile(path))
    expect(Object.keys(zip.files)).toEqual(['习题图片-第11张.png', '习题图片-第12张.png'])
    expect(await zip.file('习题图片-第12张.png')!.async('base64')).toBe(api.images.get(api.calls[11]!.id)!.b64_json)
    await page.getByRole('button', { name: '保存到云端', exact: true }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toContainText('2 张图片 · 保存为一份云端 PDF')
    await dialog.getByRole('button', { name: '保存到云端', exact: true }).click()
    await expect(dialog).toContainText('已保存到云端')
    expect(api.cloudUploads[0]!.pdf.toString('latin1').match(/\/Type\s*\/Page\b/g)).toHaveLength(2)
    await dialog.getByRole('button', { name: '完成', exact: true }).click()
    await page.reload()
    await page.getByRole('button', { name: '图片出题', exact: true }).click()
    await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
    await expect(page.getByRole('button', { name: '批量下载图片（12 张）', exact: true })).toBeVisible()
    expect(api.calls).toHaveLength(12)
    expect(api.unexpected).toEqual([])
    await noHorizontalOverflow(page)
  })
}

// 真实浏览器、图片解码、IndexedDB、ZIP 和 PDF；图片为明确标注的离线绘制素材。
async function imageApi(page: Page, context: BrowserContext, options: { holdFirst?: boolean; holdAll?: boolean; parallel?: number; unknownFirst?: boolean; rejectFirst?: boolean; quotaAt?: number; configured?: boolean; role?: 'admin' | 'user' } = {}) {
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
  const releases: (() => void)[] = []
  const cloudUploads: { params: Record<string, string>; pdf: Buffer }[] = []
  const publications: Record<string, unknown>[] = []
  let cloudArchive: Record<string, unknown> | null = null
  let releaseFirst = () => {}
  const firstGate = new Promise<void>(resolve => { releaseFirst = resolve })
  await context.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    let data: unknown
    if (path === '/api/v1/auth/me') data = { id: 7, username: 'teacher', role: options.role || 'user' }
    else if (path === '/api/v1/scope/available') data = { available: Object.fromEntries(['一', '二', '三', '四', '五', '六'].map(n => [`小学${n}年级`, ['数学', '语文', '英语']])) }
    else if (path === '/api/v1/scope') data = { allowed: [], books: [{
      id: 'offline-math', semester: '上册', series: '离线浏览器测试教材',
      source_url: 'https://example.test/textbook', verified_on: '2026-10-11',
      units: ['20 以内加法', '20 以内减法', '认识图形', '位置与方向', '认识钟表'].map((title, index) => ({ title, page: index + 1, topics: [] })),
    }] }
    else if (path === '/api/v1/me/templates') data = { templates: [] }
    else if (path === '/api/v1/me/usage') data = { requests: 0 }
    else if (path === '/api/v1/image-generation/options') data = { configured: options.configured !== false,
      ...(options.parallel === undefined ? {} : { max_concurrency: options.parallel, default_concurrency: Math.min(2, options.parallel) }) }
    else if (path === '/api/v1/generation/options') data = { revision: 'offline-images', timeout_ms: 900000, task_timeout_seconds: 870 }
    else if (path === '/api/v1/image-generation/prompt') data = { prompt: '离线出题说明：根据所选知识点生成练习。' }
    else if (path === '/api/v1/library/folders') data = { items: [{ id: 'math-folder', name: '数学练习', paper_count: cloudArchive ? 1 : 0 }] }
    else if (path === '/api/v1/library/summary') data = { storage_bytes: cloudUploads.reduce((sum, upload) => sum + upload.pdf.length, 0), storage_limit_bytes: 5 * 1024 ** 3 }
    else if (path === '/api/v1/library/import') {
      const params = Object.fromEntries(new URL(route.request().url()).searchParams)
      const pdf = route.request().postDataBuffer()!
      cloudUploads.push({ params, pdf })
      cloudArchive ||= { id: 'cloud-images', title: params.title, grade: params.grade, subject: params.subject,
        question_count: Number(params.question_count || 0), folder_id: params.folder_id || null, folder_name: params.folder_id ? '数学练习' : null,
        group_name: '', favorite: false, version: 1, file_status: 'ready', file_error: '', publication_id: null,
        page_count: (pdf.toString('latin1').match(/\/Type\s*\/Page\b/g) || []).length, created_at: 1700000000,
        thumbnail_url: '/api/v1/library/assets/cloud-page', assets: [{ id: 'cloud-pdf', kind: 'pdf', url: '/api/v1/library/assets/cloud-pdf' }],
      }
      data = cloudArchive
    } else if (path === '/api/v1/library/papers') data = { items: cloudArchive ? [cloudArchive] : [], total: cloudArchive ? 1 : 0, has_more: false }
    else if (path === '/api/v1/library/papers/cloud-images') data = cloudArchive
    else if (path === '/api/v1/library/assets/cloud-pdf') {
      await route.fulfill({ contentType: 'application/pdf', headers: { 'Content-Disposition': 'attachment; filename="cloud-images.pdf"' }, body: cloudUploads[0]!.pdf }); return
    } else if (path === '/api/v1/library/assets/cloud-page') {
      await route.fulfill({ contentType: 'image/png', body: Buffer.from(b64, 'base64') }); return
    } else if (path === '/api/v1/admin/site/categories') data = { items: [{ id: 'practice', name: '同步练习', is_visible: true }] }
    else if (path === '/api/v1/admin/catalog/papers') {
      publications.push(route.request().postDataJSON())
      if (cloudArchive) cloudArchive.publication_id = 'cloud-publication'
      data = { id: 'cloud-publication', title: cloudArchive?.title, status: 'draft', page_count: cloudArchive?.page_count }
    }
    else if (path === '/api/v1/generate-image') {
      const id = route.request().headers()['x-request-id']!
      const params = route.request().postDataJSON() as ImageWorksheetParams
      calls.push({ id, params })
      const callNumber = calls.length
      if (callNumber === options.quotaAt) {
        await route.fulfill({ status: 429, json: { detail: { code: 'generation_failure_quota', error: '过去 24 小时生成失败次数过多，请稍后再试；失败不计入生成额度' } } })
        return
      }
      const image: WorksheetImage = { request_id: id, b64_json: b64, width: 600, height: 850, mime_type: 'image/png', prompt: 'OFFLINE IMAGE FIXTURE - NOT AI OUTPUT' }
      images.set(id, image)
      if (options.holdAll) await new Promise<void>(resolve => { releases.push(resolve) })
      if (callNumber === 1) {
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
  return { calls, queries, unexpected, releaseFirst, releases, images, cloudUploads, publications }
}

for (const width of [390, 1440]) {
  test(`并行生图可暂停续跑、乱序完成后按原序下载，并记住同时生成数 ${width}px`, async ({ page, context }, info) => {
    await page.setViewportSize({ width, height: 950 })
    const api = await imageApi(page, context, { parallel: 2, holdAll: true })
    await openImages(page)
    await configure(page, 4)
    await expect(page.getByRole('combobox', { name: '同时生成图片数' })).toHaveValue('2')
    await page.getByRole('button', { name: '生成 4 张图片', exact: true }).click()
    await expect.poll(() => api.releases.length).toBe(2)
    await expect(page.locator('.image-batch-status')).toContainText('正在同时生成 2 张')
    await page.getByRole('button', { name: '暂停后续生成' }).click()
    await expect(page.locator('.image-batch-status')).toContainText('进行中的图片完成后暂停')
    api.releases[1]!()
    await expect(page.locator('.image-batch-status')).toContainText('已完成 1 / 4 张')
    expect(api.calls).toHaveLength(2)
    api.releases[0]!()
    await expect(page.locator('.image-batch-status')).toContainText('本批次已暂停')
    await page.getByRole('button', { name: '继续生成剩余 2 张' }).click()
    await expect.poll(() => api.releases.length).toBe(4)
    api.releases[3]!(); api.releases[2]!()
    await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
    expect(api.calls.map(call => call.params.image_index)).toEqual([1, 2, 3, 4])
    expect(new Set(api.calls.map(call => call.id)).size).toBe(4)
    await downloadImages(page, info.outputPath('parallel-images.zip'), [...api.images.values()])
    if (width < 768) await page.getByRole('button', { name: '出题设置', exact: true }).click()
    await page.getByRole('combobox', { name: '同时生成图片数' }).selectOption('1')
    await page.reload()
    await page.getByRole('button', { name: '图片出题', exact: true }).click()
    await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
    if (width < 768) await page.getByRole('button', { name: '出题设置', exact: true }).click()
    await expect(page.getByRole('combobox', { name: '同时生成图片数' })).toHaveValue('1')
    expect(api.calls).toHaveLength(4)
    expect(api.unexpected).toEqual([])
    await noHorizontalOverflow(page)
  })
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

async function downloadImages(page: Page, path: string, images: WorksheetImage[]) {
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: `批量下载图片（${images.length} 张）`, exact: true }).click()
  const file = await download
  expect(await file.failure()).toBeNull()
  expect(file.suggestedFilename()).toBe(`习题图片-${images[0]!.request_id.slice(0, 8)}-${images.length}张.zip`)
  await file.saveAs(path)
  const zip = await JSZip.loadAsync(await readFile(path))
  expect(Object.keys(zip.files)).toEqual(images.map((_, index) => `习题图片-第${String(index + 1).padStart(2, '0')}张.png`))
  for (const [index, image] of images.entries()) {
    expect(await zip.file(`习题图片-第${String(index + 1).padStart(2, '0')}张.png`)!.async('base64')).toBe(image.b64_json)
  }
}

for (const width of [1440, 390]) {
  test(`图片保存到云端，刷新后可下载并稍后准备小程序发布 ${width}px`, async ({ page, context }, info) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 })
    const api = await imageApi(page, context, { role: 'admin' })
    await openImages(page); await configure(page, 2)
    await page.getByRole('button', { name: '生成 2 张图片', exact: true }).click()
    await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
    await page.getByRole('button', { name: '保存到云端', exact: true }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toContainText('2 张图片 · 保存为一份云端 PDF')
    await dialog.getByRole('textbox', { name: '云端图片标题' }).fill('图片云端练习')
    await dialog.getByRole('combobox', { name: '图片云端文件夹' }).click()
    await page.getByRole('option', { name: '数学练习' }).click()
    await dialog.getByRole('button', { name: '保存到云端', exact: true }).click()
    await expect(dialog).toContainText('已保存到云端')
    expect(api.cloudUploads).toHaveLength(1)
    expect(api.cloudUploads[0]!.params).toMatchObject({ title: '图片云端练习', grade: '小学一年级', subject: '数学', keyword: catalogKeyword, folder_id: 'math-folder' })
    expect(api.cloudUploads[0]!.params.request_id).toMatch(/^[a-f0-9]{64}$/)
    expect(api.cloudUploads[0]!.pdf.toString('latin1').match(/\/Type\s*\/Page\b/g)).toHaveLength(2)
    expect(api.publications).toHaveLength(0)
    await dialog.getByRole('button', { name: '查看云端试卷' }).click()
    await expect(dialog).toContainText('图片云端练习')
    await expect(dialog).toContainText('数学练习')
    const download = page.waitForEvent('download')
    await dialog.getByRole('button', { name: '下载归档 PDF' }).click()
    const file = await download
    const path = info.outputPath('cloud-images.pdf')
    await file.saveAs(path)
    expect(await readFile(path)).toEqual(api.cloudUploads[0]!.pdf)
    await dialog.getByRole('button', { name: '关闭', exact: true }).last().click()
    await page.reload()
    await page.getByRole('button', { name: '图片出题', exact: true }).click()
    await page.locator('.image-preview-heading').getByRole('button', { name: '云端试卷', exact: true }).click()
    await expect(dialog).toContainText('图片云端练习')
    await dialog.getByRole('button', { name: '准备发布到小程序' }).click()
    await expect(dialog).toContainText('使用已保存的云端文件')
    await dialog.getByRole('combobox', { name: '习题分类' }).click()
    await page.getByRole('option', { name: '同步练习' }).click()
    await dialog.getByRole('button', { name: '保存为习题草稿' }).click()
    await expect(dialog).toContainText('已添加为后台习题草稿')
    await expect(dialog.getByRole('link', { name: '前往后台查看' })).toHaveAttribute('href', '/admin/#papers?paper=cloud-publication')
    expect(api.publications).toEqual([{ paper_id: 'cloud-images', title: '图片云端练习', category_id: 'practice', description: '', download_mode: 'pdf', view_access: 'inherit', download_access: 'inherit' }])
    await dialog.getByRole('button', { name: '完成', exact: true }).click()
    await expect(dialog.getByRole('link', { name: '查看小程序发布' })).toBeVisible()
    await page.screenshot({ path: info.outputPath(`image-cloud-${width}.png`) })
    await noHorizontalOverflow(page)
    expect(api.cloudUploads).toHaveLength(1)
    expect(api.calls).toHaveLength(2)
    expect(api.unexpected).toEqual([])
  })
}

test('快速设置、修改原批次设置、复用和下载 ZIP/PDF，历史图片可在刷新后恢复', async ({ page, context }, info) => {
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
  const originalImages = api.calls.map(call => api.images.get(call.id)!)
  await downloadImages(page, info.outputPath('image-worksheets.zip'), originalImages)
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
  await downloadImages(page, info.outputPath('restored-image-worksheets.zip'), originalImages)
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
    await downloadImages(page, info.outputPath('mobile-image-worksheets.zip'), api.calls.map(call => api.images.get(call.id)!))
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

test('断线后查询原请求，同时自动完成剩余图片', async ({ page, context }) => {
  const api = await imageApi(page, context, { unknownFirst: true })
  await openImages(page)
  await configure(page, 2)
  await page.getByRole('button', { name: '生成 2 张图片' }).click()
  await expect(page.locator('.image-batch-status')).toContainText('生成结果待确认')
  await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成', { timeout: 15_000 })
  expect(api.calls).toHaveLength(2)
  expect(api.queries).toEqual([api.calls[0].id])
  await expect(page.getByRole('button', { name: '批量下载图片（2 张）' })).toBeEnabled()
  expect(api.unexpected).toEqual([])
})

for (const width of [390, 1440]) {
  test(`第13张被限流时暂停并保留前12张，继续时只生成剩余图片 ${width}px`, async ({ page, context }, info) => {
    await page.setViewportSize({ width, height: 950 })
    const api = await imageApi(page, context, { quotaAt: 13 })
    await openImages(page); await configure(page, 15)
    await page.getByRole('button', { name: '生成 15 张图片', exact: true }).click()
    await expect(page.locator('.image-batch-status')).toContainText('已完成 12 / 15 张')
    await expect(page.getByText(/第 13 张：.*已暂停后续图片/)).toBeVisible()
    await expect(page.getByRole('button', { name: '继续生成剩余 3 张', exact: true })).toBeEnabled()
    expect(api.calls).toHaveLength(13)
    const originalIds = api.calls.slice(0, 12).map(call => call.id)
    await page.screenshot({ path: info.outputPath('quota-paused.png') })
    await noHorizontalOverflow(page)
    await page.getByRole('button', { name: '继续生成剩余 3 张', exact: true }).click()
    await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
    expect(api.calls.slice(13).map(call => call.params.image_index)).toEqual([13, 14, 15])
    expect(api.calls.slice(0, 12).map(call => call.id)).toEqual(originalIds)
    expect(api.calls).toHaveLength(16)
    expect(api.unexpected).toEqual([])
  })
}

test('单张明确失败后自动继续生成其他图片，修改设置不会改变本批次的重试条件', async ({ page, context }) => {
  const api = await imageApi(page, context, { rejectFirst: true })
  await openImages(page)
  await configure(page, 3)
  await page.getByRole('button', { name: '生成 3 张图片' }).click()
  await expect(page.locator('.image-batch-status')).toContainText('部分图片未完成')
  await expect(page.locator('.image-batch-status')).toContainText('已完成 2 / 3 张')
  expect(api.calls.map(call => call.params.image_index)).toEqual([1, 2, 3])
  await page.getByRole('textbox', { name: '图片知识点' }).fill('新的知识点')
  await expect(page.locator('.image-batch-status')).toContainText('可能产生新的费用')
  await page.getByRole('button', { name: '继续生成剩余 1 张' }).click()
  await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
  expect(api.calls).toHaveLength(4)
  expect(api.calls[0].id).not.toBe(api.calls[3].id)
  expect(api.calls[3].params.keyword).toBe(catalogKeyword)
  expect(api.unexpected).toEqual([])
})

test('多张图片可只重新生成当前图片，取消确认不会发起请求', async ({ page, context }) => {
  const api = await imageApi(page, context)
  await openImages(page)
  await configure(page, 3)
  await page.getByRole('button', { name: '生成 3 张图片', exact: true }).click()
  await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
  const originalIds = api.calls.map(call => call.id)
  await page.getByRole('button', { name: '第 2 张 · 已完成', exact: true }).click()
  page.once('dialog', dialog => {
    expect(dialog.message()).toContain('第 2 张图片')
    expect(dialog.message()).toContain('新的生图请求费用')
    void dialog.accept()
  })
  await page.getByRole('button', { name: '重新生成本张', exact: true }).click()
  await expect(page.locator('.image-batch-status')).toContainText('本批图片已全部完成')
  expect(api.calls).toHaveLength(4)
  expect(api.calls[3]!.params.image_index).toBe(2)
  expect(api.calls[3]!.id).not.toBe(originalIds[1])
  expect(api.calls[0]!.id).toBe(originalIds[0])
  expect(api.calls[2]!.id).toBe(originalIds[2])
  const callsBeforeCancel = api.calls.length
  page.once('dialog', dialog => void dialog.dismiss())
  await page.getByRole('button', { name: '重新生成本张', exact: true }).click()
  expect(api.calls).toHaveLength(callsBeforeCancel)
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
