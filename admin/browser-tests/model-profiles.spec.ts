import { expect, test, type BrowserContext } from '@playwright/test'

type Profile = { id: string; name: string; enabled: boolean; baseUrl: string; model: string; timeout: number; hasKey?: boolean; apiKey?: string; maxTokens?: number; size?: string; responseFormat?: string }

async function fixture(context: BrowserContext, gate = Promise.resolve()) {
  const text: Profile[] = [
    { id: 'text-main', name: '文本主模型', enabled: true, baseUrl: 'https://text.example.test/v1', model: 'text-main', timeout: 120, maxTokens: 16384, hasKey: true },
    { id: 'text-backup', name: '文本备用', enabled: true, baseUrl: 'https://backup.example.test/v1', model: 'text-backup', timeout: 60, maxTokens: 8192, hasKey: true },
  ]
  const image: Profile[] = [{ id: 'image-main', name: '图片主模型', enabled: true, baseUrl: 'https://image.example.test/v1', model: 'image-main', timeout: 300, size: '1024x1536', responseFormat: 'auto', hasKey: true }]
  const versions = { text: 1, image: 1 }
  const writes: { path: string; body: { revision: string; models: Profile[] } }[] = []
  const probes: Record<string, unknown>[] = []
  const modelFetches: Record<string, unknown>[] = []
  await context.route('**/api/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname
    if (path.endsWith('/auth/me')) { await route.fulfill({ json: { id: 1, username: 'admin', role: 'admin' } }); return }
    if (path.endsWith('/test-llm')) {
      probes.push(request.postDataJSON())
      await route.fulfill({ json: { reply: 'offline fixture' } }); return
    }
    if (path.endsWith('/llm-models')) {
      modelFetches.push(request.postDataJSON())
      await route.fulfill({ json: { status: 'ok', models: ['text-main', 'backup-model', 'third-model'], count: 3 } }); return
    }
    if (!path.endsWith('/llm-config') && !path.endsWith('/image-config')) {
      await route.fulfill({ status: 503, json: { detail: '未启用的离线接口' } }); return
    }
    const models = path.endsWith('/llm-config') ? text : image
    const kind = models === text ? 'text' : 'image'
    if (request.method() === 'PUT') {
      const body = request.postDataJSON()
      writes.push({ path, body })
      await gate
      if (body.revision !== String(versions[kind])) {
        await route.fulfill({ status: 409, json: { detail: { code: 'model_config_conflict', error: '模型配置已在其他窗口更新，本次修改未保存' } } }); return
      }
      const next = body.models.map((model: Profile) => {
        const saved = { ...model, hasKey: !!model.apiKey || !!models.find(value => value.id === model.id)?.hasKey }
        delete saved.apiKey
        return saved
      })
      models.splice(0, models.length, ...next)
      versions[kind]++
    }
    if (request.method() === 'DELETE') {
      if (request.headers()['if-match'] !== String(versions[kind])) {
        await route.fulfill({ status: 409, json: { detail: { code: 'model_config_conflict', error: '模型配置已在其他窗口更新，本次清空已取消' } } }); return
      }
      models.splice(0); versions[kind]++
    }
    await route.fulfill({ json: { ...(models[0] ?? { baseUrl: '', model: '', timeout: 120, hasKey: false }), models, revision: String(versions[kind]) } })
  })
  return { writes, probes, modelFetches, text, image, changeText: () => { versions.text++; text[0]!.name = '另一窗口已保存' } }
}

