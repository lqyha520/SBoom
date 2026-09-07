import { defineStore } from 'pinia'
import {
  DEFAULT_LAYOUT,
  LS,
  TEMPLATES,
  TYPE_DEFAULT,
  TYPE_GROUPS_BY_GRADE,
  TYPE_GROUPS_DEFAULT,
} from '../constants'
import * as api from '../api'
import type {
  CustomType,
  Difficulty,
  GameData,
  MyTemplate,
  PaperData,
  PaperStyle,
  PaperTemplate,
  ScopeData,
  SecLayout,
  Section,
} from '../types'
import { ensureQids, gradeNumOf, mockQuestions, uid } from '../utils'
import { UID_KEY, userPrefix } from './auth'

/** 当前登录用户的 localStorage 命名空间前缀（多用户数据隔离） */
const _uid = localStorage.getItem(UID_KEY) || ''
const K = (k: string): string => (_uid ? userPrefix(_uid) + k : k)

function load<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(K(key))
    return raw ? { ...fallback, ...JSON.parse(raw) } : fallback
  } catch {
    return fallback
  }
}
function loadArr<T>(key: string): T[] {
  try {
    return JSON.parse(localStorage.getItem(K(key)) || '[]')
  } catch {
    return []
  }
}

/** 兼容旧版保存的「我的模板」格式（cards._layout、缺 difficulty/templateId、paperSnapshot） */
function migrateMyTemplates(raw: any[]): MyTemplate[] {
  return (raw || [])
    .filter(t => t && t.name)
    .map(t => ({
      name: t.name,
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
        count: c.count ?? 1,
        layout: { ...DEFAULT_LAYOUT, ...(c.layout || c._layout || {}) },
      })),
      // V2 完整数据原样保留（含每题富文本）
      sections: t.sections || undefined,
      paperSnapshot: t.paperSnapshot || undefined,
    }))
}

/** 解析旧版 paperSnapshot DOM，把编辑过的题干/选项文字回填到 mock 题目上 */
function applyOldSnapshot(cards: { type: string; count: number; data: GameData }[], snapshot: string): void {
  try {
    const doc = new DOMParser().parseFromString(snapshot, 'text/html')
    const blocks = doc.querySelectorAll('.sec-block')
    cards.forEach((card, ci) => {
      const block = blocks[ci]
      if (!block) return
      const qEls = block.querySelectorAll('.q')
      qEls.forEach((qEl, qi) => {
        const q = card.data.questions[qi]
        if (!q) return
        const stemEl = qEl.querySelector('[data-e="stem"]')
        if (stemEl && q.stem != null) {
          const t = stemEl.textContent || ''
            .replace(/^[①-㊿]\s*/, '')
            .replace(/^\[第\d+关\]\s*/, '')
            .trim()
          if (t) q.stem = t
        }
        const optsEl = qEl.querySelector('[data-e="opts"]')
        if (optsEl && q.options) {
          const lines = Array.from(optsEl.children)
            .map(d => (d.textContent || '').replace(/^[A-H][.、：:．]\s*/, '').trim())
            .filter(Boolean)
          if (lines.length) q.options = lines
        }
      })
    })
  } catch { /* 解析失败保持 mock */ }
}

