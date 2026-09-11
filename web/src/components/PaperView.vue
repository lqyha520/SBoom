<script setup lang="ts">
/**
 * PaperView：A4 试卷渲染器
 * - 测量分页：离屏渲染完整卷面 → 按大题块高度切页 → 每页一张固定 297mm 的纸
 * - 排版模式：Sortable 拖拽排序（大题/题目可跨大题移动）、删除、表格列宽行高、
 *   题目自由移动/调整大小；退出时 DOM 顺序回写数据
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Sortable from 'sortablejs'
import type { PaperData, PaperSection, PaperStyle, PaperTemplate } from '../types'
import { computeScores, gradeNumOf } from '../utils'
import PaperPage from './PaperPage.vue'

const props = defineProps<{
  paper: PaperData
  template: PaperTemplate
  style: PaperStyle
  showAnswers?: boolean
  /** 允许纸面文字编辑（第 3 步） */
  editable?: boolean
  /** 排版模式（拖拽/删除/缩放） */
  layoutMode?: boolean
  addDay?: boolean
  /** 预览缩放（适配容器宽度，纯视觉） */
  zoom?: number
}>()

const emit = defineEmits<{
  (e: 'layout-done'): void
  (e: 'toggle-element', key: string): void
  (e: 'title-edited', title: string, html: string): void
  /** 大题 layout 被纸面交互修改（表格拖拽等），父级需同步回数据源 */
  (e: 'layout-updated', sid: string, layout: PaperSection['layout']): void
  /** 标题垂直拖拽产生偏移，父级需写回 store.style */
  (e: 'title-offset', v: number): void
}>()

const stackEl = ref<HTMLElement | null>(null)
const measureEl = ref<HTMLElement | null>(null)
/** 每页的大题分段：sec = 大题索引；qFrom/qTo = 题目切片 [from, to)；first = 本段带大题标题 */
interface PageChunk { sec: number; qFrom: number; qTo: number; first: boolean }
const pages = ref<PageChunk[][]>([])
/** 强制重挂载测量纸 */
const measureTick = ref(0)

const kidOn = computed(() => {
  if (props.style.kidFont === 'on') return true
  if (props.style.kidFont === 'off') return false
  const g = gradeNumOf(props.paper.grade) || 0
  return g >= 1 && g <= 2
})

const scores = computed(() => computeScores(props.paper.sections))

/** 测量纸用：每个大题整块一段 */
const allChunks = computed(() => props.paper.sections.map((_, i) => ({ sec: i, qFrom: 0, qTo: Infinity, first: true })))

/* ── 分页测量 ── */
const measureKey = computed(() =>
  JSON.stringify([
    props.paper.sections.map(s => [s.type, (s.data.questions || []).map(q => [q._qid, q.stem, q.options?.length]), s.layout]),
    props.paper.title,
    (props.paper as any).footerOverride,
    props.showAnswers,
    props.template,
    props.style,
    kidOn.value,
    measureTick.value,
  ]),
)

