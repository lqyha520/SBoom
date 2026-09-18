<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useExamStore } from '../stores/exam'
import { TYPE_NAME } from '../constants'
import { answerOf } from '../utils'
const props = defineProps<{ sectionId?: string; paperIndex?: number }>()
const emit = defineEmits<{ close: [] }>()
const store = useExamStore()
const selected = ref(props.sectionId || '')
const error = ref(''), notice = ref(''), confirming = ref('')
const options = computed(() => props.paperIndex === undefined
  ? store.sections.map(item => ({ value: item.id, label: item.name || TYPE_NAME[item.type] || item.type }))
  : (store.papers[props.paperIndex]?.sections || []).map((item, index) => ({ value: item._sid || String(index), label: item.name || TYPE_NAME[item.type] || item.type })))
watch(options, items => { if (!items.some(item => item.value === selected.value)) selected.value = items[0]?.value || '' }, { immediate: true })
const section = computed(() => store.questionSection(selected.value, props.paperIndex))
async function replace() {
  const qid = confirming.value; confirming.value = ''; error.value = ''; notice.value = ''
  try { await store.replaceQuestion(selected.value, qid, props.paperIndex); notice.value = '已替换此题，可通过撤销恢复原题' }
  catch (cause) { error.value = cause instanceof Error ? cause.message : '替换失败，原题已保留' }
}
</script>
<template>
  <UModal :open="true" title="管理题目" :dismissible="!store.generating" :close="!store.generating" :ui="{ content: 'max-w-2xl' }" @update:open="value => { if (!value) emit('close') }">
    <template #body>
      <USelect v-model="selected" :items="options" aria-label="选择要管理的大题" :disabled="store.generating" class="w-full mb-4" />
      <p class="text-sm text-muted mb-4">锁定的题目会在重新生成时保留。单题替换会发送新的模型请求，可能产生费用。</p>
      <UAlert v-if="section?.type === 'reading'" title="阅读理解与文章关联，请从大题菜单整体重新生成" color="info" class="mb-4" />
      <UAlert v-if="error" :title="error" color="error" class="mb-4" /><UAlert v-if="notice" :title="notice" color="success" class="mb-4" />
      <div v-for="(question, index) in section?.data?.questions || []" :key="question._qid" class="border-b border-default py-3">
        <p class="text-sm whitespace-pre-wrap">{{ index + 1 }}. {{ question.stem || [question.left_expr, question.right_expr].filter(Boolean).join(' ○ ') || [question.top, question.left, question.right].filter(value => value != null).join(' / ') || '配对题' }}</p>
        <p class="text-xs text-muted mt-1">答案：{{ answerOf(question) }}</p>
        <div class="flex gap-2 mt-2">
          <UButton :label="question._locked ? '已锁定 · 点击解锁' : '锁定此题'" :icon="question._locked ? 'i-lucide-lock-keyhole' : 'i-lucide-lock-keyhole-open'" size="xs" variant="soft" :disabled="store.generating || section?.type === 'reading' || !!question._replacement" @click="store.toggleQuestionLock(selected, question._qid!, paperIndex)" />
          <UButton :label="question._replacement ? '查询并重试换题' : '换一道题'" icon="i-lucide-refresh-cw" size="xs" variant="outline" :disabled="store.generating || question._locked || section?.type === 'reading'" @click="confirming = question._qid!" />
        </div>
      </div>
    </template>
    <template #footer><UButton label="完成" :disabled="store.generating" @click="emit('close')" /></template>
  </UModal>
  <UModal :open="!!confirming" title="替换这道题？" description="仅替换此题，其他题目保持不变。请求可能产生费用；失败时保留原题，仍在处理的请求不会重复发送。" @update:open="value => { if (!value) confirming = '' }"><template #footer><UButton label="取消" variant="outline" @click="confirming = ''" /><UButton label="确认换题" @click="replace" /></template></UModal>
</template>
