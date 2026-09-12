<script setup lang="ts">
import { computed, ref } from 'vue'
import type { PaperData, PaperSection, PaperStyle, PaperTemplate, Question } from '../types'
import { DIFF_NAME } from '../constants'
import { sanitizeRich } from '../sanitize'
import SectionBlock from './SectionBlock.vue'

/** 页内大题分段（与 PaperView 的 PageChunk 对应） */
export interface PageChunkLite { sec: number; qFrom: number; qTo: number; first: boolean }

const props = defineProps<{
  paper: PaperData
  /** 要渲染的大题分段（null 段 = 整块渲染，向后兼容） */
  chunks: PageChunkLite[]
  template: PaperTemplate
  style: PaperStyle
  kidOn: boolean
  showAnswers: boolean
  editable: boolean
  /** 测量模式：不限高 */
  measuring?: boolean
  /** 是否最后一页（页脚/奖励区） */
  isLast?: boolean
  /** 多份时标题加（第X天） */
  addDay?: boolean
  /** 传入则显示每大题分值 */
  scores?: Map<Question, number>
}>()

const blocks = computed(() =>
  props.chunks
    .map(c => ({ sec: props.paper.sections[c.sec], chunk: c }))
    .filter(x => x.sec) as { sec: PaperSection; chunk: PageChunkLite }[],
)

const paperTitle = computed(() => {
  const t = props.template
  return (
    props.paper.title ||
    (t.titlePrefix ? `${t.titlePrefix} · ${props.paper.grade}${props.paper.subject}${t.titleSuffix || ''}` : `${props.paper.grade}${props.paper.subject}${t.titleSuffix || '测试卷'}`)
  )
})

const subParts = computed(() => {
  const t = props.template
  const parts: string[] = []
  if (t.headerExtra) parts.push(t.headerExtra)
  parts.push('范围：' + props.paper.keyword)
  parts.push('难度：' + ((DIFF_NAME as any)[props.paper.difficulty] || props.paper.difficulty))
  if (t.showScore) parts.push('满分 100 分')
  return parts
})

function onTitleBlur(e: FocusEvent) {
  if (!props.editable) return
  const el = e.target as HTMLElement
  // innerHTML 会包含 ✕ 删除按钮和（第X天）后缀，克隆后剔除再存；存前净化防 XSS
  const clone = el.cloneNode(true) as HTMLElement
  clone.querySelectorAll('.el-del').forEach(n => n.remove())
  props.paper.title = clone.innerText.replace(/（第\d+天）\s*$/, '').trim()
  props.paper.titleHtml = sanitizeRich(clone.innerHTML.replace(/（第\d+天）\s*(<\/\w+>)?\s*$/, '$1'))
  emit('title-edited', props.paper.title, props.paper.titleHtml)
}
function onFooterBlur(e: FocusEvent) {
  if (!props.editable) return
  props.paper.footerOverride = (e.target as HTMLElement).innerText.trim()
}

/* ── 卷头/卷尾元素单独删除（排版能力，随 paper 数据持久化） ── */
const emit = defineEmits<{ (e: 'toggle-element', key: string): void; (e: 'title-edited', title: string, html: string): void; (e: 'title-offset', v: number): void }>()
const hiddenList = computed<string[]>(() => props.paper.hiddenElements || [])
function isHidden(key: string): boolean {
  return hiddenList.value.includes(key)
}
function toggleHidden(key: string) {
  // 结果页：paper 是 store 里的对象，直接改（响应式生效）
  // 搭建预览：paper 是 computed 快照，通过 emit 让父级回写 store
  const list: string[] = [...(props.paper.hiddenElements || [])]
  const i = list.indexOf(key)
  if (i >= 0) list.splice(i, 1)
  else list.push(key)
  props.paper.hiddenElements = list
  emit('toggle-element', key)
}

