<script setup lang="ts">
import { ref, watch } from 'vue'
import { useExamStore } from '../stores/exam'

const open = defineModel<boolean>('open', { default: false })
const store = useExamStore()
const config = ref({ ...store.customTemplate })
watch(open, value => { if (value) config.value = { ...store.customTemplate } })
function apply() {
  store.saveCustomTemplate(config.value)
  open.value = false
}
</script>

<template>
  <UModal v-model:open="open" title="自定义卷面模板">
    <template #body>
      <div class="field-stack">
        <UFormField label="标题前缀"><UInput v-model="config.titlePrefix" maxlength="20" placeholder="例如：每日一练" /></UFormField>
        <UFormField label="标题后缀"><UInput v-model="config.titleSuffix" maxlength="20" placeholder="例如：测试卷" /></UFormField>
        <UFormField label="页脚文字"><UInput v-model="config.footer" maxlength="40" /></UFormField>
        <UCheckbox v-model="config.showInfoRow" label="姓名与班级栏" />
        <UCheckbox v-model="config.showNotice" label="注意事项" />
        <UCheckbox v-model="config.showScore" label="分数" />
      </div>
    </template>
    <template #footer><UButton color="neutral" variant="outline" label="取消" @click="open = false" /><UButton label="应用模板" @click="apply" /></template>
  </UModal>
</template>
