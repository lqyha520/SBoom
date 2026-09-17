import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

type PageLike = { route: string; options?: Record<string, unknown> }

function compile(relative: string) {
  return ts.transpileModule(readFileSync(new URL(relative, import.meta.url), 'utf8'),
    { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText
}

/** 真机行为：登录页由 navigateTo 压栈，微信给出的 options 保持编码态且不自解码。 */
function loadNavigation(pages: PageLike[], backFails = false) {
  const returnRoute: Record<string, any> = {}
  vm.runInNewContext(compile('../src/services/return-route.ts'), { exports: returnRoute, require: () => ({}) })
  const calls: string[] = []
  const exports: Record<string, any> = {}
  vm.runInNewContext(compile('../src/services/navigation.ts'), {
    exports,
    require: (id: string) => id === './return-route' ? returnRoute : id === 'vue' ? { reactive: (value: unknown) => value } : {},
    uni: {
      navigateTo: (options: any) => { calls.push('navigateTo ' + options.url) },
      redirectTo: (options: any) => { calls.push('redirectTo ' + options.url) },
      switchTab: (options: any) => { calls.push('switchTab ' + options.url) },
      navigateBack: (options: any = {}) => { calls.push('navigateBack ' + (options.delta || 1)); if (backFails) options.fail?.({ errMsg: 'navigateBack:fail' }) },
    },
    getCurrentPages: () => pages,
  })
  return { visit: exports.visitDestination as (target: string, replace?: boolean) => void, calls }
}

test('login returns to the paper page it came from without duplicating it', () => {
  const app = loadNavigation([
    { route: 'pages/home/index' },
    { route: 'pages/paper/index', options: { id: 'abc_123-45', scope: 'catalog' } },
    { route: 'pages/login/index', options: { returnTo: '%2Fpages%2Fpaper%2Findex%3Fid%3Dabc_123-45' } },
  ])
  app.visit('/pages/paper/index?id=abc_123-45', true)
  assert.deepEqual(app.calls, ['navigateBack 1'])
})

test('login returns to a search or request page with encoded parameters', () => {
  const app = loadNavigation([
    { route: 'pages/requests/index', options: { title: encodeURIComponent('分数应用题'), grade: encodeURIComponent('六年级') } },
    { route: 'pages/login/index' },
  ])
  app.visit('/pages/requests/index?title=' + encodeURIComponent('分数应用题') + '&grade=' + encodeURIComponent('六年级'), true)
  assert.deepEqual(app.calls, ['navigateBack 1'])
})

test('a different target still replaces the login page instead of popping the stack', () => {
  const app = loadNavigation([
    { route: 'pages/paper/index', options: { id: 'other-paper' } },
    { route: 'pages/login/index' },
  ])
  app.visit('/pages/paper/index?id=abc_123-45', true)
  assert.deepEqual(app.calls, ['redirectTo /pages/paper/index?id=abc_123-45'])
})

test('a login page opened as the only page cannot pop and falls back to replace', () => {
  const app = loadNavigation([{ route: 'pages/login/index' }])
  app.visit('/pages/paper/index?id=abc_123-45', true)
  assert.deepEqual(app.calls, ['redirectTo /pages/paper/index?id=abc_123-45'])
})

test('a failed pop still lands on the target page', () => {
  const app = loadNavigation([
    { route: 'pages/paper/index', options: { id: 'abc_123-45' } },
    { route: 'pages/login/index' },
  ], true)
  app.visit('/pages/paper/index?id=abc_123-45', true)
  assert.deepEqual(app.calls, ['navigateBack 1', 'redirectTo /pages/paper/index?id=abc_123-45'])
})

test('tab pages keep using switchTab and inbox jumps keep pushing', () => {
  const tab = loadNavigation([{ route: 'pages/library/index' }, { route: 'pages/login/index' }])
  tab.visit('/pages/library/index', true)
  assert.deepEqual(tab.calls, ['switchTab /pages/library/index'])
  const inbox = loadNavigation([{ route: 'pages/messages/index' }, { route: 'pages/paper/index', options: { id: 'abc' } }])
  inbox.visit('/pages/paper/index?id=abc')
  assert.deepEqual(inbox.calls, ['navigateTo /pages/paper/index?id=abc'])
})
