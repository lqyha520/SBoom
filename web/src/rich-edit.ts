import { sanitizeRich } from './sanitize'

/**
 * 卷面可编辑区域的内容回写。
 *
 * 题号（①、51.）、选项字母（A.）、连线序号（（1））是渲染时加在内容最前面的标签，和内容处在同一个
 * contenteditable 里。回写时只去掉「渲染时加的那个标签」，不按字符集猜：早期的 [①-㊿] 覆盖
 * U+2460–U+32BF 整段，关闭题号时会把《「【□○△ 等正文首字当成题号删掉。
 * 标签可能被一起加粗/改色（整项选中后设格式），所以按文字跨节点删除，保留格式标签。
 */

/** 排版模式注入到卷面里的控件（拖拽手柄、删除按钮、缩放条），不属于题目内容 */
const EDITOR_UI = '.sort-handle, .el-del, .q-tools, .sec-tools, .cell-resizer, .col-resizer, .row-resizer'
const BLOCKS = new Set(['DIV', 'P', 'LI', 'TR', 'TABLE', 'THEAD', 'TBODY', 'UL', 'OL', 'CENTER'])

export interface EditedContent {
  /** 净化后的富文本，不含标签（写进 _stemHtml / _optsHtml） */
  html: string
  /** 纯文本，不含标签（写进 stem / options / 连线项） */
  text: string
}

const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/** 渲染在内容最前面的固定标签，如题号「①」「51.」、连线序号「（1）」 */
export function labelPattern(label: string): RegExp {
  return new RegExp(`^\\s*${escapeRegExp(label.trim())}\\s*`)
}

/** 选项字母：渲染为「A. 」；用户把点改成「、」「：」等也照样认 */
export function optionLabel(index: number): RegExp {
  return new RegExp(`^\\s*${String.fromCharCode(65 + index)}\\s*[.、：:．]\\s*`)
}

/** 旧缓存可能已经带着标签（例如整项加粗时字母被包进 <b>），渲染时据此避免重复加标签 */
export function startsWithLabel(html: string, label: RegExp): boolean {
  return label.test(html.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' '))
}

/** 读取卷面元素（或渲染用的 HTML 串）的内容，去掉最前面的标签 */
export function readEdited(source: HTMLElement | string, label: RegExp | null): EditedContent {
  // 在惰性文档里解析和克隆：不加载图片、不执行脚本，也不改动页面上的元素
  const root = document.implementation.createHTMLDocument('').body
  if (typeof source === 'string') root.innerHTML = source
  else source.childNodes.forEach(node => root.appendChild(root.ownerDocument.importNode(node, true)))
  root.querySelectorAll(EDITOR_UI).forEach(node => node.remove())
  if (label) dropLeadingText(root, label)
  return { html: sanitizeRich(root.innerHTML), text: plainText(root) }
}

/** 按纯文本匹配标签，再从前往后跨文本节点删掉同样多的字符 */
function dropLeadingText(root: HTMLElement, label: RegExp) {
  const match = (root.textContent || '').match(label)
  let remaining = match ? match[0].length : 0
  const walker = root.ownerDocument.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  while (remaining > 0 && walker.nextNode()) {
    const node = walker.currentNode as Text
    const cut = Math.min(remaining, node.data.length)
    node.data = node.data.slice(cut)
    remaining -= cut
  }
}

/** 纯文本：换行只按 <br> 和块级元素计算，不依赖浏览器排版（测试环境与浏览器结果一致） */
function plainText(root: Node): string {
  let out = ''
  const visit = (node: Node) => {
    node.childNodes.forEach(child => {
      if (child.nodeType === Node.TEXT_NODE) out += (child as Text).data
      else if (child.nodeName === 'BR') out += '\n'
      else if (child.nodeType === Node.ELEMENT_NODE) {
        const block = BLOCKS.has(child.nodeName)
        if (block) out += '\n'
        visit(child)
        if (block) out += '\n'
      }
    })
  }
  visit(root)
  return out.replace(/[ \t]*\n[ \t]*/g, '\n').replace(/\n{2,}/g, '\n').trim()
}
