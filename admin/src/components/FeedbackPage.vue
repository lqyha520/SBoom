<script setup lang="ts">
import { useAdminRefresh } from '../admin-page'
import { computed, onMounted, ref, watch } from 'vue'
import { fetchAdminFeedbacks, type AdminFeedback } from '../api'

const feedbacks = ref<AdminFeedback[]>([])
const onlyOob = ref(false)
const loading = ref(false)
const error = ref('')
const page = ref(1)
const pageSize = 20
const rows = computed(() => feedbacks.value.slice((page.value - 1) * pageSize, page.value * pageSize))
let request = 0
async function load() {
  const id = ++request
  loading.value = true
  error.value = ''
  try {
    const result = await fetchAdminFeedbacks(200, onlyOob.value)
    if (id === request) { feedbacks.value = result; page.value = 1 }
  } catch (e: unknown) {
    if (id === request) error.value = e instanceof Error ? e.message : '反馈加载失败'
  } finally { if (id === request) loading.value = false }
}
watch(onlyOob, load)
useAdminRefresh(load, () => { request++; loading.value = false })
</script>

<template>
  <section class="admin-section" aria-label="用户反馈列表">
    <div class="section-toolbar"><div class="actions-row"><h2>最近反馈</h2><UBadge color="neutral" variant="soft">{{ feedbacks.length }}</UBadge></div><div class="actions-row"><USwitch v-model="onlyOob" label="仅超纲反馈" size="sm" /><UTooltip text="刷新反馈"><UButton icon="i-lucide-refresh-cw" color="neutral" variant="outline" aria-label="刷新反馈" :loading="loading" @click="load" /></UTooltip></div></div>
    <UAlert v-if="error" :title="error" color="error" variant="soft" class="notice" role="alert" />
    <div class="data-scroll" :aria-busy="loading"><table class="data-table"><thead><tr><th scope="col">用户</th><th scope="col">类型</th><th scope="col">试卷 ID</th><th scope="col">反馈内容</th><th scope="col">提交时间</th></tr></thead><tbody>
      <tr v-for="item in rows" :key="item.id"><td class="name-cell">{{ item.username || '已删除用户' }}</td><td><UBadge :color="item.is_oob ? 'warning' : 'info'" variant="subtle" size="sm">{{ item.is_oob ? '超纲' : '一般' }}</UBadge></td><td class="date-cell">{{ item.game_id }}</td><td class="comment-cell">{{ item.comment || '无附加内容' }}</td><td class="date-cell">{{ item.created_at }}</td></tr>
      <tr v-if="!rows.length"><td colspan="5"><div class="empty-state"><UIcon :name="loading ? 'i-lucide-loader-circle' : 'i-lucide-message-square'" class="size-7" :class="{ 'animate-spin': loading }" /><h3>{{ loading ? '正在加载反馈' : error ? '反馈暂不可用' : '暂无' + (onlyOob ? '超纲' : '') + '反馈' }}</h3></div></td></tr>
    </tbody></table></div>
    <div class="table-footer"><span>最近 {{ feedbacks.length }} 条 / 最多 200 条</span><UPagination v-if="feedbacks.length > pageSize" v-model:page="page" :total="feedbacks.length" :items-per-page="pageSize" :sibling-count="1" size="sm" /></div>
  </section>
</template>
