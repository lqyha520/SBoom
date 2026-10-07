<script setup lang="ts">
import FormatBar from './FormatBar.vue'

withDefaults(
  defineProps<{
    layoutMode: boolean
    disabled?: boolean
    canLayout: boolean
    answers?: boolean
    manage?: boolean
    saveTemplate?: boolean
  }>(),
  { answers: undefined },
)
defineEmits<{
  settings: []
  layout: []
  cancel: []
  manage: []
  save: []
  'update:answers': [value: boolean]
}>()
</script>

<template>
  <div
    class="preview-toolbar paper-edit-toolbar no-print"
    role="toolbar"
    aria-label="卷面编辑"
  >
    <FormatBar :disabled="disabled || layoutMode" />
    <div class="actions-row paper-edit-actions">
      <USwitch
        v-if="answers !== undefined"
        :model-value="answers"
        label="显示答案"
        size="sm"
        :disabled="disabled || layoutMode"
        @update:model-value="$emit('update:answers', $event)"
      />
      <template v-if="!layoutMode">
        <UTooltip text="卷面设置"
          ><UButton
            icon="i-lucide-settings-2"
            aria-label="编辑卷面设置"
            color="neutral"
            variant="ghost"
            :disabled="disabled"
            @click="$emit('settings')"
        /></UTooltip>
        <UTooltip v-if="manage" text="管理题目"
          ><UButton
            icon="i-lucide-list-checks"
            aria-label="管理题目"
            color="neutral"
            variant="ghost"
            :disabled="disabled"
            @click="$emit('manage')"
        /></UTooltip>
        <UTooltip text="排版模式"
          ><UButton
            icon="i-lucide-move"
            aria-label="排版模式"
            color="neutral"
            variant="ghost"
            :disabled="disabled || !canLayout"
            @click="$emit('layout')"
        /></UTooltip>
        <UTooltip v-if="saveTemplate" text="保存模板"
          ><UButton
            icon="i-lucide-bookmark-plus"
            aria-label="保存模板"
            color="neutral"
            variant="ghost"
            :disabled="disabled || !canLayout"
            @click="$emit('save')"
        /></UTooltip>
      </template>
      <template v-else>
        <UButton
          label="取消"
          color="neutral"
          variant="ghost"
          @click="$emit('cancel')"
        />
        <UButton
          label="完成排版"
          icon="i-lucide-check"
          @click="$emit('layout')"
        />
      </template>
    </div>
  </div>
</template>

<style scoped>
.paper-edit-actions {
  flex-wrap: wrap;
}
@media (max-width: 620px) {
  .paper-edit-actions button {
    min-width: 44px;
    min-height: 44px;
  }
}
</style>
