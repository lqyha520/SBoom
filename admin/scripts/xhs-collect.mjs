const periodLabels = { day: '一天内', week: '一周内', half_year: '半年内', all: '不限' }
const sortLabels = { general: '综合', popular: '最多点赞', latest: '最新' }

export class XhsAccessError extends Error {
  constructor(code, message) { super(message); this.code = code }
}

const dataRequestErrors = new WeakMap()
function isPlatformDataRequest(request) {
  if (!['xhr', 'fetch'].includes(request.resourceType())) return false
  try {
    const url = new URL(request.url())
    return (url.hostname === 'xiaohongshu.com' || url.hostname.endsWith('.xiaohongshu.com')) &&
      url.pathname.startsWith('/api/') && /\/search(?:\/|$)/.test(url.pathname)
  } catch { return false }
}

async function assertPageAccess(currentPage) {
  const dataError = dataRequestErrors.get(currentPage)
  if (dataError) throw dataError
  const pageText = await currentPage.locator('body').innerText({ timeout: 5000 })
  const cardTexts = await currentPage.locator('section.note-item').allInnerTexts()
  // 笔记本身可能讨论账号风控，不能把搜索结果内容当作平台提示。
  let message = pageText.replace(/\s+/g, ' ').trim()
  for (const cardText of cardTexts) {
    const text = cardText.replace(/\s+/g, ' ').trim()
    if (text) message = message.replace(text, '')
  }
  if (/(?:非|不是|不符合|不符|不像).{0,24}真人|真人.{0,24}(?:操作习惯|操作行为)|(?:账号|帐号|账户)(?:存在)?异常|(?:账号|帐号|账户|功能).{0,12}(?:受限|限制)|非正常(?:访问|操作)|访问异常|操作异常|操作频繁|频繁操作|请求过于频繁/.test(message)) {
    throw new XhsAccessError('account_restricted', '小红书提示非真人操作、账号异常或功能受限，已停止采集。请先在官方 App 查看原因并完成验证或申诉，限制解除后再恢复。')
  }
  if (/website-login\/error/.test(currentPage.url()) || /IP存在风险|安全限制|网络环境.{0,12}异常/.test(message)) {
    throw new XhsAccessError('restricted', '小红书暂时限制了当前网络环境，已停止采集。请先查看平台提示并处理限制。')
  }
  if (/安全检查|安全验证|滑块验证|验证码|完成验证/.test(message)) {
    throw new XhsAccessError('verification', '小红书当前要求安全验证，已停止采集。请打开原账号窗口手动处理，确认限制解除后再恢复。')
  }
  if (!cardTexts.length && /扫码登录|登录后搜索|登录后查看|手机号登录|立即登录/.test(message)) {
    throw new XhsAccessError('login', '登录已失效，请点“登录小红书”完成登录后重试。')
  }
}

async function openFilterPanel(currentPage) {
  await assertPageAccess(currentPage)
  const filter = currentPage.locator('.filter').first()
  if (await filter.count() === 0) throw new Error('搜索页暂未显示时间筛选菜单，请刷新后重试。')
  await filter.hover({ timeout: 5000 })
  const panel = filter.locator('.filter-panel').first()
  if (!(await panel.isVisible().catch(() => false))) {
    await filter.click({ timeout: 5000 })
  }
  try { await panel.waitFor({ state: 'visible', timeout: 5000 }) }
  catch { throw new Error('搜索页暂未打开筛选菜单，请刷新后重试。') }
  return panel
}

async function clickFilterTag(panel, sectionLabel, optionLabel) {
  await assertPageAccess(panel.page())
  const section = panel.locator('.filters').filter({ hasText: sectionLabel }).first()
  const options = section.locator('.tag-container > .tags:not([aria-hidden="true"])')
  const option = options.filter({ hasText: optionLabel }).first()
  if (await option.count() === 0 || !(await option.isVisible().catch(() => false))) {
    throw new Error(`搜索页没有显示“${optionLabel}”筛选项，请在小红书页面确认筛选条件后再重试。`)
  }
  if ((await option.getAttribute('class') || '').split(/\s+/).includes('active')) return
  await option.click({ timeout: 5000 })
  for (let attempt = 0; attempt < 20; attempt++) {
    if ((await option.getAttribute('class') || '').split(/\s+/).includes('active')) return
    await panel.page().waitForTimeout(100)
  }
  throw new Error(`小红书未能应用“${optionLabel}”筛选条件，请刷新后重试。`)
}

async function applyFilters(currentPage, task) {
  const sortLabel = sortLabels[task.sort_by]
  if (!sortLabel) throw new Error('不支持的排序条件')
  let panel = await openFilterPanel(currentPage)
  await clickFilterTag(panel, '排序依据', sortLabel)
  panel = await openFilterPanel(currentPage)
  await clickFilterTag(panel, '发布时间', periodLabels[task.period])
  await assertPageAccess(currentPage)
  const confirm = currentPage.getByText('确定', { exact: true }).first()
  if (await confirm.count() && await confirm.isVisible()) await confirm.click({ timeout: 5000 })
  await currentPage.waitForTimeout(1500)
}