/** 旧版装饰设置迁移：lc_paper_bg + lc_paper_kid → 统一的 paper style（只读全局旧键） */
function migratePaperStyle(): Partial<PaperStyle> | null {
  if (localStorage.getItem(K(LS.paperStyle))) return null // 新格式已存在，不迁移
  try {
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

const STYLE_DEFAULTS: PaperStyle = {
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
}

export const useExamStore = defineStore('exam', {
  state: () => {
    // 恢复自定义模板的持久化配置
    const customTpl = TEMPLATES.find(t => t.id === 'custom')!
    try {
      const savedCustom = JSON.parse(localStorage.getItem(K(LS.customTemplate)) || 'null')
      if (savedCustom) Object.assign(customTpl, savedCustom)
    } catch { /* ignore */ }
    let templateId = 'exam'
    try {
      const p = JSON.parse(localStorage.getItem(K(LS.template)) || 'null')
      if (p?.id && TEMPLATES.some(t => t.id === p.id)) templateId = p.id
    } catch { /* ignore */ }

    return {
      /* 当前视图：搭建 | 结果 */
      view: 'build' as 'build' | 'result',

      /* 基础数据 */
      available: {} as Record<string, string[]>,
      availableLoading: false,
      availableError: '',
      scope: null as ScopeData | null,
      scopeLoading: false,

      /* 出题条件 */
      grade: '',
      subject: '',
      keyword: '',
      selectedTags: [] as string[],
      title: '',
      /** 标题富文本（排版模式改色/加粗后缓存，改标题文字时清空） */
      titleHtml: '' as string,
      difficulty: 'medium' as Difficulty,
      /** 搭建态预览中被删除的卷头/卷尾元素（notice/inforow/footer/reward/title/subline/banner） */
      hiddenElements: [] as string[],

      /* 搭建区 */
      sections: [] as Section[],

      /* 生成结果 */
      papers: [] as PaperData[],
      generating: false,
      generateError: '',
      /** 生成进度文案（如：正在生成第 2/5 份…） */
      generateProgress: '',

      /* 预览 */
      showAnswers: false,
      layoutMode: false,

      /* 批量 */
      paperCount: 1,
      addDayLabel: true,

      /* 卷面配置 */
      templateId,
      style: (() => {
        const s = load<PaperStyle>(LS.paperStyle, STYLE_DEFAULTS)
        // 大字号不再默认跟随年级：已存的 auto 归一为 off
        if (s.kidFont === 'auto') s.kidFont = 'off'
        const migrated = migratePaperStyle()
        return migrated ? { ...s, ...migrated } : s
      })(),

      /* 自定义题型 / 我的模板（模型配置已收归后台 /admin 统一管理） */
      customTypes: loadArr<CustomType>(LS.customTypes),
      myTemplates: migrateMyTemplates(loadArr<any>(LS.myTemplates)),
    }
  },

  getters: {
    template(state): PaperTemplate {
      return TEMPLATES.find(t => t.id === state.templateId) || TEMPLATES[0]
    },
    subjects(state): string[] {
      return state.available[state.grade] || []
    },
    /** 当前年级+科目的题型分组（含自定义题型组） */
    typeGroups(state): [string, string[] | CustomType[]][] {
      const gNum = gradeNumOf(state.grade)
      const byGrade = state.subject && TYPE_GROUPS_BY_GRADE[state.subject]?.[gNum]
      const groups: [string, string[] | CustomType[]][] = byGrade
        ? byGrade.map(([label, types]) => [label, [...types]])
        : TYPE_GROUPS_DEFAULT.map(([label, types]) => [label, [...types]])
      if (state.customTypes.length) groups.push(['自定义', [...state.customTypes]])
      return groups
    },
    totalQuestions(state): number {
      return state.sections.reduce(
        (s, x) => s + (x.status === 'ready' && x.data ? x.data.questions.length : x.count),
        0,
      )
    },
    hasLoading(state): boolean {
      return state.sections.some(s => s.status === 'loading')
    },
    errorCount(state): number {
      return state.sections.filter(s => s.status === 'error').length
    },
    canGenerate(state): boolean {
      return state.sections.length > 0 && !state.generating
    },
  },

  actions: {
    /* ── 初始化 ── */
    async init() {
      this.availableLoading = true
      this.availableError = ''
      try {
        this.available = await api.fetchAvailable()
      } catch (e: any) {
        this.availableError = '年级加载失败，请刷新重试'
      } finally {
        this.availableLoading = false
      }
      // 多用户：从服务端同步「我的模板」（服务端优先，保留本地独有）
      this.syncTemplatesFromServer()
    },

    /** 与服务端模板列表合并（服务端版本优先，本地独有的追加） */
    async syncTemplatesFromServer() {
      try {
        const server = await api.fetchTemplates()
        if (!server.length) return
        const local = this.myTemplates
        const names = new Set(server.map(t => t.name))
        const merged = [...server, ...local.filter(t => !names.has(t.name))]
        this.myTemplates = merged.slice(0, 20)
        localStorage.setItem(K(LS.myTemplates), JSON.stringify(this.myTemplates))
      } catch { /* 离线/后端不可达时用本地数据 */ }
    },

    /* ── 条件选择 ── */
    selectGrade(g: string) {
      if (this.grade === g) return
      this.grade = g
      this.subject = ''
      this.scope = null
      this.selectedTags = []
      this.keyword = ''
    },

    async selectSubject(s: string) {
      this.subject = s
      if (!this.grade || !s) return
      this.scopeLoading = true
      try {
        this.scope = await api.fetchScope(this.grade, s)
      } catch {
        this.scope = null
      } finally {
        this.scopeLoading = false
      }
    },

    toggleTag(tag: string) {
      const i = this.selectedTags.indexOf(tag)
      if (i >= 0) this.selectedTags.splice(i, 1)
      else this.selectedTags.push(tag)
      this.keyword = this.selectedTags.join('、')
    },

    setKeyword(kw: string) {
      this.keyword = kw
      // 手动输入时清掉点选状态，避免回写覆盖
      this.selectedTags = []
    },

    /* ── 搭建区 ── */
    addSection(type: string, count?: number, customName?: string) {
      const cnt = Math.min(99, Math.max(1, count ?? TYPE_DEFAULT[type] ?? 4))
      const sec: Section = {
        id: uid('s'),
        type,
        name: customName,
        count: cnt,
        status: 'ready',
        data: { questions: mockQuestions(type, cnt), topic: '' },
        layout: { ...DEFAULT_LAYOUT },
      }
      this.sections.push(sec)
    },

    removeSection(id: string) {
      const i = this.sections.findIndex(s => s.id === id)
      if (i >= 0) this.sections.splice(i, 1)
    },

    moveSection(from: number, to: number) {
      if (from === to || from < 0 || to < 0 || from >= this.sections.length || to >= this.sections.length) return
      const [item] = this.sections.splice(from, 1)
      this.sections.splice(to, 0, item)
    },

    setSectionCount(id: string, n: number) {
      const sec = this.sections.find(s => s.id === id)
      if (!sec || !sec.data) return
      let qs = sec.data.questions
      if (n < qs.length) {
        qs = qs.slice(0, n)
      } else if (n > qs.length) {
        qs = [...qs, ...mockQuestions(sec.type, n - qs.length)]
      }
      sec.count = n
      sec.data.questions = qs
    },

    async retrySection(id: string) {
      const sec = this.sections.find(s => s.id === id)
      if (!sec) return
      sec.status = 'loading'
      sec.error = ''
      try {
        const data = await api.generateOne({
          grade: this.grade,
          subject: this.subject,
          keyword: this.keyword,
          game_type: sec.type,
          difficulty: this.difficulty,
          question_count: sec.count,
        })
        sec.data = { questions: data.questions || [], passage: (data as any).passage, topic: data.topic }
        ensureQids(sec.data)
        sec.count = (data.questions || []).length || sec.count
        sec.status = 'ready'
      } catch (e: any) {
        sec.status = 'error'
        sec.error = e.message || '生成失败'
      }
    },

    /* ── 生成整卷 ── */
    async generate() {
      if (!this.sections.length || this.generating) return
      this.generating = true
      this.generateError = ''
      try {
        // 合并同题型（取最大题数）
        const byType = new Map<string, number>()
        this.sections.forEach(s => {
          byType.set(s.type, Math.max(byType.get(s.type) || 0, s.count))
        })
        const items = [...byType.entries()].map(([game_type, question_count]) => ({ game_type, question_count }))

        const nPapers = Math.max(1, Math.min(20, this.paperCount))
        const papers: PaperData[] = []
        for (let k = 0; k < nPapers; k++) {
          this.generateProgress = nPapers > 1 ? `正在生成第 ${k + 1}/${nPapers} 份…` : 'AI 出题中…'
          const sections = await api.generateBatch({
            grade: this.grade,
            subject: this.subject,
            keyword: this.keyword,
            difficulty: this.difficulty,
            items,
          })
          // 按题型回填到卡片（同题型多卡共用同一份）
          for (const resp of sections) {
            const data = { questions: resp.questions || [], passage: (resp as any).passage, topic: resp.topic }
            ensureQids(data)
            this.sections
              .filter(s => s.type === resp.game_type)
              .forEach(s => {
                s.data = data
                s.status = 'ready'
                s.error = ''
                s.count = (resp.questions || []).length || s.count
              })
          }
          // 没覆盖到的题型标记失败
          this.sections.forEach(s => {
            if (!sections.some(r => r.game_type === s.type)) {
              s.status = 'error'
              s.error = '生成失败'
            }
          })
          papers.push({
            grade: this.grade,
            subject: this.subject,
            keyword: this.keyword,
            title: this.title,
            titleHtml: this.titleHtml || undefined,
            difficulty: this.difficulty,
            sections: this.sections.map(s => ({
              type: s.type,
              name: s.name,
              data: s.data || { questions: [] },
              layout: { ...s.layout },
              _sid: s.id,
            })),
            day: nPapers > 1 ? k + 1 : undefined,
            hiddenElements: [...this.hiddenElements],
          } as PaperData)
        }
        this.papers = papers
        this.showAnswers = false
        this.view = 'result'
      } catch (e: any) {
        this.generateError = e.message || '生成失败，请重试'
      } finally {
        this.generating = false
        this.generateProgress = ''
      }
    },

    /** 卷头/卷尾元素删除切换（搭建态） */
    toggleHiddenElement(key: string) {
      const i = this.hiddenElements.indexOf(key)
      if (i >= 0) this.hiddenElements.splice(i, 1)
      else this.hiddenElements.push(key)
    },

    /** 左栏直接改标题文字：清掉富文本缓存 */
    setTitle(t: string) {
      this.title = t
      this.titleHtml = ''
    },

    /** 结果视图 → 回到搭建 */
    backToBuild() {
      this.view = 'build'
    },

    /** 纸面交互修改了大题 layout（表格拖拽等），按 sid 同步回 sections */
    syncSectionLayout(sid: string, layout: SecLayout) {
      const sec = this.sections.find(s => s.id === sid)
      if (sec) sec.layout = { ...sec.layout, ...layout }
    },

    /** 搭建态排版模式完成后：把纸面回写结果同步回 sections */
    syncSections(newSections: { type: string; _sid?: string; count?: number; data: GameData; layout: SecLayout }[]) {
      const byId = new Map(this.sections.map(s => [s.id, s]))
      const out: Section[] = []
      newSections.forEach(ns => {
        const orig = ns._sid ? byId.get(ns._sid) : undefined
        if (orig) {
          // 保留原卡片身份，替换题目数据
          orig.data = ns.data
          orig.count = (ns.data.questions || []).length
          out.push(orig)
        } else {
          out.push({
            id: uid('s'),
            type: ns.type,
            name: (ns as any).name,
            count: (ns.data.questions || []).length,
            status: 'ready' as const,
            data: ns.data,
            layout: ns.layout || { ...DEFAULT_LAYOUT },
          })
        }
      })
      this.sections = out
    },

    /** 用当前搭建区再来一批（题目不同） */
    async regenerate() {
      await this.generate()
    },

    /* ── 卷面配置 ── */
    setTemplate(id: string) {
      this.templateId = id
      localStorage.setItem(K(LS.template), JSON.stringify({ id }))
    },

    saveCustomTemplate(cfg: Partial<PaperTemplate>) {
      const t = TEMPLATES.find(t => t.id === 'custom')!
      Object.assign(t, cfg)
      localStorage.setItem(K(LS.customTemplate), JSON.stringify(cfg))
      this.templateId = 'custom'
      localStorage.setItem(K(LS.template), JSON.stringify({ id: 'custom' }))
    },

    setStyle(patch: Partial<PaperStyle>) {
      Object.assign(this.style, patch)
      localStorage.setItem(K(LS.paperStyle), JSON.stringify(this.style))
    },

    applyStylePreset(preset: 'standard' | 'colorful' | 'fun') {
      if (preset === 'standard') this.setStyle({ bg: 'none', banner: false, secColor: false, frame: 'none', encourage: false, reward: false })
      else if (preset === 'colorful') this.setStyle({ bg: 'dots', bgOpacity: 70, banner: true, secColor: true, frame: 'none', encourage: false, reward: false })
      else this.setStyle({ bg: 'clouds', bgOpacity: 60, banner: true, secColor: true, frame: 'rainbow', encourage: true, reward: true, kidFont: 'on' })
    },

    /* ── 自定义题型 ── */
    addCustomType(name: string, baseType: string, defaultCount: number) {
      this.customTypes.push({ id: 'custom_' + Date.now().toString(36), name, baseType, defaultCount })
      localStorage.setItem(K(LS.customTypes), JSON.stringify(this.customTypes))
    },

    removeCustomType(id: string) {
      this.customTypes = this.customTypes.filter(t => t.id !== id)
      localStorage.setItem(K(LS.customTypes), JSON.stringify(this.customTypes))
    },

    /* ── 我的模板 ── */
    saveMyTemplate(name: string) {
      const tpl: MyTemplate = {
        name,
        grade: this.grade,
        subject: this.subject,
        keyword: this.keyword,
        title: this.title,
        titleHtml: this.titleHtml || undefined,
        difficulty: this.difficulty,
        templateId: this.templateId,
        style: { ...this.style },
        hiddenElements: [...this.hiddenElements],
        cards: this.sections.map(s => ({ type: s.type, name: s.name, count: s.count, layout: { ...s.layout } })),
        // 完整数据：含每题编辑后的文字与富文本（加粗/字号/颜色），恢复时原样还原
        sections: JSON.parse(JSON.stringify(this.sections)).map((s: any) => ({
          type: s.type,
          name: s.name,
          count: s.count,
          layout: s.layout,
          data: s.data,
        })),
      }
      const idx = this.myTemplates.findIndex(t => t.name === name)
      if (idx >= 0) this.myTemplates[idx] = tpl
      else this.myTemplates.unshift(tpl)
      this.myTemplates = this.myTemplates.slice(0, 20)
      localStorage.setItem(K(LS.myTemplates), JSON.stringify(this.myTemplates))
      // 同步到服务端（失败不影响本地使用，下次登录会再合并）
      api.upsertTemplate(tpl).catch(() => {})
    },

    loadMyTemplate(name: string): boolean {
      const tpl = this.myTemplates.find(t => t.name === name)
      if (!tpl) return false
      if (!tpl.cards.length && !tpl.sections?.length) return false
      this.grade = tpl.grade
      this.subject = tpl.subject
      this.keyword = tpl.keyword
      this.selectedTags = []
      this.difficulty = tpl.difficulty
      this.templateId = tpl.templateId
      this.title = tpl.title || ''
      this.titleHtml = (tpl as any).titleHtml || ''
      if (tpl.style) this.setStyle(tpl.style)
      this.hiddenElements = [...(tpl.hiddenElements || [])]

      if (tpl.sections?.length) {
        // V2：完整还原（每题文字、版式、数量都在）
        this.sections = JSON.parse(JSON.stringify(tpl.sections)).map((s: any) => ({
          id: uid('s'),
          type: s.type,
          name: s.name,
          count: s.count,
          status: 'ready' as const,
          data: s.data,
          layout: { ...DEFAULT_LAYOUT, ...s.layout },
        }))
      } else {
        // 旧格式：mock 占位 + 快照文字回填
        const cards = tpl.cards.map(c => ({
          type: c.type,
          name: (c as any).name,
          count: c.count,
          data: { questions: mockQuestions(c.type, c.count) },
          layout: { ...DEFAULT_LAYOUT, ...c.layout },
        }))
        if (tpl.paperSnapshot) applyOldSnapshot(cards, tpl.paperSnapshot)
        this.sections = cards.map(c => ({
          id: uid('s'),
          type: c.type,
          name: c.name,
          count: c.count,
          status: 'ready' as const,
          data: c.data,
          layout: c.layout,
        }))
      }
      this.selectSubject(tpl.subject)
      return true
    },

    deleteMyTemplate(name: string) {
      this.myTemplates = this.myTemplates.filter(t => t.name !== name)
      localStorage.setItem(K(LS.myTemplates), JSON.stringify(this.myTemplates))
      api.deleteTemplateOnServer(name).catch(() => {})
    },
  },
})
