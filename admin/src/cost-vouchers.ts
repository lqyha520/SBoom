import { request } from './api'
import { change } from './growth'
import { downloadBlob } from '../../shared/download'
import type { Attachment } from './settlement-operations'
export interface CostVoucher { id: string; admin_id: number; reference: string; name: string; total_fen: number; evidence: string; revision: number; expense_fen: number; deduction_fen: number; expense_remaining_fen: number; deduction_remaining_fen: number; count: number; entries: { kind: string; id: string; amount_fen: number; source_ref: string }[]; files: Attachment[] }
export type CostVoucherInput = Pick<CostVoucher, 'admin_id' | 'reference' | 'name' | 'total_fen' | 'evidence' | 'revision'>
const base = '/api/v1/admin/settlements/cost-vouchers'
export const costVouchers = (owner: number | undefined, q: string, page: number) => request<{ items: CostVoucher[]; total: number; page: number }>(base + '?' + new URLSearchParams({ q, page: String(page), ...(owner ? { admin_id: String(owner) } : {}) }))
export const saveCostVoucher = (actor: number, value: CostVoucherInput, id?: string) => change<CostVoucher>(base + (id ? '/' + id : ''), actor, value, id ? 'PUT' : 'POST')
export async function uploadCostVoucher(actor: number, id: string, file: File) {
  if (file.size > 2 * 1024 * 1024) throw new Error('凭据附件限 2MB')
  return request(base + '/' + id + '/files?name=' + encodeURIComponent(file.name), { method: 'POST', headers: { 'Content-Type': 'application/octet-stream', 'X-Workspace-User': String(actor) }, body: file })
}
export async function downloadCostVoucher(file: Attachment) { downloadBlob(await request<Blob>('/api/v1/admin/settlements/cost-voucher-files/' + file.id, undefined, 'blob'), file.name) }
