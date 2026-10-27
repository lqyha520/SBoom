import { describe, expect, it } from 'vitest'
import { imagePayload, modelDrafts, modelError, newModel, textPayload } from '../model-profiles'

describe('多模型草稿与请求', () => {
  it('兼容原配置并沿用密钥绑定 ID', () => {
    const drafts = modelDrafts({ baseUrl: 'https://text.test/v1', model: 'old', timeout: 60, hasKey: true }, 'text')
    expect(drafts).toHaveLength(1)
    expect(drafts[0]).toMatchObject({ id: 'legacy', apiKey: '', hasKey: true, enabled: true })
    expect(textPayload(drafts).models[0]).not.toHaveProperty('hasKey')
  })
  it('空列表不恢复旧配置，新模型不复用已有 ID', () => {
    expect(modelDrafts({ baseUrl: '', model: '', timeout: 60, hasKey: false, models: [] }, 'text')).toEqual([])
    expect(newModel('text').id).not.toBe(newModel('text').id)
  })
  it('顺序与启停原样提交，文本与图片字段相互隔离', () => {
    const primary = { ...newModel('text'), model: ' primary ', apiKey: ' key ' }
    const backup = { ...newModel('image'), model: 'backup', enabled: false, requestMode: 'async' as const }
    const text = textPayload([backup, primary]).models
    expect(text.map(model => model.id)).toEqual([backup.id, primary.id])
    expect(text[0]?.enabled).toBe(false)
    expect(text[1]).toMatchObject({ apiKey: 'key', model: 'primary' })
    expect(text[0]).not.toHaveProperty('size')
    expect(text[0]).not.toHaveProperty('requestMode')
    const image = imagePayload([backup]).models[0]
    expect(image).toMatchObject({ size: '1024x1536', responseFormat: 'auto', requestMode: 'async' })
    expect(image).not.toHaveProperty('maxTokens')
  })
  it('提交版本号，避免旧窗口覆盖新配置', () => {
    expect(textPayload([], 'text-revision').revision).toBe('text-revision')
    expect(imagePayload([], 'image-revision').revision).toBe('image-revision')
  })
  it('按模型保存兼容参数，图片请求不携带文本采样字段', () => {
    const profile = { ...newModel('text'), samplingMode: 'omit' as const, tokenParameter: 'max_completion_tokens' as const }
    expect(textPayload([profile]).models[0]).toMatchObject({ samplingMode: 'omit', tokenParameter: 'max_completion_tokens' })
    expect(imagePayload([profile]).models[0]).not.toHaveProperty('samplingMode')
    expect(imagePayload([profile]).models[0]).not.toHaveProperty('tokenParameter')
  })
  it('校验所有模型的地址、密钥与数值，停用项可以没有密钥', () => {
    const valid = { ...newModel('text'), model: 'm', baseUrl: 'https://example.test/v1', apiKey: 'test-key' }
    expect(modelError(valid, 'text')).toBe('')
    for (const change of [
      { baseUrl: 'https://user:key@example.test' }, { baseUrl: 'https://example.test?key=value' },
      { baseUrl: 'https://[broken' }, { baseUrl: 'https://example.test:0' }, { model: '' },
      { timeout: NaN }, { timeout: 9 }, { timeout: 601 }, { timeout: 30.5 },
      { maxTokens: 0 }, { maxTokens: 131073 }, { apiKey: '' },
    ]) expect(modelError({ ...valid, ...change }, 'text')).not.toBe('')
    expect(modelError({ ...valid, enabled: false, apiKey: '' }, 'text')).toBe('')
    expect(modelError({ ...valid, enabled: false, apiKey: '' }, 'text', true)).not.toBe('')
    expect(modelError({ ...valid, hasKey: true, apiKey: '' }, 'text', true)).toBe('')
    expect(modelError({ ...valid, size: 'auto' }, 'image')).toBe('')
    expect(modelError({ ...valid, size: '10x20' }, 'image')).not.toBe('')
  })
})
