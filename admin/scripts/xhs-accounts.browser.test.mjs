/** 用隔离测试目录和离线页面验证真实 Chromium 的多账号存储隔离，不登录或访问真实小红书。 */
import assert from 'node:assert/strict'
import { afterEach, beforeEach, test } from 'node:test'
import { mkdtemp, rm } from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'
import { chromium } from '@playwright/test'
import { createXhsAccounts } from './xhs-accounts.mjs'
import { extractCards } from './xhs-collect.mjs'

let folder, service, launched
const origin = 'https://localhost'
const fixture = '<!doctype html><meta charset="utf-8"><title>离线账号隔离测试</title><h1>隔离测试页面</h1><button type="button">上传图文</button><input id="file" type="file" accept="image/png" multiple><div id="editor" hidden><input placeholder="填写标题"><div role="textbox" class="tiptap" contenteditable="true"></div></div><script>file.onchange=()=>setTimeout(()=>editor.hidden=false,800)</script>'
beforeEach(async () => {
  folder = await mkdtemp(path.join(os.tmpdir(), 'lc-account-browser-')); launched = []
  service = createXhsAccounts({ rootDir: folder, launch: async (directory, options) => {
    assert.equal(options.headless, false, '产品必须打开可见窗口')
    const context = await chromium.launchPersistentContext(directory, { ...options, headless: true })
    await context.route('**/*', route => route.request().isNavigationRequest() ? route.fulfill({ contentType: 'text/html; charset=utf-8', body: fixture }) : route.abort())
    launched.push({ directory, context }); return context
  } })
})
afterEach(async () => { await service?.shutdown(); await rm(folder, { recursive: true, force: true }) })
const add = async (name, request_id) => (await service.add(origin, { name, note: '', request_id })).account
const pageFor = context => context.pages().find(page => page.url().startsWith('https://www.xiaohongshu.com/'))

test('查看笔记新标签复用所选账号登录环境和完整链接，不覆盖原页或影响其他账号', async () => {
  const a = await add('账号 A', 'request-note-a'), b = await add('账号 B', 'request-note-b')
  await service.open(origin, { account_id: a.id }); await service.open(origin, { account_id: b.id })
  const ca = launched[0].context, cb = launched[1].context, original = pageFor(ca)
  await original.evaluate(() => { localStorage.setItem('note-account', 'A'); document.querySelector('h1').textContent = '原页面的未保存内容' })
  await pageFor(cb).evaluate(() => localStorage.setItem('note-account', 'B'))
  const originalUrl = original.url(), bPages = cb.pages().length
  const url = 'https://www.xiaohongshu.com/search_result/65abcdef0123456789abcdef?xsec_token=fixture-token&xsec_source=pc_search'
  await service.openNote(origin, { account_id: a.id, url })
  const page = ca.pages().at(-1)
  assert.equal(launched.length, 2)
  assert.equal(page.url(), url)
  assert.equal(await page.evaluate(() => localStorage.getItem('note-account')), 'A')
  assert.equal(original.url(), originalUrl)
  assert.equal(await original.locator('h1').textContent(), '原页面的未保存内容')
  assert.equal(cb.pages().length, bPages)
  assert.equal(await pageFor(cb).evaluate(() => localStorage.getItem('note-account')), 'B')
})

