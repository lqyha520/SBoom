/** Local-only browser bridge. It keeps the user's XHS session in a dedicated Chrome profile on this computer. */
import http from 'node:http'
import { authorizeLocalRequest } from './xhs-authorization.mjs'
import os from 'node:os'
import path from 'node:path'
import { appendFile, mkdir, readFile, rename, writeFile } from 'node:fs/promises'
import { MAX_ASSIST_REQUEST } from './xhs-publish-assist.mjs'
import { createXhsAccounts } from './xhs-accounts.mjs'
import { extractCards, XhsAccessError } from './xhs-collect.mjs'

const host = '127.0.0.1'
const port = Number(process.env.XHS_COLLECTOR_PORT || 17632)
const profileDir = path.join(process.env.LOCALAPPDATA || path.join(os.homedir(), '.local', 'share'), 'learn-coach', 'xhs-research-profile')
const logFile = path.join(path.dirname(profileDir), 'xhs-collector.log')
const stateFile = path.join(path.dirname(profileDir), 'xhs-collector-state.json')
const jobsFile = path.join(path.dirname(profileDir), 'xhs-collector-jobs.json')
const accounts = createXhsAccounts({ rootDir: path.dirname(profileDir) })
let readingPublication = false
const allowedOrigins = new Set([
  'https://sboom.bcxtech.cn',
  'https://localhost', 'https://127.0.0.1',
  'http://127.0.0.1:8000', 'http://localhost:8000',
  'http://127.0.0.1:5173', 'http://localhost:5173',
  'http://127.0.0.1:5174', 'http://localhost:5174',
  'http://127.0.0.1:4173', 'http://localhost:4173',
  ...(process.env.LEARN_COACH_ADMIN_ORIGIN || '').split(',').map(value => value.trim()).filter(Boolean),
])

let enabled = true
let pauseReason = ''
let busy = false
const jobs = new Map()
let jobWrites = Promise.resolve()

function log(message) {
  console.log(message)
  void appendFile(logFile, `${new Date().toISOString()} ${message}\n`, 'utf8').catch(() => {})
}

await mkdir(path.dirname(profileDir), { recursive: true })
try {
  const saved = JSON.parse(await readFile(stateFile, 'utf8'))
  if (typeof saved.enabled === 'boolean') enabled = saved.enabled
  if (typeof saved.pause_reason === 'string') pauseReason = saved.pause_reason
  if (pauseReason) enabled = false
} catch { /* first run defaults to enabled */ }
try {
  const saved = JSON.parse(await readFile(jobsFile, 'utf8'))
  if (Array.isArray(saved)) for (const job of saved.slice(-50)) {
    if (job?.task && !job.task.account_id) job.task.account_id = 'legacy-research'
    if (job?.task) job.account_id = job.task.account_id
    if (!job || typeof job.task_id !== 'string' || !/^[a-zA-Z0-9_-]{8,80}$/.test(job.task_id) ||
      !allowedOrigins.has(job.origin) || !validTask(job.task) || !['running', 'completed', 'failed'].includes(job.status) ||
      (job.status === 'completed' && !Array.isArray(job.items))) continue
    if (job.status === 'running') Object.assign(job, { status: 'failed', stage: 'failed', error_code: 'interrupted',
      error: '采集器重启中断了任务，可以重试。', retryable: true })
    jobs.set(job.task_id, job)
  }
} catch { /* 首次启动或缓存损坏时重新采集，后台已保存的记录不受影响。 */ }

function saveJobs() {
  const data = JSON.stringify([...jobs.values()])
  jobWrites = jobWrites.catch(() => {}).then(async () => {
    await writeFile(`${jobsFile}.tmp`, data, { encoding: 'utf8', mode: 0o600 })
    await rename(`${jobsFile}.tmp`, jobsFile)
  })
  return jobWrites
}

function publicJob(job) {
  const { origin, task, ...result } = job
  return result
}

