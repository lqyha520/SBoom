import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import * as vue from 'vue'

function fixture(deny = false, needAuthorization = true, clipboardError: { errMsg: string; errno?: number } | null = null) {
  const storage = new Map(), results: unknown[] = [], copies: string[] = [], modals: any[] = [], navigations: string[] = [], toasts: string[] = []
  let need!: (resolve: (value: unknown) => void) => void
  const exports: Record<string, any> = {}
  vm.runInNewContext(ts.transpileModule(readFileSync(new URL('../src/services/privacy.ts', import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText, {
    exports, require: () => vue, console: { warn() {}, log() {}, error() {} },
    uni: { getStorageSync: (key: string) => storage.get(key), setStorageSync: (key: string, value: string) => storage.set(key, value),
      showToast(options: any) { toasts.push(options.title) }, showModal(options: any) { modals.push(options) }, navigateTo(options: any) { navigations.push(options.url) },
      setClipboardData(options: any) {
        if (clipboardError) { options.fail?.(clipboardError); options.complete?.(clipboardError); return }
        copies.push(options.data); options.success?.({}); options.complete?.({})
      } },
    wx: { onNeedPrivacyAuthorization(callback: typeof need) { need = callback },
      getPrivacySetting(options: any) { options.success({ privacyContractName: '测试指引', needAuthorization }) },
      requirePrivacyAuthorize(options: any) { if (deny) options.fail({ errMsg: 'requirePrivacyAuthorize:fail privacy permission is not authorized' }); else options.success({}) } },
  })
  exports.installPrivacy()
  return { api: exports, copies, results, modals, navigations, toasts, request: () => need(value => results.push(value)) }
}
async function settle() { for (let i = 0; i < 8; i++) await Promise.resolve() }

test('privacy refusal completes caller state without touching clipboard; a later agreement can retry', async () => {
  const denied = fixture(true)
  let failures = 0, complete = 0
  denied.api.copyWithPrivacy({ data: 'secret', fail: () => failures++, complete: () => complete++ })
  await settle()
  assert.equal(failures, 1); assert.equal(complete, 1); assert.equal(denied.copies.length, 0)
  const agreed = fixture()
  agreed.api.copyWithPrivacy({ data: 'approved' }); await settle()
  assert.deepEqual(agreed.copies, ['approved'])
})

test('native privacy queue resolves each pending request once and legal consent is versioned', () => {
  const app = fixture()
  assert.equal(app.api.hasConsent(), false)
  app.api.rememberConsent(); assert.equal(app.api.hasConsent(), true)
  app.request(); app.request()
  assert.equal(app.api.privacyState.open, true)
  app.api.resolvePrivacy(false); app.api.resolvePrivacy(true)
  assert.equal(app.results.length, 2)
  assert.equal(app.api.privacyState.open, false)
  assert.equal((app.results[0] as any).event, 'disagree')
  app.request(); app.api.resolvePrivacy(true)
  assert.equal((app.results[2] as any).buttonId, 'privacy-agree')
})

test('privacy failure points to the authorization entry instead of a dead-end toast', async () => {
  const app = fixture(true)
  app.api.copyWithPrivacy({ data: 'secret' }); await settle()
  assert.equal(app.modals.length, 1)
  assert.match(app.modals[0].content, /10 秒/)
  app.modals[0].success({ confirm: true })
  assert.deepEqual(app.navigations, ['/subpages/privacy/index?kind=privacy'])
  const agreed = fixture(true, false)
  agreed.api.copyWithPrivacy({ data: 'secret' }); await settle()
  assert.equal(agreed.modals.length, 0)
})

test('clipboard blocked by an undeclared privacy scope reports a retry hint instead of the auth dead end', async () => {
  const app = fixture(false, false, { errMsg: 'setClipboardData:fail api scope is not declared in the privacy agreement', errno: 112 })
  let failed = 0
  app.api.copyWithPrivacy({ data: 'secret', fail: () => failed++ }); await settle()
  assert.equal(failed, 1)
  assert.equal(app.modals.length, 0)
  assert.deepEqual(app.toasts, ['微信暂不允许复制，请稍后重试'])
})
