import { defineStore } from 'pinia'
import {
  DEFAULT_LAYOUT,
  LS,
  LLM_DEFAULTS,
  TEMPLATES,
  TYPE_DEFAULT,
  TYPE_GROUPS_BY_GRADE,
  TYPE_GROUPS_DEFAULT,
} from '../constants'
import * as api from '../api'
import type {
  CustomType,
  Difficulty,
  LlmConfig,
  MyTemplate,
  PaperData,
  PaperStyle,
  PaperTemplate,
  ScopeData,
  Section,
} from '../types'
import { ensureQids, gradeNumOf, mockQuestions, uid } from '../utils'

function load<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? { ...fallback, ...JSON.parse(raw) } : fallback
  } catch {
    return fallback
  }
}
function loadArr<T>(key: string): T[] {
  try {
    return JSON.parse(localStorage.getItem(key) || '[]')
  } catch {
    return []
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
  kidFont: 'auto',
  exportBg: false,
}

export const useExamStore = defineStore('exam', {
  state: () => {
    // 恢复自定义模板的持久化配置
    const customTpl = TEMPLATES.find(t => t.id === 'custom')!
    try {
      const savedCustom = JSON.parse(localStorage.getItem(LS.customTemplate) || 'null')
      if (savedCustom) Object.assign(customTpl, savedCustom)
    } catch { /* ignore */ }
    let templateId = 'exam'
    try {
      const p = JSON.parse(localStorage.getItem(LS.template) || 'null')
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
      difficulty: 'medium' as Difficulty,

      /* 搭建区 */
      sections: [] as Section[],

      /* 生成结果 */
      papers: [] as PaperData[],
      generating: false,
      generateError: '',

      /* 预览 */
      showAnswers: false,
      layoutMode: false,

      /* 批量 */
      paperCount: 1,
      addDayLabel: true,

      /* 卷面配置 */
      templateId,
      style: load<PaperStyle>(LS.paperStyle, STYLE_DEFAULTS),

      /* 自定义题型 / 我的模板 / LLM */
      customTypes: loadArr<CustomType>(LS.customTypes),
      myTemplates: loadArr<MyTemplate>(LS.myTemplates),
      llm: load<LlmConfig>(LS.llm, LLM_DEFAULTS as LlmConfig),
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
        count: cnt,
        status: 'ready',
        data: { questions: mockQuestions(type, cnt), topic: '' },
        layout: { ...DEFAULT_LAYOUT },
      }
      if (customName) (sec as any).name = customName
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
      const qs = sec.data.questions
      if (n < qs.length) {
        sec.data.questions = qs.slice(0, n)
      } else if (n > qs.length) {
        qs.push(...mockQuestions(sec.type, n - qs.length))
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
          llm: this.llm,
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
          const sections = await api.generateBatch({
            grade: this.grade,
            subject: this.subject,
            keyword: this.keyword,
            difficulty: this.difficulty,
            items,
            llm: this.llm,
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
            difficulty: this.difficulty,
            sections: this.sections.map(s => ({
              type: s.type,
              data: s.data || { questions: [] },
              layout: { ...s.layout },
              _sid: s.id,
            })),
            day: nPapers > 1 ? k + 1 : undefined,
          })
        }
        this.papers = papers
        this.showAnswers = false
        this.view = 'result'
      } catch (e: any) {
        this.generateError = e.message || '生成失败，请重试'
      } finally {
        this.generating = false
      }
    },

    /** 结果视图 → 回到搭建 */
    backToBuild() {
      this.view = 'build'
    },

    /** 用当前搭建区再来一批（题目不同） */
    async regenerate() {
      await this.generate()
    },

    /* ── 卷面配置 ── */
    setTemplate(id: string) {
      this.templateId = id
      localStorage.setItem(LS.template, JSON.stringify({ id }))
    },

    saveCustomTemplate(cfg: Partial<PaperTemplate>) {
      const t = TEMPLATES.find(t => t.id === 'custom')!
      Object.assign(t, cfg)
      localStorage.setItem(LS.customTemplate, JSON.stringify(cfg))
      this.templateId = 'custom'
      localStorage.setItem(LS.template, JSON.stringify({ id: 'custom' }))
    },

    setStyle(patch: Partial<PaperStyle>) {
      Object.assign(this.style, patch)
      localStorage.setItem(LS.paperStyle, JSON.stringify(this.style))
    },

    applyStylePreset(preset: 'standard' | 'colorful' | 'fun') {
      if (preset === 'standard') this.setStyle({ bg: 'none', banner: false, secColor: false, frame: 'none', encourage: false, reward: false })
      else if (preset === 'colorful') this.setStyle({ bg: 'dots', bgOpacity: 70, banner: true, secColor: true, frame: 'none', encourage: false, reward: false })
      else this.setStyle({ bg: 'clouds', bgOpacity: 60, banner: true, secColor: true, frame: 'rainbow', encourage: true, reward: true, kidFont: 'on' })
    },

    /* ── 自定义题型 ── */
    addCustomType(name: string, baseType: string, defaultCount: number) {
      this.customTypes.push({ id: 'custom_' + Date.now().toString(36), name, baseType, defaultCount })
      localStorage.setItem(LS.customTypes, JSON.stringify(this.customTypes))
    },

    removeCustomType(id: string) {
      this.customTypes = this.customTypes.filter(t => t.id !== id)
      localStorage.setItem(LS.customTypes, JSON.stringify(this.customTypes))
    },

    /* ── 我的模板 ── */
    saveMyTemplate(name: string) {
      const tpl: MyTemplate = {
        name,
        grade: this.grade,
        subject: this.subject,
        keyword: this.keyword,
        difficulty: this.difficulty,
        templateId: this.templateId,
        cards: this.sections.map(s => ({ type: s.type, count: s.count, layout: { ...s.layout } })),
      }
      const idx = this.myTemplates.findIndex(t => t.name === name)
      if (idx >= 0) this.myTemplates[idx] = tpl
      else this.myTemplates.unshift(tpl)
      this.myTemplates = this.myTemplates.slice(0, 20)
      localStorage.setItem(LS.myTemplates, JSON.stringify(this.myTemplates))
    },

    loadMyTemplate(name: string) {
      const tpl = this.myTemplates.find(t => t.name === name)
      if (!tpl) return
      this.grade = tpl.grade
      this.subject = tpl.subject
      this.keyword = tpl.keyword
      this.selectedTags = []
      this.difficulty = tpl.difficulty
      this.templateId = tpl.templateId
      this.sections = tpl.cards.map(c => ({
        id: uid('s'),
        type: c.type,
        count: c.count,
        status: 'ready',
        data: { questions: mockQuestions(c.type, c.count) },
        layout: { ...DEFAULT_LAYOUT, ...c.layout },
      }))
      this.selectSubject(tpl.subject)
    },

    deleteMyTemplate(name: string) {
      this.myTemplates = this.myTemplates.filter(t => t.name !== name)
      localStorage.setItem(LS.myTemplates, JSON.stringify(this.myTemplates))
    },

    /* ── LLM ── */
    async saveLlm(cfg: LlmConfig) {
      this.llm = cfg
      localStorage.setItem(LS.llm, JSON.stringify(cfg))
      return api.saveLlmConfig(cfg)
    },
  },
})
