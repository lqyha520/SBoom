<script setup lang="ts">
/**
 * PaperView：A4 试卷渲染器
 * - 测量分页：离屏渲染完整卷面 → 按大题块高度切页 → 每页一张固定 297mm 的纸
 * - 排版模式：Sortable 拖拽排序（大题/题目可跨大题移动）、删除、表格列宽行高、
 *   题目自由移动/调整大小；退出时 DOM 顺序回写数据
 */
import { computed, nextTick, onActivated, onDeactivated, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type Sortable from 'sortablejs'
import type { PaperData, PaperSection, PaperStyle, PaperTemplate } from '../types'
import { computeScores, gradeNumOf } from '../utils'
import PaperPage from './PaperPage.vue'
import { paginateSections, type PageChunk, type MeasuredSection } from '../paper-pagination'
import { createSectionSignatures, createSectionMeasurements } from '../section-measurement'

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
const measureVisible = ref(true)
/** 每页的大题分段：sec = 大题索引；qFrom/qTo = 题目切片 [from, to)；first = 本段带大题标题 */
const pages = ref<PageChunk[][]>([])
/** 强制重挂载测量纸 */
const measureTick = ref(0)
const visibleRevision = ref(0)
/** 分页是否已完成至少一次（导出等待用；声明在使用前，避免可读性陷阱） */
const measured = ref(false)
const paginationError = ref('')

const kidOn = computed(() => {
  if (props.style.kidFont === 'on') return true
  if (props.style.kidFont === 'off') return false
  const g = gradeNumOf(props.paper.grade) || 0
  return g >= 1 && g <= 2
})

const scores = computed(() => computeScores(props.paper.sections))

/** 测量纸只挂载发生几何变化的大题；卷头、卷尾单独测量。 */
const measurementChunks = ref<PageChunk[]>([])
const styleForMeasure = computed(() => ({ ...props.style, titleOffsetY: 0 }))
let measurementCache: { availH: number; headH: number; tailH: number; segments: MeasuredSection[] } | undefined
const sectionSignature = createSectionSignatures()
const sectionMeasurements = createSectionMeasurements()
const sectionKeys = computed(() => props.paper.sections.map(sectionSignature))
const geometryContext = computed(() => JSON.stringify([props.template, styleForMeasure.value, kidOn.value, props.showAnswers, measureTick.value]))

/* ── 分页测量 ── */
/** 只订阅可改变卷面高度的内容；锁定和请求状态不参与测量。 */
const measureKey = computed(() => JSON.stringify([
  props.paper.title, props.paper.titleHtml, props.paper.footerOverride,
  props.paper.hiddenElements, props.paper.grade, props.paper.subject, props.paper.keyword,
  props.paper.difficulty, props.paper.day, props.addDay, props.showAnswers,
  geometryContext.value,
]))

/* 输入类变化（标题逐字输入、字号滑条拖动）防抖后再重分页，
   避免每个按键都做一次全卷测量；挂载时首次分页仍然立即执行 */
let _pagTimer: ReturnType<typeof setTimeout> | undefined
let paginationRun = 0, suspended = false, disposed = false
watch([measureKey, sectionKeys], () => {
  paginationRun++
  measured.value = false
  clearTimeout(_pagTimer)
  if (!suspended) _pagTimer = setTimeout(() => { void paginate() }, 150)
})
onMounted(() => paginate())
onDeactivated(() => { suspended = true; paginationRun++; clearTimeout(_pagTimer); measureVisible.value = false })
onActivated(() => { if (suspended) { suspended = false; void paginate() } })
// 标题拖动只用已测量的块高度重新分配页面，不再读取每道题的布局。
watch(() => props.style.titleOffsetY, () => applyMeasurements())

async function paginate() {
  if (suspended || disposed) return
  const run = ++paginationRun
  const keys = [...sectionKeys.value], context = geometryContext.value
  const dirty = sectionMeasurements.dirty(keys, context)
  measurementChunks.value = dirty.map(sec => ({ sec, qFrom: 0, qTo: Infinity, first: true }))
  measureVisible.value = true
  await nextTick()
  await new Promise(r => requestAnimationFrame(() => r(null)))
  // 等字体加载完成再测量（否则块高度偏小，分页错乱）
  try { await document.fonts?.ready } catch { /* 老浏览器忽略 */ }
  if (run !== paginationRun || suspended || disposed) return
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
  const outerHeight = (el: HTMLElement | null) => el ? el.offsetHeight + (parseFloat(getComputedStyle(el).marginTop) || 0) + (parseFloat(getComputedStyle(el).marginBottom) || 0) : 0
  const headH = outerHeight(headEl)
  const tailEl = paper.querySelector('.pv-tail') as HTMLElement | null
  const tailH = outerHeight(tailEl)

  const blocks = Array.from(paper.querySelectorAll('.sec-block')) as HTMLElement[]

  // ── 大题 → 段流：整块放得下就一段；超高就块内按行切 ──
  const updates = new Map<number, MeasuredSection>()
  blocks.forEach((b, blockIndex) => {
    const i = dirty[blockIndex]
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
      updates.set(i, { sec: i, total, headBlockH, rows, rowStride })
    } else {
      updates.set(i, { sec: i, total: 0, headBlockH: bBottom - bTop, rows, rowStride })
    }
  })

  const segments = sectionMeasurements.commit(keys, context, updates)
  measurementCache = { availH, headH, tailH, segments }
  applyMeasurements()
  measured.value = true
  measureVisible.value = false
}

