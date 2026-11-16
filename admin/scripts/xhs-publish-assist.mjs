import { createHash, randomUUID } from 'node:crypto'
import { mkdir, readFile, writeFile, rename } from 'node:fs/promises'
import path from 'node:path'
import { chromium } from '@playwright/test'

const PUBLISH_URL = 'https://creator.xiaohongshu.com/publish/publish'
const MB = 1024 * 1024
export const MAX_ASSIST_REQUEST = 58 * MB
const hash = value => createHash('sha256').update(value).digest('hex')
class AssistError extends Error {
  constructor(message, status = 409) { super(message); this.status = status }
}
const reject = message => { throw new AssistError(message, 400) }

export function validateAssistPayload(body) {
  if (!body || typeof body.record_id !== 'string' || !/^[a-zA-Z0-9_-]{8,80}$/.test(body.record_id) || !Number.isSafeInteger(body.revision) || body.revision < 1) reject('发布记录或版本无效，请重新保存。')
  if (typeof body.headline !== 'string' || !body.headline.trim() || Array.from(body.headline).length > 20 ||
      typeof body.body !== 'string' || !body.body.trim() || body.body.length > 2400) reject('标题或正文不完整、过长，请检查。')
  if (body.account_confirmed !== true || body.media_confirmed !== true || body.reviewed !== true) reject('请先完成文案复核，并确认实际登录账号和本次素材。')
  if (!Array.isArray(body.media) || !body.media.length || body.media.length > 9) reject('请选择 1–9 张图片，或 1 个 MP4 视频。')
  let total = 0
  const media = body.media.map((item, index) => {
    if (!item || !['image/png', 'image/jpeg', 'image/webp', 'video/mp4'].includes(item.type) ||
        typeof item.base64 !== 'string' || !item.base64.length || item.base64.length > 56 * MB ||
        item.base64.length % 4 !== 0 || !/^[A-Za-z0-9+/]*={0,2}$/.test(item.base64)) reject('素材格式无效，仅支持 PNG、JPEG、WebP 或 MP4。')
    const buffer = Buffer.from(item.base64, 'base64')
    const video = item.type === 'video/mp4'
    if (!buffer.length || buffer.length > (video ? 40 : 10) * MB) reject('单张图片最多 10 MB，视频最多 40 MB。')
    const valid = item.type === 'image/png' ? buffer.subarray(0, 8).equals(Buffer.from([137,80,78,71,13,10,26,10]))
      : item.type === 'image/jpeg' ? buffer[0] === 255 && buffer[1] === 216 && buffer[2] === 255
        : item.type === 'image/webp' ? buffer.toString('ascii', 0, 4) === 'RIFF' && buffer.toString('ascii', 8, 12) === 'WEBP'
          : buffer.length >= 16 && buffer.toString('ascii', 4, 8) === 'ftyp'
    if (!valid) reject('素材内容与文件类型不一致，请重新选择原始文件。')
    total += buffer.length
    const extension = { 'image/png':'png', 'image/jpeg':'jpg', 'image/webp':'webp', 'video/mp4':'mp4' }[item.type]
    return { name: `${String(index + 1).padStart(2, '0')}.${extension}`, mimeType: item.type, buffer }
  })
  const video = media.some(item => item.mimeType === 'video/mp4')
  if (video && media.length !== 1) reject('视频只能单独选择一个，不能与图片混用。')
  if (total > (video ? 40 : 30) * MB) reject('本次图片合计最多 30 MB，视频最多 40 MB。')
  return { headline: body.headline, body: body.body, media, video }
}

