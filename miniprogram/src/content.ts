import { parseDocument } from 'htmlparser2'
import type { Question } from './types'

export type RichNode = { type: 'text'; text: string } | { name: string; attrs?: Record<string, string>; children: RichNode[] }
type ChildNode = ReturnType<typeof parseDocument>['children'][number]
const allowed = new Set(['b', 'strong', 'em', 'i', 'u', 's', 'sup', 'sub', 'p', 'div', 'span', 'br', 'ul', 'ol', 'li', 'table', 'thead', 'tbody', 'tr', 'td', 'th'])
const blocked = new Set(['script', 'style', 'iframe', 'object', 'embed', 'form', 'svg', 'math'])

export function richNodes(html: unknown, fallback = ''): RichNode[] {
  if (typeof html !== 'string' || !html) return [{ type: 'text', text: fallback }]
  let budget = 3000
  function convert(nodes: ChildNode[], depth = 0): RichNode[] {
    if (depth > 24) return []
    const result: RichNode[] = []
    for (const node of nodes) {
      if (--budget < 0) break
      if (node.type === 'text') result.push({ type: 'text', text: node.data })
      else if ('name' in node && 'children' in node && !blocked.has(node.name)) {
        const children = convert(node.children, depth + 1)
        if (allowed.has(node.name)) result.push({ name: node.name, children })
        else result.push(...children)
      }
    }
    return result
  }
  return convert(parseDocument(html.slice(0, 50000)).children)
}

export function answerText(question: Question): string {
  const answer = question.answer
  if (answer == null || answer === '') return '暂无答案'
  if (Array.isArray(answer)) {
    if (answer.every(pair => Array.isArray(pair) && pair.length === 2 && pair.every(Number.isInteger))) {
      return answer.map(([left, right]) => `${left + 1} → ${right + 1}`).join('，')
    }
    return answer.map(value => String(value ?? '')).join('，')
  }
  if (typeof answer === 'number' && question.options) return `${String.fromCharCode(65 + answer)}. ${question.options[answer] || ''}`
  return String(answer)
}

export const sectionNames: Record<string, string> = {
  quiz: '选择题', fill_blank: '填空题', true_false: '判断题', match_pair: '连线题', oral_math: '口算题',
  vertical_calc: '竖式计算', recursive_calc: '递等式计算', smart_calc: '简便计算', number_split: '数的分成',
  compare: '比大小', word_problem: '应用题', reading: '阅读理解', challenge: '挑战题',
}
export function formatDate(seconds: number) {
  const date = new Date(seconds * 1000)
  return `${date.getFullYear()}.${String(date.getMonth() + 1).padStart(2, '0')}.${String(date.getDate()).padStart(2, '0')}`
}
export function fileSize(bytes: number) { return bytes < 1024 * 1024 ? `${Math.ceil(bytes / 1024)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB` }
export function fileStatus(status: string) { return ({ pending: '文件待上传', uploading: '文件上传中', failed: '文件未就绪', ready: '已归档' } as Record<string, string>)[status] || status }
