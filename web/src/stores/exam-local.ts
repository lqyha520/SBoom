import { DEFAULT_LAYOUT, LS } from '../constants'
import type { Difficulty, GameData, MyTemplate, PaperStyle, Question } from '../types'
import { CIRCLED_NO } from '../utils'
import { userPrefix } from './auth'

export const K = (owner: string, key: string): string => userPrefix(owner || 'guest') + key

export function safeSet(key: string, val: string): boolean {
  try {
    localStorage.setItem(key, val)
    return true
  } catch (e) {
    console.warn('本地存储写入失败（可能超出配额，可清理旧模板后重试）：', key, e)
    return false
  }
}

export function load<T>(owner: string, key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(K(owner, key))
    return raw ? { ...fallback, ...JSON.parse(raw) } : fallback
  } catch {
    return fallback
  }
}

export function loadArr<T>(owner: string, key: string): T[] {
  try {
    const value = JSON.parse(localStorage.getItem(K(owner, key)) || '[]')
    return Array.isArray(value) ? value : []
  } catch {
    return []
  }
}

export function migrateMyTemplates(raw: any[]): MyTemplate[] {
  return (raw || [])
    .filter((t) => t && t.name)
    .map((t) => ({
      name: t.name,
      _revision: Number.isInteger(t._revision) ? t._revision : 0,
      _syncState: t._syncState || (t._revision ? 'synced' : 'pending'),
      _syncError: t._syncError || '',
      grade: t.grade || '',
      subject: t.subject || '',
      keyword: t.keyword || '',
      title: t.title || '',
      titleHtml: t.titleHtml || undefined,
      difficulty: (t.difficulty || 'medium') as Difficulty,
      templateId: t.templateId || 'exam',
      style: t.style || undefined,
      hiddenElements: t.hiddenElements || [],
      cards: (t.cards || []).map((c: any) => ({
        type: c.type,
        name: c.name,
        count: c.count ?? 1,
        layout: { ...DEFAULT_LAYOUT, ...(c.layout || c._layout || {}) },
      })),
      // V2 完整数据原样保留（含每题富文本）
      sections: t.sections || undefined,
      paperSnapshot: t.paperSnapshot || undefined,
    }))
}

export function applyOldSnapshot(cards: { type: string; count: number; data: GameData }[], snapshot: string): void {
  try {
    const doc = new DOMParser().parseFromString(snapshot, 'text/html')
    const blocks = doc.querySelectorAll('.sec-block')
    cards.forEach((card, ci) => {
      const block = blocks[ci]
      if (!block) return
      const qEls = block.querySelectorAll('.q')
      qEls.forEach((qEl, qi) => {
        if (qi >= card.count) return
        const existing = card.data.questions[qi]
        const q: Question = existing || { type: card.type === 'quiz' || card.type === 'challenge' ? 'multiple_choice' : card.type }
        const stemEl = qEl.querySelector('[data-e="stem"]')
        if (stemEl) {
          const t = (stemEl.textContent || '')
            .replace(CIRCLED_NO, '')
            .replace(/^\[第\d+关\]\s*/, '')
            .trim()
          if (t) q.stem = t
        }
        const optsEl = qEl.querySelector('[data-e="opts"]')
        if (optsEl) {
          const lines = Array.from(optsEl.children)
            .map((d) => (d.textContent || '').replace(/^[A-H][.、：:．]\s*/, '').trim())
            .filter(Boolean)
          if (lines.length) q.options = lines
        }
        if (!existing && (q.stem || q.options?.length)) card.data.questions.push(q)
      })
    })
  } catch {
    /* 无法读取的内容保持缺失，不编造题目或答案。 */
  }
}

export function migratePaperStyle(owner: string): Partial<PaperStyle> | null {
  try {
    if (localStorage.getItem(K(owner, LS.paperStyle))) return null
    if (localStorage.getItem('lc_legacy_owner') !== owner) return null
    const bg = JSON.parse(localStorage.getItem('lc_paper_bg') || 'null')
    const kid = JSON.parse(localStorage.getItem('lc_paper_kid') || 'null')
    if (!bg && !kid) return null
    const out: Partial<PaperStyle> = {}
    if (bg) {
      if (bg.style != null) out.bg = bg.style
      if (bg.opacity != null) out.bgOpacity = bg.opacity
      if (bg.banner != null) out.banner = bg.banner
      if (bg.secColor != null) out.secColor = bg.secColor
      if (bg.exportBg != null) out.exportBg = bg.exportBg
    }
    if (kid) {
      if (kid.frame != null) out.frame = kid.frame
      if (kid.encourage != null) out.encourage = kid.encourage
      if (kid.reward != null) out.reward = kid.reward
      if (kid.font === 'on' || kid.font === 'auto') out.kidFont = kid.font
    }
    return Object.keys(out).length ? out : null
  } catch {
    return null
  }
}

export const STYLE_DEFAULTS: PaperStyle = {
  bg: 'none',
  bgOpacity: 70,
  banner: false,
  secColor: false,
  frame: 'none',
  encourage: false,
  reward: false,
  kidFont: 'off',
  exportBg: false,
  titleScale: 1,
  titleOffsetY: 0,
}

export const styleSaveTimers = new WeakMap<object, ReturnType<typeof setTimeout>>()
