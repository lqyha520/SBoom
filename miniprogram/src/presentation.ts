import type { PaperSummary, User } from './types'

/**
 * 年级/科目的展示顺序由后台「年级科目字典」决定：/catalog/summary 已按字典排好序，
 * 前端只做去重，不再按内置学制重排（否则运营在后台调的顺序会被前端覆盖）。
 */
export function subjectTone(subject: string) {
  return subject === '语文' ? 'language' : subject === '数学' ? 'math' : subject === '英语' ? 'english' : 'general'
}

export function exerciseText(value: string | null | undefined) {
  return (value || '').replace(/试卷/g, '习题').replace(/原卷/g, '原稿')
}

/** Imported originals may have pages but no counted questions. */
export function paperExtent(paper: Pick<PaperSummary, 'question_count' | 'page_count' | 'download_mode'>, compact = false) {
  if (paper.download_mode === 'external') return '网盘资料'
  if (compact && paper.question_count > 0) return `${paper.question_count} 题`
  return [paper.question_count > 0 ? `${paper.question_count} 题` : '', paper.page_count > 0 ? `${paper.page_count} 页` : ''].filter(Boolean).join(' · ') || 'PDF 资料'
}

export function paperAccess(paper: Pick<PaperSummary, 'required_view' | 'required_download' | 'download_mode'>) {
  if (paper.required_view === 'vip') return 'VIP 专享'
  if (paper.required_download === 'vip') return 'VIP 下载'
  return paper.download_mode === 'external' ? '免费获取' : '免费 PDF'
}

export function downloadAccessHint(paper: Pick<PaperSummary, 'required_view' | 'required_download' | 'download_mode'>) {
  if (paper.required_view === 'vip') return '预览与下载均需 VIP 会员'
  if (paper.required_download === 'vip') return '可免费预览，下载需 VIP 会员'
  return paper.download_mode === 'external' ? '登录后免费获取网盘链接' : '可免费预览，登录后免费下载'
}

export function exerciseTitle(paper: Pick<PaperSummary, 'title' | 'grade' | 'subject'>) {
  const title = exerciseText(paper.title)
  const grades = [paper.grade, paper.grade.replace(/^(小学|初中|高中)/, '')]
  for (const grade of grades) {
    const prefix = `${grade}${paper.subject} `
    if (title.startsWith(prefix) && title.slice(prefix.length).trim()) return title.slice(prefix.length).trim()
  }
  return title
}

export function difficultyLabel(value: string | null | undefined) {
  const labels: Record<string, string> = { easy: '基础', medium: '进阶', hard: '挑战', mixed: '综合' }
  return value ? labels[value] || value : '未标注'
}

export function subjectOptions(subjects: string[]) {
  const preferred = ['语文', '数学', '英语']
  return [...new Set(subjects)].sort((left, right) => {
    const rank = (value: string) => preferred.includes(value) ? preferred.indexOf(value) : preferred.length
    return rank(left) - rank(right)
  })
}

export function homeSelection(papers: PaperSummary[], offset: number) {
  if (!papers.length) return []
  const start = ((Math.trunc(offset) % papers.length) + papers.length) % papers.length
  return Array.from({ length: Math.min(2, papers.length) }, (_, index) => papers[(start + index) % papers.length]!)
}

export function membershipExpiry(user: User | null) {
  if (!user?.is_vip) return user?.membership_status === 'expired' ? '会员已到期' : '未开通 VIP'
  return user.vip_expires_at ? new Date(user.vip_expires_at * 1000).toLocaleDateString('zh-CN') + ' 到期' : '长期有效'
}

/** 「我的」页概览里那格很窄，只需要一个两三个字的短标签。 */
export function membershipBadge(user: User | null, now = Date.now()) {
  if (!user?.is_vip) return user?.membership_status === 'expired' ? '已到期' : '未开通'
  if (!user.vip_expires_at) return '长期'
  const days = Math.ceil((user.vip_expires_at * 1000 - now) / 86400000)
  return days > 0 ? `${days} 天` : '已到期'
}

