<script setup lang="ts">
import { ref, watch } from 'vue'
import { useExamStore } from '../stores/exam'
import { LLM_DEFAULTS } from '../constants'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const store = useExamStore()
const baseUrl = ref(store.llm.baseUrl)
const model = ref(store.llm.model)
const apiKey = ref(store.llm.apiKey)
const timeout = ref(store.llm.timeout)
const msg = ref({ text: '', ok: true })
const testing = ref(false)

watch(
  () => props.open,
  o => { if (o) { baseUrl.value = store.llm.baseUrl; model.value = store.llm.model; apiKey.value = store.llm.apiKey; timeout.value = store.llm.timeout; msg.value = { text: '', ok: true } } },
)

async function save() {
  try {
    const r = await store.saveLlm({
      baseUrl: baseUrl.value.trim() || LLM_DEFAULTS.baseUrl,
      model: model.value.trim() || LLM_DEFAULTS.model,
      apiKey: apiKey.value.trim(),
      timeout: parseInt(String(timeout.value)) || 60,
    })
    msg.value = { text: r.message || '已保存', ok: true }
  } catch (e: any) {
    msg.value = { text: '已本地保存，但后端更新失败：' + (e?.message || e), ok: false }
  }
}

function reset() {
  baseUrl.value = LLM_DEFAULTS.baseUrl
  model.value = LLM_DEFAULTS.model
  apiKey.value = ''
  timeout.value = 60
}

async function test() {
  testing.value = true
  msg.value = { text: '', ok: true }
  try {
    const { testLlm } = await import('../api')
    const d = await testLlm()
    msg.value = { text: '连接成功！模型回复：' + d.reply, ok: true }
  } catch (e: any) {
    msg.value = { text: '连接失败：' + (e?.message || e), ok: false }
  } finally {
    testing.value = false
  }
}
</script>

<template>
  <teleport to="body">
    <div v-if="open" class="modal-mask" @click.self="emit('close')">
      <div class="modal">
        <div class="modal-head"><h3>模型配置</h3><button class="x-btn" @click="emit('close')">✕</button></div>
        <div class="modal-body">
          <div class="form-row"><label>接口地址（OpenAI 兼容）</label><input class="input" v-model="baseUrl" placeholder="https://api.deepseek.com"></div>
          <div class="form-row"><label>模型</label><input class="input" v-model="model" placeholder="deepseek-chat"></div>
          <div class="form-row"><label>密钥</label><input class="input" type="password" v-model="apiKey" placeholder="sk-...（留空则用后端 .env 配置）"></div>
          <div class="form-row"><label>超时（秒）</label><input class="input" type="number" min="10" max="600" v-model.number="timeout" style="width: 100px;"></div>
          <div class="form-msg" :class="msg.ok ? 'ok' : 'err'">{{ msg.text }}</div>
        </div>
        <div class="modal-foot">
          <button class="btn" @click="reset">恢复默认</button>
          <button class="btn" :disabled="testing" @click="test">{{ testing ? '测试中…' : '测试连接' }}</button>
          <button class="btn primary" @click="save">保存生效</button>
        </div>
      </div>
    </div>
  </teleport>
</template>