const titleSelector = 'input[placeholder*="标题"]:visible'
const editorSelector = '.tiptap[contenteditable="true"]:visible, .ql-editor[contenteditable="true"]:visible, [role="textbox"][contenteditable="true"]:visible, textarea[placeholder*="正文"]:visible'
async function safePage(page) {
  if (page.isClosed()) throw new AssistError('发布窗口已关闭，请新建辅助窗口。')
  const url = new URL(page.url())
  if (url.protocol !== 'https:' || url.hostname !== 'creator.xiaohongshu.com' || url.port || url.username || url.password) throw new AssistError('窗口已离开官方创作平台，请新建辅助窗口。')
  if (url.pathname.includes('/login')) throw new AssistError('请在专用窗口手动登录，再回工作台点击填入。')
  // 只查看可见提示；不操作登录、验证码、账号限制或协议确认。
  const warning = page.getByText(/请完成验证|安全验证|访问异常|账号异常|操作频繁|拖动滑块|滑动验证/).filter({ visible: true })
  if (await warning.count()) throw new AssistError('平台要求验证或限制操作，请在窗口按官方提示处理；本次已停止。')
  if (!url.pathname.startsWith('/publish/')) throw new AssistError('请在专用窗口打开官方“发布笔记”页面，再点击填入。')
}
async function editorText(locator) {
  return locator.evaluate(el => {
    if ('value' in el) return el.value
    // Chromium 会把空行表示成 <div><br></div>，innerText 会多读一个换行。
    // 按编辑器段落读取，保留真实空段落，避免误判或静默吞掉文字。
    function read(node) {
      if (node.nodeType === Node.TEXT_NODE) return node.textContent || ''
      if (node.nodeName === 'BR') return '\n'
      let text = ''
      for (const child of node.childNodes) {
        if (['DIV', 'P', 'LI'].includes(child.nodeName)) {
          if (text && !text.endsWith('\n')) text += '\n'
          text += read(child).replace(/\n$/, '') + '\n'
        } else text += read(child)
      }
      return text
    }
    return read(el)
  })
}
async function ensureEmpty(page) {
  for (const input of await page.locator('input[type="file"]').all()) {
    if (await input.evaluate(el => !!el.files?.length)) throw new AssistError('页面已经选过素材，已停止以避免重复上传，请手动继续或新建辅助窗口。')
  }
  if (await page.locator('img[src^="blob:"]:visible, video[src^="blob:"]:visible').count()) throw new AssistError('页面已有素材预览，请手动继续或新建辅助窗口。')
  for (const locator of [page.locator(titleSelector), page.locator(editorSelector)]) {
    if (await locator.count() > 1) throw new AssistError('页面存在多个编辑框，无法确定目标，请手动填写。')
    if (await locator.count() && (await editorText(locator)).trim()) throw new AssistError('发布页面已有内容，已停止以避免覆盖。请在该窗口继续编辑，或新建空白辅助窗口。')
  }
}