async function paginate() {
  await nextTick()
  await new Promise(r => requestAnimationFrame(() => r(null)))
  // 等字体加载完成再测量（否则块高度偏小，分页错乱）
  try { await (document as any).fonts?.ready } catch { /* 老浏览器忽略 */ }
  const mEl = measureEl.value
  if (!mEl) return
  const paper = mEl.querySelector('.paper') as HTMLElement | null
  if (!paper) return

  // 可用高度：297mm 探针 − 上下 padding
  const probe = mEl.querySelector('.pv-probe') as HTMLElement | null
  const paperH = probe ? probe.offsetHeight : paper.offsetWidth * (297 / 210)
  const cs = getComputedStyle(paper)
  const availH = paperH - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom)

  const headEl = paper.querySelector('.pv-head') as HTMLElement | null
  const headH = headEl ? headEl.offsetHeight : 0
  const tailEl = paper.querySelector('.pv-tail') as HTMLElement | null
  const tailH = tailEl ? tailEl.offsetHeight : 0

  const blocks = Array.from(paper.querySelectorAll('.sec-block')) as HTMLElement[]
  const cap = availH - headH - 16 // 每页内容容量（每页都有卷头；留 16px 余量防溢出）

  // ── 大题 → 段流：整块放得下就一段；超高就块内按行切 ──
  interface Segment { sec: number; total: number; headBlockH: number; rows: number[]; rowStride: number }
  const segments: Segment[] = []
  blocks.forEach((b, i) => {
    const qEls = Array.from(b.querySelectorAll('.q')) as HTMLElement[]
    const total = qEls.length
    const sec = props.paper.sections[i]
    const rowStride = sec?.layout?.qCols || 1
    // 全部用 viewport 坐标（getBoundingClientRect），避免 offsetTop 参照系错乱
    const bTop = b.getBoundingClientRect().top
    const bBottom = b.getBoundingClientRect().bottom
    const rows: number[] = []
    if (total > 0) {
      const tops = qEls.map(q => q.getBoundingClientRect().top)
      for (let r = 0; r < total; r += rowStride) {
        const nextTop = r + rowStride < total ? tops[r + rowStride] : bBottom
        rows.push(Math.max(20, nextTop - tops[r] + 4))
      }
      // 块头高度（大题标题 + 阅读短文等在第一题之前的部分）
      const headBlockH = Math.max(0, tops[0] - bTop + 4)
      segments.push({ sec: i, total, headBlockH, rows, rowStride })
    } else {
      segments.push({ sec: i, total: 0, headBlockH: bBottom - bTop, rows, rowStride })
    }
  })

  // ── 段流 → 页 ──
  const out: PageChunk[][] = []
  let page: PageChunk[] = []
  let used = 0
  const pushPage = () => {
    if (page.length) out.push(page)
    page = []
    used = 0
  }
  for (const seg of segments) {
    const wholeH = seg.headBlockH + seg.rows.reduce((s, r) => s + r, 0)
    if (used + wholeH <= cap) {
      // 整段放得下
      page.push({ sec: seg.sec, qFrom: 0, qTo: seg.total, first: true })
      used += wholeH
      continue
    }
    // 块内切分：逐行装
    let from = 0
    let first = true
    while (from < seg.total) {
      const room = cap - used
      const headExtra = first ? seg.headBlockH : 0
      if (room - headExtra < 50 && page.length) { pushPage(); continue }
      let acc = headExtra
      let rowCount = 0
      while (from + rowCount * seg.rowStride < seg.total) {
        const rowIdx = Math.floor((from + rowCount * seg.rowStride) / seg.rowStride)
        const rh = seg.rows[rowIdx] ?? 40
        if (acc + rh > room && rowCount > 0) break
        acc += rh
        rowCount++
        if (acc > room) break // 单行超高兜底：独占一页
      }
      const to = Math.min(from + rowCount * seg.rowStride, seg.total)
      if (to <= from) break // 防死循环
      page.push({ sec: seg.sec, qFrom: from, qTo: to, first })
      used += acc
      first = false
      from = to
      if (from < seg.total) pushPage()
    }
  }
  if (page.length) pushPage()

  // 最后一页装下卷尾（奖励区 + 页脚）：装不下则把最后一段推到新页
  if (out.length) {
    const lastPage = out[out.length - 1]
    if (lastPage.length > 1 && tailH > 30) {
      // 粗略：最后一页剩余空间不足 tailH 就挪走最后一段
      const lastSeg = lastPage[lastPage.length - 1]
      const seg = segments[lastSeg.sec]
      const segH = (lastSeg.first ? seg.headBlockH : 0) + seg.rows.slice(Math.floor(lastSeg.qFrom / seg.rowStride), Math.ceil(lastSeg.qTo / seg.rowStride)).reduce((s, r) => s + r, 0)
      if (used + tailH > cap && segH > 100) {
        const moved = lastPage.pop()!
        out.push([moved])
      }
    }
  }
  pages.value = out.length ? out : [[{ sec: 0, qFrom: 0, qTo: 0, first: true }]]
  measured.value = true
}

watch(measureKey, () => paginate(), { immediate: false })
onMounted(() => paginate())
// 纸张宽度随字体加载可能变化，稍后复测一次
onMounted(() => setTimeout(() => { measureTick.value++ }, 800))