function applyMeasurements() {
  if (!measurementCache) return
  const { availH, headH, tailH, segments } = measurementCache
  const cap = availH - headH - (props.style.titleOffsetY || 0) * 96 / 25.4 - 16
  const oversized = cap <= 0 || tailH > cap || segments.some(segment =>
    segment.headBlockH + (segment.rows[0] || 0) > cap || segment.rows.some(row => row > cap))
  paginationError.value = oversized ? '内容超出 A4 页面，请缩小字号、缩短单题或页脚后再导出' : ''
  const nextPages = paginateSections(segments, Math.max(1, cap), tailH)
  if (JSON.stringify(nextPages) !== JSON.stringify(pages.value)) pages.value = nextPages
  // 分页会整建 DOM：表格列宽/行高手柄需要随分页结果重新注入（否则丢失）
  setupTableResize()
}

// 首次测量已等待字体；仅实际字体变化时失效，不再固定延迟重复测量。
function fontsChanged() { measureTick.value++ }
onMounted(() => document.fonts?.addEventListener?.('loadingdone', fontsChanged))
onBeforeUnmount(() => { disposed = true; paginationRun++; clearTimeout(_pagTimer); document.fonts?.removeEventListener?.('loadingdone', fontsChanged) })

/* ── 表格缩放：editable 即启用（不必进排版模式）；分页重建 DOM 后由 paginate 末尾重注入 ── */
async function setupTableResize() {
  await nextTick()
  await new Promise(r => requestAnimationFrame(() => r(null)))
  const stack = stackEl.value
  if (!stack) return
  stack.querySelectorAll('.paper').forEach(paper => enableTableResize(paper))
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
    if (on) await enterLayout()
    else { teardownLayout(); visibleRevision.value++; await nextTick(); void setupTableResize() }
  },
)