// 只有“上传图文/上传视频”模式切换、文件选择与文字填入；没有发布、定时发布或提交操作。
export async function fillPublisherPage(page, payload, beforeUpload) {
  await safePage(page)
  await ensureEmpty(page)
  const label = payload.video ? '上传视频' : '上传图文'
  // 官方侧栏也有同名入口；只在发布页的模式标签中选择，避免点到导航或草稿。
  const scopedTab = page.locator('.creator-tab:visible').filter({ hasText: new RegExp(`^\\s*${label}\\s*$`) })
  const matches = await scopedTab.count() ? scopedTab : page.getByText(label, { exact: true }).filter({ visible: true })
  // 合并嵌套匹配，并排除移到屏幕外或被同位置副本遮挡的节点；仍拒绝两个可点击入口。
  const roots = await matches.evaluateAll(elements => elements.map((el, index) => {
    if (elements.some(other => other !== el && other.contains(el))) return -1
    const rect = el.getBoundingClientRect(), x = rect.x + rect.width / 2, y = rect.y + rect.height / 2
    if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) return -1
    const hit = document.elementFromPoint(x, y)
    return hit && (hit === el || el.contains(hit)) ? index : -1
  }).filter(index => index >= 0))
  if (roots.length !== 1) throw new AssistError('没有找到唯一的上传入口，请手动切换到上传图文／视频，或使用文案与素材导出。')
  const tab = matches.nth(roots[0])
  await tab.click({ timeout: 5000 })
  await safePage(page)
  await ensureEmpty(page)
  const candidates = []
  const uploadArea = page.locator('.upload-content .upload-area:visible')
  const scope = await uploadArea.count() === 1 ? uploadArea : page
  for (const input of await scope.locator('input[type="file"]').all()) {
    const accept = (await input.getAttribute('accept') || '').toLowerCase()
    if (await input.isDisabled()) continue
    // 图片上传区同时可能有单张替换控件；本次多图只使用明确支持 multiple 的入口。
    if (!payload.video && payload.media.length > 1 && await input.getAttribute('multiple') === null) continue
    if (payload.video ? /video|\.mp4/.test(accept) && !/image/.test(accept) : /image|\.png|\.jpg|\.jpeg/.test(accept) && !/video/.test(accept)) candidates.push(input)
  }
  if (candidates.length !== 1) throw new AssistError('无法确定素材上传控件，页面可能已变化，请手动上传。')
  if (payload.media.length > 1 && await candidates[0].getAttribute('multiple') === null) throw new AssistError('当前控件不支持多图，已停止，请手动上传。')
  // 持久记录发生在首次上传之前；即使断网或重启，也不会静默重传。
  await beforeUpload()
  await safePage(page)
  await candidates[0].setInputFiles(payload.media, { timeout: 60_000 })
  const title = page.locator(titleSelector), editor = page.locator(editorSelector)
  await title.waitFor({ state: 'visible', timeout: 30_000 })
  await editor.waitFor({ state: 'visible', timeout: 30_000 })
  await safePage(page)
  // 素材已由本次选择，不再检查文件控件；仍拒绝覆盖页面恢复出的文案。
  for (const field of [title, editor]) {
    if (await field.count() !== 1 || (await editorText(field)).trim()) throw new AssistError('上传后页面出现已有文案，已停止以避免覆盖，请在窗口核对。')
  }
  for (const [field, value] of [[title, payload.headline], [editor, payload.body]]) {
    const maximum = Number(await field.getAttribute('maxlength'))
    if (maximum > 0 && value.length > maximum) throw new AssistError('文案超过页面当前字数上限，请缩短后人工填写。素材可能已上传。')
  }
  await title.fill(payload.headline, { timeout: 5000 })
  await safePage(page)
  await editor.fill(payload.body, { timeout: 5000 })
  const normalize = value => value.replace(/\r\n/g, '\n').trim()
  if (normalize(await editorText(title)) !== normalize(payload.headline) || normalize(await editorText(editor)) !== normalize(payload.body)) throw new AssistError('页面文案回读不一致，请在窗口核对；不会再次覆盖。')
  await safePage(page)
  await page.bringToFront()
}

