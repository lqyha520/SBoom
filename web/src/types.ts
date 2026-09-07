/* ── 领域类型定义 ── */

/** 题目（各题型字段的超集，按形状判别渲染） */
export interface Question {
  id?: number
  type?: string
  stem?: string
  options?: string[]
  /** 选择题为索引；填空/口算为文字或数字；连线为 [leftIdx, rightIdx][] */
  answer?: number | string | [number, number][]
  acceptable_answers?: string[]
  analysis?: string
  tags?: string[]
  difficulty_level?: number
  expected_time_seconds?: number
  /** 连线题 */
  left_items?: string[]
  right_items?: string[]
  /** 数的分成 */
  top?: string | number
  left?: string | number
  right?: string | number
  /** 比大小 */
  left_expr?: string
  right_expr?: string
  /** 前端运行时标记（稳定 uid，供排版模式回写） */
  _qid?: string
  /** 富文本编辑缓存（排版模式 B/字号/颜色 的结果，v-html 原样渲染） */
  _stemHtml?: string
  _optsHtml?: string[]
}

/** 一个大题的生成数据 */
export interface GameData {
  questions: Question[]
  passage?: string
  topic?: string
  difficulty?: string
  grade?: string
  subject?: string
  [k: string]: unknown
}

/** 大题卡片排版配置 */
export interface SecLayout {
  qCols: number
  optCols: number
  tableBorder: 'none' | 'solid' | 'dashed'
  fontSize: string
  showNo: boolean
  /** 表格模式：列宽（px，按列索引；undefined = 自动） */
  colWidths?: (number | undefined)[]
  /** 表格模式：行高（px；undefined = 自动） */
  rowHeight?: number
}

/** 搭建区的大题卡片 */
export interface Section {
  id: string
  /** 实际请求后端的 game_type */
  type: string
  /** 显示名（自定义题型时为用户定义的名字） */
  name?: string
  count: number
  status: 'loading' | 'ready' | 'error'
  data: GameData | null
  layout: SecLayout
  error?: string
}

/** 结果卷中的大题 */
export interface PaperSection {
  type: string
  /** 显示名（自定义题型时为用户定义的名字） */
  name?: string
  data: GameData
  layout: SecLayout
  /** 稳定 id（排版模式 DOM 回写用） */
  _sid?: string
}

/** 一份完整试卷 */
export interface PaperData {
  grade: string
  subject: string
  keyword: string
  title: string
  /** 标题富文本（排版模式改色/加粗缓存） */
  titleHtml?: string
  difficulty: string
  sections: PaperSection[]
  /** 第几份（1 起，多份生成时） */
  day?: number
}

/** 自定义题型 */
export interface CustomType {
  id: string
  name: string
  baseType: string
  defaultCount: number
}

/** 卷面模板（卷头/信息栏/注意事项等开关） */
export interface PaperTemplate {
  id: string
  name: string
  tag: string
  showInfoRow: boolean
  showNotice: boolean
  showScore: boolean
  titlePrefix: string
  titleSuffix: string
  footer: string
  headerExtra: string
}

/** 卷面装饰风格（彩色 + 童趣合并） */
export interface PaperStyle {
  bg: 'none' | 'dots' | 'grid' | 'stars' | 'clouds' | 'rainbow'
  bgOpacity: number
  banner: boolean
  secColor: boolean
  frame: 'none' | 'rainbow' | 'stars' | 'crayon' | 'dots'
  encourage: boolean
  reward: boolean
  /** auto=低年级自动放大 / on / off */
  kidFont: 'auto' | 'on' | 'off'
  exportBg: boolean
  /** 标题字号缩放（1 = 默认 22pt） */
  titleScale: number
}

export type Difficulty = 'easy' | 'medium' | 'hard'

/** 知识点范围（含学期分组） */
export interface ScopeData {
  allowed: string[]
  semesters?: Record<'上册' | '下册', string[]>
}

/** 我保存的卷面模板 */
export interface MyTemplate {
  name: string
  grade: string
  subject: string
  keyword: string
  title: string
  /** 标题富文本 */
  titleHtml?: string
  difficulty: Difficulty
  templateId: string
  /** 卷面装饰风格（背景/边框/字号等），恢复时原样应用 */
  style?: PaperStyle
  /** 已删除的卷头/卷尾元素 */
  hiddenElements?: string[]
  cards: { type: string; count: number; layout: SecLayout }[]
  /** 完整数据（V2）：每题编辑后的文字/答案/版式，恢复时原样还原 */
  sections?: { type: string; count: number; layout: SecLayout; data: GameData }[]
  /** 旧版 DOM 快照（迁移兼容用） */
  paperSnapshot?: string
}
