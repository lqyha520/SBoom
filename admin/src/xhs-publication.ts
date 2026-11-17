import { request } from './api'
import { cleanWorkflowData, type PublicationData, type WorkflowRecord } from './xhs-workflow'

export const publicationChecks = [
  { key: 'rights_checked', label: '已确认文字、图片、视频和资料的原创或使用授权' },
  { key: 'truth_checked', label: '已核对事实与题目答案，删除无法证明的效果承诺' },
  { key: 'privacy_checked', label: '已检查个人信息、未成年人信息和图片中的隐私' },
  { key: 'media_checked', label: '已逐张检查实际上传的图片或视频及其文字' },
  { key: 'platform_checked', label: '已核对平台最新规则及商业合作、AI 内容等所需标识' },
] as const
export interface PublicationCheckResult {
  blockers: string[]
  findings: { code: string; title: string; message: string; evidence: string[] }[]
  duplicates: { id: string; title: string }[]
  notice: string
}
export const checkPublication = (data: PublicationData, record_id?: string, parent_id?: string) => request<PublicationCheckResult>('/api/v1/admin/xhs-workflow/publication-check', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ data: cleanWorkflowData(data), record_id, parent_id }),
})
export const refreshPublicationDraft = (id: string, revision: number) => request<WorkflowRecord<PublicationData>>(`/api/v1/admin/xhs-workflow/publications/${id}/refresh-draft`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ revision }),
})
