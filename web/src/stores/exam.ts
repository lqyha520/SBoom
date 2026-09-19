import { defineStore } from 'pinia'
import { watch, type WatchStopHandle } from 'vue'
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
// randomId：crypto.randomUUID 是 [SecureContext] 限定 API，http://内网IP 下不存在
import { randomId } from '../../../shared/webcrypto'
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
  PaperSection,
} from '../types'
import { deepClone, ensureQids, gradeNumOf, mockQuestions, uid } from '../utils'
import { useAuthStore, userPrefix } from './auth'
import { createGenerationRun, runGenerationJob, GenerationStopped, type GenerationContext, type GenerationMode, type GenerationRun } from '../generation'
import * as persistence from '../persistence'
import type { HistoryEntry, HistoryReason, WorkspaceSnapshot } from '../persistence'
export { deepClone } from '../utils'

/** 当前登录用户的 localStorage 命名空间前缀（多用户数据隔离）。
 *  localStorage 被禁用（隐私模式/权限策略）时不至于在模块加载期抛错白屏 */
const K = (owner: string, key: string): string => userPrefix(owner || 'guest') + key

/** 安全写入 localStorage：配额超限（Safari 5MB / 隐私模式）不再抛穿调用链 */
function safeSet(key: string, val: string): boolean {
  try {
    localStorage.setItem(key, val)
    return true
  } catch (e) {
    console.warn('本地存储写入失败（可能超出配额，可清理旧模板后重试）：', key, e)
    return false
  }
}