for (const width of [1440, 390, 320]) {
  test(`多模型排序、停用、增删、标签草稿与保存 ${width}px`, async ({ page, context }, info) => {
    const server = await fixture(context)
    await page.setViewportSize({ width, height: 1000 })
    await page.goto('/admin/#llm')
    const text = page.getByRole('region', { name: '全局模型配置', exact: true })
    const image = page.getByRole('region', { name: '图片生成服务', exact: true })
    await expect(text.locator('.model-select')).toHaveCount(2)
    await text.getByRole('button', { name: '上移模型 2', exact: true }).click()
    await text.locator('.model-select').first().click()
    await text.getByRole('button', { name: '拉取模型', exact: true }).click()
    await expect.poll(() => server.modelFetches.length).toBe(1)
    expect(server.modelFetches[0]).toMatchObject({ id: 'text-backup', baseUrl: 'https://backup.example.test/v1', apiKey: '' })
    await text.getByRole('combobox', { name: '从拉取结果选择' }).click()
    await page.getByRole('option', { name: 'backup-model', exact: true }).click()
    await expect(text.getByRole('textbox', { name: '模型名称', exact: false })).toHaveValue('backup-model')
    await text.getByRole('textbox', { name: '备注名称' }).fill('备用模型优先处理')
    await text.getByRole('switch', { name: '启用', exact: true }).click()
    await page.getByRole('tab', { name: '图片出题' }).click()
    await image.getByRole('textbox', { name: '生图模型名称' }).fill('image-draft')
    await page.getByRole('tab', { name: '文本出题' }).click()
    await expect(text.getByRole('textbox', { name: '备注名称' })).toHaveValue('备用模型优先处理')
    await expect(text.getByRole('switch', { name: '启用', exact: true })).not.toBeChecked()
    await text.getByRole('button', { name: '保存配置', exact: true }).click()
    await expect(text.getByText('模型配置已保存', { exact: true })).toBeVisible()
    expect(server.writes[0]?.body.models.map(model => model.id)).toEqual(['text-backup', 'text-main'])
    expect(server.writes[0]?.body.models[0]).toMatchObject({ apiKey: '', enabled: false })
    expect(server.writes[0]?.body.models[0]).not.toHaveProperty('hasKey')
    await text.getByRole('button', { name: '测试连接', exact: true }).click()
    await expect.poll(() => server.probes.length).toBe(1)
    expect(server.probes[0]).toMatchObject({ id: 'text-backup', apiKey: '' })
    await text.getByRole('button', { name: '添加模型', exact: true }).click()
    await text.getByRole('textbox', { name: '备注名称' }).fill('第三个模型')
    await text.getByRole('textbox', { name: '接口地址', exact: false }).fill('https://third.example.test/v1')
    await text.getByRole('textbox', { name: '模型名称', exact: false }).fill('third-model-with-a-long-provider-identifier')
    await text.getByLabel('API 密钥', { exact: true }).fill('temporary-ui-key')
    await text.getByRole('button', { name: '保存配置', exact: true }).click()
    await expect(text.getByText('模型配置已保存', { exact: true })).toBeVisible()
    expect(server.writes[1]?.body.models).toHaveLength(3)
    await expect(text.getByLabel('API 密钥', { exact: true })).toHaveValue('')
    await page.screenshot({ path: info.outputPath(`text-models-${width}.png`), fullPage: true, animations: 'disabled' })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    const overlaps = await text.locator('input, button, [role="switch"]').evaluateAll(elements =>
      elements.filter(element => {
        const rect = element.getBoundingClientRect()
        return rect.width > 0 && (rect.left < -1 || rect.right > innerWidth + 1)
      }).map(element => element.outerHTML))
    expect(overlaps).toEqual([])
    await text.getByRole('button', { name: '移除模型 3', exact: true }).click()
    await page.getByRole('dialog', { name: '移除模型', exact: true }).getByRole('button', { name: '确认移除' }).click()
    await text.getByRole('button', { name: '保存配置', exact: true }).click()
    await expect(text.getByText('模型配置已保存', { exact: true })).toBeVisible()
    expect(server.text).toHaveLength(2)
    await page.getByRole('tab', { name: '图片出题' }).click()
    await expect(image.getByRole('textbox', { name: '生图模型名称' })).toHaveValue('image-draft')
    await image.getByRole('button', { name: '保存生图配置', exact: true }).click()
    await expect(image.getByText('模型配置已保存', { exact: true })).toBeVisible()
    expect(server.image[0]?.model).toBe('image-draft')
    await page.screenshot({ path: info.outputPath(`image-models-${width}.png`), fullPage: true, animations: 'disabled' })
  })
}

test('保存期间禁止编辑，失败后仍保留模型列表草稿', async ({ page, context }) => {
  let release!: () => void
  const server = await fixture(context, new Promise<void>(resolve => { release = resolve }))
  await page.goto('/admin/#llm')
  const text = page.getByRole('region', { name: '全局模型配置', exact: true })
  await text.getByRole('textbox', { name: '备注名称' }).fill('保存中')
  await text.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect.poll(() => server.writes.length).toBe(1)
  await expect(text.getByRole('textbox', { name: '备注名称' })).toBeDisabled()
  await expect(text.getByRole('button', { name: '添加模型', exact: true })).toBeDisabled()
  release()
  await expect(text.getByText('模型配置已保存', { exact: true })).toBeVisible()
  await page.route('**/api/v1/admin/llm-config', route => route.fulfill({ status: 400, json: { detail: { error: '模型配置未通过校验' } } }))
  await text.getByRole('textbox', { name: '备注名称' }).fill('失败后保留')
  await text.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(text.getByText('模型配置未通过校验', { exact: true })).toBeVisible()
  await expect(text.getByRole('textbox', { name: '备注名称' })).toHaveValue('失败后保留')
  await expect(text.getByText('未保存', { exact: true })).toBeVisible()
})

