import { request } from './api'
import type { Page } from './catalog'

export interface MiniUser {
  id: string; username: string; nickname?: string; avatar: string; avatar_url?: string | null; has_password: boolean
  membership: 'regular' | 'vip'; is_vip: boolean
  membership_status: 'regular' | 'active' | 'expired'; vip_expires_at: number | null
  is_active: boolean; revision: number; created_at: number; updated_at: number
  login_method: 'wechat' | 'password'
}
/** 预设头像的图案与名称。键表与 app/models/mini.py 的 PROFILE_AVATARS、小程序 presentation.ts 保持一致 */
export const AVATAR_CHOICES: { key: string; glyph: string; label: string }[] = [
  { key: 'fox', glyph: '🦊', label: '小狐狸' }, { key: 'panda', glyph: '🐼', label: '小熊猫' },
  { key: 'penguin', glyph: '🐧', label: '小企鹅' }, { key: 'deer', glyph: '🦌', label: '小鹿' },
  { key: 'rabbit', glyph: '🐰', label: '小兔子' }, { key: 'koala', glyph: '🐨', label: '小考拉' },
  { key: 'owl', glyph: '🦉', label: '小猫头鹰' }, { key: 'dolphin', glyph: '🐬', label: '小海豚' },
  { key: 'tiger', glyph: '🐯', label: '小老虎' }, { key: 'frog', glyph: '🐸', label: '小青蛙' },
  { key: 'bee', glyph: '🐝', label: '小蜜蜂' }, { key: 'octopus', glyph: '🐙', label: '小章鱼' },
  { key: 'cat', glyph: '🐱', label: '小猫' }, { key: 'whale', glyph: '🐳', label: '小鲸鱼' },
  { key: 'turtle', glyph: '🐢', label: '小乌龟' }, { key: 'squirrel', glyph: '🐿️', label: '小松鼠' },
]
const AVATAR_GLYPHS: Record<string, string> = Object.fromEntries(AVATAR_CHOICES.map(choice => [choice.key, choice.glyph]))
/** 没选头像的账号返回空串，由前端回退到「昵称首字」展示。 */
export function avatarGlyph(key: string | null | undefined) { return AVATAR_GLYPHS[key || ''] || '' }
export interface MembershipEdit {
  revision: number; membership: 'regular' | 'vip'; vip_expires_at: number | null; is_active: boolean
}
/** 管理员改小程序用户资料。三个字段都可选，只提交真正要改的；new_password 为重置密码（无需原密码） */
export interface MiniProfileEdit {
  revision: number; nickname?: string; avatar?: string; new_password?: string
}
export interface TypeRule {
  question_type: string; label: string; paper_count: number; view_access: 'free' | 'vip'
  download_access: 'free' | 'vip'; revision: number; updated_at: number
}
function mutation(method: string, adminId: number, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json', 'X-Workspace-User': String(adminId) }, body: JSON.stringify(body) }
}
export function miniUsers(q: string, membership: string, offset: number) {
  return request<Page<MiniUser>>('/api/v1/admin/mini-users?' + new URLSearchParams({ q, membership, offset: String(offset), limit: '20' }))
}
export function createMiniUser(adminId: number, username: string, password: string) {
  return request<MiniUser>('/api/v1/admin/mini-users', mutation('POST', adminId, { username, password }))
}
export function updateMembership(adminId: number, id: string, body: MembershipEdit) {
  return request<MiniUser>('/api/v1/admin/mini-users/' + encodeURIComponent(id), mutation('PUT', adminId, body))
}
export function updateMiniProfile(adminId: number, id: string, body: MiniProfileEdit) {
  return request<MiniUser>('/api/v1/admin/mini-users/' + encodeURIComponent(id), mutation('PATCH', adminId, body))
}
export interface MiniDeleteResult { status: string; username: string; removed: Record<string, number> }
export function deleteMiniUser(adminId: number, id: string) {
  return request<MiniDeleteResult>('/api/v1/admin/mini-users/' + encodeURIComponent(id), mutation('DELETE', adminId, undefined))
}
export function typeRules() { return request<{ items: TypeRule[] }>('/api/v1/admin/catalog/type-rules') }
export function updateTypeRule(adminId: number, rule: TypeRule) {
  return request<TypeRule>('/api/v1/admin/catalog/type-rules/' + encodeURIComponent(rule.question_type), mutation('PUT', adminId, {
    revision: rule.revision, view_access: rule.view_access, download_access: rule.download_access,
  }))
}
