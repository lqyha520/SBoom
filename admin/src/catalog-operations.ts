import { request } from './api'
import type { HealthPage, LinkCheck, ScheduleItem, SchedulePage } from '../../shared/teaching'
export const getSchedules = (offset = 0, status = '') => request<SchedulePage>('/api/v1/admin/catalog/schedules?' + new URLSearchParams({ offset: String(offset), status }))
export const getSchedule = (id: string) => request<ScheduleItem | null>('/api/v1/admin/catalog/schedules/' + id)
export const saveSchedule = (id: string, catalog_revision: number, schedule_revision: number, scheduled_at: number) => request<ScheduleItem>('/api/v1/admin/catalog/schedules/' + id, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ catalog_revision, schedule_revision, scheduled_at, confirm_publication: true }) })
export const cancelSchedule = (item: ScheduleItem) => request<void>(`/api/v1/admin/catalog/schedules/${item.catalog_id}?revision=${item.revision}`, { method: 'DELETE' })
export const getCatalogHealth = (q = '', offset = 0, onlyIssues = false, category = '') => request<HealthPage>('/api/v1/admin/catalog/health?' + new URLSearchParams({ q, offset: String(offset), only_issues: String(onlyIssues), category }), {}, 'json', 60000)
export const probeCatalogLink = (id: string, manual = false) => request<LinkCheck>(`/api/v1/admin/catalog/health/${id}/${manual ? 'confirm' : 'probe'}`, { method: 'POST' }, 'json', 20000)
export function localDateTime(epoch: number) {
  const date = new Date(epoch * 1000)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}
