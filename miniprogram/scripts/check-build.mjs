import assert from 'node:assert/strict'
import { readdir, readFile, stat } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawnSync } from 'node:child_process'
import { loadEnv } from 'vite'

const project = fileURLToPath(new URL('../', import.meta.url))
const output = process.env.UNI_OUTPUT_DIR ? path.resolve(process.env.UNI_OUTPUT_DIR) : path.join(project, 'dist/build/mp-weixin')
const wxssCompiler = process.env.WECHAT_WCSC_PATH
let wxssCount = 0
const json = async file => JSON.parse(await readFile(file, 'utf8'))
const app = await json(path.join(output, 'app.json'))
const config = await json(path.join(output, 'project.config.json'))
const manifest = await json(path.join(project, 'src/manifest.json'))
const pages = await json(path.join(project, 'src/pages.json'))

assert.equal(config.compileType, 'miniprogram')
assert.equal(config.setting.urlCheck, true, 'Legal-domain verification must stay enabled')
assert.deepEqual(app.pages, pages.pages.map(page => page.path), 'All configured pages must be built')
assert.equal(app.pages[0], 'pages/home/index', 'The standalone home page must be the launch page')
assert.ok(!app.pages.some(page => /pages\/(private|folders)\//.test(page)), 'Consumer apps must not ship private workspace pages')
assert.equal(app.tabBar.list[0].pagePath, app.pages[0], 'The first tab must point to the home page')
assert.equal(app.tabBar.list[1].text, '习题库', 'The public tab must use exercise terminology')
assert.equal(app.window.navigationStyle, 'custom', 'Custom navigation must also apply to WeChat')
assert.ok(app.tabBar.list.length <= 5, 'WeChat supports at most five native tabs')
const allPages = [...app.pages, ...(app.subPackages || []).flatMap(pkg => pkg.pages.map(page => pkg.root + '/' + page))]
assert.equal(allPages.length, pages.pages.length + (pages.subPackages || []).flatMap(pkg => pkg.pages).length)
for (const page of allPages) {
  for (const extension of ['.js', '.json', '.wxml', '.wxss']) await stat(path.join(output, page + extension))
}
await stat(path.join(output, 'app.wxss'))
const banner = await readFile(path.join(output, 'static/banners/study.jpg'))
assert.deepEqual([...banner.subarray(0, 3)], [0xff, 0xd8, 0xff], 'The home banner must ship as a valid JPEG')
assert.ok(banner.length < 150 * 1024, 'Keep the local banner within its asset budget')
const notebook = await readFile(path.join(output, 'static/illustrations/notebook.png'))
assert.equal(notebook.subarray(1, 4).toString(), 'PNG', 'The approved notebook must ship as a local PNG')
assert.ok(notebook.length < 30 * 1024, 'Keep the illustration within its asset budget')
for (const component of ['AppTabBar', 'PageChrome', 'MembershipSheet']) {
  await stat(path.join(output, 'components', component + '.wxml'))
}
const notices = await readFile(path.join(output, 'static/THIRD_PARTY_NOTICES.txt'), 'utf8')
assert.ok(notices.includes('2023 weisheng') && notices.includes('Unsplash') && notices.includes('3dicons'), 'Ship all UI and image license notices')
const detail = await json(path.join(output, 'pages/paper/index.json'))
assert.ok(!('question-read' in (detail.usingComponents || {})), 'Do not reintroduce a separate reading mode')
for (const item of app.tabBar.list) {
  assert.ok(app.pages.includes(item.pagePath))
  for (const icon of [item.iconPath, item.selectedIconPath]) {
    const bytes = await readFile(path.join(output, icon))
    assert.equal(bytes.subarray(1, 4).toString(), 'PNG', `Missing PNG tab icon: ${icon}`)
    assert.ok(bytes.length < 40 * 1024, `Tab icon too large: ${icon}`)
  }
  const selectedIcon = item.iconPath.replace(/\.png$/, '-selected.png')
  const selectedBytes = await readFile(path.join(output, selectedIcon))
  assert.equal(selectedBytes.subarray(1, 4).toString(), 'PNG', `Missing custom tab icon: ${selectedIcon}`)
  assert.ok(selectedBytes.length < 40 * 1024, `Custom tab icon too large: ${selectedIcon}`)
}

let size = 0, mainSize = 0
let count = 0
async function inspect(directory) {
  for (const item of await readdir(directory, { withFileTypes: true })) {
    const file = path.join(directory, item.name)
    if (item.isDirectory()) { await inspect(file); continue }
    const bytes = (await stat(file)).size
    size += bytes
    if (!path.relative(output, file).startsWith('subpages' + path.sep)) mainSize += bytes
    count++
    if (/\.(js|json|wxml)$/.test(item.name)) {
      assert.ok(!/learning\s+coach/i.test(await readFile(file, 'utf8')), `Removed branding in ${path.relative(output, file)}`)
    }
    if (item.name.endsWith('.wxss')) {
      const styles = (await readFile(file, 'utf8')).replace(/\/\*[\s\S]*?\*\//g, '')
      // WXSS rejects bare pseudo-classes after a combinator (for example
      // `.row > :last-child`), even when the uni-app build accepts the CSS.
      assert.ok(!/[>+~]\s*:(?!:)/.test(styles), `Unsupported bare pseudo-class in ${path.relative(output, file)}; use an explicit class selector`)
      if (wxssCompiler) {
        const compiled = spawnSync(wxssCompiler, ['-lc', '-o', process.platform === 'win32' ? 'NUL' : '/dev/null', path.relative(output, file)], {
          cwd: output, encoding: 'utf8', windowsHide: true, timeout: 15000,
        })
        assert.ok(!compiled.error && compiled.status === 0, `WXSS compiler rejected ${path.relative(output, file)}: ${compiled.error?.message || compiled.stderr || compiled.stdout}`)
      }
      wxssCount++
    }
    if (item.name.endsWith('.json')) {
      const value = await json(file)
      for (const component of Object.values(value.usingComponents || {})) {
        assert.equal(typeof component, 'string')
        if (component.startsWith('plugin://')) continue
        const target = component.startsWith('/') ? path.join(output, component.slice(1)) : path.resolve(directory, component)
        assert.ok(!path.relative(output, target).startsWith('..'), 'Component escapes the package')
        await stat(target + '.json')
        await stat(target + '.wxml')
      }
    }
  }
}
await inspect(output)
assert.ok(mainSize < 2 * 1024 * 1024, 'The main package must remain below 2 MiB')
const assets = await readFile(path.join(output, 'services/assets.js'), 'utf8')
assert.ok(assets.includes('openDocument'), 'WeChat must use the native PDF viewer')
assert.ok(!assets.includes('document.createElement'), 'H5-only PDF code leaked into WeChat')
const login = await readFile(path.join(output, 'pages/login/index.wxml'), 'utf8')
assert.ok(!login.includes('placeholder="密码"'), 'The H5 password form leaked into WeChat')
assert.ok(!login.includes('绑定'), 'Consumer login must not offer workbench binding')
const loginCode = await readFile(path.join(output, 'pages/login/index.js'), 'utf8')
assert.ok(loginCode.includes('微信一键登录'), 'The mini-program must keep the real WeChat login entry')
assert.ok(loginCode.includes('/api/v1/mini/login'), 'WeChat login must use the independent consumer endpoint')
assert.ok(!loginCode.includes('login-password'), 'Do not ship H5 account login logic into WeChat')

const release = process.argv.includes('--release')
const env = loadEnv('production', project, 'VITE_')
if (release) {
  assert.match(manifest['mp-weixin'].appid, /^wx[0-9a-f]{16}$/i, 'Set the real mp-weixin AppID in src/manifest.json')
  assert.equal(config.appid, manifest['mp-weixin'].appid, 'Rebuild after changing the AppID')
  const base = (env.VITE_API_BASE_URL || '').trim()
  assert.ok(base, 'Set VITE_API_BASE_URL (miniprogram/.env.production.local) to the public HTTPS API origin before running check:release')
  const origin = new URL(base)
  assert.equal(origin.protocol, 'https:', 'A public HTTPS API origin is required')
  assert.ok(!origin.username && !origin.password && !origin.search && !origin.hash && origin.pathname === '/', 'Use an API origin without credentials, paths or query strings')
  assert.ok(!/^(localhost|127\.|\[?::1\]?$)/i.test(origin.hostname), 'Loopback origins cannot be used by devices')
  const api = await readFile(path.join(output, 'services/api.js'), 'utf8')
  assert.ok(api.includes(origin.origin), 'Rebuild after changing the API origin')
}
console.log(`WeChat package OK: ${count} files, ${(mainSize / 1024).toFixed(1)} KiB main / 2048 KiB; ${(size / 1024).toFixed(1)} KiB total.`)
if (wxssCompiler) console.log(`WeChat stylesheet compiler OK: ${wxssCount} WXSS files.`)
if (!release) console.log('Structural checks only. Run check:release after configuring the AppID and HTTPS origin; device testing is still required.')
