import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import { parse } from 'vue/compiler-sfc'

type Template = NonNullable<ReturnType<typeof parse>['descriptor']['template']>
type Root = NonNullable<Template['ast']>
type TemplateNode = Root | Root['children'][number]

function vueFiles(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name)
    return entry.isDirectory() ? vueFiles(path) : entry.name.endsWith('.vue') ? [path] : []
  })
}

test('Wot v2 empty states keep their actions in supported named slots', () => {
  let checked = 0
  for (const path of vueFiles(fileURLToPath(new URL('../src/', import.meta.url)))) {
    const { descriptor, errors } = parse(readFileSync(path, 'utf8'), { filename: path })
    assert.equal(errors.length, 0, path)
    function visit(node: TemplateNode) {
      if (node.type === 1 && node.tag === 'wd-empty') {
        checked++
        for (const child of node.children) {
          if (child.type === 3 || (child.type === 2 && !child.content.trim())) continue
          assert.ok(child.type === 1 && child.tag === 'template', `${path}: Wot Empty ignores default-slot content`)
          assert.ok(child.props.some(prop => prop.type === 7 && prop.name === 'slot' &&
            prop.arg?.type === 4 && ['bottom', 'image'].includes(prop.arg.content)), `${path}: unsupported Wot Empty slot`)
        }
      }
      if (node.type === 0 || node.type === 1) node.children.forEach(visit)
    }
    if (descriptor.template?.ast) visit(descriptor.template.ast)
  }
  assert.ok(checked >= 4, 'Expected authenticated, catalog and detail empty states to be inspected')
})

