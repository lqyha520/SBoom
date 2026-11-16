<script setup lang="ts">
import { permissionDirective as vPermission } from '../permissions'
import { canAdmin } from '../permissions'
import XhsGettingStarted from './XhsGettingStarted.vue'
import XhsTodayTasks from './XhsTodayTasks.vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { xhsContentTabs } from '../admin-navigation'
import { navigateAdmin, type AdminTab } from '../navigation'

const props = defineProps<{ active: AdminTab; userId: number }>()
const nav = ref<HTMLElement | null>(null)
const stage = computed(() => xhsContentTabs.findIndex(item => item.id === props.active))
const descriptions = ['寻找值得制作的读者问题', '把灵感整理为具体计划', '制作并复核原创练习资料', '准备文案、封面和内页', '安排发布，完成发布前检查']
function openStage(tab: AdminTab) { if (tab !== props.active) navigateAdmin(tab, {}) }
function showActiveStage() {
  const container = nav.value, button = container?.querySelector<HTMLElement>('[aria-current="page"]')
  if (!container || !button) return
  const bounds = container.getBoundingClientRect(), active = button.getBoundingClientRect()
  if (active.right > bounds.right) container.scrollLeft += active.right - bounds.right + 8
  else if (active.left < bounds.left) container.scrollLeft -= bounds.left - active.left + 8
}
watch(() => props.active, async () => {
  await nextTick()
  showActiveStage()
}, { immediate: true })
onMounted(() => window.addEventListener('resize', showActiveStage))
onBeforeUnmount(() => window.removeEventListener('resize', showActiveStage))
</script>

<template>
  <div class="xhs-content-navigation">
    <div class="workbench-heading"><div><span class="workbench-eyebrow">小红书 · 内容创作</span><h1>内容工作台</h1><p>{{ descriptions[stage] }}</p></div><div class="content-tools"><UButton v-permission="'xhsPublishing:create'" v-if="canAdmin('xhsPublishing', 'create')" label="发图文" icon="i-lucide-image-plus" size="sm" @click="navigateAdmin('xhsPublishing',{new:'1'})" /><XhsTodayTasks v-if="['xhsMaterials', 'xhsDrafts', 'xhsPublishing', 'xhsAnalytics'].every(id => canAdmin(id))" /><XhsGettingStarted v-if="['xhsIdeas', 'xhsMaterials', 'xhsDrafts', 'xhsPublishing'].every(id => canAdmin(id, 'create'))" :user-id="userId" /></div></div>
    <nav ref="nav" aria-label="内容制作阶段">
      <button v-for="(item, index) in xhsContentTabs.filter(item => canAdmin(item.id))" :key="item.id" type="button"
        :aria-current="active === item.id ? 'page' : undefined"
        :title="`打开${item.label}列表`" @click="openStage(item.id)">
        <span class="stage-number" aria-hidden="true">{{ index + 1 }}</span><UIcon :name="item.icon" class="size-4" /><span>{{ item.label }}</span>
      </button>
    </nav>
    <p class="workflow-hint">阶段入口查看全部内容；继续当前内容请用编辑页的下一步。</p>
  </div>
</template>

<style scoped>
.xhs-content-navigation { min-width:0;max-width:1440px;margin:0 auto 20px;padding:20px 22px 12px;border:1px solid #dce8e0;border-radius:16px;background:linear-gradient(110deg,#fff,#f3f9f5); }
.workbench-heading { display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:18px; }
.workbench-eyebrow { display:block;color:#5a7b68;font-size:11px;font-weight:600;letter-spacing:.06em;margin-bottom:6px; }
h1 { margin:0;color:#203c30;font-size:22px;font-weight:700; }
.workbench-heading p { margin:6px 0 0;color:#728679;font-size:12px; }
.content-tools { display:flex;gap:8px;flex-wrap:wrap;flex-shrink:0; }
nav { display:flex;gap:6px;min-width:0;overflow-x:auto;padding:3px;border-top:1px solid #e1ece5;padding-top:12px;scrollbar-width:thin; }
nav button { display:flex;align-items:center;justify-content:center;gap:8px;flex:1;min-height:42px;padding:10px 14px;border-radius:9px;color:var(--ui-text-muted);font-size:13px;white-space:nowrap;cursor:pointer; }
.stage-number { display:grid;place-items:center;width:20px;height:20px;background:#eef2ef;border-radius:50%;font-size:10px;color:#73887a; }
nav button[aria-current="page"] .stage-number { color:#fff;background:#318764; }
nav button:hover { background:var(--ui-bg-muted);color:var(--ui-text); }
nav button[aria-current="page"] { background:#e0f2e9;color:#087955;font-weight:600; }
nav button:focus-visible { outline:2px solid var(--ui-primary);outline-offset:1px; }
@media(max-width:1100px) { nav button { flex:none; }.xhs-content-navigation { padding:18px 16px 12px; } }
@media(max-width:800px) { .xhs-content-navigation { margin-bottom:14px;padding:16px 12px 10px; }.workbench-heading { flex-wrap:wrap;gap:14px; } nav button { min-height:44px;padding:10px 12px; }.stage-number { display:none; }.content-tools { flex-shrink:1; } }
</style>