test('A/B 的 Cookie、localStorage、IndexedDB、缓存隔离；重开 A 恢复原数据，B 不受影响', async () => {
  const a = await add('账号 A', 'request-account-a'), b = await add('账号 B', 'request-account-b')
  await service.open(origin, { account_id: a.id }); await service.open(origin, { account_id: b.id })
  const ca = launched[0].context, cb = launched[1].context, pa = pageFor(ca), pb = pageFor(cb)
  assert.notEqual(launched[0].directory, launched[1].directory)
  await ca.addCookies([{ name: 'lc_fixture', value: 'account-a-only', domain: 'www.xiaohongshu.com', path: '/', expires: Math.floor(Date.now()/1000)+3600, secure: true }])
  await pa.evaluate(async () => {
    localStorage.setItem('account-fixture', 'A')
    await new Promise((resolve, reject) => {
      const request = indexedDB.open('account-fixture', 1)
      request.onupgradeneeded = () => request.result.createObjectStore('data')
      request.onerror = () => reject(request.error)
      request.onsuccess = () => { const db = request.result, tx = db.transaction('data', 'readwrite'); tx.objectStore('data').put('A','owner'); tx.oncomplete = () => { db.close(); resolve() } }
    })
    await (await caches.open('account-fixture')).put('/fixture-only', new Response('A'))
  })
  assert.equal((await cb.cookies()).length, 0)
  assert.deepEqual(await pb.evaluate(async () => ({ local: localStorage.getItem('account-fixture'), dbs: (await indexedDB.databases()).map(db=>db.name), caches: await caches.keys() })), { local: null, dbs: [], caches: [] })
  const count = ca.pages().length
  await pa.locator('h1').evaluate(el => el.textContent = 'A 正在编辑的页面')
  await service.open(origin, { account_id: a.id })
  assert.equal(launched.length, 2); assert.equal(ca.pages().length, count)
  assert.equal(await pa.locator('h1').innerText(), 'A 正在编辑的页面')
  await service.close(origin, { account_id: a.id, acknowledged: true })
  assert.equal(pb.isClosed(), false)
  await service.open(origin, { account_id: a.id })
  const restored = launched[2].context
  assert.equal(launched[2].directory, launched[0].directory)
  assert.equal((await restored.cookies()).find(cookie=>cookie.name==='lc_fixture').value, 'account-a-only')
  assert.equal(await pageFor(restored).evaluate(()=>localStorage.getItem('account-fixture')), 'A')
  assert.deepEqual(await pageFor(restored).evaluate(async()=>({dbs:(await indexedDB.databases()).map(db=>db.name),caches:await caches.keys()})),{dbs:['account-fixture'],caches:['account-fixture']})
  assert.equal((await cb.cookies()).length, 0)
})
test('辅助发布复用选中账号的浏览器；填入期间拒绝关闭或归档，不影响另一个账号', async () => {
  const a = await add('辅助账号', 'request-publish-a'), b = await add('另一个账号', 'request-publish-b')
  await service.open(origin, { account_id: a.id }); await service.open(origin, { account_id: b.id })
  const body = { record_id: 'publication-fixture', revision: 1 }
  const opened = await service.publication(origin, a.id, 'open', body)
  assert.equal(launched.length, 2)
  await service.publication(origin, a.id, 'prepare', { ...body, token: opened.session.token, headline: '隔离测试', body: '内容', reviewed: true, media_confirmed: true, account_confirmed: true, media: [{ type:'image/png',base64:'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=' }] })
  await assert.rejects(service.close(origin, { account_id: a.id, acknowledged: true }), /正在辅助/)
  await assert.rejects(service.collect(origin, a.id, { query: '测试' }, async () => []), /正在辅助/)
  await assert.rejects(service.update(origin, { account_id: a.id, revision: a.revision, name: a.name, note: '', archived: true }), /关闭/)
  await service.open(origin, { account_id: b.id })
  const publishPage = launched[0].context.pages().at(-1)
  await publishPage.locator('.tiptap').waitFor({ state: 'visible' })
  for (let attempt=0; attempt<30; attempt++) {
    if (!(await service.publication(origin,a.id,'state')).busy) break
    await new Promise(resolve=>setTimeout(resolve,100))
  }
  assert.equal((await service.publication(origin,a.id,'state')).session.status, 'prepared')
  assert.equal(await publishPage.locator('input[placeholder]').inputValue(), '隔离测试')
  const preview = await service.publication(origin, a.id, 'preview')
  assert.equal(Buffer.from(preview.image, 'base64').subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10])), true)
  assert.equal(preview.controls.uploads.length, 1)
  await assert.rejects(service.publication('https://untrusted.example', a.id, 'preview'), /属于其他/)
  assert.equal(launched[1].context.pages().some(page=>new URL(page.url()).hostname==='creator.xiaohongshu.com'), false)
})

