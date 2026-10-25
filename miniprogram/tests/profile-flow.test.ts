import { usePageLifecycle } from '../src/services/page-lifecycle'
import { reconcileRows } from '../src/services/catalog-rows'
import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import * as vue from 'vue'
import { parse } from 'vue/compiler-sfc'
import { clipNickname, nicknameError, registrationAccountError } from '../../shared/mini-profile'

function moduleFixture(file: string, modules: Record<string, unknown>, expose = '', globals: Record<string, unknown> = {}) {
  let source = readFileSync(new URL('../src/' + file, import.meta.url), 'utf8')
  if (file.endsWith('.vue')) source = parse(source).descriptor.scriptSetup!.content
  const exports: Record<string, any> = {}
  vm.runInNewContext(ts.transpileModule(source + '\n' + expose, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText, {
    exports, require: (id: string) => id === 'vue' ? vue : modules[id] || (id.endsWith('/page-lifecycle') ? { usePageLifecycle, captureScroll: (save: (top: number) => void) => save(600) } : id.endsWith('/catalog-rows') ? { reconcileRows } : id.endsWith('/page-navigation') ? { navigatePage: (options: unknown) => (globals.uni as any)?.navigateTo?.(options) } : {}), ...globals,
  })
  return exports
}

const user = () => ({ id: 'reader', username: 'wx1234567890', nickname: '小海豚', avatar: '', avatar_url: null, is_vip: false })

test('新注册至少8位，已有6位密码仍可进入登录请求', async () => {
  const calls: string[] = []
  const api = moduleFixture('pages/login/index.vue', {
    '@dcloudio/uni-app': { onLoad() {}, onShow() {}, onHide() {}, onUnload() {} },
    '../../services/privacy': { hasConsent: () => true, rememberConsent() {} },
    '../../services/api': { errorMessage: String, request: async (path: string) => { calls.push(path); return {} } },
    '../../services/session': { loginMini() {} },
    '../../services/navigation': { visitDestination() {} },
    '../../../../shared/mini-profile': { registrationAccountError },
  }, 'exports.form = { username, password, webMode, submitWeb, error }')
  const form = api.form
  form.username.value = 'reader'; form.password.value = '123456'; form.webMode.value = 'register'
  await form.submitWeb(); assert.match(form.error.value, /8 位/); assert.equal(calls.length, 0)
  form.webMode.value = 'login'; await form.submitWeb(); assert.deepEqual(calls, ['/api/v1/mini/login-password'])
  form.webMode.value = 'register'; form.password.value = '12345678'; await form.submitWeb()
  assert.equal(calls.at(-1), '/api/v1/mini/register')
})

test('修改密码拒绝7位新密码，接受6位旧密码与8位新密码', async () => {
  const calls: string[][] = []
  const api = moduleFixture('components/PasswordSheet.vue', {
    '../services/session': { session: { user: { has_password: true } }, savePassword: async (...values: string[]) => { calls.push(values) } },
    '../services/tabbar-overlay': { useTabBarOverlay() {} },
  }, 'exports.form = { current, next, confirm, canSave, localError, save }', { defineProps: () => ({ open: true }), defineEmits: () => () => {} })
  const form = api.form
  form.current.value = '123456'; form.next.value = form.confirm.value = '1234567'
  await form.save(); assert.equal(calls.length, 0); assert.match(form.localError.value, /8 位/)
  form.next.value = form.confirm.value = '12345678'; assert.equal(form.canSave.value, true); await form.save()
  assert.deepEqual(calls, [['123456', '12345678']])
})

test('opening a native photo picker keeps the profile draft alive across hide/show', async () => {
  const hooks: Record<string, () => void> = {}
  const session = vue.reactive({ user: user() })
  let refreshes = 0, summaryRefreshes = 0, pulled = 0
  const page = moduleFixture('pages/account/index.vue', {
    '@dcloudio/uni-app': { onHide: (fn: () => void) => { hooks.hide = fn }, onShow: (fn: () => void) => { hooks.show = fn }, onUnload: (fn: () => void) => { hooks.unload = fn }, onPullDownRefresh: (fn: () => void) => { hooks.pull = fn } },
    '../../services/session': { session, ensureSession: async () => true, refreshMembership: async () => { refreshes++ } },
    '../../services/api': { errorMessage: String, fetchCatalogSummary: async (options: { force?: boolean }) => { if (options.force) summaryRefreshes++; return {} } },
    '../../services/growth': { refreshUnread: async () => {} },
    '../../services/latest-request': { createLatestRequest: () => ({ invalidate() {} }) },
    '../../services/tabbar-overlay': { useTabBarOverlay() {} },
  }, 'exports.profile = { openProfile, profileOpen }', { uni: { $on() {}, $off() {}, stopPullDownRefresh() { pulled++ } } })
  page.profile.openProfile()
  hooks.hide!()
  assert.equal(page.profile.profileOpen.value, true)
  hooks.show!()
  assert.equal(page.profile.profileOpen.value, true)
  assert.equal(refreshes, 0)
  await hooks.pull!()
  assert.equal(refreshes, 1)
  assert.equal(summaryRefreshes, 1)
  assert.equal(pulled, 1)
  hooks.unload!()
  assert.equal(page.profile.profileOpen.value, false)
})

test('a slow membership refresh cannot revert a newly saved avatar', async () => {
  let previousResponse!: (value: unknown) => void
  const next = { ...user(), avatar: 'photo:new', avatar_url: '/api/v1/mini/me/avatar/new' }
  const old = user()
  const service = moduleFixture('services/session.ts', {
    './api': { unauthorizedHandler() {}, request: (path: string) => path === '/api/v1/mini/me'
      ? new Promise(resolve => { previousResponse = resolve }) : Promise.resolve(next) },
  })
  service.session.user = old
  const refresh = service.refreshMembership()
  await service.saveAvatar({ image: 'image-data' })
  previousResponse(old)
  await refresh
  assert.equal(service.session.user.avatar, 'photo:new')
  assert.equal(service.session.user.avatar_url, next.avatar_url)
})

async function profileFixture(prepare = async (_path: string) => ({ path: 'wxfile://compressed', image: 'image-data' })) {
  const props = vue.reactive({ open: false })
  const session = vue.reactive({ user: user() })
  const calls: { type: string; payload: Record<string, unknown> }[] = []
  const emitted: string[] = []
  const source = moduleFixture('components/ProfileSheet.vue', {
    '../services/session': {
      session,
      async saveProfile(payload: Record<string, unknown>) { calls.push({ type: 'preset', payload }); Object.assign(session.user, payload) },
      async saveAvatar(payload: Record<string, unknown>) { calls.push({ type: 'photo', payload }); Object.assign(session.user, { avatar: 'photo:changed' }, payload) },
    },
    '../services/profile-photo': { prepareProfilePhoto: prepare },
    '../services/api': { errorMessage: (cause: Error) => cause.message },
    '../services/tabbar-overlay': { useTabBarOverlay() {} },
    '../../../shared/mini-profile': { clipNickname, nicknameError },
  }, 'exports.profile = { nickname, avatar, photo, choosePreset, selectPhoto, save, canSave, editNickname }', {
    defineProps: () => props, defineEmits: () => (event: string) => emitted.push(event),
  })
  props.open = true
  await vue.nextTick()
  return { ...source.profile, props, calls, emitted }
}

test('choosing a default after a photo saves only the selected preset and edited nickname', async () => {
  const profile = await profileFixture()
  await profile.selectPhoto('wxfile://selected')
  profile.choosePreset('rabbit')
  profile.nickname.value = '小兔'
  assert.equal(profile.photo.value, null)
  await profile.save()
  assert.equal(profile.calls.length, 1)
  assert.equal(profile.calls[0].type, 'preset')
  assert.equal(profile.calls[0].payload.avatar, 'rabbit')
  assert.equal(profile.calls[0].payload.nickname, '小兔')
  assert.deepEqual(profile.emitted, ['saved'])
})

test('pasted nicknames are clipped to 32 code points as they are entered', async () => {
  const profile = await profileFixture()
  profile.editNickname({ detail: { value: '😀'.repeat(40) } })
  assert.equal(profile.nickname.value, '😀'.repeat(32))
  assert.equal(profile.canSave.value, true)
})

test('selected photos and nicknames are submitted together and late picker results are ignored', async () => {
  const profile = await profileFixture()
  await profile.selectPhoto('wxfile://selected')
  profile.nickname.value = '向阳'
  await profile.save()
  assert.equal(profile.calls[0].type, 'photo')
  assert.equal(profile.calls[0].payload.image, 'image-data')
  assert.equal(profile.calls[0].payload.nickname, '向阳')

  let complete!: (value: { path: string; image: string }) => void
  const delayed = await profileFixture(() => new Promise(resolve => { complete = resolve }))
  const reading = delayed.selectPhoto('wxfile://late')
  delayed.props.open = false; await vue.nextTick()
  delayed.props.open = true; await vue.nextTick()
  complete({ path: 'wxfile://late', image: 'late-image' }); await reading
  assert.equal(delayed.photo.value, null)
  assert.equal(delayed.canSave.value, false)
})
