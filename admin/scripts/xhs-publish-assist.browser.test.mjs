/** 离线模拟官方页面，测试真实 Chromium 填写；所有网络请求拦截，不向小红书传输测试内容。 */
import assert from 'node:assert/strict'
import { after, before, beforeEach, afterEach, test } from 'node:test'
import { chromium } from '@playwright/test'
import { fillPublisherPage, validateAssistPayload } from './xhs-publish-assist.mjs'

let browser, context, page
const fixture = ({ existing = '', warning = '', duplicate = false, maximum = 2000 } = {}) => `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>隔离测试 · 辅助发布</title><style>body{font:18px sans-serif;margin:40px}button,input{font:inherit;margin:12px;padding:8px}.tiptap{white-space:pre-wrap;border:1px solid #ccc;padding:12px;min-height:100px}</style>
<h1>隔离测试 · 创作页面</h1><p>${warning}</p>
<button type="button" id="images">上传图文</button><button type="button" id="video">上传视频</button>
<input id="upload" type="file" multiple accept="image/png,image/jpeg,image/webp">${duplicate ? '<input type="file" accept="image/png" multiple>' : ''}
<form><div id="fields" ${existing ? '' : 'hidden'}><input placeholder="填写标题会有更多赞哦" maxlength="20" value="${existing}"><div role="textbox" class="tiptap" contenteditable="true" maxlength="${maximum}"></div></div>
<button type="submit" id="publish">发布</button><button type="submit">定时发布</button></form>
<script>window.events={uploads:[],clicks:[],submits:0};document.addEventListener('click',e=>{if(e.target.tagName==='BUTTON')events.clicks.push(e.target.textContent)});document.querySelector('form').onsubmit=e=>{e.preventDefault();events.submits++};
images.onclick=()=>upload.accept='image/png,image/jpeg,image/webp';video.onclick=()=>{upload.accept='video/mp4';upload.removeAttribute('multiple')};
upload.onchange=async()=>{events.uploads.push(await Promise.all([...upload.files].map(async f=>({name:f.name,type:f.type,bytes:[...new Uint8Array(await f.arrayBuffer())]}))));fields.hidden=false};</script></html>`
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64')
const payload = () => validateAssistPayload({ record_id: 'fixture-123', revision: 1, headline: '找规律练习', body: '先观察数字。\n再填写答案。\n\n#数学 #一年级', reviewed: true, account_confirmed: true, media_confirmed: true,
  media: [{ type: 'image/png', base64: png.toString('base64') }, { type: 'image/jpeg', base64: Buffer.from([255,216,255,224,0,1,2]).toString('base64') }] })
