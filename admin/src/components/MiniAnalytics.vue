<script setup lang="ts">
import { computed, onActivated, onDeactivated, ref } from 'vue'
import type { UserInfo } from '../api'
import { siteAnalytics, type Analytics } from '../site'

const props = defineProps<{ user: UserInfo }>()
const data = ref<Analytics | null>(null)
const loading = ref(false)
const error = ref('')
let sequence = 0

const peak = computed(() => Math.max(1, ...(data.value?.new_users_timeline || []).map(item => item.total)))
const maxCategoryPapers = computed(() => Math.max(1, ...(data.value?.by_category || []).map(item => item.papers)))
const message = (cause: unknown) => (cause instanceof Error ? cause.message : '加载失败，请重试')
const date = (stamp: number) => new Date(stamp * 1000).toLocaleDateString('zh-CN')

async function load() {
  const current = ++sequence
  loading.value = true; error.value = ''
  try {
    const result = await siteAnalytics()
    if (current === sequence) data.value = result
  } catch (cause) { if (current === sequence) error.value = message(cause) }
  finally { if (current === sequence) loading.value = false }
}

onActivated(load)
onDeactivated(() => { sequence++; loading.value = false })
</script>

<template>
  <section class="admin-section" aria-label="内容数据看板">
    <div class="section-toolbar">
      <p class="section-hint">只看已发布内容的运营数据，下架与草稿不计入互动统计。</p>
      <UTooltip text="刷新"><UButton icon="i-lucide-refresh-cw" color="neutral" variant="ghost" aria-label="刷新看板" :loading="loading" @click="load" /></UTooltip>
    </div>
    <UAlert v-if="error" :title="error" color="error" variant="soft" class="notice" />
    <div v-if="!data && loading" class="loading-block"><UIcon name="i-lucide-loader-circle" class="size-6 animate-spin" /><span>正在统计</span></div>
    <template v-else-if="data">
      <div class="metric-grid">
        <div class="metric"><div class="metric-label"><span>已发布习题</span><UIcon name="i-lucide-library" class="size-4" /></div><div class="metric-number">{{ data.papers.published }}</div><div class="metric-detail">草稿 {{ data.papers.draft }} · 下架 {{ data.papers.withdrawn }}</div></div>
        <div class="metric"><div class="metric-label"><span>小程序用户</span><UIcon name="i-lucide-contact-round" class="size-4" /></div><div class="metric-number">{{ data.users.total }}</div><div class="metric-detail">近 7 天新增 {{ data.users.new_7d }} · 近 30 天 {{ data.users.new_30d }}</div></div>
        <div class="metric"><div class="metric-label"><span>有效 VIP</span><UIcon name="i-lucide-crown" class="size-4" /></div><div class="metric-number">{{ data.users.vip }}</div><div class="metric-detail">启用账号 {{ data.users.active }} 个</div></div>
        <div class="metric"><div class="metric-label"><span>互动总量</span><UIcon name="i-lucide-activity" class="size-4" /></div><div class="metric-number">{{ data.engagement.favorites + data.engagement.downloads }}</div><div class="metric-detail">收藏 {{ data.engagement.favorites }} · 下载 {{ data.engagement.downloads }}</div></div>
      </div>

      <div class="panel">
        <h2 class="section-title">近 14 天新增小程序用户</h2>
        <div class="timeline">
          <div v-for="point in data.new_users_timeline" :key="point.date" class="timeline-col">
            <span class="timeline-value">{{ point.total }}</span>
            <div class="timeline-bar" :style="{ height: Math.round(Math.max(4, (point.total / peak) * 100)) + '%' }" />
            <span class="timeline-label">{{ point.date }}</span>
          </div>
        </div>
      </div>

      <div class="panel-grid">
        <div class="panel">
          <h2 class="section-title">收藏榜</h2>
          <ol class="rank-list">
            <li v-for="(item, index) in data.top_favorites" :key="item.id"><span class="rank-index">{{ index + 1 }}</span><span class="rank-title">{{ item.title }}</span><span class="rank-category">{{ item.category || '未分类' }}</span><strong class="rank-total">{{ item.total }}</strong></li>
            <li v-if="!data.top_favorites.length" class="rank-empty">还没有已发布习题</li>
          </ol>
        </div>
        <div class="panel">
          <h2 class="section-title">下载榜</h2>
          <ol class="rank-list">
            <li v-for="(item, index) in data.top_downloads" :key="item.id"><span class="rank-index">{{ index + 1 }}</span><span class="rank-title">{{ item.title }}</span><span class="rank-category">{{ item.category || '未分类' }}</span><strong class="rank-total">{{ item.total }}</strong></li>
            <li v-if="!data.top_downloads.length" class="rank-empty">还没有已发布习题</li>
          </ol>
        </div>
      </div>

      <div class="panel">
        <h2 class="section-title">分类内容分布</h2>
        <table class="plain-table">
          <thead><tr><th>分类</th><th class="num-col">习题</th><th class="num-col">收藏</th><th class="num-col">下载</th><th class="bar-col">占比</th></tr></thead>
          <tbody>
            <tr v-for="row in data.by_category" :key="row.name">
              <td class="name-cell">{{ row.name }}</td>
              <td class="num-col">{{ row.papers }}</td>
              <td class="num-col">{{ row.favorites }}</td>
              <td class="num-col">{{ row.downloads }}</td>
              <td class="bar-col"><div class="bar-track"><div class="bar-fill" :style="{ width: Math.round((row.papers / maxCategoryPapers) * 100) + '%' }" /></div></td>
            </tr>
            <tr v-if="!data.by_category.length"><td colspan="5" class="rank-empty">暂无已发布内容</td></tr>
          </tbody>
        </table>
      </div>

      <div v-if="data.idle_papers.length || data.papers_without_category" class="panel">
        <h2 class="section-title">待处理</h2>
        <ul class="todo-list">
          <li v-if="data.papers_without_category"><UIcon name="i-lucide-folder-x" class="size-4" /><span>有 <strong>{{ data.papers_without_category }}</strong> 份习题没有关联到分类，小程序首页专题位不会收录它们。去「公共习题」编辑时选择分类即可。</span></li>
          <li v-if="data.idle_papers.length"><UIcon name="i-lucide-trending-down" class="size-4" /><span>有 <strong>{{ data.idle_papers.length }}</strong> 份已发布习题至今无人收藏或下载：{{ data.idle_papers.slice(0, 3).map(item => item.title).join('、') }}{{ data.idle_papers.length > 3 ? ' 等' : '' }}。</span></li>
        </ul>
      </div>
    </template>
  </section>