test('采集与账号管理复用登录环境，保留发布页，阻止同账号关闭和发布；其他账号不受影响', async () => {
  const a = await add('采集账号', 'request-collect-a'), b = await add('另一账号', 'request-collect-b')
  await service.open(origin, { account_id: a.id })
  await service.publication(origin, a.id, 'open', { record_id: 'publication-research', revision: 1 })
  const context = launched[0].context, original = context.pages().slice(), publishPage = original.at(-1)
  await pageFor(context).evaluate(() => localStorage.setItem('research-fixture-account', 'A'))
  await publishPage.locator('h1').evaluate(el => el.textContent = '发布页面未保存的内容')
  let unlock, entered
  const gate = new Promise(resolve => { unlock = resolve }), ready = new Promise(resolve => { entered = resolve })
  const task = { query: '一年级数学', period: 'week', sort_by: 'popular', note_limit: 10 }
  const cards = Array.from({ length: 10 }, (_, i) => `<section class="note-item" data-note-id="offline-${i}"><a class="title" href="/explore/offline-${i}">笔记 ${i}</a><span class="name">老师</span><span class="like-wrapper"><span class="count">20</span></span></section>`).join('')
  const filters = '<div class="filter">筛选<div class="filter-panel"><div class="filters">排序依据<div class="tag-container"><span class="tags active">最多点赞</span></div></div><div class="filters">发布时间<div class="tag-container"><span class="tags active">一周内</span></div></div></div></div>'
  await context.route('**/search_result/**', route => route.fulfill({ contentType: 'text/html; charset=utf-8', body: `<!doctype html><meta charset="utf-8">${filters}${cards}` }))
  let searchPage
  const running = service.collect(origin, a.id, task, async page => {
    searchPage = page; entered(); await gate
    const notes = await extractCards(page, task)
    assert.equal(await page.evaluate(() => localStorage.getItem('research-fixture-account')), 'A')
    return notes
  })
  await ready
  try {
    await assert.rejects(service.close(origin, { account_id: a.id, acknowledged: true }), /正在/)
    await assert.rejects(service.update(origin, { account_id: a.id, revision: a.revision, name: a.name, note: '', archived: true }), /正在/)
    await assert.rejects(service.publication(origin, a.id, 'open', { record_id: 'other-record', revision: 1 }), /正在/)
    await service.open(origin, { account_id: b.id })
    assert.equal(launched.length, 2)
  } finally { unlock() }
  assert.equal((await running).length, 10)
  assert.equal(searchPage.isClosed(), true)
  assert.equal(original.some(page => page.isClosed()), false)
  assert.equal(await publishPage.locator('h1').innerText(), '发布页面未保存的内容')
})

test('登录失败保留搜索现场；重试仍用原账号；被用户导航的标签页不关闭', async () => {
  const a = await add('登录测试', 'request-login-a')
  await service.open(origin, { account_id: a.id })
  const context = launched[0].context, task = { query: '测试', period: 'week', sort_by: 'popular', note_limit: 10 }
  await context.route('**/search_result/**', route => route.fulfill({ contentType: 'text/html; charset=utf-8', body: '<meta charset="utf-8">扫码登录' }))
  await assert.rejects(service.collect(origin, a.id, task, page => extractCards(page, task)), /登录已失效/)
  const failedPage = context.pages().at(-1)
  assert.match(failedPage.url(), /search_result/)
  assert.equal(failedPage.isClosed(), false)
  assert.equal((await service.list(origin)).items[0].busy, false)
  await service.open(origin, { account_id: a.id })
  await service.collect(origin, a.id, task, async page => { await page.goto('https://creator.xiaohongshu.com/'); return [] })
  assert.equal(context.pages().at(-1).isClosed(), false)
  assert.equal(launched.length, 1)
})
