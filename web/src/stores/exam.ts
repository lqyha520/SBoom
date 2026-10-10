import { defineStore } from 'pinia'
import {
  DEFAULT_LAYOUT,
  MAX_QUESTIONS_PER_TYPE,
  MAX_GENERATION_TYPES,
  LS,
  TEMPLATES,
  TYPE_DEFAULT,
  TYPE_GROUPS_BY_GRADE,
  TYPE_GROUPS_DEFAULT,
} from '../constants'
import * as api from '../api'
import type { CustomType, GameData, PaperTemplate, PaperStyle, SecLayout, Section, PaperSection } from '../types'
import { ensureQids, gradeNumOf, uid } from '../utils'
import { beginLayout, finishLayout, captureEdit, recordEdit, undoEdit, redoEdit, type EditSnapshot } from '../workspace-history'
import { K, safeSet, styleSaveTimers } from './exam-local'
import { createExamState } from './exam-state'
import { draftActions } from './exam-draft'
import { generationActions } from './exam-generation'
import { templatesActions } from './exam-templates'
export { deepClone } from '../utils'

export const useExamStore = defineStore('exam', {
  state: createExamState,

  getters: {
    hasBuildSettings(state): boolean {
      return !!(state.grade || state.subject || state.keyword || state.selectedTags.length ||
        state.title || state.titleHtml || state.sections.length || state.hiddenElements.length ||
        state.difficulty !== 'medium' || state.paperCount !== 1 || !state.addDayLabel)
    },
    canClearSettings(state): boolean {
      return (this.hasBuildSettings || !!state.pendingRun) && state.persistenceReady &&
        !state.generating && !state.accountChanged && !state.historyBusy
    },
    hasPendingEdits(state): boolean {
      return (
        state.sections.some(
          (section) => section.pendingGeneration || section.data?.questions.some((question) => question._replacement),
        ) ||
        state.papers.some((paper) =>
          paper.sections.some((section) => section.data.questions.some((question) => question._replacement)),
        )
      )
    },
    canUndo(state): boolean {
      return (
        !!state.undoStack.length &&
        !state.generating &&
        !state.accountChanged &&
        !state.layoutMode &&
        !this.hasPendingEdits
      )
    },
    canRedo(state): boolean {
      return (
        !!state.redoStack.length &&
        !state.generating &&
        !state.accountChanged &&
        !state.layoutMode &&
        !this.hasPendingEdits
      )
    },
    template(state): PaperTemplate {
      if (state.templateId === 'custom') return state.customTemplate
      return TEMPLATES.find((t) => t.id === state.templateId) || TEMPLATES[0]
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
      return state.sections.reduce((sum, section) => sum + section.count, 0)
    },
    hasLoading(state): boolean {
      return state.sections.some((s) => s.status === 'loading')
    },
    errorCount(state): number {
      return state.sections.filter((s) => s.status === 'error').length
    },
    generationIssue(state): string {
      if (state.keyword.length > 100) return '已选知识点超过100字，请缩小本次出题范围'
      if (state.sections.some((s) => !Number.isInteger(s.count) || s.count < 1 || s.count > MAX_QUESTIONS_PER_TYPE)) {
        return `每个大题需设置 1 至 ${MAX_QUESTIONS_PER_TYPE} 道题`
      }
      if (new Set(state.sections.map((s) => s.type)).size > MAX_GENERATION_TYPES) {
        return `一次最多生成 ${MAX_GENERATION_TYPES} 种题型`
      }
      return ''
    },
    canGenerate(state): boolean {
      return (
        !!state.grade &&
        !!state.subject &&
        !!state.keyword.trim() &&
        state.sections.length > 0 &&
        !state.generating &&
        !state.accountChanged &&
        !this.generationIssue
      )
    },
  },
  actions: {
    ...draftActions,
    ...generationActions,
    ...templatesActions,
    editSnapshot(): EditSnapshot {
      return captureEdit(this)
    },

    recordEdit(key = '') {
      recordEdit(this, key)
    },

    beginLayout() { beginLayout(this) },

    finishLayout(cancel = false) {
      finishLayout(this, cancel)
      clearTimeout(styleSaveTimers.get(this))
      safeSet(K(this.ownerId, LS.paperStyle), JSON.stringify(this.style))
    },

    async requestGeneration() {
      if (!this.canGenerate || this.layoutMode) return
      if ((this.papers.length || this.pendingRun || this.hasPendingEdits) &&
        !window.confirm(`将按${this.grade}${this.subject}「${this.keyword}」生成 ${this.paperCount} 份新试卷，产生新的模型调用费用（以服务商实际计费为准）。当前结果会先保存到本机历史，保存失败将停止。是否继续？`)) return
      await this.generate()
    },

    undo() {
      const { grade, subject } = this
      undoEdit(this)
      if (this.grade !== grade || this.subject !== subject) void this.selectSubject(this.subject)
    },

    redo() {
      const { grade, subject } = this
      redoEdit(this)
      if (this.grade !== grade || this.subject !== subject) void this.selectSubject(this.subject)
    },

    async clearSettings(): Promise<boolean> {
      if (!this.canClearSettings) return false
      const pending = !!this.pendingRun || this.hasPendingEdits
      if (pending) {
        const owner = this.ownerId
        this.historyBusy = true
        try {
          if (!await this.saveHistory('before-clear')) {
            this.generateError = this.storageError || '未完成请求保存失败，设置尚未清空，请稍后重试'
            return false
          }
        } finally {
          this.historyBusy = false
        }
        if (!this.canClearSettings || this.ownerId !== owner) return false
      }
      if (this.layoutMode) this.finishLayout()
      // 未完成请求通过完整历史快照恢复，避免普通撤销丢失请求编号。
      if (pending) {
        this.undoStack = []
        this.redoStack = []
      } else this.recordEdit()
      this.scopeRevision++
      this.grade = ''
      this.subject = ''
      this.keyword = ''
      this.selectedTags = []
      this.title = ''
      this.titleHtml = ''
      this.difficulty = 'medium'
      this.hiddenElements = []
      this.sections = []
      this.paperCount = 1
      this.addDayLabel = true
      this.scope = null
      this.scopeLoading = false
      this.generateError = ''
      this.generateWarn = ''
      this.pendingRun = null
      this.generationJobs = []
      this.failedCount = 0
      this.generateProgress = ''
      this.stopRequested = false
      this.view = 'build'
      return true
    },

    questionSection(id: string, paperIndex?: number): Section | PaperSection | undefined {
      const section =
        paperIndex === undefined
          ? this.sections.find((item) => item.id === id)
          : this.papers[paperIndex]?.sections.find((item, index) => (item._sid || String(index)) === id)
      if (section?.data) ensureQids(section.data)
      return section
    },

    toggleQuestionLock(id: string, qid: string, paperIndex?: number) {
      if (this.generating || this.accountChanged) return
      const section = this.questionSection(id, paperIndex)
      const question = section?.data?.questions.find((item) => item._qid === qid)
      if (!question || section?.type === 'reading' || question._replacement) return
      this.recordEdit()
      question._locked = !question._locked
    },

    /* ── 初始化与本地版本 ── */
    async init() {
      // 草稿持久化失败（IndexedDB 被禁用、存储配额耗尽等）不能连坐：年级科目必须照常加载，
      // 否则工作台会整片空白，用户完全看不出问题出在本地存储上。
      this.availableLoading = true
      this.availableError = ''
      await Promise.allSettled([
        this.initPersistence().catch(error => {
          this.persistenceReady = true
          this.draftState = 'error'
          this.storageError = error instanceof Error ? error.message : '本地草稿初始化失败'
        }),
        api.fetchAvailable().then(value => { this.available = value }).catch(() => {
          this.availableError = '年级加载失败，请刷新重试'
        }).finally(() => { this.availableLoading = false }),
      ])
      if (this.grade && this.subject) void this.selectSubject(this.subject)
      void this.syncTemplatesFromServer()
      void this.refreshUsage()
    },

    /* ── 条件选择 ── */
    selectGrade(g: string) {
      if (this.generating || this.grade === g) return
      this.scopeRevision++
      this.grade = g
      this.subject = ''
      this.scope = null
      this.scopeLoading = false
      this.selectedTags = []
      this.keyword = ''
    },

    async selectSubject(s: string) {
      if (this.generating) return
      if (this.subject !== s) {
        this.keyword = ''
        this.selectedTags = []
      }
      this.subject = s
      this.scope = null
      const revision = ++this.scopeRevision
      this.scopeLoading = false
      if (!this.grade || !s) return
      const grade = this.grade
      this.scopeLoading = true
      try {
        const scope = await api.fetchScope(grade, s)
        if (this.scopeRevision === revision && this.grade === grade && this.subject === s) this.scope = scope
      } catch {
        if (this.scopeRevision === revision && this.grade === grade && this.subject === s) this.scope = null
      } finally {
        if (this.scopeRevision === revision && this.grade === grade && this.subject === s) this.scopeLoading = false
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
      if (this.generating || this.accountChanged) return
      this.recordEdit()
      const cnt = Math.min(MAX_QUESTIONS_PER_TYPE, Math.max(1, Math.round(count || TYPE_DEFAULT[type] || 4)))
      const sec: Section = {
        id: uid('s'),
        type,
        name: customName,
        count: cnt,
        status: 'ready',
        data: { questions: [], topic: '', missing_count: cnt },
        layout: { ...DEFAULT_LAYOUT },
      }
      this.sections.push(sec)
    },

    removeSection(id: string) {
      if (this.generating || this.accountChanged) return
      this.recordEdit()
      const i = this.sections.findIndex((s) => s.id === id)
      if (i >= 0) this.sections.splice(i, 1)
    },

    moveSection(from: number, to: number) {
      if (this.generating || this.accountChanged) return
      if (from === to || from < 0 || to < 0 || from >= this.sections.length || to >= this.sections.length) return
      this.recordEdit()
      const [item] = this.sections.splice(from, 1)
      this.sections.splice(to, 0, item)
    },

    setSectionCount(id: string, n: number) {
      if (this.generating || this.accountChanged) return
      const sec = this.sections.find((s) => s.id === id)
      if (!sec || !sec.data) return
      this.recordEdit()
      n = Math.min(MAX_QUESTIONS_PER_TYPE, Math.max(1, Math.round(n) || 1))
      if (sec.data.questions.slice(n).some((question) => question._locked)) {
        this.generateError = '减少题数会移除已锁定题目，请先在管理题目中解锁'
        return
      }
      let qs = sec.data.questions
      if (n < qs.length) {
        qs = qs.slice(0, n)
      }
      sec.count = n
      sec.data.questions = qs
      sec.data.missing_count = Math.max(0, n - qs.length)
    },

    /** 卷头/卷尾元素删除切换（搭建态） */
    toggleHiddenElement(key: string) {
      this.recordEdit()
      const i = this.hiddenElements.indexOf(key)
      if (i >= 0) this.hiddenElements.splice(i, 1)
      else this.hiddenElements.push(key)
    },

    /** 左栏直接改标题文字：清掉富文本缓存 */
    setTitle(t: string) {
      this.recordEdit('title')
      this.title = t
      this.titleHtml = ''
    },

    /** 结果视图 → 回到搭建 */
    backToBuild() {
      this.view = 'build'
    },

    /** 纸面交互修改了大题 layout（表格拖拽等），按 sid 同步回 sections */
    syncSectionLayout(sid: string, layout: SecLayout) {
      const sec = this.sections.find((s) => s.id === sid)
      if (sec) sec.layout = { ...sec.layout, ...layout }
    },

    /** 搭建态排版模式完成后：把纸面回写结果同步回 sections */
    syncSections(newSections: { type: string; _sid?: string; count?: number; data: GameData; layout: SecLayout }[]) {
      const byId = new Map(this.sections.map((s) => [s.id, s]))
      const out: Section[] = []
      newSections.forEach((ns) => {
        const orig = ns._sid ? byId.get(ns._sid) : undefined
        if (orig) {
          // 保留原卡片身份，替换题目数据
          orig.data = ns.data
          if (!ns.data.missing_count) orig.count = (ns.data.questions || []).length
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

    /* ── 卷面配置 ── */
    setTemplate(id: string) {
      this.recordEdit()
      this.templateId = id
      safeSet(K(this.ownerId, LS.template), JSON.stringify({ id }))
    },

    saveCustomTemplate(cfg: Partial<PaperTemplate>) {
      this.recordEdit('custom-template')
      // 写响应式 state（而非模块常量）：编辑中的卷面立即生效
      Object.assign(this.customTemplate, cfg)
      safeSet(K(this.ownerId, LS.customTemplate), JSON.stringify(cfg))
      this.setTemplate('custom')
    },

    setStyle(patch: Partial<PaperStyle>) {
      this.recordEdit('style')
      Object.assign(this.style, patch)
      // 持久化防抖：标题拖拽/字号滑条每个 mousemove 都会调 setStyle，
      // 立即写盘会以 60+/s 的频率序列化整份样式（且触发重分页测量键变化）
      clearTimeout(styleSaveTimers.get(this))
      const owner = this.ownerId
      const style = { ...this.style }
      styleSaveTimers.set(
        this,
        setTimeout(() => {
          safeSet(K(owner, LS.paperStyle), JSON.stringify(style))
        }, 300),
      )
    },

    applyStylePreset(preset: 'standard' | 'colorful' | 'fun') {
      if (preset === 'standard')
        this.setStyle({ bg: 'none', banner: false, secColor: false, frame: 'none', encourage: false, reward: false })
      else if (preset === 'colorful')
        this.setStyle({
          bg: 'dots',
          bgOpacity: 70,
          banner: true,
          secColor: true,
          frame: 'none',
          encourage: false,
          reward: false,
        })
      else
        this.setStyle({
          bg: 'clouds',
          bgOpacity: 60,
          banner: true,
          secColor: true,
          frame: 'rainbow',
          encourage: true,
          reward: true,
          kidFont: 'on',
        })
    },

    /* ── 自定义题型 ── */
    addCustomType(name: string, baseType: string, defaultCount: number) {
      this.customTypes.push({ id: 'custom_' + Date.now().toString(36), name, baseType, defaultCount })
      safeSet(K(this.ownerId, LS.customTypes), JSON.stringify(this.customTypes))
    },

    removeCustomType(id: string) {
      this.customTypes = this.customTypes.filter((t) => t.id !== id)
      safeSet(K(this.ownerId, LS.customTypes), JSON.stringify(this.customTypes))
    },
  },
})