/* ── 头像 ── */

export interface AvatarChoice { key: string; glyph: string; label: string; background: string; color: string; image?: string }

/**
 * 预设头像。key 必须和后端 app/models/mini.py 的 PROFILE_AVATARS 一致，
 * 新增时两端一起改。五个可选头像使用本地图片，历史头像保留 emoji 回退。
 */
export const AVATAR_CHOICES: AvatarChoice[] = [
  { key: 'fox', glyph: '🦊', label: '小狐狸', background: '#fdeee2', color: '#b3653a', image: '/static/avatars/fox.png' },
  { key: 'panda', glyph: '🐼', label: '小熊猫', background: '#eef1f4', color: '#55606d', image: '/static/avatars/panda.png' },
  { key: 'penguin', glyph: '🐧', label: '小企鹅', background: '#e8f1fa', color: '#3f6f9c', image: '/static/avatars/penguin.png' },
  { key: 'deer', glyph: '🦌', label: '小鹿', background: '#f4ecdf', color: '#8a6a3f', image: '/static/avatars/deer.png' },
  { key: 'rabbit', glyph: '🐰', label: '小兔子', background: '#fdeef4', color: '#b3567f', image: '/static/avatars/rabbit.png' },
  { key: 'koala', glyph: '🐨', label: '小考拉', background: '#edf0f7', color: '#4f6183' },
  { key: 'owl', glyph: '🦉', label: '小猫头鹰', background: '#f0ecf9', color: '#6b5399' },
  { key: 'dolphin', glyph: '🐬', label: '小海豚', background: '#e6f3f6', color: '#2f7a8c' },
  { key: 'tiger', glyph: '🐯', label: '小老虎', background: '#fdf1e0', color: '#b8791f' },
  { key: 'frog', glyph: '🐸', label: '小青蛙', background: '#eaf5e6', color: '#4f8a3c' },
  { key: 'bee', glyph: '🐝', label: '小蜜蜂', background: '#fdf6da', color: '#9a7a13' },
  { key: 'octopus', glyph: '🐙', label: '小章鱼', background: '#f9ecf2', color: '#a34b76' },
  { key: 'cat', glyph: '🐱', label: '小猫', background: '#fdf0e6', color: '#b06a35' },
  { key: 'whale', glyph: '🐳', label: '小鲸鱼', background: '#e9eefa', color: '#4a63a8' },
  { key: 'turtle', glyph: '🐢', label: '小乌龟', background: '#e8f4ec', color: '#3f7f5a' },
  { key: 'squirrel', glyph: '🐿️', label: '小松鼠', background: '#f7ecdf', color: '#96603a' },
]

/** Five visible presets; historical choices remain readable for existing users. */
export const DEFAULT_AVATAR_CHOICES = AVATAR_CHOICES.slice(0, 5)

export function avatarChoice(key: string | null | undefined) {
  return AVATAR_CHOICES.find(choice => choice.key === key) || null
}

export interface AvatarLook { glyph: string; initial: string; background: string; color: string; preset: boolean }

/**
 * 头像的最终呈现：选了预设就用预设的图案与配色；没选则回退到「首字 + 由账号
 * id 派生的稳定配色」——同一账号每次进来颜色一致，不同账号彼此区分，不用配图。
 */
export function profileAvatar(user: Pick<User, 'id' | 'username' | 'nickname' | 'avatar'> | null): AvatarLook {
  const initial = (Array.from((user?.nickname || user?.username || '').trim())[0] || '').toUpperCase()
  const choice = avatarChoice(user?.avatar)
  if (choice) return { glyph: choice.glyph, initial, background: choice.background, color: choice.color, preset: true }
  let hue = 0
  for (const char of user?.id || '') hue = (hue * 31 + char.charCodeAt(0)) % 360
  return { glyph: '', initial, background: `hsl(${hue}, 44%, 92%)`, color: `hsl(${hue}, 32%, 36%)`, preset: false }
}