test('consumer routes and UI do not expose workbench accounts or private spaces', () => {
  const root = new URL('../src/', import.meta.url)
  const pages = JSON.parse(readFileSync(new URL('pages.json', root), 'utf8'))
  for (const path of ['topic', 'messages', 'requests', 'closure', 'membership', 'orders']) assert.ok(pages.pages.some((page: { path: string }) => page.path === `pages/${path}/index`), path)
  assert.ok(!pages.pages.some((page: { path: string }) => /pages\/(private|folders)\//.test(page.path)))
  for (const file of ['pages/account/index.vue', 'pages/login/index.vue', 'pages/paper/index.vue', 'services/api.ts', 'services/session.ts']) {
    const source = readFileSync(new URL(file, root), 'utf8')
    assert.ok(!/私人习题|管理文件夹|关联已有工作台|\/api\/v1\/library\/|\/api\/v1\/auth\//.test(source), file)
  }
})

test('detail content and downloads are gated by server-provided permissions', () => {
  const source = readFileSync(new URL('../src/pages/paper/index.vue', import.meta.url), 'utf8')
  assert.ok(source.includes('v-if="verified && !paper.can_view"'))
  assert.ok(source.includes('if (!paper.value || !verified.value || loading.value || downloading.value) return'))
  assert.ok(source.includes('if (!paper.value.can_download)'))
  assert.ok(source.includes('await requestCatalogDownload(id.value, edition.value)'))
  assert.ok(!source.includes('fetchPaper('))
})

test('catalog rows remain renderable without an intersection observer callback', () => {
  const source = readFileSync(new URL('../src/components/CatalogList.vue', import.meta.url), 'utf8')
  const template = parse(source).descriptor.template!.content
  assert.ok(template.includes('<PaperRow v-for="paper in items"'))
  assert.ok(!template.includes('WindowSection'))
  assert.ok(!template.includes('pageVisible'))
})

test('custom page chrome is enabled on WeChat as well as H5', () => {
  const pages = JSON.parse(readFileSync(new URL('../src/pages.json', import.meta.url), 'utf8'))
  assert.equal(pages.globalStyle.navigationStyle, 'custom')
  assert.equal(pages.tabBar.list.length, 4)
  const tabbar = readFileSync(new URL('../src/components/AppTabBar.vue', import.meta.url), 'utf8')
  assert.ok(tabbar.includes('uni.switchTab'))
  assert.ok(tabbar.includes('tabBarObscured'))
  const login = readFileSync(new URL('../src/pages/login/index.vue', import.meta.url), 'utf8')
  assert.ok(login.includes('const agreed = ref(false)'))
  assert.ok(login.includes("provider: 'weixin'"))
  assert.ok(login.includes("request<Authenticated>('/api/v1/mini/login'"))
})

test('the reader and page chrome share one back button and keep zoom direction static', () => {
  const read = (file: string) => readFileSync(new URL('../src/' + file, import.meta.url), 'utf8')
  assert.ok(read('components/ChromeBack.vue').includes('name="arrow-left"'), 'ChromeBack must render the standard arrow icon')
  for (const host of ['components/PageChrome.vue', 'components/PaperPreview.vue']) {
    const source = read(host)
    assert.ok(source.includes("import ChromeBack from './ChromeBack.vue'"), host + ' must reuse the shared back button')
    assert.ok(source.includes('<ChromeBack'), host + ' must render the shared back button')
    assert.ok(!/class="[^"]*chrome-back/.test(source), host + ' must not inline its own back button')
    // 自定义组件的事件名不能和原生事件同名：叫 tap 时，`$emit('tap')` 和内部 <button>
    // 冒泡到组件节点上的原生 tap 会命中同一个 bindtap，一次点击跑两遍处理函数，
    // 返回一次退了两级（反馈页返回直接落到列表页，详情页被一起弹掉）。
    assert.ok(/<ChromeBack[^>]*@press=/.test(source), host + ' must bind the custom press event')
    assert.ok(!/<ChromeBack[^>]*@(tap|click)=/.test(source), host + ' must not bind a native event name on the back button')
  }
  const back = read('components/ChromeBack.vue')
  assert.ok(back.includes('defineEmits<{ press: [] }>()'), 'ChromeBack must declare a non-native event name')
  // 只看模板，注释里提到历史写法是允许的。
  const backTemplate = back.slice(back.indexOf('</script>'))
  assert.ok(backTemplate.includes("$emit('press')"), 'ChromeBack must emit press')
  assert.ok(!backTemplate.includes("$emit('tap')"), 'ChromeBack must not emit tap: it double-fires with the native event')
  const preview = read('components/PaperPreview.vue')
  // 动态改 direction 会在双指缩放中途打断 movable-view 的手势，表现为放大后拖不动
  assert.ok(preview.includes('direction="all"'), 'movable-view must keep a static direction')
  assert.ok(!/:direction=/.test(preview), 'movable-view direction must not be bound dynamically')
})

test('the reader header uses the total bar height and tab pages always keep the top inset', () => {
  const read = (file: string) => readFileSync(new URL('../src/' + file, import.meta.url), 'utf8')
  const preview = read('components/PaperPreview.vue')
  // chromeBar().height 已经包含状态栏；header 用 padding-top 顶出状态栏 + border-box，
  // 再写 navigationTop + navigationHeight 就会把状态栏算两遍、标题栏偏高。
  assert.ok(preview.includes("height: navigationHeight + 'px'"), 'the reader header must use the total bar height')
  assert.ok(!preview.includes('navigationTop + navigationHeight'), 'the status bar must not be counted twice')
  // 首页/我的/资料库(tab 态) 没有返回按钮，但仍必须让出状态栏+胶囊的高度，
  // 否则内容会顶到最上面被系统区域挡住。
  const chrome = read('components/PageChrome.vue')
  assert.ok(chrome.includes('height.value = bar.height'), 'page chrome must reserve the bar height')
  assert.ok(!chrome.includes('props.back ? bar.height'), 'reserving the bar height must not depend on the back button')
})

test('static Wot button and icon names exist in the installed icon font', () => {
  const font = readFileSync(new URL('../node_modules/@wot-ui/ui/components/wd-icon/iconfont.scss', import.meta.url), 'utf8')
  const icons = new Set(Array.from(font.matchAll(/\.wd-icon-([\w-]+):before/g), match => match[1]))
  for (const path of vueFiles(fileURLToPath(new URL('../src/', import.meta.url)))) {
    const { descriptor } = parse(readFileSync(path, 'utf8'), { filename: path })
    function visit(node: TemplateNode) {
      if (node.type === 1 && ['wd-icon', 'wd-button', 'wd-cell'].includes(node.tag)) {
        const names = node.tag === 'wd-icon' ? ['name'] : ['icon', 'prefix-icon', 'suffix-icon']
        for (const prop of node.props) {
          if (prop.type === 6 && names.includes(prop.name) && prop.value) {
            assert.ok(icons.has(prop.value.content), path + ': unsupported icon ' + prop.value.content)
          }
        }
      }
      if (node.type === 0 || node.type === 1) node.children.forEach(visit)
    }
    if (descriptor.template?.ast) visit(descriptor.template.ast)
  }
})

test('sign-out confirmation stays above settings and gates the logout request', () => {
  const source = readFileSync(new URL('../src/pages/account/index.vue', import.meta.url), 'utf8')
  const { descriptor } = parse(source)
  let settingsLayer = 0
  let logoutLayer = 0
  function visit(node: TemplateNode) {
    if (node.type === 1 && node.tag === 'wd-popup') {
      const model = node.props.find(prop => prop.type === 7 && prop.name === 'model')
      const layer = node.props.find(prop => prop.type === 7 && prop.name === 'bind' && prop.arg?.type === 4 && prop.arg.content === 'z-index')
      if (model?.type === 7 && model.exp?.type === 4 && layer?.type === 7 && layer.exp?.type === 4) {
        if (model.exp.content === 'settingsOpen') settingsLayer = Number(layer.exp.content)
        if (model.exp.content === 'logoutOpen') logoutLayer = Number(layer.exp.content)
      }
    }
    if (node.type === 0 || node.type === 1) node.children.forEach(visit)
  }
  if (descriptor.template?.ast) visit(descriptor.template.ast)
  assert.ok(settingsLayer > 0 && logoutLayer > settingsLayer)
  assert.ok(source.includes('busy.value || !logoutOpen.value || !session.user'))
  assert.ok(!source.includes('confirmAction'))
})
