<script setup lang="ts">
import { ref } from 'vue'
import { useExamStore } from '../stores/exam'
import { TYPE_NAME } from '../constants'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const store = useExamStore()
const saveName = ref('')

function save() {
  const name = saveName.value.trim()
  if (!name || !store.sections.length) return
  store.saveMyTemplate(name)
  saveName.value = ''
}

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
          <!-- 保存当前卷面 -->
          <div class="card" style="padding: 12px; margin-bottom: 14px; background: var(--surface2);">
            <div style="font-size: 12px; color: var(--ink2); margin-bottom: 8px;">
              把<b>当前卷面</b>存为模板（含题目文字、富文本样式、大题版式、装饰风格、已删元素）
            </div>
            <div style="display: flex; gap: 8px;">
              <input class="input" v-model="saveName" maxlength="20" placeholder="模板名称，如：三年级口算每日一练" @keyup.enter="save">
              <button class="btn primary" style="flex: none;" :disabled="!saveName.trim() || !store.sections.length" @click="save">保存</button>
            </div>
          </div>

          <!-- 模板列表 -->
          <div v-if="!store.myTemplates.length" class="empty" style="padding: 28px;">
            <span>还没有保存的模板<br>搭好卷面 / 排版完成后，输入名称保存</span>
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
