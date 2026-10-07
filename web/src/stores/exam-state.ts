import { TEMPLATES, LS } from '../constants'
import type {
  CustomType,
  Difficulty,
  PaperData,
  PaperStyle,
  PaperTemplate,
  ScopeData,
  Section,
} from '../types'
import type { GenerationRun } from '../generation'
import type { HistoryEntry } from '../persistence'
import type { EditSnapshot } from '../workspace-history'
import type * as api from '../api'
import { useAuthStore } from './auth'
import { K, load, loadArr, migrateMyTemplates, migratePaperStyle, STYLE_DEFAULTS } from './exam-local'

export const createExamState = () => {
  const ownerId = String(useAuthStore().user?.id || '')
  // 自定义模板存为响应式 state（历史实现直接改模块常量 TEMPLATES 的 custom 项，
  // 它不是响应式对象——正在使用 custom 模板时编辑配置，卷面不更新，要切走再切回才生效）
  const customTpl: PaperTemplate = { ...TEMPLATES.find((t) => t.id === 'custom')! }
  try {
    const savedCustom = JSON.parse(localStorage.getItem(K(ownerId, LS.customTemplate)) || 'null')
    if (savedCustom) Object.assign(customTpl, savedCustom)
  } catch {
    /* ignore */
  }
  let templateId = 'exam'
  try {
    const p = JSON.parse(localStorage.getItem(K(ownerId, LS.template)) || 'null')
    if (p?.id && TEMPLATES.some((t) => t.id === p.id)) templateId = p.id
  } catch {
    /* ignore */
  }

  return {
    ownerId,
    accountChanged: false,
    persistenceReady: false,
    draftState: 'loading' as 'loading' | 'saving' | 'saved' | 'error',
    draftSavedAt: 0,
    storageError: '',
    history: [] as HistoryEntry[],
    historyBusy: false,
    historyLoading: false,
    historyError: '',
    historyOffset: 0,
    historyQuery: '',
    historyHasMore: false,
    draftId: '',
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
    scopeRevision: 0,

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
}

export type ExamState = ReturnType<typeof createExamState>
