import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import * as vue from 'vue'
import { parse } from 'vue/compiler-sfc'
import { nicknameError } from '../../shared/mini-profile'

function moduleFixture(file: string, modules: Record<string, unknown>, expose = '', globals: Record<string, unknown> = {}) {
  let source = readFileSync(new URL('../src/' + file, import.meta.url), 'utf8')
  if (file.endsWith('.vue')) source = parse(source).descriptor.scriptSetup!.content
  const exports: Record<string, any> = {}
  vm.runInNewContext(ts.transpileModule(source + '\n' + expose, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText, {
    exports, require: (id: string) => id === 'vue' ? vue : modules[id] || {}, ...globals,
  })
  return exports
}

const user = () => ({ id: 'reader', username: 'wx1234567890', nickname: '小海豚', avatar: '', avatar_url: null, is_vip: false })

test('opening a native photo picker keeps the profile draft alive across hide/show', () => {
  const hooks: Record<string, () => void> = {}
  const session = vue.reactive({ user: user() })
  let refreshes = 0
  const page = moduleFixture('pages/account/index.vue', {
    '@dcloudio/uni-app': { onHide: (fn: () => void) => { hooks.hide = fn }, onShow: (fn: () => void) => { hooks.show = fn }, onUnload: (fn: () => void) => { hooks.unload = fn } },
    '../../services/session': { session, ensureSession: async () => true, refreshMembership: async () => { refreshes++ } },
    '../../services/latest-request': { createLatestRequest: () => ({ invalidate() {} }) },
    '../../services/tabbar-overlay': { useTabBarOverlay() {} },
  }, 'exports.profile = { openProfile, profileOpen }')
  page.profile.openProfile()
  hooks.hide!()
  assert.equal(page.profile.profileOpen.value, true)
  hooks.show!()
  assert.equal(page.profile.profileOpen.value, true)
  assert.equal(refreshes, 0)
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
    '../../../shared/mini-profile': { nicknameError },
  }, 'exports.profile = { nickname, avatar, photo, choosePreset, selectPhoto, save, canSave }', {
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
