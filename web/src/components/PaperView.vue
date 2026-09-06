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

const emit = defineEmits<{ (e: 'layout-done'): void }>()

const stackEl = ref<HTMLElement | null>(null)
const measureEl = ref<HTMLElement | null>(null)
/** 每页的大题索引切片 */
const pages = ref<number[][]>([[]])
/** 强制重挂载测量纸 */
const measureTick = ref(0)

const kidOn = computed(() => {
  if (props.style.kidFont === 'on') return true
  if (props.style.kidFont === 'off') return false
  const g = gradeNumOf(props.paper.grade) || 0
  return g >= 1 && g <= 2
})

const scores = computed(() => computeScores(props.paper.sections))

const allIdxs = computed(() => props.paper.sections.map((_, i) => i))

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
  const pageCap = availH - headH - 4 // 余量
  const chunks: number[][] = []
  const heights: number[] = []
  let cur: number[] = []
  let curH = 0
  blocks.forEach((b, i) => {
    const h = b.offsetHeight || 0
    heights.push(h)
    if (cur.length && curH + h > pageCap) {
      chunks.push(cur)
      cur = []
      curH = 0
    }
    cur.push(i)
    curH += h
  })
  if (cur.length) chunks.push(cur)

  // 最后一页要装下卷尾（奖励区 + 页脚）
  if (chunks.length) {
    const last = chunks[chunks.length - 1]
    const lastH = last.reduce((s, i) => s + heights[i], 0)
    if (lastH + tailH > availH - headH && last.length > 1) {
      chunks.push([last.pop()!])
    }
  }
  pages.value = chunks.length ? chunks : [[]]
}

watch(measureKey, () => paginate(), { immediate: false })
onMounted(() => paginate())
// 纸张宽度随字体加载可能变化，稍后复测一次
onMounted(() => setTimeout(() => { measureTick.value++ }, 800))

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
    enableTableResize(paper)
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
function enableTableResize(paper: Element) {
  paper.querySelectorAll('.q-table').forEach(table0 => {
    const table = table0 as HTMLElement
    table.querySelectorAll('td').forEach(td0 => {
      const td = td0 as HTMLElement
      td.style.position = 'relative'
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
        const onMove = (ev: MouseEvent) => {
          const w = Math.max(15, sw + ev.clientX - sx)
          allRows.forEach(row => {
            const c = (row as HTMLElement).children[colIndex] as HTMLElement | undefined
            if (c) c.style.width = w + 'px'
          })
        }
        const onUp = () => {
          document.removeEventListener('mousemove', onMove)
          document.removeEventListener('mouseup', onUp)
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
        const onMove = (ev: MouseEvent) => {
          const h = Math.max(15, sh + ev.clientY - sy)
          row.querySelectorAll('td').forEach(t => ((t as HTMLElement).style.height = h + 'px'))
        }
        const onUp = () => {
          document.removeEventListener('mousemove', onMove)
          document.removeEventListener('mouseup', onUp)
        }
        document.addEventListener('mousemove', onMove)
        document.addEventListener('mouseup', onUp)
      })
    })
  })
}

onBeforeUnmount(() => teardownLayout())

defineExpose({ applyLayout, repaginate: () => { measureTick.value++ } })
</script>

<template>
  <div ref="stackEl" class="paper-stack" :style="{ zoom: zoom ?? 1 }">
    <PaperPage
      v-for="(pg, i) in pages"
      :key="i"
      :paper="paper"
      :idxs="pg"
      :template="template"
      :style="style"
      :kid-on="kidOn"
      :show-answers="!!showAnswers"
      :editable="!!editable"
      :is-last="i === pages.length - 1"
      :add-day="addDay"
      :scores="scores"
    />
  </div>
  <!-- 离屏测量纸 -->
  <div ref="measureEl" class="offscreen" aria-hidden="true">
    <div class="pv-probe" style="height: 297mm; width: 210mm; position: absolute;"></div>
    <PaperPage
      :key="'m' + measureTick"
      :paper="paper"
      :idxs="allIdxs"
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
