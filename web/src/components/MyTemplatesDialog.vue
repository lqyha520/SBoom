<script setup lang="ts">
import { useExamStore } from '../stores/exam'
import { TYPE_NAME } from '../constants'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const store = useExamStore()

function use(name: string) {
  if (store.loadMyTemplate(name)) emit('close')
}
</script>

<template>
  <teleport to="body">
    <div v-if="open" class="modal-mask" @click.self="emit('close')">
      <div class="modal" style="width: 520px;">
        <div class="modal-head">
          <h3>我的模板</h3>
          <button class="x-btn" @click="emit('close')">✕</button>
        </div>
        <div class="modal-body">
          <!-- 模板列表 -->
          <div v-if="!store.myTemplates.length" class="empty" style="padding: 28px;">
            <span>还没有保存的模板<br>点预览区的「💾 保存模板」按钮保存当前卷面</span>
          </div>

          <div v-for="t in store.myTemplates" :key="t.name" style="display: flex; align-items: center; gap: 10px; padding: 11px 0; border-top: 1px solid var(--border);">
            <div style="flex: 1; min-width: 0;">
              <b style="font-size: 13px;">{{ t.name }}</b>
              <div style="font-size: 12px; color: var(--ink3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                {{ t.grade }}{{ t.subject }} · {{ t.difficulty === 'easy' ? '简单' : t.difficulty === 'hard' ? '困难' : '中等' }} ·
                {{ t.cards.map(c => `${TYPE_NAME[c.type] || c.type}×${c.count}`).join('、') }}
              </div>
            </div>
            <button class="btn mini primary" @click="use(t.name)">使用</button>
            <button class="btn mini danger" @click="store.deleteMyTemplate(t.name)">删除</button>
          </div>
        </div>
      </div>
    </div>
  </teleport>
</template>
