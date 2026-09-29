import DOMPurify from 'dompurify'

/**
 * 试卷富文本净化（v-html 渲染前必经）。
 *
 * 背景：题干/选项/标题支持 contenteditable 富文本（排版模式可改字号/颜色），
 * 内容会随模板持久化到 localStorage 与服务端；若不净化，粘贴的
 * <img onerror> / <a href="javascript:"> 会在渲染时执行（存储型 XSS，
 * 且会经「管理端查看用户模板」攻击管理员会话）。
 *
 * 白名单保留排版所需的标签/属性（含 font 的 color/size/face——
 * execCommand('foreColor'/'fontSize') 在 Chrome 产出的就是 <font> 标记）；
 * on* 事件、script/iframe、外链资源全部剔除。
 */

const ALLOWED_TAGS = [
  'B', 'STRONG', 'I', 'EM', 'U', 'S', 'SUP', 'SUB',
  'SPAN', 'FONT', 'BR', 'WBR', 'P', 'DIV', 'CENTER',
  'UL', 'OL', 'LI',
  'TABLE', 'THEAD', 'TBODY', 'TR', 'TD', 'TH',
]

const ALLOWED_ATTR = ['style', 'color', 'face', 'size', 'align']
const STYLE_PROPERTIES = new Set(['color', 'background-color', 'font-size', 'font-family', 'font-weight', 'font-style', 'text-decoration', 'text-align', 'vertical-align', 'line-height'])
DOMPurify.addHook('afterSanitizeAttributes', node => {
  const el = node as HTMLElement
  if (!el.style) return
  for (const property of Array.from(el.style)) {
    const value = el.style.getPropertyValue(property)
    if (!STYLE_PROPERTIES.has(property) || /url\s*\(|var\s*\(|expression\s*\(/i.test(value)) el.style.removeProperty(property)
    else el.style.setProperty(property, value, '')
  }
  if (!el.style.length) el.removeAttribute('style')
})

const FORBID_CONTENTS = ['script', 'style', 'iframe', 'object', 'embed', 'form']

/* 清除排版模式 UI 的历史残留（⠿ 拖拽手柄 / ✕ 删除按钮曾随 innerHTML 一起
   存进模板富文本，会在卷面上渲染出灰色字符） */
DOMPurify.addHook('afterSanitizeElements', node => {
  if (node.nodeType === 1) {
    const el = node as Element
    if (el.classList && (el.classList.contains('sort-handle') || el.classList.contains('el-del'))) {
      el.remove()
    }
  }
})

/** 净化富文本 HTML（写入缓存与渲染前统一走这里） */
export function sanitizeRich(html: string | null | undefined): string {
  if (!html) return ''
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    FORBID_CONTENTS,
    // 教训：不要自定义 ALLOWED_URI_REGEXP！DOMPurify 会用 URI 正则去校验
    // 「非 URI 安全」属性的值（font 的 color/size/face 等），自定义过严会把
    // 合法的颜色/字号属性一并剥掉（曾导致保存的标题颜色全部消失）。
    // 默认正则已能拦截 javascript: 等危险协议，且本白名单不含 a/img/script，
    // 实际 URI 攻击面为零。
  })
}