test('保存冲突保留草稿，载入最新配置前必须确认', async ({ page, context }) => {
  const server = await fixture(context)
  await page.goto('/admin/#llm')
  const text = page.getByRole('region', { name: '全局模型配置', exact: true })
  await text.getByRole('textbox', { name: '备注名称' }).fill('当前窗口的草稿')
  server.changeText()
  await text.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(text.getByText('本地修改已保留，服务器配置未被覆盖。')).toBeVisible()
  expect(server.text[0]?.name).toBe('另一窗口已保存')
  await expect(text.getByRole('textbox', { name: '备注名称' })).toHaveValue('当前窗口的草稿')
  await text.getByRole('button', { name: '载入最新配置', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '载入最新配置', exact: true })
  await dialog.getByRole('button', { name: '保留本地修改' }).click()
  await expect(text.getByRole('textbox', { name: '备注名称' })).toHaveValue('当前窗口的草稿')
  await text.getByRole('button', { name: '载入最新配置', exact: true }).click()
  await dialog.getByRole('button', { name: '确认载入' }).click()
  await expect(text.getByRole('textbox', { name: '备注名称' })).toHaveValue('另一窗口已保存')
  await text.getByRole('textbox', { name: '备注名称' }).fill('核对后重新保存')
  await text.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(text.getByText('模型配置已保存', { exact: true })).toBeVisible()
  expect(server.text[0]?.name).toBe('核对后重新保存')
})

test('旧窗口不能清除新配置，错误字段定位到对应模型且不发请求', async ({ page, context }) => {
  const server = await fixture(context)
  await page.goto('/admin/#llm')
  const text = page.getByRole('region', { name: '全局模型配置', exact: true })
  await text.getByRole('textbox', { name: '接口地址', exact: false }).fill('not-a-url')
  await text.locator('.model-select').nth(1).click()
  await text.getByRole('button', { name: '保存配置', exact: true }).click()
  await expect(text.getByText(/模型 1：接口地址无效/)).toBeVisible()
  await expect(text.getByRole('textbox', { name: '接口地址', exact: false })).toHaveValue('not-a-url')
  expect(server.writes).toHaveLength(0)
  server.changeText()
  await text.getByRole('button', { name: '清除全局配置', exact: true }).click()
  await page.getByRole('dialog', { name: '清除全局模型配置', exact: true }).getByRole('button', { name: '确认清除' }).click()
  await expect(text.getByText('本地修改已保留，服务器配置未被覆盖。')).toBeVisible()
  expect(server.text).toHaveLength(2)
})

test('图片备用模型校验尺寸并保留独立参数', async ({ page, context }) => {
  const server = await fixture(context)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/admin/#llm')
  await page.getByRole('tab', { name: '图片出题' }).click()
  const image = page.getByRole('region', { name: '图片生成服务', exact: true })
  await image.getByRole('button', { name: '添加模型', exact: true }).click()
  await image.getByRole('textbox', { name: '生图接口地址' }).fill('https://second.example.test/v1')
  await image.getByRole('textbox', { name: '生图模型名称' }).fill('image-backup')
  await image.getByLabel('生图 API 密钥', { exact: true }).fill('offline-image-key')
  await image.getByRole('textbox', { name: '图片尺寸' }).fill('wrong')
  await image.getByRole('button', { name: '保存生图配置', exact: true }).click()
  await expect(image.getByText(/模型 2：图片尺寸须为/)).toBeVisible()
  expect(server.writes).toHaveLength(0)
  await image.getByRole('textbox', { name: '图片尺寸' }).fill('auto')
  await image.getByRole('button', { name: '保存生图配置', exact: true }).click()
  await expect(image.getByText('模型配置已保存', { exact: true })).toBeVisible()
  expect(server.image[1]).toMatchObject({ model: 'image-backup', size: 'auto', timeout: 300 })
  expect(server.image[1]).not.toHaveProperty('maxTokens')
  expect(server.text).toHaveLength(2)
})

test('内网 HTTP 缺少 randomUUID 时仍能加载和新增模型', async ({ page, context }) => {
  await fixture(context)
  await page.addInitScript(() => { Object.defineProperty(crypto, 'randomUUID', { value: undefined, configurable: true }) })
  await page.goto('/admin/#llm')
  const text = page.getByRole('region', { name: '全局模型配置', exact: true })
  await expect(text.locator('.model-select')).toHaveCount(2)
  await text.getByRole('button', { name: '添加模型', exact: true }).click()
  await expect(text.locator('.model-select')).toHaveCount(3)
  await expect(text.getByRole('textbox', { name: '备注名称' })).toHaveValue('')
})
