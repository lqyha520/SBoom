import { request } from './api'
import { referralQuery, type ReferralFilters } from './referrals'
import type { ApiResponse, ApiSchemas } from '../../shared/api-schema'

export type ConversionFilters = Pick<ReferralFilters, 'admin_id' | 'start_date' | 'end_date' | 'campaign_id'>
export type ConversionCounts = ApiSchemas['ConversionCounts']
export type ConversionGroup = ApiSchemas['ConversionGroup']
export type ConversionData = ApiResponse<'GET /api/v1/admin/referrals/conversion'>
export const getConversion = (filters: ConversionFilters, page = 1) => request<ConversionData>('/api/v1/admin/referrals/conversion?' + referralQuery(filters) + '&page=' + page)
export const conversionPercent = (value: number | null) => value === null ? '—' : `${(value / 100).toFixed(2)}%`