function failure(error) {
  const text = error instanceof Error ? error.message : '采集失败，请重试。'
  if (error instanceof XhsAccessError) return { error_code: error.code, retryable: false, error: text }
  if (/Timeout|timed out|net::|fetch failed/i.test(text)) return { error_code: 'network', retryable: true, error: '访问小红书超时或网络连接中断，请检查网络后重试。' }
  if (/网络环境|IP存在风险|安全限制/.test(text)) return { error_code: 'restricted', retryable: false, error: text }
  if (/安全验证|验证/.test(text)) return { error_code: 'verification', retryable: false, error: text }
  if (/登录/.test(text)) return { error_code: 'login', retryable: false, error: text }
  if (/筛选|菜单/.test(text)) return { error_code: 'page_changed', retryable: false, error: text }
  return { error_code: 'unknown', retryable: false, error: text }
}

async function pauseAfterAccessFailure(result) {
  if (!['account_restricted', 'restricted', 'verification', 'collection_uncertain'].includes(result.error_code)) return
  enabled = false
  pauseReason = result.error
  await saveEnabledState(false).catch(() => { log('采集已停止，但暂停状态保存失败，请检查本机磁盘空间。') })
  result.error += ' 本机采集器已自动关闭；人工检查并确认可继续后再开启。'
}

const taskKeys = ['account_id', 'query', 'period', 'sort_by', 'note_limit']
function cachedResult(origin, task) {
  return [...jobs.values()].reverse().find(job => {
    const age = Date.now() - Date.parse(job.cache_created_at || job.updated_at)
    return job.origin === origin && job.status === 'completed' && Array.isArray(job.items) &&
      age >= 0 && age < 10 * 60_000 && taskKeys.every(key => job.task[key] === task[key])
  })
}

async function runJob(job) {
  const progress = async (stage, collected = job.collected) => {
    Object.assign(job, { stage, collected, updated_at: new Date().toISOString() })
    await saveJobs()
  }
  try {
    await progress('opening')
    const items = await accounts.collect(job.origin, job.account_id, job.task, page => extractCards(page, job.task, progress))
    Object.assign(job, { status: 'completed', stage: 'completed', items, collected: items.length, cache_created_at: new Date().toISOString() })
    await saveJobs()
  } catch (error) {
    const result = failure(error)
    await pauseAfterAccessFailure(result)
    Object.assign(job, result, { status: 'failed', stage: 'failed', updated_at: new Date().toISOString() })
    log(`采集任务 ${job.task_id} 失败：${job.error}`)
    await saveJobs().catch(() => { log('采集结果缓存写入失败，请检查本机磁盘空间。') })
  } finally { busy = false }
}

function validTask(task) {
  return task && typeof task.account_id === 'string' && /^(?:legacy-(?:publisher|research)|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})$/.test(task.account_id) && typeof task.query === 'string' && task.query.trim().length > 0 && task.query.length <= 120 &&
    ['day', 'week', 'half_year', 'all'].includes(task.period) && ['general', 'popular', 'latest'].includes(task.sort_by) &&
    Number.isInteger(task.note_limit) && task.note_limit >= 10 && task.note_limit <= 100
}

async function saveEnabledState(value, reason = pauseReason) {
  const temporaryFile = `${stateFile}.tmp`
  await writeFile(temporaryFile, JSON.stringify({ enabled: value, pause_reason: reason }), { encoding: 'utf8', mode: 0o600 })
  await rename(temporaryFile, stateFile)
}

function send(response, status, body, origin) {
  response.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
    'Access-Control-Allow-Origin': origin,
    'Vary': 'Origin',
  })
  response.end(JSON.stringify(body))
}

function readJson(request, maximum = 16_384) {
  return new Promise((resolve, reject) => {
    const chunks = []
    let length = 0
    request.on('data', chunk => {
      length += chunk.length
      if (length > maximum) { reject(new Error('请求内容过大')); request.destroy(); return }
      chunks.push(chunk)
    })
    request.on('end', () => {
      try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8'))) }
      catch { reject(new Error('采集条件格式无效')) }
    })
    request.on('error', reject)
  })
}

