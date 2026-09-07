<script setup lang="ts">
import { computed } from 'vue'
import type { PaperData, PaperSection, PaperStyle, PaperTemplate } from '../types'
import { DIFF_NAME } from '../constants'
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
  scores?: Map<any, number>
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
  // innerHTML 会包含 ✕ 删除按钮和（第X天）后缀，克隆后剔除再存
  const clone = el.cloneNode(true) as HTMLElement
  clone.querySelectorAll('.el-del').forEach(n => n.remove())
  props.paper.title = clone.innerText.replace(/（第\d+天）\s*$/, '').trim()
  ;(props.paper as any).titleHtml = clone.innerHTML.replace(/（第\d+天）\s*(<\/\w+>)?\s*$/, '$1')
  emit('title-edited', props.paper.title, (props.paper as any).titleHtml)
}
function onFooterBlur(e: FocusEvent) {
  if (!props.editable) return
  ;(props.paper as any).footerOverride = (e.target as HTMLElement).innerText.trim()
}

/* ── 卷头/卷尾元素单独删除（排版能力，随 paper 数据持久化） ── */
const emit = defineEmits<{ (e: 'toggle-element', key: string): void; (e: 'title-edited', title: string, html: string): void }>()
const hiddenList = computed<string[]>(() => (props.paper as any).hiddenElements || [])
function isHidden(key: string): boolean {
  return hiddenList.value.includes(key)
}
function toggleHidden(key: string) {
  // 结果页：paper 是 store 里的对象，直接改（响应式生效）
  // 搭建预览：paper 是 computed 快照，通过 emit 让父级回写 store
  const p = props.paper as any
  const list: string[] = [...(p.hiddenElements || [])]
  const i = list.indexOf(key)
  if (i >= 0) list.splice(i, 1)
  else list.push(key)
  p.hiddenElements = list
  emit('toggle-element', key)
}
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
      <!-- 卷头 -->
      <div class="pv-head">
        <div v-if="!isHidden('banner')" class="exam-head" :data-plain="style.banner ? '0' : '1'">
          <span v-if="editable" class="el-del" title="删除整个卷头" @click="toggleHidden('banner')">✕</span>
          <h1
            v-if="!isHidden('title')"
            class="can-edit"
            :contenteditable="editable"
            spellcheck="false"
            @blur="onTitleBlur"
            :style="{ position: 'relative', fontSize: `calc(${kidOn ? '26pt' : '22pt'} * ${style.titleScale ?? 1})` }"
          >
            <span v-if="editable" class="el-del" title="删除标题" @click.stop="toggleHidden('title')">✕</span>
            <!-- eslint-disable-next-line vue/no-v-html -->
            <span v-if="(paper as any).titleHtml" v-html="(paper as any).titleHtml"></span>
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
          {{ (paper as any).footerOverride ?? template.footer }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pv-head, .pv-tail { display: flow-root; }
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