/* ── 标题垂直拖拽：editable 状态下按住标题（避开 ✕ 按钮）上下拖 ──
   页面里有 measure 模式（px 与 mm 换算），统一按 mm 计算：
   1mm ≈ 96/25.4 px ≈ 3.7795px
   与 contenteditable 共存：mousedown 不拦截（保留点击编辑），
   移动超过 3px 才进入拖拽态并才 preventDefault */
const MM = 96 / 25.4
const dragState = ref<{ startY: number; startOffset: number; dragging: boolean } | null>(null)

function onTitleDragStart(e: MouseEvent) {
  if (!props.editable) return
  if ((e.target as HTMLElement).closest('.el-del')) return // 删除按钮不触发拖拽
  const startX = e.clientX
  dragState.value = { startY: e.clientY, startOffset: props.style.titleOffsetY ?? 0, dragging: false }
  const move = (ev: MouseEvent) => {
    if (!dragState.value) return
    const dx = ev.clientX - startX
    const dyPx = ev.clientY - dragState.value.startY
    if (!dragState.value.dragging) {
      if (Math.abs(dyPx) < 3) return // 尚未构成拖拽（点击/双击编辑不受影响）
      // 横向移动为主 = 用户在框选标题文字，不是拖动标题位置 → 放弃拖拽
      if (Math.abs(dx) > Math.abs(dyPx)) {
        dragState.value = null
        window.removeEventListener('mousemove', move)
        window.removeEventListener('mouseup', up)
        return
      }
      dragState.value.dragging = true
      document.body.style.cursor = 'grabbing'
      document.body.style.userSelect = 'none'
    }
    ev.preventDefault()
    const dyMm = Math.round((dragState.value.startOffset + dyPx / MM) * 10) / 10
    const clamped = Math.max(-20, Math.min(30, dyMm))
    emit('title-offset', clamped)
  }
  const up = () => {
    dragState.value = null
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    window.removeEventListener('mousemove', move)
    window.removeEventListener('mouseup', up)
  }
  window.addEventListener('mousemove', move)
  window.addEventListener('mouseup', up)
}

/** 卷头整体应用标题偏移：负值上移（压缩顶部间距）、正值下移 */
const headStyle = computed(() => ({
  marginTop: `${props.style.titleOffsetY ?? 0}mm`,
}))

/** 标题富文本渲染前净化（模板可能来自服务端/历史数据，防存储型 XSS） */
const titleHtmlSafe = computed(() => sanitizeRich(props.paper.titleHtml))
</script>

