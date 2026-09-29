// Local diagnostics deliberately contain no messages, stacks, URLs, IDs or payloads.
type DiagnosticKind = 'runtime' | 'promise' | 'network' | 'server' | 'memory' | 'update'
interface Diagnostic { kind: DiagnosticKind; minute: number; count: number }
const KEY = 'lc-diagnostics-v1'
const kinds = new Set<DiagnosticKind>(['runtime', 'promise', 'network', 'server', 'memory', 'update'])
const events: Diagnostic[] = []
let initialized = false
let connected = true
let networkRevision = 0
let persistTimer: ReturnType<typeof setTimeout> | undefined
export function flushDiagnostics() {
  clearTimeout(persistTimer); persistTimer = undefined
  try { uni.setStorage({ key: KEY, data: events.map(event => ({ ...event })), fail() {} }) } catch { /* 诊断不能中断应用。 */ }
}
export function recordDiagnostic(kind: DiagnosticKind) {
  if (!kinds.has(kind)) return
  const minute = Math.floor(Date.now() / 60000)
  const previous = events.find(event => event.kind === kind && event.minute === minute)
  if (previous) previous.count = Math.min(999, previous.count + 1)
  else events.push({ kind, minute, count: 1 })
  while (events.length > 40) events.shift()
  clearTimeout(persistTimer)
  persistTimer = setTimeout(flushDiagnostics, 500)
}
export function diagnosticSummary() {
  return JSON.stringify({ version: 1, events: events.map(event => ({ ...event })) })
}
export function initializeRuntime() {
  if (initialized) return
  initialized = true
  try {
    const saved: unknown = uni.getStorageSync(KEY)
    if (Array.isArray(saved)) for (const item of saved.slice(-40)) {
      if (item && kinds.has(item.kind) && Number.isInteger(item.minute) && Number.isInteger(item.count)) {
        events.push({ kind: item.kind, minute: item.minute, count: Math.max(1, Math.min(999, item.count)) })
      }
    }
  } catch { /* Diagnostics are optional. */ }
  uni.$on('lc-diagnostic', recordDiagnostic)
  const network = (online: boolean) => {
    const recovered = !connected && online
    connected = online
    uni.$emit('lc-network', online)
    if (recovered) uni.$emit('lc-network-restored')
  }
  uni.onNetworkStatusChange(result => { networkRevision++; network(result.isConnected) })
  const revision = networkRevision
  uni.getNetworkType({ success: result => { if (revision === networkRevision) network(result.networkType !== 'none') } })
  // #ifdef MP-WEIXIN
  uni.onMemoryWarning?.(() => { recordDiagnostic('memory'); uni.$emit('lc-memory-warning') })
  if (uni.canIUse('getUpdateManager')) {
    const manager = uni.getUpdateManager()
    manager.onUpdateReady(() => uni.showModal({
      title: '新版本已准备好', content: '现在重启小程序以使用新版本？请先完成正在填写的内容。',
      confirmText: '立即更新', cancelText: '稍后',
      success: result => { if (result.confirm) manager.applyUpdate() },
    }))
    manager.onUpdateFailed(() => { recordDiagnostic('update'); uni.showToast({ title: '更新下载失败，请稍后重新打开小程序', icon: 'none' }) })
  }
  // #endif
}
