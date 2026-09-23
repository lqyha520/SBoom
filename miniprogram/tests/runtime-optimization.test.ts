import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import * as vue from 'vue'
import { compileScript, parse } from 'vue/compiler-sfc'
import { createBannerImages } from '../src/services/banner-images'

const compile = (source: string) => ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText
const settle = async () => { for (let i = 0; i < 12; i++) await Promise.resolve() }

test('真实编译的图片组件默认显示，显式隐藏后释放，再次显示重新加载', async () => {
  let acquired = 0, released = 0
  const descriptor = parse(readFileSync(new URL('../src/components/PrivateImage.vue', import.meta.url), 'utf8')).descriptor
  const exports: any = {}
  vm.runInNewContext(compile(compileScript(descriptor, { id: 'private-image-default' }).content), {
    exports,
    require: (name: string) => name === 'vue' ? vue : {
      acquireAsset: () => { acquired++; return { ready: Promise.resolve('/temporary'), release: () => { released++ } } },
    },
  })
  const component = exports.default
  component.render = () => null
  const renderer = vue.createRenderer<any, any>({
    insert() {}, remove() {}, createElement: () => ({}), createText: () => ({}), createComment: () => ({}),
    setText() {}, setElementText() {}, parentNode: () => null, nextSibling: () => null, patchProp() {},
  })
  const props = vue.reactive<{ src: string; active?: boolean }>({ src: '/private-preview' })
  const app = renderer.createApp({ render: () => vue.h(component, props) })
  app.mount({})
  try {
    await settle(); assert.equal(acquired, 1, '详情页未传 active 时也应加载图片')
    props.active = false; await settle(); assert.equal(released, 1)
    props.active = true; await settle(); assert.equal(acquired, 2)
  } finally { app.unmount() }
  assert.equal(released, 2)
})

test('首页隐藏时释放 Banner 图片，重新显示时重新获取，卸载不重复释放', async () => {
  const props = vue.reactive({ active: true, banners: [{ id: 'one', image_url: '/one' }, { id: 'two', image_url: '/two' }] })
  let acquired = 0, released = 0, dispose!: () => void
  const scope = vue.effectScope()
  const source = parse(readFileSync(new URL('../src/components/HomeBanner.vue', import.meta.url), 'utf8')).descriptor.scriptSetup!.content
  scope.run(() => vm.runInNewContext(compile(source), {
    exports: {}, defineProps: () => props, withDefaults: (value: unknown) => value,
    require: (id: string) => id === 'vue' ? { ...vue, onUnmounted: (fn: () => void) => { dispose = fn } }
      : id === '../services/banner-images' ? { createBannerImages }
      : id === '../services/assets' ? { acquireAsset: () => { acquired++; return { ready: Promise.resolve('/temporary'), release: () => { released++ } } } } : {},
  }))
  try {
    await settle(); assert.equal(acquired, 2)
    props.active = false; await settle(); assert.equal(released, 2)
    props.banners = [{ id: 'new', image_url: '/new' }]; await settle(); assert.equal(acquired, 2)
    props.active = true; await settle(); assert.equal(acquired, 3)
    dispose(); assert.equal(released, 3)
  } finally { scope.stop() }
})

test('runtime reconnects once, updates only with confirmation, and diagnostics never retain arbitrary content', () => {
  const handlers: Record<string, Function> = {}, emitted: string[] = []
  let saved: unknown, applied = 0, modal: any, initialNetwork: any
  const exports: any = {}
  vm.runInNewContext(compile(readFileSync(new URL('../src/services/runtime.ts', import.meta.url), 'utf8')), {
    exports,
    uni: {
      getStorageSync: () => [{ kind: 'runtime', minute: 1, count: 1, token: 'SECRET' }],
      setStorageSync: (_key: string, value: unknown) => { saved = value },
      $on: (name: string, fn: Function) => { handlers[name] = fn },
      $emit: (name: string) => emitted.push(name),
      onNetworkStatusChange: (fn: Function) => { handlers.network = fn },
      getNetworkType: (options: any) => { initialNetwork = options },
      onMemoryWarning: (fn: Function) => { handlers.memory = fn },
      canIUse: () => true,
      getUpdateManager: () => ({ onUpdateReady: (fn: Function) => { handlers.update = fn }, onUpdateFailed: (fn: Function) => { handlers.failed = fn }, applyUpdate: () => { applied++ } }),
      showModal: (options: any) => { modal = options }, showToast() {},
    },
  })
  exports.initializeRuntime(); exports.initializeRuntime()
  handlers.network!({ isConnected: false })
  initialNetwork.success({ networkType: 'wifi' }) // A stale startup response must not undo the offline event.
  assert.equal(emitted.filter(x => x === 'lc-network-restored').length, 0)
  handlers.network!({ isConnected: true }); handlers.network!({ isConnected: true })
  assert.equal(emitted.filter(x => x === 'lc-network-restored').length, 1)
  handlers.update!(); modal.success({ confirm: false }); assert.equal(applied, 0)
  handlers.update!(); modal.success({ confirm: true }); assert.equal(applied, 1)
  for (let i = 0; i < 2000; i++) exports.recordDiagnostic('network')
  exports.recordDiagnostic('https://secret.example/?token=SECRET')
  assert.ok(!exports.diagnosticSummary().includes('SECRET'))
  assert.ok(!JSON.stringify(saved).includes('SECRET'))
  const diagnostic = JSON.parse(exports.diagnosticSummary())
  assert.ok(diagnostic.events.length <= 40)
  assert.equal(diagnostic.events.find((x: any) => x.kind === 'network').count, 999)
})

test('lazy images release downloaded files offscreen and reacquire before reentry', async () => {
  let mounted!: Function, dispose!: Function, observe!: Function
  let acquired = 0, released = 0
  const props = vue.reactive({ src: '/private-image', lazy: true, active: true })
  const scope = vue.effectScope()
  const exports: any = {}
  const source = parse(readFileSync(new URL('../src/components/PrivateImage.vue', import.meta.url), 'utf8')).descriptor.scriptSetup!.content
  scope.run(() => vm.runInNewContext(compile(source + '\nexports.state = { source, visible };'), {
    exports, defineProps: () => props, withDefaults: (value: unknown) => value,
    require: (name: string) => name === 'vue'
      ? { ...vue, getCurrentInstance: () => ({ proxy: {} }), onMounted: (fn: Function) => { mounted = fn }, onUnmounted: (fn: Function) => { dispose = fn } }
      : { acquireAsset: () => { acquired++; return { ready: Promise.resolve('/temporary'), release: () => { released++ } } } },
    uni: { createIntersectionObserver: () => ({ disconnect() {}, relativeToViewport() { return this }, observe(_selector: string, fn: Function) { observe = fn } }) },
  }))
  try {
    mounted(); assert.equal(acquired, 0)
    observe({ intersectionRatio: 1 }); await settle()
    assert.equal(acquired, 1); assert.equal(exports.state.source.value, '/temporary')
    observe({ intersectionRatio: 0 }); await settle()
    assert.equal(released, 1); assert.equal(exports.state.source.value, '')
    observe({ intersectionRatio: 1 }); await settle()
    assert.equal(acquired, 2); assert.equal(exports.state.source.value, '/temporary')
    props.active = false; await settle()
    assert.equal(released, 2); assert.equal(exports.state.source.value, '')
    props.active = true; await settle()
    assert.equal(acquired, 3); assert.equal(exports.state.source.value, '/temporary')
    dispose(); assert.equal(released, 3)
  } finally { scope.stop() }
})
