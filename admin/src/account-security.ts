import { request } from './api'

export interface AdminSession {
  id: string; created_at: number; last_seen_at: number; expires_at: number
  revoked_at: number; user_agent: string; client_ip: string; current: boolean
}
export interface MfaSetup { secret: string; otpauth_url: string }
export const mfaStatus = () => request<{ enabled: boolean }>('/api/v1/auth/mfa/status')
export const setupMfa = () => request<MfaSetup>('/api/v1/auth/mfa/setup', { method: 'POST' })
export const changeMfa = (action: 'confirm' | 'disable', code: string) => request<{ enabled: boolean }>(`/api/v1/auth/mfa/${action}`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code }),
})
export const listSessions = () => request<{ sessions: AdminSession[] }>('/api/v1/admin/sessions')
export const revokeSession = (id: string) => request<void>(`/api/v1/admin/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' })