</template>

<style scoped>
.section-hint { margin: 0; max-width: 620px; color: var(--ui-text-muted); font-size: 12px; line-height: 1.7; }
.loading-block { display: flex; align-items: center; gap: 10px; padding: 40px 0; color: var(--ui-text-muted); font-size: 13px; }
.panel { margin-bottom: 28px; padding: 22px; border: 1px solid var(--ui-border); border-radius: 8px; }
.panel-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; margin-bottom: 28px; }
.panel-grid .panel { margin-bottom: 0; }
.panel .section-title { margin: 0 0 20px; }
.timeline { display: flex; align-items: flex-end; gap: 8px; height: 170px; padding-top: 8px; }
.timeline-col { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; gap: 6px; height: 100%; min-width: 0; }
.timeline-bar { width: 100%; max-width: 30px; border-radius: 3px; background: #9bcfb6; }
.timeline-value { font-size: 11px; color: var(--ui-text-muted); font-variant-numeric: tabular-nums; }
.timeline-label { font-size: 10px; color: var(--ui-text-muted); white-space: nowrap; }
.rank-list { list-style: none; margin: 0; padding: 0; }
.rank-list li { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--ui-border-muted); font-size: 13px; }
.rank-list li:last-child { border-bottom: 0; }
.rank-index { width: 20px; flex: none; color: var(--ui-text-muted); font-size: 11px; font-variant-numeric: tabular-nums; }
.rank-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rank-category { color: var(--ui-text-muted); font-size: 11px; white-space: nowrap; }
.rank-total { font-variant-numeric: tabular-nums; }
.rank-empty { color: var(--ui-text-muted); font-size: 12px; }
.plain-table { width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }
.plain-table th { padding: 8px 10px; color: var(--ui-text-muted); font-size: 11px; font-weight: 500; }
.plain-table td { padding: 10px; border-top: 1px solid var(--ui-border-muted); }
.plain-table .num-col { width: 84px; text-align: right; font-variant-numeric: tabular-nums; }
.bar-col { width: 180px; }
.bar-track { height: 6px; border-radius: 99px; background: #eef2f3; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 99px; background: #9bcfb6; }
.todo-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 14px; }
.todo-list li { display: flex; align-items: flex-start; gap: 10px; font-size: 13px; line-height: 1.7; color: var(--ui-text-toned); }
.todo-list li svg { flex: none; margin-top: 4px; color: var(--ui-warning); }
@media (max-width: 1100px) { .panel-grid { grid-template-columns: minmax(0, 1fr); } .bar-col { width: 90px; } }
</style>
