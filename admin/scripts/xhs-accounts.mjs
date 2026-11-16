import { randomUUID } from 'node:crypto'
import { mkdir, readFile, writeFile, rename, stat } from 'node:fs/promises'
import path from 'node:path'
import { chromium } from '@playwright/test'
import { createPublisher } from './xhs-publish-assist.mjs'

const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/
const legacyId = 'legacy-publisher'
const researchId = 'legacy-research'
const emptyProfile = () => ({ audience: '', direction: '', style: '', topics: '' })
function profileFields(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new AccountError('账号定位档案格式无效。', 400)
  const result = emptyProfile()
  for (const [key, maximum] of Object.entries({ audience: 200, direction: 1000, style: 1000, topics: 300 })) {
    if (typeof value[key] !== 'string' || value[key].length > maximum) throw new AccountError('账号定位档案超过允许长度或格式无效。', 400)
    result[key] = value[key].trim()
  }
  return result
}
const escapeHtml = text => text.replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]))
class AccountError extends Error {
  constructor(message, status = 409) { super(message); this.status = status }
}
export function createXhsAccounts({ rootDir, legacyProfileDir = path.join(rootDir, 'xhs-publisher-profile'), launch = (...args) => chromium.launchPersistentContext(...args) }) {
  const registryFile = path.join(rootDir, 'xhs-accounts.json')
  const contexts = new Map(), locks = new Set(), publishers = new Map()
  let registry, writes = Promise.resolve()
  const profilePath = id => {
    if (id === legacyId) return legacyProfileDir
    if (id === researchId) return path.join(rootDir, 'xhs-research-profile')
    if (typeof id !== 'string' || !uuid.test(id)) throw new AccountError('账号编号无效。', 400)
    return path.join(rootDir, 'xhs-account-profiles', id)
  }
  async function load() {
    if (registry) return
    try {
      const value = JSON.parse(await readFile(registryFile, 'utf8'))
      if (value.version !== 1 || !Array.isArray(value.items) || value.items.length > 100 || value.items.some(item =>
        !item || typeof item.id !== 'string' || (!uuid.test(item.id) && ![legacyId, researchId].includes(item.id)) ||
        typeof item.origin !== 'string' || typeof item.name !== 'string' || !Number.isSafeInteger(item.revision))) throw new Error('Invalid registry')
      if (new Set(value.items.map(item => item.id)).size !== value.items.length) throw new Error('Duplicate id')
      registry = value
    } catch (error) {
      if (error.code !== 'ENOENT') throw new AccountError('本机账号清单无法读取，已保留浏览器数据。请检查本机存储，不要重新创建同名账号。')
      registry = { version: 1, items: [] }
    }
  }
  async function transaction(fn) {
    const next = writes.catch(() => {}).then(async () => { await load(); return fn() })
    writes = next.catch(() => {})
    return next
  }
  async function save(items) {
    const next = { version: 1, items }
    await mkdir(rootDir, { recursive: true })
    await writeFile(`${registryFile}.tmp`, JSON.stringify(next), { encoding: 'utf8', mode: 0o600 })
    await rename(`${registryFile}.tmp`, registryFile)
    registry = next
  }
  async function initialize(origin) {
    await transaction(async () => {
      for (const [id, label] of [[legacyId, '原辅助发布账号'], [researchId, '原采集账号']]) {
        if (registry.items.some(item => item.id === id) || registry.items.length >= 100) continue
        try { if (!(await stat(profilePath(id))).isDirectory()) continue }
        catch (error) { if (error.code === 'ENOENT') continue; throw error }
        // 原位沿用已有目录，不复制登录数据，也不另开进程占用同一目录。
        let name = label, suffix = 1
        while (registry.items.some(item => item.origin === origin && item.name === name)) name = `${label} ${suffix++}`
        await save([...registry.items, { id, origin, name, note: '沿用之前的浏览器，请在窗口核对实际账号并修改名称。', archived: false, revision: 1, created_at: new Date().toISOString() }])
      }
    })
  }
  function get(origin, id) {
    profilePath(id)
    const item = registry?.items.find(item => item.id === id && item.origin === origin)
    if (!item) throw new AccountError('本机没有此账号，或账号属于其他后台访问地址。', 404)
    return item
  }
  const publishing = id => !!publishers.get(id)?.busy()
  const publicAccount = item => ({ id: item.id, name: item.name, note: item.note || '', revision: item.revision,
    profile: item.profile || emptyProfile(), archived: !!item.archived, created_at: item.created_at, browser_open: contexts.has(item.id), busy: locks.has(item.id) || publishing(item.id) })
  async function list(origin) {
    await initialize(origin)
    return { profile_support: true, items: registry.items.filter(item => item.origin === origin).map(publicAccount) }
  }
  function fields(body) {
    if (typeof body?.name !== 'string' || !body.name.trim() || body.name.trim().length > 60 || typeof body.note !== 'string' || body.note.length > 500) throw new AccountError('请填写 1–60 字的账号名称，备注最多 500 字。', 400)
    return { name: body.name.trim(), note: body.note.trim(), ...(body.profile === undefined ? {} : { profile: profileFields(body.profile) }) }
  }
  async function add(origin, body) {
    const value = fields(body)
    if (typeof body.request_id !== 'string' || !/^[a-zA-Z0-9_-]{8,80}$/.test(body.request_id)) throw new AccountError('请求编号无效，请重新打开新增表单。', 400)
    await initialize(origin)
    return transaction(async () => {
      const previous = registry.items.find(item => item.origin === origin && item.request_id === body.request_id)
      if (previous) {
        if (previous.name !== value.name || previous.note !== value.note || JSON.stringify(previous.profile || emptyProfile()) !== JSON.stringify(value.profile || emptyProfile())) throw new AccountError('上次新增请求已经保存。请刷新账号列表，再编辑该账号，避免重复创建。')
        return { account: publicAccount(previous) }
      }
      if (registry.items.length >= 100) throw new AccountError('本机最多管理 100 个账号配置。')
      if (registry.items.some(item => item.origin === origin && item.name.toLocaleLowerCase() === value.name.toLocaleLowerCase())) throw new AccountError('已有同名账号，请使用不同名称，或恢复已归档账号。')
      const item = { id: randomUUID(), origin, request_id: body.request_id, ...value, archived: false, revision: 1, created_at: new Date().toISOString() }
      await save([...registry.items, item])
      return { account: publicAccount(item) }
    })
  }
  async function use(origin, id, fn, allowArchived = false) {
    await initialize(origin)
    const item = get(origin, id)
    if (item.archived && !allowArchived) throw new AccountError('账号已归档，请先恢复。')
    if (locks.has(id)) throw new AccountError('这个账号正在打开或处理窗口，请稍后再试。')
    locks.add(id)
    try { return await fn(item) } finally { locks.delete(id) }
  }
  async function update(origin, body) {
    const value = fields(body)
    if (typeof body.archived !== 'boolean') throw new AccountError('账号状态无效。', 400)
    return use(origin, body.account_id, async () => transaction(async () => {
      const item = get(origin, body.account_id)
      if (body.revision !== item.revision) throw new AccountError('账号已在其他页面修改，请刷新后再编辑。')
      if (body.archived && (contexts.has(item.id) || publishing(item.id))) throw new AccountError('请先完成辅助操作并关闭该账号窗口，再归档。')
      if (registry.items.some(other => other.origin === origin && other.id !== item.id && other.name.toLocaleLowerCase() === value.name.toLocaleLowerCase())) throw new AccountError('已有同名账号，请使用不同名称。')
      const next = { ...item, ...value, archived: body.archived, revision: item.revision + 1 }
      await save(registry.items.map(other => other.id === item.id ? next : other))
      return { account: publicAccount(next) }
    }), true)
  }
  async function browser(item) {
    if (contexts.has(item.id)) return contexts.get(item.id).context
    const directory = profilePath(item.id)
    await mkdir(directory, { recursive: true })
    const context = await launch(directory, { headless: false, viewport: null })
    const entry = { context, home: null }
    contexts.set(item.id, entry)
    context.on('close', () => { if (contexts.get(item.id) === entry) contexts.delete(item.id) })
    try {
      const home = await context.newPage(); entry.home = home
      await home.goto('data:text/html;charset=utf-8,' + encodeURIComponent(`<!doctype html><meta charset="utf-8"><title>${escapeHtml(item.name)} · 小红书账号</title><style>body{font:18px system-ui;padding:50px;background:#edf6f1;color:#194936}a{display:inline-block;margin:16px 24px 0 0}</style><h1>${escapeHtml(item.name)}</h1><p>这是该账号的独立浏览器。首次使用请在小红书页面手动登录。</p><p>请保留本标签页，方便辨认窗口。名称为本地备注，不代表当前已登录身份。</p><a href="https://www.xiaohongshu.com/explore" target="_blank" rel="noopener">打开小红书</a><a href="https://creator.xiaohongshu.com/" target="_blank" rel="noopener">打开创作平台</a>`))
      return context
    } catch (error) { await context.close().catch(() => {}); throw error }
  }
  async function open(origin, body, noteUrl) {
    return use(origin, body.account_id, async item => {
      if (publishing(item.id)) throw new AccountError('该账号正在辅助填入，请等待完成后再打开。')
      const context = await browser(item), entry = contexts.get(item.id)
      if (noteUrl) {
        const page = await context.newPage()
        await page.goto(noteUrl, { waitUntil: 'domcontentloaded', timeout: 30_000 })
        await page.bringToFront()
        return { account: publicAccount(item) }
      }
      const pages = context.pages().filter(page => !page.isClosed() && page !== entry.home && page.url() !== 'about:blank')
      let page = pages.at(-1)
      if (!page) { page = await context.newPage(); await page.goto('https://www.xiaohongshu.com/explore', { waitUntil: 'domcontentloaded', timeout: 30_000 }) }
      await page.bringToFront()
      return { account: publicAccount(item) }
    })
  }
  async function openNote(origin, body) {
    let url
    try { url = new URL(body?.url) } catch { throw new AccountError('笔记链接无效。', 400) }
    if (typeof body.url !== 'string' || body.url.length > 2000 || url.protocol !== 'https:' || url.hostname !== 'www.xiaohongshu.com' ||
      url.username || url.password || url.port || !/^\/(?:explore|search_result)\/[A-Za-z0-9_-]{8,80}\/?$/.test(url.pathname)) {
      throw new AccountError('仅支持小红书 HTTPS 笔记链接。', 400)
    }
    return open(origin, body, body.url)
  }
  async function close(origin, body) {
    if (body.acknowledged !== true) throw new AccountError('关闭窗口会丢失尚未保存的页面编辑，请先确认。')
    return use(origin, body.account_id, async item => {
      if (publishing(item.id)) throw new AccountError('该账号正在辅助填入，请等待完成后再关闭。')
      await contexts.get(item.id)?.context.close()
      return { account: publicAccount(item) }
    })
  }
  async function publication(origin, id, action, body) {
    return use(origin, id, async item => {
      let entry = publishers.get(id)
      if (!entry) {
        const publisher = createPublisher({ profileDir: profilePath(id), journalFile: id === legacyId ? path.join(rootDir, 'xhs-publisher-attempts.json') : path.join(profilePath(id), 'assist-attempts.json'), launch: () => browser(get(origin, id)) })
        entry = { publisher, busy: () => publisher.state(origin).busy }
        publishers.set(id, entry)
      }
      const result = action === 'state' ? entry.publisher.state(origin) : await entry.publisher[action](origin, body)
      return { ...result, session: result.session ? { ...result.session, account_id: item.id } : null }
    })
  }
  async function collect(origin, id, task, extract) {
    return use(origin, id, async item => {
      if (publishing(id)) throw new AccountError('该账号正在辅助填入，请完成后再采集。')
      const context = await browser(item)
      const page = await context.newPage()
      const search = `https://www.xiaohongshu.com/search_result/?keyword=${encodeURIComponent(task.query)}`
      // 只操作此次新建的标签页；失败保留现场，便于手动登录或验证。
      const items = await extract(page)
      if (!page.isClosed() && page.url() === search) await page.close().catch(() => {})
      return items
    })
  }
  return { list, add, update, open, openNote, close, publication, collect,
    validate: (origin, id) => use(origin, id, item => {
      if (publishing(item.id)) throw new AccountError('该账号正在辅助填入，请完成后再采集。')
      return publicAccount(item)
    }),
    summary: () => ({ accounts_open: contexts.size, accounts_busy: locks.size > 0, publisher_busy: [...publishers.values()].some(item => item.busy()) }),
    async shutdown() { await Promise.allSettled([...contexts.values()].map(entry => entry.context.close())) },
    error(error) { return { status: error instanceof AccountError ? error.status : (Number.isInteger(error.status) ? error.status : 502), error: error instanceof AccountError || Number.isInteger(error.status) ? error.message : '本机账号操作失败，已保留浏览器数据。请检查窗口或本机服务后重试。' } },
  }
}