async function enterLayout() {
  // sortablejs（约 45KB）只在进入排版模式时按需加载，不进入工作台首屏 bundle。
  const { default: SortableCtor } = await import('sortablejs')
  if (!props.layoutMode) return
  const stack = stackEl.value
  if (!stack) return
  stack.querySelectorAll('.paper').forEach(paper => {
    const exam = paper.querySelector('.exam') as HTMLElement | null
    if (!exam) return

    // 大题排序
    sortables.push(
      new SortableCtor(exam, {
        animation: 150,
        handle: 'h2.sec',
        draggable: '.sec-block',
        ghostClass: 'sortable-ghost',
      }),
    )

    // 题目排序（可跨大题）—— 拖拽手柄注入到题干前
    paper.querySelectorAll('.sec-block').forEach(secEl => {
      sortables.push(
        new SortableCtor(secEl as HTMLElement, {
          group: 'questions',
          animation: 150,
          handle: '.sort-handle',
          draggable: '.q',
          ghostClass: 'sortable-ghost',
        }),
      )
      // 大题删除按钮
      addLayoutTools(secEl as HTMLElement, 'sec')
    })

    // 题目删除按钮 + 排序手柄 + 自由移动 + 大小调整
    paper.querySelectorAll('.q').forEach(qEl => {
      addLayoutTools(qEl as HTMLElement, 'q')
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

/** 鼠标拖拽以外提供可聚焦的排序和删除按钮。 */
function addLayoutTools(element: HTMLElement, kind: 'sec' | 'q') {
  const tools = document.createElement('div')
  const label = kind === 'sec' ? '大题' : '题目'
  tools.className = kind + '-tools'
  tools.innerHTML = `<button type="button" class="tool-btn" data-move="-1" aria-label="上移${label}">↑</button><button type="button" class="tool-btn" data-move="1" aria-label="下移${label}">↓</button><button type="button" class="tool-btn del" aria-label="删除${label}">✕</button>`
  tools.addEventListener('click', event => {
    event.stopPropagation()
    const button = (event.target as HTMLElement).closest('button')
    if (!button) return
    if (button.dataset.move) {
      const items = Array.from(stackEl.value?.querySelectorAll(kind === 'sec' ? '.sec-block' : '.q') || [])
      const at = items.indexOf(element), delta = Number(button.dataset.move), target = items[at + delta]
      if (target) { if (delta < 0) target.before(element); else target.after(element); button.focus() }
    } else if (confirm(`确定删除这${kind === 'sec' ? '个大题' : '道题'}吗？`)) element.remove()
  })
  element.appendChild(tools)
}

function teardownLayout() {
  sortables.forEach(s => s.destroy())
  sortables = []
  // 还原 free-move 注入的监听与内联样式（题目回到正常文档流）
  freeMoveCleanups.forEach(fn => fn())
  freeMoveCleanups = []
  const stack = stackEl.value
  if (!stack) return
  // 注意 .sort-handle 也要清（enterLayout 注入的拖拽手柄，漏掉会残留 ⠿ 图标）
  stack.querySelectorAll('.q-tools, .sec-tools, .sort-handle, .cell-resizer, .col-resizer, .row-resizer').forEach(el => el.remove())
}

/** 排版模式完成：DOM 顺序/删除回写数据，返回新 sections（供调用方同步外部状态） */
function applyLayout(): PaperSection[] | null {
  const stack = stackEl.value
  if (!stack) return null
  const paperEl = stack.querySelector('.paper')
  if (!paperEl) return null

  const paper = props.paper
  const qMap = new Map<string, any>()
  paper.sections.forEach(s => (s.data.questions || []).forEach(q => {
    // 搭建预览里的格式示例不能被排版回写到正式试卷数据。
    if (q._qid && !q._preview) qMap.set(q._qid, q)
  }))

  const newSections: PaperSection[] = []
  stack.querySelectorAll('.sec-block').forEach(block => {
    const sid = block.getAttribute('data-sid') || ''
    const orig = paper.sections.find(s => s._sid === sid)
    if (!orig) return
    const qs: any[] = []
    block.querySelectorAll('.q').forEach(qEl => {
      const q = qMap.get(qEl.getAttribute('data-qid') || '')
      if (q) qs.push(q)
    })
    const existing = newSections.find(section => section._sid === sid)
    if (existing) existing.data.questions.push(...qs)
    else newSections.push({ ...orig, data: { ...orig.data, questions: qs } })
  })
  paper.sections = newSections
  teardownLayout()
  emit('layout-done')
  return newSections
}

/* ── 题目自由移动（拖拽空白处）──
   注册的监听与内联样式都记录到 freeMoveCleanups，退出排版模式时统一还原，
   否则残留 mousedown 监听会让退出后的题目仍可被拖走 */
let freeMoveCleanups: Array<() => void> = []
function enableFreeMove(qEl: HTMLElement) {
  qEl.style.position = 'relative'
  qEl.style.cursor = 'grab'
  const onDown = (e: MouseEvent) => {
    const t = e.target as HTMLElement
    if (t.closest('.q-tools') || t.closest('.cell-resizer') || t.closest('[contenteditable="true"]') || t.closest('.col-resizer') || t.closest('.row-resizer') || t.closest('.sort-handle')) return
    e.preventDefault()
    const sx = e.clientX, sy = e.clientY
    const ox = qEl.offsetLeft, oy = qEl.offsetTop
    let dragging = true
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
  }
  qEl.addEventListener('mousedown', onDown)
  freeMoveCleanups.push(() => {
    qEl.removeEventListener('mousedown', onDown)
    qEl.style.position = ''
    qEl.style.cursor = ''
    qEl.style.left = ''
    qEl.style.top = ''
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
        cr.tabIndex = 0
        cr.setAttribute('role', 'separator'); cr.setAttribute('aria-label', '调整列宽（左右方向键）'); cr.setAttribute('aria-orientation', 'vertical')
        cr.addEventListener('keydown', event => {
          if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return
          event.preventDefault()
          const index = Array.from(td.parentElement!.children).indexOf(td)
          const widths = [...(sec.layout.colWidths || [])]
          widths[index] = Math.max(15, (widths[index] || td.offsetWidth) + (event.key === 'ArrowLeft' ? -5 : 5))
          sec.layout.colWidths = widths; emit('layout-updated', sec._sid || '', { ...sec.layout })
        })
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
        rr.tabIndex = 0
        rr.setAttribute('role', 'separator'); rr.setAttribute('aria-label', '调整行高（上下方向键）'); rr.setAttribute('aria-orientation', 'horizontal')
        rr.addEventListener('keydown', event => {
          if (!['ArrowUp', 'ArrowDown'].includes(event.key)) return
          event.preventDefault()
          sec.layout.rowHeight = Math.max(15, (sec.layout.rowHeight || td.offsetHeight) + (event.key === 'ArrowUp' ? -5 : 5))
          emit('layout-updated', sec._sid || '', { ...sec.layout })
        })
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
})

/** stack 实际高度（缩放占位补偿用） */
const stackH = ref(0)
async function measureStackH() {
  await nextTick()
  if (stackEl.value) stackH.value = stackEl.value.offsetHeight
}
// pages 是整体替换，无需 deep 监听
watch(() => pages.value, () => measureStackH())
onMounted(() => measureStackH())
</script>

<template>
  <p v-if="paginationError" role="alert" class="no-print p-3 text-error">{{ paginationError }}</p>
  <!-- 预览缩放：transform:scale（纯视觉，不影响 mm 布局；zoom 会改 mm→px 换算压扁纸面）
       wrapper 的高度用 scale 后的值占位，避免滚动区留白/裁切 -->
  <div
    class="paper-scaler-wrap"
    :style="{ width: `${210 * (zoom ?? 1)}mm`, margin: '0 auto', height: stackH > 0 ? `${Math.round(stackH * (zoom ?? 1))}px` : undefined }"
  >
    <!-- pv-zoom 类供 @media print 强制重置缩放：zoom<100% 时打印出来的应是原尺寸而非缩小版 -->
    <div class="pv-zoom" :style="{ width: '210mm', transform: `scale(${zoom ?? 1})`, transformOrigin: 'top left' }">
      <div ref="stackEl" class="paper-stack" :data-pagination-error="paginationError || undefined" :data-pagination-pending="!measured || undefined">
      <PaperPage
        v-for="(pg, i) in pages"
        :key="visibleRevision + ':' + i"
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
  <div v-if="measureVisible" ref="measureEl" class="offscreen" aria-hidden="true" inert>
    <div class="pv-probe" style="height: 297mm; width: 210mm; position: absolute;"></div>
    <PaperPage
      :key="'m' + measureTick"
      :paper="paper"
      :chunks="measurementChunks"
      :template="template"
      :style="styleForMeasure"
      :kid-on="kidOn"
      :show-answers="!!showAnswers"
      :editable="false"
      :is-last="true"
      measuring
    />
  </div>
</template>