before(async () => { browser = await chromium.launch({ headless: true }) })
after(async () => { await browser?.close() })
beforeEach(async () => {
  context = await browser.newContext()
  await context.route('**/*', route => route.request().isNavigationRequest() ? route.fulfill({ contentType: 'text/html; charset=utf-8', body: fixture() }) : route.abort())
  page = await context.newPage()
  await page.goto('https://creator.xiaohongshu.com/publish/publish')
})
afterEach(async () => {
  const events = await page.evaluate(() => window.events)
  assert.equal(events.submits, 0, '不得提交任何发布表单')
  assert(!events.clicks.includes('发布') && !events.clicks.includes('定时发布'), '不得点击最终发布')
  await context.close()
})
test('真实浏览器按素材顺序上传并准确填入多行正文和话题，最终提交为零', async () => {
  let recorded = false
  await fillPublisherPage(page, payload(), async () => { recorded = true })
  assert(recorded)
  const events = await page.evaluate(() => window.events)
  assert.deepEqual(events.clicks, ['上传图文'])
  assert.deepEqual(events.uploads[0].map(file => file.name), ['01.png', '02.jpg'])
  assert.deepEqual(events.uploads[0][0].bytes, [...png])
  assert.equal(await page.locator('input[placeholder]').inputValue(), payload().headline)
  assert.equal(await page.locator('.tiptap').evaluate(el => [...el.childNodes].map(node => node.textContent).join('\n')), payload().body)
})
test('单视频选择视频入口，最终提交为零', async () => {
  const data = payload(); data.video = true; data.media = [{ name: '01.mp4', mimeType: 'video/mp4', buffer: Buffer.from([0,0,0,16,102,116,121,112,105,115,111,109,0,0,0,0]) }]
  await fillPublisherPage(page, data, async () => {})
  const events = await page.evaluate(() => window.events)
  assert.deepEqual(events.clicks, ['上传视频'])
  assert.equal(events.uploads[0][0].type, 'video/mp4')
})
test('官方侧栏同名入口和封面控件不干扰发布页的图文上传', async () => {
  const html = fixture()
    .replace('<button type="button" id="images">上传图文</button>', '<aside><div>上传图文</div></aside><div class="creator-tab"><span class="creator-tab"><span class="creator-tab">上传图文</span></span></div><div class="creator-tab" style="position:absolute;left:-9999px">上传图文</div><button type="button" id="images" hidden>上传图文</button>')
    .replace('<input id="upload"', '<input type="file" accept="image/png" aria-label="上传封面图片"><div class="upload-content"><div class="upload-area"><input id="upload"')
    .replace('<form>', '</div></div><form>')
    .replace('images.onclick=', "document.querySelector('.creator-tab').onclick=()=>{events.clicks.push('发布页图文模式');upload.accept='image/png'};images.onclick=")
  await page.setContent(html)
  await fillPublisherPage(page, payload(), async () => {})
  const events = await page.evaluate(() => window.events)
  assert.deepEqual(events.clicks, ['发布页图文模式'])
  assert.equal(events.uploads.length, 1)
  assert.equal(await page.getByLabel('上传封面图片').evaluate(el=>el.files.length), 0)
})
test('发布页存在两个同名模式时拒绝选择，不上传', async () => {
  await page.setContent(fixture().replace('<button type="button" id="images">上传图文</button>', '<div class="creator-tab"><span>上传图文</span></div><div class="creator-tab"><span>上传图文</span></div><button type="button" id="images" hidden>上传图文</button>'))
  await assert.rejects(fillPublisherPage(page, payload(), async()=>assert.fail('不得上传')), /上传入口/)
  assert.equal((await page.evaluate(()=>window.events)).uploads.length, 0)
})
test('已有文案时不切换模式、不覆盖、不上传', async () => {
  await page.setContent(fixture({ existing: '用户正在编辑' }))
  await assert.rejects(fillPublisherPage(page, payload(), async () => assert.fail('不得上传')), /已有内容/)
  assert.equal(await page.locator('input[placeholder]').inputValue(), '用户正在编辑')
  assert.deepEqual((await page.evaluate(() => window.events)).clicks, [])
})
test('未登录和非官方页面停止，不输入账号或验证码', async () => {
  await page.goto('https://creator.xiaohongshu.com/login')
  await assert.rejects(fillPublisherPage(page, payload(), async () => assert.fail('不得上传')), /手动登录/)
  await page.goto('https://example.invalid/publish/publish')
  await assert.rejects(fillPublisherPage(page, payload(), async () => assert.fail('不得上传')), /离开官方/)
})
test('出现安全验证时停止，不点击验证或上传', async () => {
  await page.setContent(fixture({ warning: '请完成验证' }))
  await assert.rejects(fillPublisherPage(page, payload(), async () => assert.fail('不得上传')), /验证/)
  assert.deepEqual((await page.evaluate(() => window.events)).clicks, [])
})
test('上传控件有歧义或页面标题改变时停止', async () => {
  await page.setContent(fixture({ duplicate: true }))
  await assert.rejects(fillPublisherPage(page, payload(), async () => assert.fail('不得上传')), /上传控件/)
  await page.setContent(fixture().replace('>上传图文<', '>新的上传入口<'))
  await assert.rejects(fillPublisherPage(page, payload(), async () => assert.fail('不得上传')), /上传入口/)
})
test('平台字数上限更小时不静默截断；保留已上传文件供人工处理', async () => {
  await page.setContent(fixture({ maximum: 10 }))
  await assert.rejects(fillPublisherPage(page, payload(), async () => {}), /字数上限/)
  assert.equal(await page.locator('input[placeholder]').inputValue(), '')
  assert.equal((await page.evaluate(() => window.events)).uploads.length, 1)
})
test('首次上传前持久记录失败则不上传', async () => {
  await assert.rejects(fillPublisherPage(page, payload(), async () => { throw new Error('磁盘写入失败') }), /磁盘写入失败/)
  assert.equal((await page.evaluate(() => window.events)).uploads.length, 0)
})
