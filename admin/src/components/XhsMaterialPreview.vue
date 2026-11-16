<script setup lang="ts">
import { permissionDirective as vPermission } from '../permissions'
import { onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { materialDocument, materialFilename } from '../xhs-content-export'
import { cleanWorkflowData, materialReviewFingerprint, workflowError, type MaterialData } from '../xhs-workflow'
import { downloadBlob } from '../../../shared/download'

const props = defineProps<{ data: MaterialData; session: number }>()
const open = ref(false), loading = ref(false), answers = ref(false), pages = ref<string[]>([]), error = ref(''), notice = ref('')
const zoom = ref(100)
let sequence = 0, document: Blob | null = null, filename = ''
function clear() {
  sequence++; loading.value = false; document = null; pages.value = []
}
async function preview(withAnswers = false) {
  clear(); open.value = true; answers.value = withAnswers; error.value = ''; notice.value = ''
  const key = sequence, value = cleanWorkflowData(props.data)
  loading.value = true
  try {
    const result = await materialDocument(value, withAnswers, true)
    if (key !== sequence || !open.value) return
    document = result.pdf; filename = materialFilename(value, withAnswers); pages.value = result.pages
  } catch (cause) { if (key === sequence) error.value = workflowError(cause) }
  finally { if (key === sequence) loading.value = false }
}
function download() { if (document) downloadBlob(document, filename, 2000) }
watch(() => [props.session, props.data.title, materialReviewFingerprint(props.data)], (value, previous) => {
  clear()
  if (value[0] !== previous[0]) open.value = false
  else if (open.value) notice.value = '资料已修改，请重新预览当前内容。'
}, { flush: 'sync' })
watch(open, value => { if (!value) clear() })
function close() { open.value = false; clear() }
onDeactivated(close); onBeforeUnmount(clear)
</script>

<template>
  <UButton label="预览资料 PDF" variant="outline" :disabled="!data.questions.length" @click="preview()" />
  <UModal v-model:open="open" title="资料 PDF 预览" :ui="{ content: 'max-w-6xl' }">
    <template #body>
      <div class="workflow-actions mb-4">
        <UButton label="学生卷" :variant="answers ? 'outline' : 'solid'" :disabled="loading" @click="preview(false)" />
        <UButton label="答案与讲解" :variant="answers ? 'solid' : 'outline'" :disabled="loading" @click="preview(true)" />
        <UButton v-permission="'xhsMaterials:export'" label="下载当前预览" variant="outline" :disabled="!pages.length || loading" @click="download" />
        <span v-if="pages.length" role="status">共 {{ pages.length }} 页</span>
      </div>
      <div v-if="pages.length" class="workflow-actions mb-3">
        <UButton label="缩小预览" size="sm" variant="outline" :disabled="zoom<=100" @click="zoom-=50" />
        <UButton label="放大预览" size="sm" variant="outline" :disabled="zoom>=250" @click="zoom+=50" />
        <UButton label="适应宽度" size="sm" variant="ghost" :disabled="zoom===100" @click="zoom=100" />
        <span>{{ zoom }}%</span>
      </div>
      <UAlert v-if="error" :title="error" color="error" role="alert" />
      <UAlert v-if="notice" :title="notice" color="warning" role="status" />
      <div v-if="loading" class="pdf-loading" role="status">正在生成预览…</div>
      <div v-else-if="pages.length" class="pdf-preview">
        <figure v-for="(page,index) in pages" :key="index" :style="{width:zoom+'%'}"><img :src="page" :alt="`${answers ? '答案讲解' : '学生卷'}第${index+1}页预览`" loading="lazy" /><figcaption>第 {{ index+1 }} 页</figcaption></figure>
      </div>
      <p v-if="pages.length" class="workflow-hint">请检查分页、题目留白和答案讲解；下载当前预览可获得相同版式的 PDF。</p>
    </template>
  </UModal>
</template>

<style scoped>
.pdf-preview{width:100%;max-height:65vh;min-height:320px;overflow:auto;border:1px solid #dce8e0;border-radius:10px;background:#f6f9f7}
.pdf-preview figure{margin:0;padding:10px}.pdf-preview img{display:block;width:100%;height:auto}.pdf-preview figcaption{text-align:center;margin-top:8px;color:#638071;font-size:12px}
.pdf-loading{display:grid;place-items:center;min-height:220px;color:#638071}
</style>
