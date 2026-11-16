import { request } from './api'
import { downloadBlob } from '../../shared/download'
import type { ApiSchemas } from '../../shared/api-schema'

export type FinanceLedgerEntry = ApiSchemas['FinanceLedgerEntry']
export type FinanceLedgerInput = ApiSchemas['FinanceLedgerInput']
export type FinanceLedgerPage = ApiSchemas['FinanceLedgerPage']
function query(params: Record<string, string | number>) { return new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])) }
export const financeLedger = (params: Record<string, string | number> = {}) => request<FinanceLedgerPage>('/api/v1/admin/finance-ledger?' + query(params))
export const createFinanceLedger = (body: FinanceLedgerInput) => request<FinanceLedgerEntry>('/api/v1/admin/finance-ledger', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
export const updateFinanceLedger = (identifier: string, body: FinanceLedgerInput & { revision: number }) => request<FinanceLedgerEntry>('/api/v1/admin/finance-ledger/' + encodeURIComponent(identifier), { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
export const voidFinanceLedger = (item: FinanceLedgerEntry) => request<FinanceLedgerEntry>('/api/v1/admin/finance-ledger/' + encodeURIComponent(item.identifier!) + '/void?revision=' + item.revision, { method: 'POST' })
export async function exportFinanceLedger(params: Record<string, string | number>) {
  const blob = await request<Blob>('/api/v1/admin/finance-ledger/export.csv?' + query(params), undefined, 'blob')
  downloadBlob(blob, '经营账本.csv')
}
export function moneyFen(value: string): number {
  if (!/^\d+(\.\d{1,2})?$/.test(value.trim())) throw new Error('金额最多填写两位小数')
  const [whole, fraction = ''] = value.trim().split('.')
  const fen = Number(whole) * 100 + Number(fraction.padEnd(2, '0'))
  if (!Number.isSafeInteger(fen) || fen > 10_000_000_000) throw new Error('金额超出允许范围')
  return fen
}