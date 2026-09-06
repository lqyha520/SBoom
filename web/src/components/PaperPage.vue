<script setup lang="ts">
import { computed } from 'vue'
import type { PaperData, PaperSection, PaperStyle, PaperTemplate } from '../types'
import { DIFF_NAME } from '../constants'
import SectionBlock from './SectionBlock.vue'

const props = defineProps<{
  paper: PaperData
  /** 要渲染的大题索引切片 */
  idxs: number[]
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

const blocks = computed(() => props.idxs.map(i => props.paper.sections[i]).filter(Boolean) as PaperSection[])

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
  props.paper.title = (e.target as HTMLElement).innerText.trim()
}
function onFooterBlur(e: FocusEvent) {
  if (!props.editable) return
  ;(props.paper as any).footerOverride = (e.target as HTMLElement).innerText.trim()
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
        <div class="exam-head" :data-plain="style.banner ? '0' : '1'">
          <h1 class="can-edit" :contenteditable="editable" spellcheck="false" @blur="onTitleBlur">
            {{ paperTitle }}<template v-if="paper.day && addDay">（第{{ paper.day }}天）</template>
          </h1>
          <div class="sub-line">{{ subParts.join(' ｜ ') }}</div>
          <div v-if="template.showInfoRow" class="info-row">
            <div>姓名：<span>&nbsp;</span></div>
            <div>班级：<span>&nbsp;</span></div>
            <div>学号：<span>&nbsp;</span></div>
            <div>得分：<span>&nbsp;</span></div>
          </div>
        </div>
        <div v-if="template.showNotice" class="notice">
          <b>注意事项：</b>① 答题前请将姓名、班级填写清楚；② 选择题答案填入答题卡；③ 保持卷面整洁，字迹工整。
        </div>
      </div>

      <!-- 大题块 -->
      <SectionBlock
        v-for="(sec, k) in blocks"
        :key="sec._sid || sec.type + '_' + idxs[k]"
        :section="sec"
        :sec-index="idxs[k]"
        :show-score="template.showScore"
        :show-answers="showAnswers"
        :editable="editable"
        :encourage="style.encourage"
        :scores="scores"
      />

      <!-- 卷尾 -->
      <div v-if="isLast" class="pv-tail">
        <div v-if="style.reward" class="reward-box">
          <span class="reward-title">今天的表现：</span>
          <span class="reward-stars">☆ ☆ ☆</span>
          <span class="reward-msg">老师给你涂星星～</span>
        </div>
        <div class="footer-note can-edit" :contenteditable="editable" spellcheck="false" @blur="onFooterBlur">
          {{ (paper as any).footerOverride ?? template.footer }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pv-head, .pv-tail { display: flow-root; }
</style>