/* ── 表格缩放：editable 即启用（不必进排版模式） ── */
let tableResizePapers: Element[] = []
async function setupTableResize() {
  await nextTick()
  await new Promise(r => requestAnimationFrame(() => r(null)))
  const stack = stackEl.value
  if (!stack) return
  stack.querySelectorAll('.paper').forEach(paper => {
    tableResizePapers.push(paper)
    enableTableResize(paper)
  })
}
watch(
  () => [props.editable, props.paper.sections.map((s: any) => s.layout?.tableBorder).join(',')] as const,
  () => setupTableResize(),
  { immediate: true },
)

/* ── 排版模式 ── */
let sortables: Sortable[] = []

watch(
  () => props.layoutMode,
  async on => {
    await nextTick()
    if (on) enterLayout()
    else teardownLayout()
  },
)

function enterLayout() {
  const stack = stackEl.value
  if (!stack) return
  stack.querySelectorAll('.paper').forEach(paper => {
    const exam = paper.querySelector('.exam') as HTMLElement | null
    if (!exam) return

    // 大题排序
    sortables.push(
      new Sortable(exam, {
        animation: 150,
        handle: 'h2.sec',
        draggable: '.sec-block',
        ghostClass: 'sortable-ghost',
      }),
    )

    // 题目排序（可跨大题）—— 拖拽手柄注入到题干前
    paper.querySelectorAll('.sec-block').forEach(secEl => {
      sortables.push(
        new Sortable(secEl as HTMLElement, {
          group: 'questions',
          animation: 150,
          handle: '.sort-handle',
          draggable: '.q',
          ghostClass: 'sortable-ghost',
        }),
      )
      // 大题删除按钮
      const tools = document.createElement('div')
      tools.className = 'sec-tools'
      tools.innerHTML = `<span class="tool-btn del">✕ 删除大题</span>`
      tools.addEventListener('click', e => {
        if ((e.target as HTMLElement).textContent?.includes('删除大题')) {
          if (confirm('确定删除整个大题吗？')) (secEl as HTMLElement).remove()
        }
      })
      ;(secEl as HTMLElement).appendChild(tools)
    })

    // 题目删除按钮 + 排序手柄 + 自由移动 + 大小调整
    paper.querySelectorAll('.q').forEach(qEl => {
      const tools = document.createElement('div')
      tools.className = 'q-tools'
      tools.innerHTML = `<span class="tool-btn del">✕</span>`
      tools.addEventListener('click', e => {
        e.stopPropagation()
        if (confirm('确定删除这道题吗？')) qEl.remove()
      })
      qEl.appendChild(tools)
      const stem = qEl.querySelector('[data-e="stem"], .split-wrap, .compare-row')
      if (stem && !stem.querySelector('.sort-handle')) {
        const h = document.createElement('span')
        h.className = 'sort-handle'
        h.textContent = '⠿'
        stem.appendChild(h)
      }
      enableFreeMove(qEl as HTMLElement)
    })

    enableCellResize(paper)
  })
}

function teardownLayout() {
  sortables.forEach(s => s.destroy())
  sortables = []
  const stack = stackEl.value
  if (!stack) return
  stack.querySelectorAll('.q-tools, .sec-tools, .cell-resizer, .col-resizer, .row-resizer').forEach(el => el.remove())
}

/** 排版模式完成：DOM 顺序/删除回写数据，返回新 sections（供调用方同步外部状态） */
function applyLayout(): PaperSection[] | null {
  const stack = stackEl.value
  if (!stack) return null
  const paperEl = stack.querySelector('.paper')
  if (!paperEl) return null

  const paper = props.paper
  const qMap = new Map<string, any>()
  paper.sections.forEach(s => (s.data.questions || []).forEach(q => { if (q._qid) qMap.set(q._qid, q) }))

  const newSections: PaperSection[] = []
  paperEl.querySelectorAll('.sec-block').forEach(block => {
    const sid = block.getAttribute('data-sid') || ''
    const orig = paper.sections.find(s => s._sid === sid)
    if (!orig) return
    const qs: any[] = []
    block.querySelectorAll('.q').forEach(qEl => {
      const q = qMap.get(qEl.getAttribute('data-qid') || '')
      if (q) qs.push(q)
    })
    newSections.push({ ...orig, data: { ...orig.data, questions: qs } })
  })
  paper.sections = newSections
  teardownLayout()
  emit('layout-done')
  return newSections
}

