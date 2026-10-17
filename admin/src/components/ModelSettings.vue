<script setup lang="ts">
import { ref } from 'vue'
import ModelProfilesEditor from './ModelProfilesEditor.vue'
import ImageModelSettings from './ImageModelSettings.vue'

const modelTab = ref('text')
</script>

<template>
  <UTabs v-model="modelTab" :items="[{ value: 'text', label: '文本出题', icon: 'i-lucide-file-text' }, { value: 'image', label: '图片出题', icon: 'i-lucide-image' }]" :content="false" variant="link" aria-label="模型服务类型" class="mb-7" :ui="{ list: 'gap-6 p-0', trigger: 'px-0 pb-3' }" />
  <ModelProfilesEditor v-show="modelTab === 'text'" kind="text" />
  <ImageModelSettings v-show="modelTab === 'image'" />
</template>