export function createPublisher({ profileDir, journalFile, launch = (...args) => chromium.launchPersistentContext(...args), fill = fillPublisherPage }) {
  let context, session, busy = false, history
  const state = origin => {
    if (!session || session.origin !== origin) return { available: true, busy, session: null }
    return { available: true, busy, session: { token: session.token, record_id: session.record_id, revision: session.revision,
      status: session.status, message: session.message, browser_open: !!session.page && !session.page.isClosed(), touched: session.touched } }
  }
  async function loadHistory() {
    if (history) return
    try {
      const value = JSON.parse(await readFile(journalFile, 'utf8'))
      if (!Array.isArray(value) || value.some(item => !item || !/^[a-f0-9]{64}$/.test(item.key))) throw new Error('Invalid journal')
      history = value
    } catch (error) {
      if (error.code !== 'ENOENT') throw new AssistError('本机辅助记录无法读取，为避免重复上传已停止，请检查本机存储。')
      history = []
    }
  }
  async function remember(key) {
    const next = [...history.filter(item => item.key !== key), { key, at: new Date().toISOString() }].slice(-500)
    await writeFile(`${journalFile}.tmp`, JSON.stringify(next), { encoding: 'utf8', mode: 0o600 })
    await rename(`${journalFile}.tmp`, journalFile)
    history = next
  }
  async function open(origin, body) {
    if (busy) throw new AssistError('辅助窗口正在处理请求，请稍后查看状态。')
    if (!body || typeof body.record_id !== 'string' || !/^[a-zA-Z0-9_-]{8,80}$/.test(body.record_id) || !Number.isSafeInteger(body.revision) || body.revision < 1) reject('请先保存发布记录。')
    const fresh = body.new_session === true && body.acknowledged === true
    if (session && !fresh) {
      if (session.origin !== origin || session.record_id !== body.record_id || session.revision !== body.revision) throw new AssistError('已有其他内容的辅助窗口，请先检查旧窗口，再新建本条的辅助窗口。')
      if (session.page && !session.page.isClosed()) {
        await session.page.bringToFront()
        return state(origin)
      }
      if (session.touched) throw new AssistError('原窗口已关闭且曾尝试上传，请先检查小红书草稿和已发布笔记，再新建空白辅助窗口。')
      // 尚未上传的关闭页面可以直接恢复；上传尝试记录仍会在 prepare 中检查。
    }
    busy = true
    try {
      await loadHistory()
      await mkdir(profileDir, { recursive: true })
      if (!context) {
        context = await launch(profileDir, { headless: false, viewport: null })
        context.on('close', () => { context = undefined })
      }
      const page = await context.newPage()
      page.setDefaultTimeout(5000)
      session = { origin, record_id: body.record_id, revision: body.revision, token: randomUUID(), page,
        status: 'waiting', message: '请手动登录，确认账号与空白发布页后再点击填入。', touched: false, allowRepeat: fresh }
      await page.goto(PUBLISH_URL, { waitUntil: 'domcontentloaded', timeout: 30_000 })
      await page.bringToFront()
      return state(origin)
    } catch (error) {
      if (session?.origin === origin) { session.status = 'paused'; session.message = '窗口未能完整打开，请检查网络并在窗口手动打开发布页。' }
      throw error
    } finally { busy = false }
  }
  async function prepare(origin, body) {
    if (busy) throw new AssistError('正在填入中，请查看状态，不要重复上传。')
    if (!session || session.origin !== origin || body?.token !== session.token || body?.record_id !== session.record_id || body?.revision !== session.revision) throw new AssistError('辅助会话已变化，请重新打开并确认账号。')
    if (session.touched) return state(origin)
    if (!session.page || session.page.isClosed()) throw new AssistError('辅助窗口已关闭，请新建辅助窗口。')
    const payload = validateAssistPayload(body)
    const key = hash(`${origin}\n${body.record_id}`)
    if (history.some(item => item.key === key) && !session.allowRepeat) throw new AssistError('这条记录曾尝试上传。请先检查旧窗口和账号中的草稿／已发布笔记，再明确新建辅助窗口。')
    busy = true
    session.status = 'filling'; session.message = '正在填入，请勿操作发布窗口。'
    // 返回任务状态后在本机继续；浏览器刷新不会取消任务，也不会自动重试。
    void (async () => {
      try {
        await fill(session.page, payload, async () => { await remember(key); session.touched = true })
        session.status = 'prepared'
        session.message = '文案已填入，素材已交给页面。请等待平台处理完成，核对顺序、封面、话题、标识和账号，再由你点击发布。'
      } catch (error) {
        session.status = 'paused'
        session.message = error instanceof AssistError ? error.message : '填入中断或页面响应超时，请检查窗口中的实际内容。可能已有素材，不会自动重试。'
      } finally { busy = false }
    })()
    return state(origin)
  }
  return {
    state, open, prepare,
    async preview(origin) {
      if (busy) throw new AssistError('正在填入，请等待完成后查看窗口。')
      if (!session || session.origin !== origin || !session.page) throw new AssistError('请先打开本条内容的辅助窗口。')
      await safePage(session.page)
      const controls = await session.page.evaluate(() => ({
        tabs: [...document.querySelectorAll('.creator-tab')].map(el => ({ text: el.textContent.trim(), classes: el.className, tag: el.tagName,
          parent: el.parentElement.className, rect: el.getBoundingClientRect().toJSON() })),
        uploads: [...document.querySelectorAll('input[type="file"]')].map(el => ({ accept: el.accept, multiple: el.multiple, classes: el.className, area: !!el.closest('.upload-area') })),
      }))
      return { ...state(origin), controls, image: (await session.page.screenshot({ type: 'png' })).toString('base64') }
    },
    async close() { await context?.close() },
    error(error) { return { status: error instanceof AssistError ? error.status : 502, error: error instanceof AssistError ? error.message : '本机辅助发布不可用，请检查浏览器或本机存储后重试。' } },
  }
}