const server = http.createServer(async (request, response) => {
  const origin = request.headers.origin || ''
  if (!allowedOrigins.has(origin)) { response.writeHead(403, { 'Cache-Control': 'no-store' }); response.end(); return }
  if (request.method === 'OPTIONS') {
    response.writeHead(204, {
      'Access-Control-Allow-Origin': origin,
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, X-Admin-Capability',
      'Access-Control-Allow-Private-Network': 'true',
      'Access-Control-Max-Age': '600',
      'Vary': 'Origin',
    })
    response.end()
    return
  }
  if (request.method === 'POST' && !/^application\/json(?:;|$)/i.test(request.headers['content-type'] || '')) { send(response, 415, { error: '请更新工作台，并使用 JSON 提交请求。' }, origin); return }
  if (request.method === 'GET' && request.url === '/health') {
    send(response, 200, { ready: true, version: 11, authorization: true, publishing: true, accounts: true, enabled, pause_reason: pauseReason, browser_open: false, background: false, busy }, origin)
    return
  }
  if (!await authorizeLocalRequest(request, origin)) { send(response, 403, { error: '没有此操作的后台权限，或凭证已过期，请刷新后重试。' }, origin); return }
  if (request.method === 'GET' && (request.url === '/accounts' || request.url === '/publisher/state' || request.url?.startsWith('/publisher/state?') || request.url?.startsWith('/publisher/preview?'))) {
    try {
      const url = new URL(request.url, 'http://127.0.0.1')
      const result = url.pathname === '/accounts' ? await accounts.list(origin) : await accounts.publication(origin, url.searchParams.get('account_id'), url.pathname === '/publisher/preview' ? 'preview' : 'state')
      send(response, 200, result, origin)
    } catch (error) { const failure = accounts.error(error); send(response, failure.status, { error: failure.error }, origin) }
    return
  }
  if (request.method === 'POST' && ['/accounts/add', '/accounts/update', '/accounts/open', '/accounts/open-note', '/accounts/close', '/publisher/open', '/publisher/prepare'].includes(request.url)) {
    if (!/^application\/json(?:;|$)/i.test(request.headers['content-type'] || '')) { send(response, 415, { error: '本机请求必须使用 JSON。' }, origin); return }
    if (request.url === '/publisher/prepare' && readingPublication) { send(response, 409, { error: '正在接收素材，请稍后再试。' }, origin); return }
    const receiving = request.url === '/publisher/prepare'
    if (receiving) readingPublication = true
    try {
      const body = await readJson(request, receiving ? MAX_ASSIST_REQUEST : 16_384)
      const result = request.url.startsWith('/accounts/') ? await accounts[request.url === '/accounts/open-note' ? 'openNote' : request.url.split('/')[2]](origin, body)
        : await accounts.publication(origin, body.account_id, receiving ? 'prepare' : 'open', body)
      send(response, 200, result, origin)
    } catch (error) {
      const failure = accounts.error(error)
      send(response, failure.status, { error: failure.error }, origin)
    } finally { if (receiving) readingPublication = false }
    return
  }
  if (request.method === 'GET' && request.url?.startsWith('/jobs/')) {
    const job = jobs.get(request.url.slice('/jobs/'.length))
    if (!job || job.origin !== origin) { send(response, 404, { error: '本机没有缓存此任务，请重新采集。' }, origin); return }
    send(response, 200, publicJob(job), origin)
    return
  }
  if (request.method === 'POST' && request.url === '/jobs') {
    let acquired = false
    let pendingJob
    try {
      const body = await readJson(request)
      if (!validTask(body) || typeof body.task_id !== 'string' || !/^[a-zA-Z0-9_-]{8,80}$/.test(body.task_id)) {
        send(response, 400, { error: '采集条件或任务编号无效。' }, origin); return
      }
      const previous = jobs.get(body.task_id)
      if (previous && previous.origin !== origin) { send(response, 409, { error: '该任务属于另一个后台来源。' }, origin); return }
      if (previous && taskKeys.some(key => previous.task[key] !== body[key])) {
        send(response, 409, { error: '任务账号或条件与本机缓存不一致，请使用原账号，或创建新任务。' }, origin); return
      }
      if (previous && (previous.status !== 'failed' || !body.retry)) {
        send(response, 200, publicJob(previous), origin); return
      }
      if (!enabled || busy) { send(response, 409, { error: !enabled ? '请先开启采集器。' : '采集器正在处理其他请求，请稍后重试。' }, origin); return }
      busy = true
      acquired = true
      await accounts.validate(origin, body.account_id)
      const cached = cachedResult(origin, body)
      const job = { task_id: body.task_id, account_id: body.account_id, origin, task: body, status: 'running', stage: 'opening', collected: 0,
        total: body.note_limit, items: [], error: '', error_code: '', retryable: false, updated_at: new Date().toISOString() }
      if (cached) Object.assign(job, { status: 'completed', stage: 'completed', items: cached.items, collected: cached.items.length,
        cached: true, cache_created_at: cached.cache_created_at || cached.updated_at })
      pendingJob = job
      jobs.delete(body.task_id)
      jobs.set(body.task_id, job)
      while (jobs.size > 50) jobs.delete(jobs.keys().next().value)
      await saveJobs()
      send(response, cached ? 200 : 202, publicJob(job), origin)
      if (cached) return
      void runJob(job)
      acquired = false
    } catch (error) {
      if (pendingJob) jobs.delete(pendingJob.task_id)
      send(response, Number.isInteger(error.status) ? error.status : 502, { error: error instanceof Error ? error.message : '无法启动采集任务。' }, origin)
    } finally { if (acquired) busy = false }
    return
  }
  if (request.method === 'POST' && request.url === '/control') {
    if (busy) { send(response, 409, { error: '采集器正在处理请求，完成后再切换采集器。' }, origin); return }
    busy = true
    try {
      const body = await readJson(request)
      if (typeof body?.enabled !== 'boolean') throw new Error('采集器状态参数无效。')
      if (body.enabled && pauseReason && body.confirmed !== true) {
        send(response, 409, { error: '采集已暂停。请先人工检查官方 App、原页面和网络，确认可继续后再开启。' }, origin); return
      }
      const nextReason = body.enabled ? '' : pauseReason
      await saveEnabledState(body.enabled, nextReason)
      enabled = body.enabled
      pauseReason = nextReason
      send(response, 200, { ready: true, enabled, pause_reason: pauseReason, browser_open: accounts.summary().accounts_open > 0, background: false, busy: false }, origin)
    } catch (error) {
      send(response, 502, { error: error instanceof Error ? error.message : '无法切换本机采集器状态。' }, origin)
    } finally {
      busy = false
    }
    return
  }
  if (request.method === 'POST' && request.url === '/open') {
    if (busy) { send(response, 409, { error: '采集器正在处理请求，完成后再打开登录窗口。' }, origin); return }
    busy = true
    try {
      const body = await readJson(request)
      await accounts.open(origin, body)
      send(response, 200, { ready: true, browser_open: true }, origin)
    } catch (error) {
      send(response, 502, { error: error instanceof Error ? error.message : '无法打开本机浏览器' }, origin)
    } finally {
      busy = false
    }
    return
  }
  if (request.method !== 'POST' || request.url !== '/collect') {
    send(response, 404, { error: '接口不存在' }, origin)
    return
  }
  if (!enabled) { send(response, 409, { error: '本机采集器已关闭，请先在工作台开启。' }, origin); return }
  if (busy) { send(response, 409, { error: '本机采集器正在处理另一个任务，请稍后重试。' }, origin); return }
  busy = true
  try {
    const task = await readJson(request)
    if (!validTask(task)) {
      send(response, 400, { error: '采集条件不完整或超出允许范围' }, origin)
      return
    }
    await accounts.validate(origin, task.account_id)
    const cached = cachedResult(origin, task)
    const items = cached ? cached.items : await accounts.collect(origin, task.account_id, task, page => extractCards(page, task))
    send(response, 200, { items }, origin)
  } catch (error) {
    const result = failure(error)
    await pauseAfterAccessFailure(result)
    log(`采集请求失败：${error instanceof Error ? error.message : '未知错误'}`)
    send(response, 502, error instanceof XhsAccessError ? result : { error: result.error }, origin)
  } finally {
    busy = false
  }
})

server.listen(port, host, () => {
  log(`小红书本机采集器已就绪：http://${host}:${port}`)
  log('采集使用所选账号的独立浏览器；首次使用请点击“登录小红书”手动登录。')
})

server.on('error', error => {
  log(`小红书本机采集器启动失败：${error.message}`)
  process.exitCode = 1
})

async function close() {
  server.close()
  await accounts.shutdown()
  process.exit(0)
}
process.on('SIGINT', close)
process.on('SIGTERM', close)