<template>
  <div
    class="paper"
    :class="{ measure: measuring }"
    :data-seccolor="style.secColor ? 1 : 0"
    :data-frame="style.frame"
    :data-encourage="style.encourage ? 1 : 0"
    :data-reward="style.reward ? 1 : 0"
    :data-kid="kidOn ? 1 : 0"
  >
    <!-- 装饰层 -->
    <div class="paper-frame-layer">
      <div class="fr fr-a"></div><div class="fr fr-b"></div>
      <div class="fr fr-top"></div><div class="fr fr-bottom"></div><div class="fr fr-left"></div><div class="fr fr-right"></div>
    </div>
    <div class="paper-bg-layer" :data-bg="style.bg" :style="{ opacity: style.bg === 'none' ? 0 : style.bgOpacity / 100 }"></div>

    <div class="exam">
      <!-- 卷头（标题偏移随拖拽变化） -->
      <div class="pv-head" :style="headStyle">
        <div v-if="!isHidden('banner')" class="exam-head" :data-plain="style.banner ? '0' : '1'">
          <span v-if="editable" class="el-del" title="删除整个卷头" @click="toggleHidden('banner')">✕</span>
          <h1
            v-if="!isHidden('title')"
            class="can-edit paper-title"
            :contenteditable="editable"
            spellcheck="false"
            :title="editable ? '上下拖动=移动位置；横向划选文字后可用工具条改色/字号' : undefined"
            @blur="onTitleBlur"
            @mousedown="onTitleDragStart"
            :style="{ position: 'relative', fontSize: `calc(${kidOn ? '26pt' : '22pt'} * ${style.titleScale ?? 1})` }"
          >
            <span v-if="editable" class="el-del" title="删除标题" @click.stop="toggleHidden('title')">✕</span>
            <!-- eslint-disable-next-line vue/no-v-html -->
            <span v-if="paper.titleHtml" v-html="titleHtmlSafe"></span>
            <template v-else>{{ paperTitle }}</template>
            <template v-if="paper.day && addDay">（第{{ paper.day }}天）</template>
          </h1>
          <div v-if="!isHidden('subline')" class="sub-line can-edit" :contenteditable="editable" spellcheck="false" style="position: relative;">
            <span v-if="editable" class="el-del" title="删除副标题行" @click="toggleHidden('subline')">✕</span>
            {{ subParts.join(' ｜ ') }}
          </div>
          <div v-if="template.showInfoRow && !isHidden('inforow')" class="info-row can-edit" :contenteditable="editable" spellcheck="false" style="position: relative;">
            <span v-if="editable" class="el-del" title="删除姓名班级栏" @click="toggleHidden('inforow')">✕</span>
            <div>姓名：<span>&nbsp;</span></div>
            <div>班级：<span>&nbsp;</span></div>
            <div>学号：<span>&nbsp;</span></div>
            <div>得分：<span>&nbsp;</span></div>
          </div>
        </div>
        <div v-if="template.showNotice && !isHidden('notice')" class="notice can-edit" :contenteditable="editable" spellcheck="false" style="position: relative;">
          <span v-if="editable" class="el-del" title="删除注意事项" @click="toggleHidden('notice')">✕</span>
          <b>注意事项：</b>① 答题前请将姓名、班级填写清楚；② 选择题答案填入答题卡；③ 保持卷面整洁，字迹工整。
        </div>
      </div>

      <!-- 大题块（分段渲染：跨页大题只渲染本页题段） -->
      <SectionBlock
        v-for="(b, k) in blocks"
        :key="(b.sec._sid || b.sec.type) + '_' + k"
        :section="b.sec"
        :sec-index="b.chunk.sec"
        :q-from="b.chunk.first ? 0 : b.chunk.qFrom"
        :q-to="b.chunk.qTo"
        :show-title="b.chunk.first"
        :show-score="template.showScore"
        :show-answers="showAnswers"
        :editable="editable"
        :encourage="style.encourage"
        :scores="scores"
      />

      <!-- 卷尾 -->
      <div v-if="isLast" class="pv-tail">
        <div v-if="style.reward && !isHidden('reward')" class="reward-box" style="position: relative;">
          <span v-if="editable" class="el-del" title="删除奖励区" @click="toggleHidden('reward')">✕</span>
          <span class="reward-title">今天的表现：</span>
          <span class="reward-stars">☆ ☆ ☆</span>
          <span class="reward-msg">老师给你涂星星～</span>
        </div>
        <div v-if="!isHidden('footer')" class="footer-note can-edit" :contenteditable="editable" spellcheck="false" @blur="onFooterBlur" style="position: relative;">
          <span v-if="editable" class="el-del" title="删除页脚" @click="toggleHidden('footer')">✕</span>
          {{ paper.footerOverride ?? template.footer }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pv-head, .pv-tail { display: flow-root; }
.paper-title { cursor: grab; }
.paper-title:active { cursor: grabbing; }
.el-del {
  position: absolute;
  right: 2px;
  top: 2px;
  width: 17px;
  height: 17px;
  line-height: 17px;
  text-align: center;
  font-size: 10px;
  color: #bbb;
  cursor: pointer;
  border-radius: 50%;
  z-index: 5;
  background: #fff;
  opacity: 0;
  transition: opacity .12s;
  user-select: none;
}
.can-edit:hover .el-del, .exam-head:hover > .el-del, .reward-box:hover .el-del, .el-del:hover { opacity: 1; }
.el-del:hover { color: var(--red); background: var(--red-light); }
</style>
