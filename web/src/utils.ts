import { CN_NUM, TYPE_NAME } from './constants'
import type { GameData, PaperSection, Question } from './types'

/* ── 年级数字：小学一~六 → 1~6，初一~三 → 7~9 ── */
const CN_GRADE_NUM: Record<string, number> = { 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9 }

export function gradeNumOf(g: string): number {
  g = g || ''
  if (g.includes('初')) {
    const m = g.match(/[一二三]/)
    return m ? 6 + (CN_GRADE_NUM[m[0]] || 0) : 7
  }
  const m = g.match(/[一二三四五六]/)
  return m ? CN_GRADE_NUM[m[0]] || 0 : 0
}

/* ── 圈号（①~㊿ 完整 Unicode 序列，50 以上退回数字） ── */
const CIRCLES = (
  '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳' + // 1-20  U+2460-
  '㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚㉛㉜㉝㉞㉟㊱㊲㊳㊴㊵㊶㊷㊸㊹㊺' + // 21-45 U+3251-
  '㊻㊼㊽㊾㊿' // 46-50 U+32B1-
)
export function cirNum(n: number): string {
  return n >= 1 && n <= 50 ? CIRCLES[n - 1] : `${n}.`
}

/* ── 判断题题干格式化：去末尾句号，补（　） ── */
export function tfStem(s: string): string {
  let t = String(s ?? '').trim()
  t = t.replace(/。+\s*$/, '')
  if (!/[（(]\s*[）)]\s*$/.test(t)) t += '（　）'
  return t
}

/* ── 剥掉 LLM 误带的选项字母前缀 ── */
export function stripOptPrefix(o: string): string {
  const m = String(o).trim().match(/^(?:[（(][A-H][）)]|[A-H](?:\.|:|：|、|．|\)|）))\s*(.+)$/)
  return m ? m[1] : String(o)
}

/* ── 数的分成空位判断 ── */
export function isBlankVal(v: unknown): boolean {
  if (v === null || v === undefined) return true
  const s = String(v).trim()
  return s === '' || /^_+$/.test(s) || s === '?' || s === '□'
}

/* ── 答案文字 ── */
export function ansText(q: Question): string {
  if (q.options && typeof q.answer === 'number') return String.fromCharCode(65 + q.answer)
  if (Array.isArray(q.answer)) return (q.answer as [number, number][]).map(p => `${p[0] + 1}－${p[1] + 1}`).join('，')
  return String(q.answer ?? '')
}

/** 统一的答案展示（含选择题选项文字） */
export function answerOf(q: Question): string {
  if (q.top != null) {
    const t = isBlankVal(q.top) ? q.answer : q.top
    const l = isBlankVal(q.left) ? q.answer : q.left
    const r = isBlankVal(q.right) ? q.answer : q.right
    return `${t} 分成 ${l} 和 ${r}`
  }
  if (q.left_expr != null) return `${q.left_expr} ○ ${q.right_expr} → ${q.answer}`
  if (q.left_items) return ((q.answer as [number, number][]) || []).map(p => `（${p[0] + 1}）→（${p[1] + 1}）`).join('；')
  let a = ansText(q)
  if (q.options && typeof q.answer === 'number') a += `（${stripOptPrefix(q.options[q.answer] || '')}）`
  return a
}

/* ── HTML 转义（v-html 渲染纯文本用） ── */
export function escHtml(s: unknown): string {
  return String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c] as string))
}

/* ── 稳定 uid ── */
let _uidSeq = 0
export function uid(prefix = 'u'): string {
  return `${prefix}${++_uidSeq}_${Math.random().toString(36).slice(2, 7)}`
}

