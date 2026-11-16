<script setup lang="ts">
import type { ImageQualityReview } from '../image-generation'
defineProps<{ review?: ImageQualityReview }>()
const labels: Record<string, string> = {
  quantity: '题型与题量', text: '文字与符号', solvability: '题目可解性', diagram: '图文对应',
  scope: '知识范围', layout: '版面与作答空间', answer_leak: '答案遮蔽', duplicates: '页内重复题',
}
const statuses = { pass: '未发现问题', fail: '发现问题', uncertain: '需核实' }
</script>

<template>
  <section class="image-quality" aria-label="图片内容检查">
    <strong>{{ review?.status === 'passed' ? '自动检查未发现问题' : review?.status === 'issues' ? '自动检查发现疑点' : '自动检查未完成' }} · 待人工核对</strong>
    <p>请核对文字、题数、解题条件和图示，再用于教学或发布。自动检查可能遗漏问题。</p>
    <p v-if="review?.reason">{{ review.reason }}</p>
    <ul v-if="review?.issues.length"><li v-for="(issue, index) in review.issues" :key="index">{{ issue.question }}：{{ issue.message }}</li></ul>
    <details v-if="review && Object.keys(review.checks).length"><summary>查看检查明细</summary><ul><li v-for="(value, key) in review.checks" :key="key">{{ labels[key] || key }}：{{ statuses[value] }}</li></ul></details>
  </section>
</template>

<style scoped>
.image-quality { padding: 14px 16px; border: 1px solid var(--ui-border); border-radius: 10px; font-size: 13px; line-height: 1.7; }
.image-quality p { margin: 5px 0; color: var(--ui-text-muted); }
.image-quality ul { margin: 6px 0; padding-left: 20px; }
.image-quality summary { cursor: pointer; }
</style>