/* ── 题目自由移动（拖拽空白处） ── */
function enableFreeMove(qEl: HTMLElement) {
  qEl.style.position = 'relative'
  qEl.style.cursor = 'grab'
  let sx = 0, sy = 0, ox = 0, oy = 0, dragging = false
  qEl.addEventListener('mousedown', (e: MouseEvent) => {
    const t = e.target as HTMLElement
    if (t.closest('.q-tools') || t.closest('.cell-resizer') || t.closest('[contenteditable="true"]') || t.closest('.col-resizer') || t.closest('.row-resizer') || t.closest('.sort-handle')) return
    e.preventDefault()
    dragging = true
    sx = e.clientX; sy = e.clientY
    ox = qEl.offsetLeft; oy = qEl.offsetTop
    qEl.style.cursor = 'grabbing'
    const onMove = (ev: MouseEvent) => {
      if (!dragging) return
      qEl.style.left = ox + ev.clientX - sx + 'px'
      qEl.style.top = oy + ev.clientY - sy + 'px'
    }
    const onUp = () => {
      dragging = false
      qEl.style.cursor = 'grab'
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  })
}

/** 非表格模式：题目右下角拖拽调整宽高 */
function enableCellResize(paper: Element) {
  paper.querySelectorAll('.q-grid .q').forEach(cell0 => {
    const cell = cell0 as HTMLElement
    const rz = document.createElement('span')
    rz.className = 'cell-resizer'
    rz.textContent = '⤡'
    cell.appendChild(rz)
    rz.addEventListener('mousedown', (e: MouseEvent) => {
      e.preventDefault(); e.stopPropagation()
      const sx = e.clientX, sy = e.clientY
      const sw = cell.offsetWidth, sh = cell.offsetHeight
      const onMove = (ev: MouseEvent) => {
        cell.style.width = Math.max(30, sw + ev.clientX - sx) + 'px'
        cell.style.height = Math.max(20, sh + ev.clientY - sy) + 'px'
      }
      const onUp = () => {
        document.removeEventListener('mousemove', onMove)
        document.removeEventListener('mouseup', onUp)
      }
      document.addEventListener('mousemove', onMove)
      document.addEventListener('mouseup', onUp)
    })
  })
}

/** 表格模式：列宽/行高拖拽 */
/** 由 sec-block DOM 反查 section 数据（_sid 对应） */
function sectionOfBlock(block: Element): PaperSection | undefined {
  const sid = block.getAttribute('data-sid') || ''
  return props.paper.sections.find(s => s._sid === sid)
}

/** 表格模式：列宽/行高拖拽 —— 实时预览 + 松手写回 layout 数据（随保存/导出继承） */
function enableTableResize(paper: Element) {
  paper.querySelectorAll('.sec-block').forEach(block => {
    const sec = sectionOfBlock(block)
    if (!sec) return
    block.querySelectorAll('.q-table').forEach(table0 => {
      const table = table0 as HTMLElement
      table.querySelectorAll('td').forEach(td0 => {
        const td = td0 as HTMLElement
        td.style.position = 'relative'
        if (td.querySelector('.col-resizer')) return // 已注入，避免重复
        // 列宽
        const cr = document.createElement('span')
        cr.className = 'col-resizer'
        td.appendChild(cr)
        cr.addEventListener('mousedown', (e: MouseEvent) => {
          e.preventDefault(); e.stopPropagation()
          const colIndex = Array.from(td.parentElement!.children).indexOf(td)
          const allRows = table.querySelectorAll('tr')
          const sx = e.clientX
          const sw = td.offsetWidth
          let finalW = sw
          const onMove = (ev: MouseEvent) => {
            finalW = Math.max(15, sw + ev.clientX - sx)
            allRows.forEach(row => {
              const c = (row as HTMLElement).children[colIndex] as HTMLElement | undefined
              if (c) c.style.width = finalW + 'px'
            })
          }
          const onUp = () => {
            document.removeEventListener('mousemove', onMove)
            document.removeEventListener('mouseup', onUp)
            // 写回数据：colgroup 会接管列宽渲染
            const cw = [...(sec.layout.colWidths || [])]
            cw[colIndex] = Math.round(finalW)
            sec.layout.colWidths = cw
            emit('layout-updated', sec._sid || '', { ...sec.layout })
            allRows.forEach(row => {
              const c = (row as HTMLElement).children[colIndex] as HTMLElement | undefined
              if (c) c.style.width = ''
            })
          }
          document.addEventListener('mousemove', onMove)
          document.addEventListener('mouseup', onUp)
        })
        // 行高
        const rr = document.createElement('span')
        rr.className = 'row-resizer'
        td.appendChild(rr)
        rr.addEventListener('mousedown', (e: MouseEvent) => {
          e.preventDefault(); e.stopPropagation()
          const row = td.closest('tr') as HTMLElement | null
          if (!row) return
          const sy = e.clientY
          const sh = td.offsetHeight
          let finalH = sh
          const onMove = (ev: MouseEvent) => {
            finalH = Math.max(15, sh + ev.clientY - sy)
            row.querySelectorAll('td').forEach(t => ((t as HTMLElement).style.height = finalH + 'px'))
          }
          const onUp = () => {
            document.removeEventListener('mousemove', onMove)
            document.removeEventListener('mouseup', onUp)
            sec.layout.rowHeight = Math.round(finalH)
            emit('layout-updated', sec._sid || '', { ...sec.layout })
            row.querySelectorAll('td').forEach(t => ((t as HTMLElement).style.height = ''))
          }
          document.addEventListener('mousemove', onMove)
          document.addEventListener('mouseup', onUp)
        })
      })
    })
  })
}

onBeforeUnmount(() => teardownLayout())

defineExpose({
  applyLayout,
  repaginate: () => { measureTick.value++ },
  /** 等分页测量完成（导出前调用） */
  ready: () => new Promise<void>(resolve => {
    const check = () => {
      if (pages.value.length && pages.value[0]?.length !== undefined && measured.value) resolve()
      else setTimeout(check, 50)
    }
    // paginate 完成会置 measured=true
    setTimeout(check, 50)
  }),
})

/** 分页是否已完成至少一次（导出等待用） */
const measured = ref(false)

/** stack 实际高度（缩放占位补偿用） */
const stackH = ref(0)
async function measureStackH() {
  await nextTick()
  if (stackEl.value) stackH.value = stackEl.value.offsetHeight
}
watch(() => pages.value, () => measureStackH(), { deep: true })
onMounted(() => measureStackH())
</script>

<template>
  <!-- 预览缩放：transform:scale（纯视觉，不影响 mm 布局；zoom 会改 mm→px 换算压扁纸面）
       wrapper 的高度用 scale 后的值占位，避免滚动区留白/裁切 -->
  <div
    class="paper-scaler-wrap"
    :style="{ width: `210mm`, margin: '0 auto', height: stackH > 0 ? `${Math.round(stackH * (zoom ?? 1))}px` : undefined }"
  >
    <div :style="{ transform: `scale(${zoom ?? 1})`, transformOrigin: 'top center' }">
      <div ref="stackEl" class="paper-stack">
      <PaperPage
        v-for="(pg, i) in pages"
        :key="i"
        :paper="paper"
        :chunks="pg"
        :template="template"
        :style="style"
        :kid-on="kidOn"
        :show-answers="!!showAnswers"
        :editable="!!editable"
        :is-last="i === pages.length - 1"
        :add-day="addDay"
        :scores="scores"
        @toggle-element="(k: string) => emit('toggle-element', k)"
        @title-edited="(t: string, h: string) => emit('title-edited', t, h)"
        @title-offset="(v: number) => emit('title-offset', v)"
      />
    </div>
  </div>
  </div>
  <!-- 离屏测量纸（整卷单页，测各块真实高度） -->
  <div ref="measureEl" class="offscreen" aria-hidden="true">
    <div class="pv-probe" style="height: 297mm; width: 210mm; position: absolute;"></div>
    <PaperPage
      :key="'m' + measureTick"
      :paper="paper"
      :chunks="allChunks"
      :template="template"
      :style="style"
      :kid-on="kidOn"
      :show-answers="!!showAnswers"
      :editable="false"
      :is-last="true"
      measuring
    />
  </div>
</template>
