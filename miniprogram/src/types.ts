export interface User {
  id: string; username: string; nickname?: string; avatar: string; avatar_url?: string | null; has_password: boolean; has_wechat?: boolean
  membership: 'regular' | 'vip'; is_vip: boolean
  vip_expires_at: number | null; membership_status: 'regular' | 'active' | 'expired'
}
export interface Question {
  id?: number
  type?: string
  stem?: string
  _stemHtml?: string
  _optsHtml?: string[]
  options?: string[]
  answer?: string | number | [number, number][]
  analysis?: string
  acceptable_answers?: string[]
  left_items?: string[]
  right_items?: string[]
  left_expr?: string
  right_expr?: string
  top?: string | number
  left?: string | number
  right?: string | number
}
export interface PaperSection {
  type: string
  name?: string
  warn?: string
  layout: Record<string, unknown>
  data: { questions: Question[]; passage?: string; [key: string]: unknown }
}
export interface Snapshot {
  schema_version: 1
  paper: {
    title: string; titleHtml?: string; grade: string; subject: string; keyword: string; difficulty: string
    sections: PaperSection[]; day?: number; hiddenElements?: string[]; footerOverride?: string
    [key: string]: unknown
  }
  template: Record<string, unknown>
  style: Record<string, unknown>
  export_options: { mode: 'student' | 'withAnswers' | 'answersOnly'; addDay: boolean; renderer_version: 'web-v1' }
}
export interface PaperSummary {
  tags?: import('./services/growth').CatalogTag[]
  can_view: boolean; can_download: boolean; required_view: 'free' | 'vip'; required_download: 'free' | 'vip'
  view_access: 'inherit' | 'free' | 'vip'; download_access: 'inherit' | 'free' | 'vip'; question_types: string[]
  scope?: 'catalog'; category?: string; description?: string; featured?: boolean; activity_at?: number
  id: string; source_id: string; version: number; title: string; grade: string; subject: string; keyword: string
  question_count: number; folder_id: string | null; folder_name: string | null; group_id: string; group_name: string
  favorite: boolean; file_status: 'pending' | 'uploading' | 'failed' | 'ready'; file_error: string; page_count: number
  created_at: number; updated_at: number; thumbnail_id: string | null; thumbnail_url: string | null
}
export interface Asset { id: string; kind: 'pdf' | 'page'; page_number: number; mime_type: string; byte_size: number; url: string }
export interface PrintEdition { kind: 'original' | 'student' | 'answers'; label: string; byte_size: number; mode: string; url?: string }
export interface PaperDetail extends PaperSummary { snapshot: Snapshot | null; assets: Asset[]; editions?: PrintEdition[]; release_number?: number; update_note?: string; versions?: { release_number: number; note: string; created_at: number }[] }
export interface CatalogSummary {
  papers: number; favorites: number; downloads: number
  grades: string[]; subjects: string[]; categories: SiteCategory[]
}
export interface SiteCategory { id: string; name: string; description: string; icon: string; paper_count?: number }
export type BannerTarget = 'none' | 'keyword' | 'category' | 'subject' | 'paper'
export interface SiteBanner {
  id: string; kicker: string; title: string; subtitle: string; action_label: string
  target_type: BannerTarget; target_value: string; image_url: string | null
  image_fit?: 'contain' | 'cover'
}
export interface SiteNotice { id: string; title: string; body: string; placement: 'popup' | 'banner'; level: 'info' | 'warning' }
export interface SiteHome {
  banners: SiteBanner[]
  notices: { popup: SiteNotice[]; banner: SiteNotice[] }
  categories: SiteCategory[]
  dictionaries: { grades: string[]; subjects: string[] }
}
export interface SiteDocument { key: string; title: string; body: string; updated_at: number }
export interface PaperList { items: PaperSummary[]; total: number; has_more: boolean }
export interface Authenticated { status: 'authenticated'; token: string; expires_at: number; user: User }
