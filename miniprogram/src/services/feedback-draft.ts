import type { FeedbackKind } from './experience'
import { readLocalDraft, writeLocalDraft } from './request-draft'

export interface FeedbackDraft { body: string; kind: FeedbackKind; paper: string }
const key = (owner: string) => 'lc-feedback-draft-v1:' + owner
export function cleanFeedbackDraft(value: unknown): FeedbackDraft {
  const input = value && typeof value === 'object' ? value as Partial<FeedbackDraft> : {}
  return {
    body: typeof input.body === 'string' ? input.body.slice(0, 2000) : '',
    kind: ['correction', 'download', 'membership', 'other'].includes(input.kind || '') ? input.kind! : 'other',
    paper: typeof input.paper === 'string' && /^[a-zA-Z0-9_-]{1,64}$/.test(input.paper) ? input.paper : '',
  }
}
export function readFeedbackDraft(owner: string) { return owner ? readLocalDraft(key(owner), cleanFeedbackDraft) : null }
export function writeFeedbackDraft(owner: string, value: FeedbackDraft) {
  const draft = cleanFeedbackDraft(value)
  return !!owner && writeLocalDraft(key(owner), draft, !!draft.body.trim())
}
/** 已提交的旧请求只能清理它自己的草稿，不能删除后来填写的内容。 */
export function clearSubmittedFeedback(owner: string, submitted: FeedbackDraft) {
  const saved = readFeedbackDraft(owner)
  if (!saved || saved.body !== submitted.body || saved.kind !== submitted.kind || saved.paper !== submitted.paper) return true
  return writeLocalDraft(key(owner), {}, false)
}