export async function extractCards(currentPage, task, progress = async () => {}) {
  const onResponse = response => {
    if ([403, 429].includes(response.status()) && isPlatformDataRequest(response.request())) {
      dataRequestErrors.set(currentPage, new XhsAccessError('restricted', '小红书的数据请求被拒绝或请求过多，已停止采集。此信号不能确认账号被风控，请先人工检查。'))
    }
  }
  const onRequestFailed = request => {
    if (isPlatformDataRequest(request) && request.failure()?.errorText !== 'net::ERR_ABORTED' && !dataRequestErrors.has(currentPage)) {
      dataRequestErrors.set(currentPage, new XhsAccessError('collection_uncertain', '小红书数据请求未完成，原因尚不明确。已暂停采集，请先人工检查网络和原页面。'))
    }
  }
  // 被动检查浏览器本来就发出的数据请求，不额外发送探测请求。
  currentPage.on('response', onResponse)
  currentPage.on('requestfailed', onRequestFailed)
  try { return await collectCards(currentPage, task, progress) }
  catch (error) {
    // 平台弹层也可能让筛选或导航超时，优先报告限制而不是普通网络错误。
    if (!(error instanceof XhsAccessError) && !currentPage.isClosed()) {
      try { await assertPageAccess(currentPage) }
      catch (accessError) { if (accessError instanceof XhsAccessError) throw accessError }
    }
    throw error
  } finally {
    currentPage.off('response', onResponse)
    currentPage.off('requestfailed', onRequestFailed)
    dataRequestErrors.delete(currentPage)
  }
}

async function collectCards(currentPage, task, progress) {
  await progress('loading', 0)
  const response = await currentPage.goto(`https://www.xiaohongshu.com/search_result/?keyword=${encodeURIComponent(task.query)}`, { waitUntil: 'domcontentloaded', timeout: 30_000 })
  if (response && [403, 429].includes(response.status())) {
    throw new XhsAccessError('restricted', '小红书拒绝了此次访问或请求过多，已停止采集。此信号不能确认账号被风控，请先人工检查。')
  }
  await currentPage.waitForTimeout(3000)
  await assertPageAccess(currentPage)
  await progress('filtering', 0)
  await applyFilters(currentPage, task)

  const collected = new Map()
  let previousCount = -1
  let unchangedPasses = 0
  for (let pass = 0; pass < 14 && collected.size < task.note_limit; pass++) {
    await assertPageAccess(currentPage)
    const cards = await currentPage.locator('section.note-item').evaluateAll(elements => elements.map((card, index) => {
      const anchor = card.querySelector('a.title[href*="/search_result/"], a.cover[href*="/search_result/"], a.title[href*="/explore/"], a.cover[href*="/explore/"]')
      const title = card.querySelector('.title')
      return {
        note_id: card.getAttribute('data-note-id') || '',
        title: (title?.innerText || '').trim(),
        author: (card.querySelector('.name')?.textContent || '').trim(),
        published_text: (card.querySelector('.time')?.textContent || '').trim(),
        likes_text: (card.querySelector('.like-wrapper .count')?.textContent || '').trim(),
        url: anchor?.href || '',
        sort_rank: Number(card.getAttribute('data-index')) || index + 1,
      }
    }))
    for (const item of cards) {
      if (item.note_id && item.url && !collected.has(item.note_id)) {
        collected.set(item.note_id, { ...item, likes_count: parseLikes(item.likes_text), captured_at: new Date().toISOString() })
      }
    }
    if (!collected.size) {
      // 空结果不能证明账号受限；保留未知状态，不继续滚动反复加载。
      throw new XhsAccessError('collection_uncertain', '搜索页没有提供可读取的笔记，原因尚不明确，可能是没有结果、加载失败或页面变化。已暂停采集，请先人工检查原页面。')
    }
    await progress('collecting', Math.min(collected.size, task.note_limit))
    if (collected.size === previousCount) unchangedPasses++
    else unchangedPasses = 0
    previousCount = collected.size
    if (collected.size >= task.note_limit || unchangedPasses >= 2 || pass === 13) break
    await assertPageAccess(currentPage)
    await currentPage.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
    // 控制加载请求的密度，不模拟真人行为或声称这是平台允许的频率。
    await currentPage.waitForTimeout(3000)
  }

  await assertPageAccess(currentPage)
  return [...collected.values()].slice(0, task.note_limit)
}

function parseLikes(raw) {
  const value = raw.trim().replaceAll(',', '')
  if (!value) return null
  const match = value.match(/^(\d+(?:\.\d+)?)(万|w)?$/i)
  if (!match) return null
  return Math.round(Number(match[1]) * (match[2] ? 10_000 : 1))
}