/** 结构化深拷贝（可含 Date 等类型；极老浏览器退回 JSON 深拷贝） */
function load<T>(owner: string, key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(K(owner, key))
    return raw ? { ...fallback, ...JSON.parse(raw) } : fallback
  } catch {
    return fallback
  }
}
function loadArr<T>(owner: string, key: string): T[] {
  try {
    const value = JSON.parse(localStorage.getItem(K(owner, key)) || '[]')
    return Array.isArray(value) ? value : []
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
function migratePaperStyle(owner: string): Partial<PaperStyle> | null {
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
  titleOffsetY: 0,
}

/** 卷面样式持久化的防抖句柄（模块级，store 重建也共用） */
interface DraftRuntime {
  owner: string
  id: string
  sequence: number
  pending: Promise<unknown>
  timer?: ReturnType<typeof setTimeout>
  stop?: WatchStopHandle
}
const draftRuntimes = new WeakMap<object, DraftRuntime>()
const styleSaveTimers = new WeakMap<object, ReturnType<typeof setTimeout>>()
const editBursts = new WeakMap<object, { key: string; at: number }>()
type EditSnapshot = Pick<WorkspaceSnapshot, 'sections' | 'papers' | 'title' | 'titleHtml' | 'style' | 'hiddenElements' | 'templateId' | 'customTemplate'>

function generationSections(sections: Section[]): GenerationContext['sections'] {
  return sections.map(section => ({ id: section.id, type: section.type, name: section.name,
    count: section.count, layout: deepClone(section.layout),
    lockedQuestions: section.data?.questions.flatMap((question, index) => question._locked && index < section.count
      ? [{ index, question: deepClone(question) }] : []) || [],
  }))
}

function sameTemplate(a: MyTemplate, b: MyTemplate) {
  const content = ({ _revision, _syncState, _syncError, ...rest }: MyTemplate) => rest
  return JSON.stringify(content(a)) === JSON.stringify(content(b))
}

export const useExamStore = defineStore('exam', {
  state: () => {
    const ownerId = String(useAuthStore().user?.id || '')
    // 自定义模板存为响应式 state（历史实现直接改模块常量 TEMPLATES 的 custom 项，
    // 它不是响应式对象——正在使用 custom 模板时编辑配置，卷面不更新，要切走再切回才生效）
    const customTpl: PaperTemplate = { ...TEMPLATES.find(t => t.id === 'custom')! }
    try {
      const savedCustom = JSON.parse(localStorage.getItem(K(ownerId, LS.customTemplate)) || 'null')
      if (savedCustom) Object.assign(customTpl, savedCustom)
    } catch { /* ignore */ }
    let templateId = 'exam'
    try {
      const p = JSON.parse(localStorage.getItem(K(ownerId, LS.template)) || 'null')
      if (p?.id && TEMPLATES.some(t => t.id === p.id)) templateId = p.id
    } catch { /* ignore */ }

    return {
      ownerId,
      accountChanged: false,
      persistenceReady: false,
      draftState: 'loading' as 'loading' | 'saving' | 'saved' | 'error',
      draftSavedAt: 0,
      storageError: '',
      history: [] as HistoryEntry[],
      historyBusy: false,
      pendingRun: null as GenerationRun | null,
      generationJobs: [] as import('../generation').GenerationJob[],
      stopRequested: false,
      undoStack: [] as EditSnapshot[],
      redoStack: [] as EditSnapshot[],
      usage: null as api.GenerationUsage | null,
      templatesSyncing: false,
      templateBusy: [] as string[],
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
      /** 部分成功的告警（如：10 份中 2 份失败已跳过） */
      generateWarn: '',
      /** 上一批生成中失败被跳过的份数（>0 时结果页显示「补齐」按钮） */
      failedCount: 0,
      /** 生成进度文案（如：正在生成 2/5 份…） */
      generateProgress: '',

      /* 预览 */
      showAnswers: false,
      layoutMode: false,

      /* 批量 */
      paperCount: 1,
      addDayLabel: true,

      /* 卷面配置 */
      templateId,
      /** 自定义模板的当前配置（响应式；template getter 在 id=custom 时返回它） */
      customTemplate: customTpl,
      style: (() => {
        const s = load<PaperStyle>(ownerId, LS.paperStyle, { ...STYLE_DEFAULTS })
        // 大字号不再默认跟随年级：已存的 auto 归一为 off
        if (s.kidFont === 'auto') s.kidFont = 'off'
        const migrated = migratePaperStyle(ownerId)
        return migrated ? { ...s, ...migrated } : s
      })(),

      /* 自定义题型 / 我的模板（模型配置已收归后台 /admin 统一管理） */
      customTypes: loadArr<CustomType>(ownerId, LS.customTypes),
      myTemplates: migrateMyTemplates(loadArr<any>(ownerId, LS.myTemplates)),
    }
  },

  getters: {
    hasPendingEdits(state): boolean {
      return state.sections.some(section => section.pendingGeneration || section.data?.questions.some(question => question._replacement))
        || state.papers.some(paper => paper.sections.some(section => section.data.questions.some(question => question._replacement)))
    },
    canUndo(state): boolean { return !!state.undoStack.length && !state.generating && !state.accountChanged && !state.layoutMode && !this.hasPendingEdits },
    canRedo(state): boolean { return !!state.redoStack.length && !state.generating && !state.accountChanged && !state.layoutMode && !this.hasPendingEdits },
    template(state): PaperTemplate {
      if (state.templateId === 'custom') return state.customTemplate
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
    generationIssue(state): string {
      if (state.sections.some(s => !Number.isInteger(s.count) || s.count < 1 || s.count > MAX_QUESTIONS_PER_TYPE)) {
        return `每个大题需设置 1 至 ${MAX_QUESTIONS_PER_TYPE} 道题`
      }
      if (new Set(state.sections.map(s => s.type)).size > MAX_GENERATION_TYPES) {
        return `一次最多生成 ${MAX_GENERATION_TYPES} 种题型`
      }
      return ''
    },
    canGenerate(state): boolean {
      return !!state.grade && !!state.subject && !!state.keyword.trim()
        && state.sections.length > 0 && !state.generating && !state.accountChanged && !this.generationIssue
    },
  },

  actions: {
    editSnapshot(): EditSnapshot {
      return deepClone({ sections: this.sections, papers: this.papers, title: this.title, titleHtml: this.titleHtml,
        style: this.style, hiddenElements: this.hiddenElements, templateId: this.templateId, customTemplate: this.customTemplate })
    },
    recordEdit(key = '') {
      if (this.generating || this.accountChanged || this.hasPendingEdits) return
      const previous = editBursts.get(this), at = Date.now()
      editBursts.set(this, { key, at })
      if (key && previous?.key === key && at - previous.at < 500) return
      const snapshot = this.editSnapshot()
      const encoded = JSON.stringify(snapshot)
      if (JSON.stringify(this.undoStack[this.undoStack.length - 1]) === encoded) return
      this.undoStack.push(snapshot); this.redoStack = []
      while (this.undoStack.length > 20 || JSON.stringify(this.undoStack).length > 4_000_000) this.undoStack.shift()
    },
    undo() {
      if (!this.canUndo) return
      editBursts.delete(this)
      this.redoStack.push(this.editSnapshot())
      Object.assign(this, deepClone(this.undoStack.pop()!))
    },
    redo() {
      if (!this.canRedo) return
      editBursts.delete(this)
      this.undoStack.push(this.editSnapshot())
      Object.assign(this, deepClone(this.redoStack.pop()!))
    },
    questionSection(id: string, paperIndex?: number): Section | PaperSection | undefined {
      const section = paperIndex === undefined ? this.sections.find(item => item.id === id)
        : this.papers[paperIndex]?.sections.find((item, index) => (item._sid || String(index)) === id)
      if (section?.data) ensureQids(section.data)
      return section
    },
    toggleQuestionLock(id: string, qid: string, paperIndex?: number) {
      if (this.generating || this.accountChanged) return
      const section = this.questionSection(id, paperIndex)
      const question = section?.data?.questions.find(item => item._qid === qid)
      if (!question || section?.type === 'reading' || question._replacement) return
      this.recordEdit(); question._locked = !question._locked
    },
    async replaceQuestion(id: string, qid: string, paperIndex?: number) {
      if (this.generating || this.accountChanged) return
      const section = this.questionSection(id, paperIndex)
      const question = section?.data?.questions.find(item => item._qid === qid)
      if (!section || !question || question._locked || section.type === 'reading') return
      const source = paperIndex === undefined ? this : this.papers[paperIndex]
      if (!source.grade || !source.subject || !source.keyword.trim()) throw new Error('请先填写年级、科目和知识点')
      const context: GenerationContext = { grade: source.grade, subject: source.subject, keyword: source.keyword,
        title: source.title, difficulty: source.difficulty as Difficulty, hiddenElements: [], count: 1,
        sections: [{ id, type: section.type, name: section.name, count: 1, layout: deepClone(section.layout) }] }
      const existing = question._replacement
      const run = existing || createGenerationRun(context)
      question._replacement = run; this.generating = true
      try {
        const result = await runGenerationJob(run.context, run.jobs[0], existing ? 'retry' : 'send', async () => {
          if (this.accountChanged) throw new Error('账号已变化，未发送请求')
          if (this.persistenceReady && this.ownerId && !await this.flushDraft()) throw new Error('请求记录保存失败，请先恢复本地存储')
        })
        if (this.accountChanged) return
        const replacement = result.sections[0]?.data.questions[0]
        if (!replacement) throw new Error('没有生成可替换的题目，原题已保留')
        const content = (value: typeof question) => JSON.stringify([value.stem?.replace(/\s+/g, ''), value.options,
          value.top, value.left, value.right, value.left_expr, value.right_expr, value.left_items, value.right_items])
        delete question._replacement
        if (section.data?.questions.some(item => content(item) === content(replacement))) throw new Error('新题与现有题目重复，原题已保留')
        this.generating = false; this.recordEdit()
        const index = section.data!.questions.findIndex(item => item._qid === qid)
        section.data!.questions[index] = { ...deepClone(replacement), _qid: qid }
      } finally {
        this.generating = false
        if (this.persistenceReady) await this.flushDraft()
        void this.refreshUsage()
      }
    },
    /* ── 初始化与本地版本 ── */
    async init() {
      // 草稿持久化失败（IndexedDB 被禁用、存储配额耗尽等）不能连坐：年级科目必须照常加载，
      // 否则工作台会整片空白，用户完全看不出问题出在本地存储上。
      try { await this.initPersistence() }
      catch (error) {
        this.persistenceReady = true
        this.draftState = 'error'
        this.storageError = error instanceof Error ? error.message : '本地草稿初始化失败'
      }
      this.availableLoading = true
      this.availableError = ''
      try { this.available = await api.fetchAvailable() }
      catch { this.availableError = '年级加载失败，请刷新重试' }
      finally { this.availableLoading = false }
      if (this.grade && this.subject) void this.selectSubject(this.subject)
      void this.syncTemplatesFromServer()
      void this.refreshUsage()
    },

    captureSnapshot(): WorkspaceSnapshot {
      return deepClone({
        version: 1, grade: this.grade, subject: this.subject, keyword: this.keyword,
        selectedTags: this.selectedTags, title: this.title, titleHtml: this.titleHtml,
        difficulty: this.difficulty, hiddenElements: this.hiddenElements,
        sections: this.sections, papers: this.papers, view: this.view,
        paperCount: this.paperCount, addDayLabel: this.addDayLabel,
        templateId: this.templateId, customTemplate: this.customTemplate, style: this.style,
        generateWarn: this.generateWarn, generateError: this.generateError, pendingRun: this.pendingRun,
      })
    },

    applySnapshot(snapshot: WorkspaceSnapshot) {
      this.undoStack = []; this.redoStack = []; this.generationJobs = []; this.stopRequested = false
      const value = deepClone(snapshot)
      this.grade = value.grade
      this.subject = value.subject
      this.keyword = value.keyword
      this.selectedTags = value.selectedTags
      this.title = value.title
      this.titleHtml = value.titleHtml
      this.difficulty = value.difficulty
      this.hiddenElements = value.hiddenElements
      this.sections = value.sections.map(section => ({
        ...section,
        status: section.status === 'loading' ? 'error' : section.status,
        error: section.status === 'loading' ? '生成请求已中断，可查询原请求结果' : section.error,
      }))
      this.papers = value.papers
      this.view = value.view === 'result' && value.papers.length ? 'result' : 'build'
      this.paperCount = value.paperCount
      this.addDayLabel = value.addDayLabel
      this.templateId = value.templateId
      this.customTemplate = value.customTemplate
      this.style = value.style
      this.generateWarn = value.generateWarn
      this.generateError = value.generateError
      this.pendingRun = value.pendingRun
      this.pendingRun?.jobs.forEach(job => job.chunks.forEach(chunk => {
        if (chunk.state === 'running') chunk.state = 'unknown'
      }))
      this.failedCount = this.pendingRun?.jobs.length || 0
      this.generating = false
      this.layoutMode = false
      this.scope = null
    },

    async initPersistence() {
      if (this.persistenceReady) return
      if (!this.ownerId) { this.persistenceReady = true; this.draftState = 'saved'; return }
      // draftSession 抛错也必须留下 runtime：否则 flushDraft() 恒返回 false，
      // 「退出登录」会被「草稿未保存」永久拦下，而真正的原因（存储不可用）没人看得到。
      let session: { previous: string | null; current: string } = { previous: null, current: randomId() }
      try { session = persistence.draftSession(this.ownerId) }
      catch (error) {
        this.storageError = error instanceof Error ? error.message : '本地草稿会话初始化失败'
      }
      const runtime: DraftRuntime = { owner: this.ownerId, id: session.current, sequence: 0, pending: Promise.resolve() }
      draftRuntimes.set(this, runtime)
      try {
        const draft = await persistence.loadDraft(runtime.owner, session.previous)
        if (draft) {
          this.applySnapshot(draft.snapshot)
          this.draftSavedAt = draft.updatedAt
        }
        this.history = await persistence.listHistory(runtime.owner)
        this.draftState = 'saved'
      } catch (error) {
        this.draftState = 'error'
        this.storageError = error instanceof Error ? error.message : '本地草稿读取失败'
      }
      this.persistenceReady = true
      runtime.stop = watch(() => [
        this.grade, this.subject, this.keyword, this.selectedTags, this.title, this.titleHtml,
        this.difficulty, this.hiddenElements, this.sections, this.papers, this.view,
        this.paperCount, this.addDayLabel, this.templateId, this.customTemplate, this.style,
        this.generateWarn, this.generateError, this.pendingRun,
      ], () => this.queueDraft(), { deep: true })
    },

    queueDraft() {
      const runtime = draftRuntimes.get(this)
      if (!runtime || this.accountChanged) return
      clearTimeout(runtime.timer)
      this.draftState = 'saving'
      runtime.timer = setTimeout(() => { void this.flushDraft() }, 350)
    },

    async flushDraft(): Promise<boolean> {
      const runtime = draftRuntimes.get(this)
      if (!runtime) return false
      clearTimeout(runtime.timer)
      const snapshot = this.captureSnapshot()
      const sequence = ++runtime.sequence
      this.draftState = 'saving'
      const write = runtime.pending.catch(() => {}).then(() => persistence.saveDraft(runtime.owner, runtime.id, snapshot))
      runtime.pending = write
      try {
        const updated = await write
        if (runtime.sequence === sequence) {
          this.draftSavedAt = updated
          this.draftState = 'saved'
          this.storageError = ''
        }
        return true
      } catch {
        this.draftState = 'error'
        this.storageError = '本地保存失败，可能存储空间不足或浏览器禁用了存储；当前内容仍在页面中'
        return false
      }
    },

    async suspendForAccountChange(): Promise<boolean> {
      this.accountChanged = true
      const saved = await this.flushDraft()
      draftRuntimes.get(this)?.stop?.()
      return saved
    },

    disposePersistence() {
      const runtime = draftRuntimes.get(this)
      if (runtime) { clearTimeout(runtime.timer); runtime.stop?.(); draftRuntimes.delete(this) }
      clearTimeout(styleSaveTimers.get(this))
    },

    async refreshHistory() {
      if (!this.ownerId) return
      try { this.history = await persistence.listHistory(this.ownerId) }
      catch { this.storageError = '历史记录读取失败，现有数据未删除' }
    },

    async saveHistory(reason: HistoryReason = 'manual'): Promise<boolean> {
      if (!this.ownerId || this.accountChanged) return false
      try {
        await persistence.addHistory(this.ownerId, this.captureSnapshot(), reason)
        await this.refreshHistory()
        return true
      } catch {
        this.storageError = '历史版本保存失败，可能存储空间不足；现有历史未删除'
        return false
      }
    },

    async saveVersion(): Promise<boolean> {
      if (this.historyBusy || this.generating || this.accountChanged) return false
      this.historyBusy = true
      try { return await this.saveHistory('manual') }
      finally { this.historyBusy = false }
    },

    async restoreHistory(id: string): Promise<boolean> {
      if (this.generating || this.historyBusy || this.accountChanged) return false
      this.historyBusy = true
      try {
        const snapshot = await persistence.getHistory(this.ownerId, id)
        if ((this.sections.length || this.papers.length || this.keyword) && !await this.saveHistory('before-restore')) return false
        this.applySnapshot(snapshot)
        await this.flushDraft()
        if (this.subject) await this.selectSubject(this.subject)
        return true
      } catch (error) {
        this.storageError = error instanceof Error ? error.message : '历史版本恢复失败'
        return false
      } finally { this.historyBusy = false }
    },

    async deleteHistory(id: string) {
      await persistence.removeHistory(this.ownerId, id)
      await this.refreshHistory()
    },

    async refreshUsage() {
      try { this.usage = await api.fetchGenerationUsage() }
      catch { this.usage = null }
    },

    persistTemplates(): boolean {
      const saved = safeSet(K(this.ownerId, LS.myTemplates), JSON.stringify(this.myTemplates))
      if (!saved) this.storageError = '模板本地保存失败，请检查浏览器存储空间'
      return saved
    },

    async syncTemplate(name: string): Promise<boolean> {
      if (this.templateBusy.includes(name) || this.accountChanged) return false
      const template = this.myTemplates.find(value => value.name === name)
      if (!template || template._syncState === 'conflict') return false
      const sent = deepClone(template)
      this.templateBusy.push(name)
      try {
        const revision = await api.upsertTemplate(sent)
        if (this.accountChanged) return false
        const current = this.myTemplates.find(value => value.name === name)
        if (current) {
          const unchanged = sameTemplate(current, sent)
          current._revision = revision
          current._syncState = unchanged ? 'synced' : 'pending'
          current._syncError = ''
          this.persistTemplates()
        }
        return true
      } catch (error) {
        const current = this.myTemplates.find(value => value.name === name)
        if (current) {
          current._syncState = error instanceof api.ApiError && error.status === 409 ? 'conflict' : 'pending'
          current._syncError = error instanceof Error ? error.message : '同步失败'
          this.persistTemplates()
        }
        return false
      } finally { this.templateBusy = this.templateBusy.filter(value => value !== name) }
    },

    async syncTemplatesFromServer() {
      if (this.templatesSyncing || this.accountChanged) return
      this.templatesSyncing = true
      try {
        const server = migrateMyTemplates(await api.fetchTemplates())
        if (this.accountChanged) return
        const local = new Map(this.myTemplates.map(template => [template.name, template]))
        const merged = server.map(remote => {
          const own = local.get(remote.name)
          local.delete(remote.name)
          if (!own || own._syncState === 'synced' || sameTemplate(own, remote)) return { ...remote, _syncState: 'synced' as const }
          if ((own._revision || 0) !== remote._revision) {
            own._syncState = 'conflict'
            own._syncError = '服务端存在其他版本，本地修改已保留；请另存为新模板'
          }
          return own
        })
        for (const own of local.values()) {
          if (own._revision) {
            own._syncState = 'conflict'
            own._syncError = '服务端模板已删除，本地副本已保留'
          }
          merged.push(own)
        }
        this.myTemplates = merged
        this.persistTemplates()
        for (const template of this.myTemplates.filter(value => value._syncState === 'pending')) await this.syncTemplate(template.name)
      } catch { /* Offline edits remain pending and visible. */ }
      finally { this.templatesSyncing = false }
    },

    /* ── 条件选择 ── */
    selectGrade(g: string) {
      if (this.generating || this.grade === g) return
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
      if (!this.grade || !s) return
      const grade = this.grade
      this.scopeLoading = true
      try {
        const scope = await api.fetchScope(grade, s)
        if (this.grade === grade && this.subject === s) this.scope = scope
      } catch {
        if (this.grade === grade && this.subject === s) this.scope = null
      } finally {
        if (this.grade === grade && this.subject === s) this.scopeLoading = false
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
        data: { questions: mockQuestions(type, cnt), topic: '' },
        layout: { ...DEFAULT_LAYOUT },
      }
      this.sections.push(sec)
    },

    removeSection(id: string) {
      if (this.generating || this.accountChanged) return
      this.recordEdit()
      const i = this.sections.findIndex(s => s.id === id)
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
      const sec = this.sections.find(s => s.id === id)
      if (!sec || !sec.data) return
      this.recordEdit()
      n = Math.min(MAX_QUESTIONS_PER_TYPE, Math.max(1, Math.round(n) || 1))
      if (sec.data.questions.slice(n).some(question => question._locked)) {
        this.generateError = '减少题数会移除已锁定题目，请先在管理题目中解锁'
        return
      }
      let qs = sec.data.questions
      if (n < qs.length) {
        qs = qs.slice(0, n)
      } else if (n > qs.length) {
        qs = [...qs, ...mockQuestions(sec.type, n - qs.length)]
      }
      sec.count = n
      sec.data.questions = qs
    },

    async retrySection(id: string, mode: 'retry' | 'recover' = 'retry') {
      if (this.generating || this.accountChanged) return
      const section = this.sections.find(value => value.id === id)
      if (!section || !this.grade || !this.subject || !this.keyword.trim()) return
      const context: GenerationContext = {
        grade: this.grade, subject: this.subject, keyword: this.keyword, title: this.title,
        titleHtml: this.titleHtml, difficulty: this.difficulty, hiddenElements: [...this.hiddenElements],
        count: 1, sections: generationSections([section]),
      }
      const existing = section.pendingGeneration
      if (mode === 'recover' && !existing) {
        section.error = '没有可查询的原请求，未发送新请求'
        return
      }
      if (existing && (existing.context.grade !== this.grade || existing.context.subject !== this.subject
          || existing.context.keyword !== this.keyword || existing.context.sections[0].count !== section.count)) {
        section.error = '原请求的条件已变化，请恢复原草稿或重新生成整卷'
        return
      }
      const run = existing || createGenerationRun(context)
      section.pendingGeneration = run
      section.status = 'loading'
      section.error = ''
      this.generating = true
      try {
        const paper = await runGenerationJob(run.context, run.jobs[0], existing ? mode : 'send', async () => {
          if (this.accountChanged) throw new Error('账号已变化，未发送请求')
          if (this.persistenceReady) await this.flushDraft()
        })
        if (this.accountChanged) return
        section.data = deepClone(paper.sections[0].data)
        section.warn = paper.sections[0].warn
        section.status = 'ready'
        delete section.pendingGeneration
      } catch (error) {
        section.status = 'error'
        section.error = error instanceof Error ? error.message : '生成失败，未自动重试'
      } finally {
        this.generating = false
        if (this.persistenceReady) await this.flushDraft()
        void this.refreshUsage()
      }
    },

    /* ── 生成整卷 ── */
    async generate() {
      if (!this.canGenerate) return
      this.undoStack = []; this.redoStack = []
      this.generating = true
      try {
        if ((this.papers.length || this.pendingRun || this.sections.some(section => section.pendingGeneration))
            && this.persistenceReady && this.ownerId && !await this.saveHistory('before-generate')) return
        if (this.accountChanged) return
      const context: GenerationContext = {
        grade: this.grade, subject: this.subject, keyword: this.keyword.trim(),
        title: this.title, titleHtml: this.titleHtml || undefined, difficulty: this.difficulty,
        hiddenElements: [...this.hiddenElements], count: Math.max(1, Math.min(20, Math.round(this.paperCount) || 1)),
        sections: generationSections(this.sections),
      }
      this.pendingRun = createGenerationRun(context)
      // Each result paper has its own locks; preserve them for the corresponding next paper.
      this.pendingRun.jobs.forEach(job => {
        const previous = this.papers.find((paper, index) => (paper.day || index + 1) === job.index + 1)
        if (!previous || previous.grade !== context.grade || previous.subject !== context.subject || previous.keyword !== context.keyword) return
        const perPaper = deepClone(context)
        perPaper.sections.forEach(section => {
          const old = previous.sections.find(item => item._sid === section.id)
          if (old) section.lockedQuestions = old.data.questions.flatMap((question, index) => question._locked && index < section.count
            ? [{ index, question: deepClone(question) }] : [])
        })
        job.context = perPaper
        job.chunks = createGenerationRun({ ...perPaper, count: 1 }).jobs[0].chunks
      })
      this.papers = []
      this.failedCount = 0
      } finally { this.generating = false }
      await this.runPendingGeneration('send')
    },

    async runPendingGeneration(mode: GenerationMode) {
      const run = this.pendingRun
      if (!run || this.generating || this.accountChanged) return
      this.generating = true
      this.stopRequested = false
      this.generateError = ''
      this.generateWarn = ''
      const pending = [...run.jobs]
      this.generationJobs = [...run.jobs]
      const completed = new Set<number>()
      const errors: string[] = []
      const total = pending.length
      let finished = 0
      let filled = false
      const prefix = mode === 'recover' ? '正在查询' : mode === 'retry' ? '正在补齐' : '正在生成'
      this.generateProgress = prefix + ' 0/' + total + ' 份'
      try {
        await Promise.all(Array.from({ length: Math.min(3, total) }, async () => {
          while (pending.length && !this.accountChanged && !this.stopRequested) {
            const job = pending.shift()!
            job.startedAt = Date.now(); job.finishedAt = undefined; job.error = ''
            try {
              const paper = await runGenerationJob(job.context || run.context, job, mode, async () => {
                if (this.accountChanged) throw new Error('账号已变化，未发送新请求')
                if (this.stopRequested) throw new GenerationStopped()
                if (this.persistenceReady) await this.flushDraft()
                if (this.accountChanged) throw new Error('账号已变化，未发送新请求')
                if (this.stopRequested) throw new GenerationStopped()
              })
              if (this.accountChanged) return
              completed.add(job.index)
              this.papers.push(paper)
              run.jobs = run.jobs.filter(value => value.index !== job.index)
              this.papers.sort((a, b) => (a.day || 1) - (b.day || 1))
              if (!filled && this.grade === run.context.grade && this.subject === run.context.subject && this.keyword.trim() === run.context.keyword) {
                filled = true
                paper.sections.forEach(result => {
                  const section = this.sections.find(value => value.id === result._sid)
                  if (!section) return
                  section.data = deepClone(result.data)
                  section.warn = result.warn
                  section.status = result.data.questions.length ? 'ready' : 'error'
                  section.error = result.data.questions.length ? '' : '该大题没有可用题目'
                })
              }
            } catch (error) {
              job.error = error instanceof Error ? error.message : '生成失败'
              errors.push(error instanceof Error ? error.message : '生成失败')
            }
            job.finishedAt = Date.now()
            finished++
            this.generateProgress = prefix + ' ' + finished + '/' + total + ' 份'
          }
        }))
        if (this.accountChanged) return
        run.jobs = run.jobs.filter(job => !completed.has(job.index))
        this.failedCount = run.jobs.length
        if (!run.jobs.length) this.pendingRun = null
        const warningCount = this.papers.reduce((count, paper) => count + paper.sections.filter(section => section.warn).length, 0)
        const warnings = []
        if (this.failedCount) warnings.push(this.failedCount + ' 份尚未完成，未自动重发；可查询原请求或手动补齐')
        if (warningCount) warnings.push(warningCount + ' 个大题有质量或缺题提示，请核对后使用')
        this.generateWarn = warnings.join('；')
        if (this.papers.length) {
          this.showAnswers = false
          this.view = 'result'
          if (completed.size) await this.saveHistory('generated')
        } else {
          this.generateError = errors[0] || '没有可用试卷'
        }
      } finally {
        this.generating = false
        this.generateProgress = ''
        if (this.persistenceReady) await this.flushDraft()
        void this.refreshUsage()
      }
    },

    async recoverPending() {
      await this.runPendingGeneration('recover')
    },

    async retryFailed() {
      await this.runPendingGeneration('retry')
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

    /** 用当前搭建区再来一批（题目不同） */
    async regenerate() {
      await this.generate()
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
      styleSaveTimers.set(this, setTimeout(() => {
        safeSet(K(owner, LS.paperStyle), JSON.stringify(style))
      }, 300))
    },

    applyStylePreset(preset: 'standard' | 'colorful' | 'fun') {
      if (preset === 'standard') this.setStyle({ bg: 'none', banner: false, secColor: false, frame: 'none', encourage: false, reward: false })
      else if (preset === 'colorful') this.setStyle({ bg: 'dots', bgOpacity: 70, banner: true, secColor: true, frame: 'none', encourage: false, reward: false })
      else this.setStyle({ bg: 'clouds', bgOpacity: 60, banner: true, secColor: true, frame: 'rainbow', encourage: true, reward: true, kidFont: 'on' })
    },

    /* ── 自定义题型 ── */
    addCustomType(name: string, baseType: string, defaultCount: number) {
      this.customTypes.push({ id: 'custom_' + Date.now().toString(36), name, baseType, defaultCount })
      safeSet(K(this.ownerId, LS.customTypes), JSON.stringify(this.customTypes))
    },

    removeCustomType(id: string) {
      this.customTypes = this.customTypes.filter(t => t.id !== id)
      safeSet(K(this.ownerId, LS.customTypes), JSON.stringify(this.customTypes))
    },

    /* ── 我的模板 ── */
    async saveMyTemplate(name: string) {
      if (!name.trim() || name.length > 120 || this.accountChanged) return { local: false, synced: false }
      const existing = this.myTemplates.find(template => template.name === name)
      const tpl: MyTemplate = {
        name,
        _revision: existing?._revision || 0,
        _syncState: existing?._syncState === 'conflict' ? 'conflict' : 'pending',
        _syncError: existing?._syncState === 'conflict' ? existing._syncError : '',
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
        sections: deepClone(this.sections).map((s: any) => ({
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
      const local = this.persistTemplates()
      const synced = await this.syncTemplate(name)
      return { local, synced }
    },

    loadMyTemplate(name: string): boolean {
      if (this.generating || this.accountChanged) return false
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
        this.sections = deepClone(tpl.sections).map((s: any) => ({
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

    async deleteMyTemplate(name: string) {
      if (this.accountChanged || this.templateBusy.includes(name)) throw new Error('模板正在同步，请稍后再试')
      const template = this.myTemplates.find(value => value.name === name)
      if (!template) return
      let revision = template._revision || 0
      if (!revision) {
        const remote = (await api.fetchTemplates()).find(value => value.name === name)
        if (remote) {
          if (!sameTemplate(template, migrateMyTemplates([remote])[0])) throw new Error('服务端存在同名的其他版本，未删除任何数据')
          revision = remote._revision || 0
        }
      }
      if (revision) await api.deleteTemplateOnServer(name, revision)
      if (this.accountChanged) return
      this.myTemplates = this.myTemplates.filter(template => template.name !== name)
      this.persistTemplates()
    },

    async copyMyTemplate(name: string, newName: string): Promise<boolean> {
      const original = this.myTemplates.find(template => template.name === name)
      if (!original || !newName.trim() || newName.length > 120 || this.accountChanged) return false
      if (this.myTemplates.some(template => template.name === newName.trim())) throw new Error('已有同名模板，请更换名称')
      this.myTemplates.unshift({ ...deepClone(original), name: newName.trim(), _revision: 0, _syncState: 'pending', _syncError: '' })
      const local = this.persistTemplates()
      const synced = await this.syncTemplate(newName.trim())
      return local || synced
    },
  },
})
