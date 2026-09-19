import { reactive } from 'vue'
import { authGeneration } from './api'
import { inboxState, readMessages, type Message } from './growth'

export const readSync = reactive({ pending: 0, busy: false, error: '' })
let epoch = -1
let pending = new Map<string, number>()
let running: Promise<void> | null = null
function scope() {
  if (epoch === authGeneration()) return
  epoch = authGeneration(); pending = new Map(); running = null
  readSync.pending = 0; readSync.busy = false; readSync.error = ''
}

/** Reading content never waits for the idempotent read receipt. */
export function markMessageRead(message: Message) {
  scope()
  if (message.read_at) return
  const queued = pending.get(message.id)
  if (queued) { message.read_at = queued; void syncMessageReads(); return }
  const timestamp = Date.now() / 1000
  pending.set(message.id, timestamp); message.read_at = timestamp
  readSync.pending = pending.size
  inboxState.unread = Math.max(0, inboxState.unread - 1)
  void syncMessageReads()
}

export function applyPendingReads(items: Message[], unread: number) {
  scope()
  for (const message of items) {
    // A lost write response can still have succeeded on the server.
    if (message.read_at) { pending.delete(message.id); continue }
    const timestamp = pending.get(message.id)
    if (timestamp) message.read_at = timestamp
  }
  readSync.pending = pending.size
  if (!pending.size) readSync.error = ''
  inboxState.unread = Math.max(0, unread - pending.size)
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
        await readMessages(id)
        if (generation !== authGeneration()) return
        queue.delete(id); readSync.pending = queue.size
        inboxState.unread = Math.max(0, inboxState.unread - queue.size)
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
  pending.clear(); readSync.pending = 0; readSync.error = ''
}
