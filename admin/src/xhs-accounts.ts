import { assistRequest } from './xhs-publish-assist'
export interface AccountProfile { audience: string; direction: string; style: string; topics: string }
export interface AccountSnapshot extends AccountProfile { id: string; name: string }
export const emptyAccountProfile = (): AccountProfile => ({ audience: '', direction: '', style: '', topics: '' })
export const emptyAccountSnapshot = (): AccountSnapshot => ({ id: '', name: '', ...emptyAccountProfile() })
export interface XhsAccount { id: string; name: string; note: string; revision: number; archived: boolean; created_at: string; browser_open: boolean; busy: boolean; profile?: AccountProfile }
export const listXhsAccounts = () => assistRequest<{ items: XhsAccount[]; profile_support?: boolean }>('/accounts')
export const addXhsAccount = (data: { name: string; note: string; request_id: string; profile?: AccountProfile }) => assistRequest<{ account: XhsAccount }>('/accounts/add', data)
export const updateXhsAccount = (data: { account_id: string; revision: number; name: string; note: string; archived: boolean; profile?: AccountProfile }) => assistRequest<{ account: XhsAccount }>('/accounts/update', data)
export const openXhsAccount = (account_id: string) => assistRequest<{ account: XhsAccount }>('/accounts/open', { account_id })
export const openXhsNote = (account_id: string, url: string) => assistRequest<{ account: XhsAccount }>('/accounts/open-note', { account_id, url })
export const closeXhsAccount = (account_id: string) => assistRequest<{ account: XhsAccount }>('/accounts/close', { account_id, acknowledged: true })
