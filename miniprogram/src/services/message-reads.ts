import { reactive } from 'vue'
import { authGeneration } from './api'
import { inboxState, readMessages, unreadTracker, type Message } from './growth'

export const readSync = reactive({ pending: 0, busy: false, error: '' })
let epoch = -1
let pending = new Map<string, number>()
let confirmed = new Map<string, number>()
let running: Promise<void> | null = null
function scope() {
  if (epoch === authGeneration()) return
  epoch = authGeneration(); pending = new Map(); confirmed = new Map(); running = null
  readSync.pending = inboxState.pending = 0; readSync.busy = false; readSync.error = ''
}

/** Reading content never waits for the idempotent read receipt. */
export function markMessageRead(message: Message) {
  scope()
  if (message.read_at) return
  const queued = pending.get(message.id)
  if (queued) { message.read_at = queued; void syncMessageReads(); return }
  const timestamp = Date.now() / 1000
  unreadTracker.changed()
  pending.set(message.id, timestamp); message.read_at = timestamp
  readSync.pending = inboxState.pending = pending.size
  inboxState.unread = Math.max(0, inboxState.unread - 1)
  void syncMessageReads()
}

export function applyPendingReads(items: Message[], unread: number, apply = unreadTracker.read()) {
  scope()
  for (const message of items) {
    // A lost write response can still have succeeded on the server.
    if (message.read_at) { pending.delete(message.id); confirmed.delete(message.id); continue }
    const timestamp = pending.get(message.id) || confirmed.get(message.id)
    if (timestamp) message.read_at = timestamp
  }
  readSync.pending = inboxState.pending = pending.size
  if (!pending.size) readSync.error = ''
  apply(unread, pending.size)
}

export function syncMessageReads(): Promise<void> {
  scope()
  if (running) return running
  if (!pending.size) return Promise.resolve()
  const generation = epoch, queue = pending
  readSync.busy = true; readSync.error = ''
  const work = Promise.resolve().then(async () => {
    while (queue.size && generation === authGeneration()) {
      const id = queue.keys().next().value!
      try {
        await readMessages(id, () => queue.size - Number(queue.has(id)))
        if (generation !== authGeneration()) return
        // 保留有限的近期确认标记，合并写入完成后才到达的旧列表。
        const timestamp = queue.get(id)
        if (timestamp) confirmed.set(id, timestamp)
        if (confirmed.size > 500) confirmed.delete(confirmed.keys().next().value!)
        queue.delete(id); readSync.pending = inboxState.pending = queue.size
      } catch {
        if (generation === authGeneration()) readSync.error = '已读状态暂未同步，不影响查看消息'
        return
      }
    }
  }).finally(() => {
    if (running === work) { running = null; readSync.busy = false }
  })
  running = work
  return work
}

export async function markAllMessagesRead() {
  scope()
  const generation = epoch
  await syncMessageReads()
  if (generation !== authGeneration()) return
  await readMessages()
  if (generation !== authGeneration()) return
  pending.clear(); readSync.pending = inboxState.pending = 0; readSync.error = ''
}
