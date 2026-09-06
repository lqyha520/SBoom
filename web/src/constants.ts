import type { Difficulty, PaperTemplate, SecLayout } from './types'

/* ── 题型 ── */
export const TYPE_NAME: Record<string, string> = {
  quiz: '选择题',
  fill_blank: '填空题',
  match_pair: '连线配对',
  challenge: '闯关挑战',
  oral_math: '口算题',
  reading: '阅读理解',
  vertical_calc: '竖式计算',
  recursive_calc: '脱式计算',
  smart_calc: '简便计算',
  number_split: '数的分成',
  compare: '比大小',
  true_false: '判断题',
  word_problem: '应用题',
}

/** 按年级+科目动态显示题型（依据人教版真实试卷结构） */
export const TYPE_GROUPS_BY_GRADE: Record<string, Record<number, [string, string[]][]>> = {
  数学: {
    1: [['基础', ['oral_math', 'fill_blank', 'true_false', 'quiz', 'number_split', 'compare']], ['计算', ['vertical_calc']], ['应用', ['word_problem']], ['配对', ['match_pair']]],
    2: [['基础', ['oral_math', 'fill_blank', 'true_false', 'quiz', 'number_split', 'compare']], ['计算', ['vertical_calc']], ['应用', ['word_problem', 'challenge']], ['配对', ['match_pair']]],
    3: [['基础', ['fill_blank', 'true_false', 'quiz', 'oral_math']], ['计算', ['vertical_calc', 'recursive_calc']], ['应用', ['word_problem']], ['拓展', ['challenge', 'reading', 'match_pair']]],
    4: [['基础', ['fill_blank', 'true_false', 'quiz', 'oral_math']], ['计算', ['vertical_calc', 'recursive_calc', 'smart_calc']], ['应用', ['word_problem']], ['拓展', ['challenge', 'reading', 'match_pair']]],
    5: [['基础', ['fill_blank', 'true_false', 'quiz', 'oral_math']], ['计算', ['vertical_calc', 'recursive_calc', 'smart_calc']], ['应用', ['word_problem']], ['拓展', ['challenge', 'reading', 'match_pair']]],
    6: [['基础', ['fill_blank', 'true_false', 'quiz', 'oral_math']], ['计算', ['vertical_calc', 'recursive_calc', 'smart_calc']], ['应用', ['word_problem']], ['拓展', ['challenge', 'reading', 'match_pair']]],
    7: [['基础', ['fill_blank', 'true_false', 'quiz']], ['计算', ['oral_math', 'vertical_calc', 'recursive_calc', 'smart_calc']], ['应用', ['word_problem']], ['拓展', ['challenge', 'reading', 'match_pair']]],
    8: [['基础', ['fill_blank', 'true_false', 'quiz']], ['计算', ['oral_math', 'vertical_calc', 'recursive_calc', 'smart_calc']], ['应用', ['word_problem']], ['拓展', ['challenge', 'reading', 'match_pair']]],
    9: [['基础', ['fill_blank', 'true_false', 'quiz']], ['计算', ['oral_math', 'vertical_calc', 'recursive_calc', 'smart_calc']], ['应用', ['word_problem']], ['拓展', ['challenge', 'reading', 'match_pair']]],
  },
  语文: {
    1: [['字词', ['fill_blank', 'match_pair', 'quiz']]],
    2: [['字词', ['fill_blank', 'match_pair', 'quiz']]],
    3: [['基础', ['fill_blank', 'quiz', 'match_pair']], ['拓展', ['reading', 'challenge']]],
    4: [['基础', ['fill_blank', 'quiz', 'match_pair']], ['拓展', ['reading', 'challenge']]],
    5: [['基础', ['fill_blank', 'quiz', 'match_pair']], ['拓展', ['reading', 'challenge']]],
    6: [['基础', ['fill_blank', 'quiz', 'match_pair']], ['拓展', ['reading', 'challenge']]],
    7: [['基础', ['fill_blank', 'quiz', 'match_pair']], ['拓展', ['reading', 'challenge']]],
    8: [['基础', ['fill_blank', 'quiz', 'match_pair']], ['拓展', ['reading', 'challenge']]],
    9: [['基础', ['fill_blank', 'quiz', 'match_pair']], ['拓展', ['reading', 'challenge']]],
  },
  英语: {
    1: [['基础', ['quiz', 'match_pair', 'fill_blank']]],
    2: [['基础', ['quiz', 'match_pair', 'fill_blank']]],
    3: [['基础', ['quiz', 'match_pair', 'fill_blank']], ['拓展', ['reading']]],
    4: [['基础', ['quiz', 'match_pair', 'fill_blank']], ['拓展', ['reading']]],
    5: [['基础', ['quiz', 'match_pair', 'fill_blank']], ['拓展', ['reading', 'challenge']]],
    6: [['基础', ['quiz', 'match_pair', 'fill_blank']], ['拓展', ['reading', 'challenge']]],
    7: [['基础', ['quiz', 'match_pair', 'fill_blank']], ['拓展', ['reading', 'challenge']]],
    8: [['基础', ['quiz', 'match_pair', 'fill_blank']], ['拓展', ['reading', 'challenge']]],
    9: [['基础', ['quiz', 'match_pair', 'fill_blank']], ['拓展', ['reading', 'challenge']]],
  },
}

