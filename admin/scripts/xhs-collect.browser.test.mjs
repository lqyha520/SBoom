/** 使用离线页面验证风控提示和停止条件，不访问真实小红书。 */
import assert from 'node:assert/strict'
import { afterEach, beforeEach, test } from 'node:test'
import { chromium } from '@playwright/test'
import { extractCards } from './xhs-collect.mjs'

let browser, page, visits
const task = { query: '测试', period: 'week', sort_by: 'popular', note_limit: 10 }
const filters = '<div class="filter">筛选<div class="filter-panel"><div class="filters">排序依据<div class="tag-container"><span class="tags active">最多点赞</span></div></div><div class="filters">发布时间<div class="tag-container"><span class="tags active">一周内</span></div></div></div></div>'
const cards = (title = '数学练习') => Array.from({ length: 10 }, (_, i) => `<section class="note-item" data-note-id="offline-${i}"><a class="title" href="/explore/offline-${i}">${title}</a></section>`).join('')
const offline = async html => page.route('**/*', route => {
  visits++
  return route.request().isNavigationRequest() ? route.fulfill({ contentType: 'text/html; charset=utf-8', body: `<meta charset="utf-8">${filters}${html}` }) : route.abort()
})
beforeEach(async () => {
  browser = await chromium.launch({ headless: true }); page = await browser.newPage(); visits = 0
  // 离线页面同步加载，测试无需等待真实网站的加载时间。
  page.waitForTimeout = async () => {}
})
afterEach(async () => { await browser?.close() })

test('非真人提示即使与笔记同时出现也停止，不进行筛选或滚动', async () => {
  await offline('<div role="alert">您的操作不符合真人操作习惯</div>' + cards())
  await assert.rejects(extractCards(page, task), error => error.code === 'account_restricted')
  assert.equal(visits, 1)
})

test('搜索笔记讨论账号异常不会误判；已采够数量不再滚动', async () => {
  await offline(cards('账号存在异常／部分功能受限，怎么申诉？') + '<script>window.scrollTo=()=>{ throw new Error("不应该再次滚动") }</script>')
  assert.equal((await extractCards(page, task)).length, 10)
  assert.equal(visits, 1)
})

test('滚动加载后出现平台限制立即停止，不返回部分结果或继续滚动', async () => {
  await offline(cards() + '<script>window.scrolls=0;window.scrollTo=()=>{window.scrolls++;const alert=document.createElement("div");alert.textContent="账号存在异常，部分功能受限";document.body.append(alert)}</script>')
  await assert.rejects(extractCards(page, { ...task, note_limit: 20 }), error => error.code === 'account_restricted')
  assert.equal(await page.evaluate(() => window.scrolls), 1)
})

test('取得卡片后新出现安全验证，也不能被当作采集成功', async () => {
  await offline(cards())
  await assert.rejects(extractCards(page, task, async stage => {
    if (stage === 'collecting') await page.evaluate(() => {
      const alert = document.createElement('div'); alert.textContent = '请完成安全验证'; document.body.append(alert)
    })
  }), error => error.code === 'verification')
})

test('HTTP 429 不作为普通网络失败，不继续加载或采集', async () => {
  await page.route('**/*', route => {
    visits++
    return route.fulfill({ status: 429, body: 'Too many requests' })
  })
  await assert.rejects(extractCards(page, task), error => error.code === 'restricted')
  assert.equal(visits, 1)
})

test('筛选操作超时时优先识别已出现的账号限制', async () => {
  await offline(cards())
  const original = page.locator.bind(page)
  page.locator = selector => {
    const locator = original(selector)
    if (selector === '.filter') locator.first = () => ({
      count: async () => 1,
      hover: async () => {
        await page.evaluate(() => {
          const alert = document.createElement('div'); alert.textContent = '您的账号存在异常'; document.body.append(alert)
        })
        throw new Error('hover: Timeout 5000ms exceeded')
      },
    })
    return locator
  }
  await assert.rejects(extractCards(page, task), error => error.code === 'account_restricted')
  assert.equal(visits, 1)
})

test('主页面无任何限制文字但数据请求被拒绝时停止，不仅检查导航状态', async () => {
  await offline(cards() + '<script>fetch("/api/search/notes")</script>')
  await page.route('**/api/**', route => route.fulfill({ status: 429, body: '{}' }))
  const response = page.waitForResponse(value => value.url().includes('/api/search/notes'))
  page.waitForTimeout = async () => { await response }
  await assert.rejects(extractCards(page, task), error => error.code === 'restricted')
  assert.equal(await page.locator('body').innerText().then(text => text.includes('账号异常')), false)
})

test('无提示且数据请求失败时保留原因不明，不推断账号已被风控', async () => {
  await offline(cards() + '<script>fetch("/api/search/notes").catch(()=>{})</script>')
  await page.route('**/api/**', route => route.abort('failed'))
  const failed = page.waitForEvent('requestfailed')
  page.waitForTimeout = async () => { await failed }
  await assert.rejects(extractCards(page, task), error => error.code === 'collection_uncertain' && error.message.includes('原因尚不明确'))
})

test('没有笔记与没有可见限制提示时暂停，不继续滚动或宣称账号受限', async () => {
  await offline('<script>window.scrollTo=()=>{throw new Error("不应继续滚动")}</script>')
  await assert.rejects(extractCards(page, task), error => error.code === 'collection_uncertain' && !error.message.includes('账号受限'))
  assert.equal(visits, 1)
})

test('第三方数据请求被拒绝不当成小红书账号限制', async () => {
  await offline(cards() + '<script>fetch("https://metrics.example.com/api/track",{mode:"no-cors"})</script>')
  await page.route('https://metrics.example.com/**', route => route.fulfill({ status: 429, body: '{}' }))
  const response = page.waitForResponse(value => value.url().includes('metrics.example.com'))
  page.waitForTimeout = async () => { await response }
  assert.equal((await extractCards(page, task)).length, 10)
})

test('页面主动取消旧搜索请求不会误判为访问失败', async () => {
  await offline(cards() + '<script>fetch("/api/search/notes").catch(()=>{})</script>')
  await page.route('**/api/**', route => route.abort('aborted'))
  const failed = page.waitForEvent('requestfailed')
  page.waitForTimeout = async () => { await failed }
  assert.equal((await extractCards(page, task)).length, 10)
})