/* ── 排版预览用的模拟题目 ── */
export function mockQuestions(type: string, count: number): Question[] {
  const qs: Question[] = []
  for (let i = 0; i < count; i++) {
    const n = i + 1
    if (type === 'quiz') {
      qs.push({ type: 'multiple_choice', stem: `${n + 2} + 3 = ？`, options: ['3', '4', '5', '6'], answer: 2, analysis: '' })
    } else if (type === 'fill_blank') {
      qs.push({ type: 'fill_blank', stem: `${n} + ${n} = ____`, answer: `${n * 2}`, analysis: '' })
    } else if (type === 'oral_math') {
      qs.push({ type: 'oral_math', stem: `${n}×${n * 7}=`, answer: `${n * n * 7}`, analysis: '' })
    } else if (type === 'vertical_calc') {
      qs.push({ type: 'vertical_calc', stem: `${123 + n} + ${456 - n} =`, answer: '579', analysis: '' })
    } else if (type === 'recursive_calc') {
      qs.push({ type: 'recursive_calc', stem: `${100 + n} − ${n * 3} + ${n * 2} =`, answer: '', analysis: '' })
    } else if (type === 'smart_calc') {
      qs.push({ type: 'smart_calc', stem: `${n * 25}×4 =`, answer: `${n * 100}`, analysis: '' })
    } else if (type === 'match_pair') {
      qs.push({ type: 'match_pair', stem: '连一连。', left_items: ['2+3', '4+1'], right_items: ['5', '5'], answer: [[0, 0], [1, 1]], analysis: '' })
    } else if (type === 'challenge') {
      qs.push({ type: 'challenge', stem: `第${n}关：${n * 2} + ${n} = ____`, answer: `${n * 3}`, analysis: '' })
    } else if (type === 'reading') {
      qs.push({ type: 'reading', stem: `${n}. 读一读，答一答。`, answer: '', analysis: '' })
    } else if (type === 'number_split') {
      const top = n + 8
      if (n % 2 === 1) qs.push({ type: 'number_split', top, left: n, right: '__', answer: top - n, analysis: '' })
      else qs.push({ type: 'number_split', top: '__', left: n, right: n + 1, answer: n + (n + 1), analysis: '' })
    } else if (type === 'compare') {
      const a = n + 2, b = n + 1
      qs.push({ type: 'compare', left_expr: `${a}`, right_expr: `${b}`, answer: a > b ? '>' : a < b ? '<' : '=', analysis: '' })
    } else if (type === 'true_false') {
      qs.push({ type: 'true_false', stem: `${n + 5} 比 ${n} 大`, answer: '√', analysis: '' })
    } else if (type === 'word_problem') {
      qs.push({ type: 'word_problem', stem: `小明有${n + 3}个苹果，吃了${n}个，还剩几个？`, answer: '3', analysis: '' })
    } else {
      qs.push({ type, stem: `第 ${n} 题：模拟题目，排版预览用。`, answer: '', analysis: '' })
    }
  }
  qs.forEach(q => { q._qid = uid('q') })
  return qs
}

/* ── 分值：客观题每题 2 分，其余平摊，总和恒为 100 ── */
export function computeScores(sections: PaperSection[]): Map<Question, number> {
  const score = new Map<Question, number>()
  const allQs = sections.flatMap(s => s.data.questions || [])
  const isObj = (q: Question) => !!q.options
  const objQs = allQs.filter(isObj)
  const subQs = allQs.filter(q => !isObj(q))
  if (subQs.length) {
    objQs.forEach(q => score.set(q, 2))
    const remain = Math.max(100 - objQs.length * 2, subQs.length)
    const base = Math.floor(remain / subQs.length)
    let extra = remain - base * subQs.length
    subQs.forEach(q => score.set(q, base + (extra-- > 0 ? 1 : 0)))
  } else if (allQs.length) {
    const base = Math.floor(100 / allQs.length)
    let extra = 100 - base * allQs.length
    allQs.forEach(q => score.set(q, base + (extra-- > 0 ? 1 : 0)))
  }
  return score
}

/* ── 汇总行文字 ── */
export function summaryText(grade: string, subject: string, keyword: string, sections: PaperSection[]): string {
  const total = sections.reduce((s, x) => s + (x.data.questions?.length || 0), 0)
  const parts = sections.map(s => `${TYPE_NAME[s.type] || s.type}×${s.data.questions?.length || 0}`).join(' + ')
  return `${grade} ${subject} ｜ ${keyword} ｜ 共 ${total} 题（${parts}）｜ 满分 100 分`
}

export function secTitle(type: string, si: number, name?: string): string {
  return `${CN_NUM[si] || si + 1}、${name || TYPE_NAME[type] || type}`
}

/** 确保题目都有 _qid（生成/回填后调用） */
export function ensureQids(data: GameData): void {
  ;(data.questions || []).forEach(q => { if (!q._qid) q._qid = uid('q') })
}
