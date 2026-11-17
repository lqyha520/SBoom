import { request } from './api'
import { change } from './growth'
import { downloadBlob } from '../../shared/download'
export interface Campaign { spend_fen?: number | null; landing_kind?: 'home' | 'topic' | 'paper'; landing_id?: string; id: string; admin_id: number; admin_name: string; code: string; name: string; source: string; active: boolean; budget_fen: number | null; revision: number; path: string; registrations: number; paying_users: number; reward_fen: number; unknown: number; reward_known?: number; budget_reached: boolean }
export interface Budget { revision: number; budget_fen: number | null; used_fen: number; unknown: number; reward_known?: number; reached: boolean }
const base = '/api/v1/admin/referrals'
export const campaigns = (admin?: number, filters: Record<string, string> = {}) => request<{ items: Campaign[]; total: number; page: number }>(base + '/campaigns?' + new URLSearchParams({ ...filters, ...(admin ? { admin_id: String(admin) } : {}) }))
export const createCampaign = (actor: number, value: { admin_id: number; name: string; source: string; budget_fen: number | null; spend_fen?: number | null; landing_kind?: string; landing_id?: string }) => change<Campaign>(base + '/campaigns', actor, value)
export const updateCampaign = (actor: number, item: Campaign, value: { name: string; source: string; budget_fen: number | null; active: boolean; spend_fen?: number | null; landing_kind?: string; landing_id?: string }) => change<Campaign>(base + '/campaigns/' + item.id, actor, { ...value, admin_id: item.admin_id, revision: item.revision }, 'PUT')
export const loadBudget = (id: number) => request<Budget>(base + '/budget/' + id)
export const saveBudget = (actor: number, id: number, value: Budget, amount: number | null) => change<Budget>(base + '/budget/' + id, actor, { revision: value.revision, budget_fen: amount }, 'PUT')
export async function campaignQr(actor: number, id: string, version: string) {
  const blob = await request<Blob>(base + '/qrcode', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Workspace-User': String(actor) }, body: JSON.stringify({ campaign_id: id, env_version: version }) }, 'blob')
  return blob
}

export async function downloadCampaign(actor: number, id: string, version: string) {
  const blob = await campaignQr(actor, id, version)
  downloadBlob(blob, '活动推广码-' + id + (blob.type.includes('jpeg') ? '.jpg' : '.png'))
}
export interface CampaignPerformance {
  campaign: Campaign; income: import('./referrals').ReferralSummary; spend_fen: number | null;
  known_spend_fen?: number; remainder_fen: number | null; return_bps: number | null;
  trend: { day: string; paid_fen: number; paying_users: number }[];
}
export const campaignPerformance = (id: string) => request<CampaignPerformance>(base + '/campaigns/' + id + '/performance')
export interface Acquisition { visits: number; started: number; registered: number; paid: number; tracking_since: number; as_of: number }
export const acquisition = (filters: import('./referral-conversion').ConversionFilters) => request<Acquisition>(base + '/acquisition?' + new URLSearchParams(Object.entries(filters).filter(([, value]) => value !== undefined) as [string, string][]))