/** 其他科目默认题型 */
export const TYPE_GROUPS_DEFAULT: [string, string[]][] = [
  ['基础', ['quiz', 'fill_blank', 'match_pair']],
  ['拓展', ['reading', 'challenge']],
]

export const TYPE_DEFAULT: Record<string, number> = {
  quiz: 4,
  fill_blank: 4,
  match_pair: 1,
  challenge: 3,
  oral_math: 6,
  reading: 1,
  vertical_calc: 4,
  recursive_calc: 4,
  smart_calc: 4,
  number_split: 5,
  compare: 5,
  true_false: 5,
  word_problem: 3,
}

export const CN_NUM = ['一', '二', '三', '四', '五', '六', '七', '八', '九']
export const DIFF_NAME: Record<Difficulty, string> = { easy: '简单', medium: '中等', hard: '困难' }

export const DEFAULT_LAYOUT: SecLayout = {
  qCols: 1,
  optCols: 2,
  tableBorder: 'none',
  fontSize: '',
  showNo: true,
}

/* ── 卷面模板 ── */
export const TEMPLATES: PaperTemplate[] = [
  { id: 'exam', name: '标准试卷', tag: '测验/考试', showInfoRow: true, showNotice: true, showScore: true, titlePrefix: '', titleSuffix: '测试卷', footer: '—— 卷终 · 认真检查，你一定行！——', headerExtra: '' },
  { id: 'daily', name: '每日一练', tag: '每日练习', showInfoRow: false, showNotice: false, showScore: false, titlePrefix: '每日一练', titleSuffix: '', footer: '坚持就是胜利！', headerExtra: '日期：______  用时：______' },
  { id: 'weekend', name: '周末作业', tag: '周末巩固', showInfoRow: true, showNotice: true, showScore: false, titlePrefix: '周末巩固', titleSuffix: '练习', footer: '—— 认真完成，周一检查！——', headerExtra: '' },
  { id: 'unit', name: '单元测验', tag: '单元复习', showInfoRow: true, showNotice: true, showScore: true, titlePrefix: '第  单元', titleSuffix: '测验卷', footer: '—— 卷终 · 认真答题 ——', headerExtra: '时间：40 分钟' },
  { id: 'custom', name: '自定义', tag: '自定义', showInfoRow: true, showNotice: true, showScore: true, titlePrefix: '', titleSuffix: '', footer: '', headerExtra: '' },
]

/* ── 鼓励语 ── */
export const ENCOURAGE_MAP: Record<string, string> = {
  quiz: '选一选，我最棒！',
  fill_blank: '填一填，我能行！',
  true_false: '判一判，我会辨！',
  match_pair: '连一连，找朋友！',
  oral_math: '算一算，我最快！',
  vertical_calc: '算一算，我最快！',
  recursive_calc: '算一算，我最快！',
  smart_calc: '算一算，我最巧！',
  number_split: '分一分，难不倒我！',
  compare: '比一比，我细心！',
  word_problem: '解一解，我最聪明！',
  reading: '读一读，我最认真！',
  challenge: '闯一闯，我是小勇士！',
}

/* ── localStorage keys ── */
export const LS = {
  customTypes: 'lc_custom_types',
  template: 'lc_template',
  customTemplate: 'lc_custom_template',
  paperStyle: 'lc_paper_style',
  llm: 'lc_llm_cfg',
  myTemplates: 'lc_my_templates',
} as const

export const LLM_DEFAULTS = {
  baseUrl: 'https://ai.bcxtech.cc.cd/v1',
  model: 'gpt-5.6-terra',
  apiKey: '',
  timeout: 60,
}
