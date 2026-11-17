<script setup lang="ts">
import { permissionDirective as vPermission } from '../permissions'
import { ref } from 'vue'
import { randomId } from '../../../shared/webcrypto'
import { createWorkflow, goWorkflow, workflowError, type IdeaData } from '../xhs-workflow'
import { previewReviewIdea } from '../xhs-workspace'
const props = defineProps<{ publicationId: string; checkpoint: number; disabled?: boolean }>()
const open = ref(false), busy = ref(false), error = ref(''), data = ref<IdeaData | null>(null), reasons = ref<string[]>([]), createId = ref('')
async function preview() {
  if (busy.value || props.disabled) return
  busy.value = true; error.value = ''
  try { const result = await previewReviewIdea(props.publicationId, props.checkpoint); data.value = result.data; reasons.value = result.reasons; createId.value = randomId(); open.value = true }
  catch (cause) { error.value = workflowError(cause) } finally { busy.value = false }
}
async function save() {
  if (!data.value || busy.value) return
  busy.value = true; error.value = ''
  try { const saved = await createWorkflow('ideas', createId.value, null, data.value); open.value = false; goWorkflow('ideas', saved.id) }
  catch (cause) { error.value = workflowError(cause) } finally { busy.value = false }
}
</script>
<template><div><UButton v-permission="'xhsIdeas:create'" label="复盘转选题" size="sm" variant="outline" :disabled="disabled" :loading="busy" @click="preview" /><p v-if="error && !open" role="alert" class="workflow-hint">{{ error }}</p><UModal v-model:open="open" title="把复盘整理为下一篇选题" :dismissible="!busy"><template #body><div v-if="data" class="workflow-editor"><div class="workflow-step"><p v-for="reason in reasons" :key="reason">{{ reason }}</p><p>这是待验证的选题草稿，请结合读者反馈修改；不同阶段的数据不混合比较。</p></div><label class="workflow-field"><span>后续选题名称</span><UInput v-model="data.title" aria-label="复盘选题名称" maxlength="120" /></label><div class="workflow-grid"><label class="workflow-field"><span>适用年级</span><UInput v-model="data.grade" maxlength="20" /></label><label class="workflow-field"><span>科目</span><UInput v-model="data.subject" maxlength="20" /></label></div><label class="workflow-field"><span>目标读者</span><UInput v-model="data.audience" maxlength="200" /></label><label class="workflow-field"><span>要解决的问题</span><UTextarea v-model="data.problem" :rows="3" maxlength="2000" /></label><label class="workflow-field"><span>下一篇的切入点</span><UTextarea v-model="data.angle" aria-label="复盘选题切入点" :rows="4" maxlength="2000" /></label><p class="workflow-hint">确认后进入选题库，可继续制作资料；原发布记录与复盘数据会保留。</p><UAlert v-if="error" :title="error" color="error" /></div></template><template #footer><UButton label="取消" variant="outline" :disabled="busy" @click="open=false" /><UButton v-permission="'xhsIdeas:create'" label="确认加入选题库" :loading="busy" :disabled="!data?.title.trim()" @click="save" /></template></UModal></div></template>
