<script setup lang="ts">
import { canAdmin, permissionDirective as vPermission } from '../permissions'
import { adminRoute } from '../navigation'
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted } from 'vue'
import XhsDraftRecovery from './XhsDraftRecovery.vue'
import type { DraftBackupController } from '../xhs-draft-backup'
import type { BaseData, WorkflowRecord } from '../xhs-workflow'
import { formatWorkflowDate, workflowStatus } from '../xhs-workflow'
import { workflowIcons, workflowSummary } from '../xhs-workflow-presentation'

const props = defineProps<{ backup?: DraftBackupController; title: string; description: string; editing: boolean; loading: boolean; busy: boolean; error: string; notice: string; dirty: boolean; items: WorkflowRecord<BaseData>[]; total: number; page: number; statuses: string[]; createLabel?: string; saveDisabled?: boolean; saveHint?: string }>()
const q = defineModel<string>('q', { default: '' }), filter = defineModel<string>('filter', { default: '' })
const emit = defineEmits<{ open: [id?: string]; back: []; save: []; search: []; reset: []; page: [value: number] }>()
const selectedFilter = computed({ get: () => filter.value || '__all__', set: value => { filter.value = value === '__all__' ? '' : value } })
const saveAction = computed(() => new URLSearchParams(adminRoute.query).has('id') ? 'update' : 'create')
const canSave = computed(() => canAdmin(adminRoute.tab, saveAction.value) && !props.saveDisabled && !props.busy && !props.loading && !props.backup?.recovery.value)
const filtered = computed(() => !!q.value.trim() || !!filter.value)
function shortcut(event: KeyboardEvent) {
  if (!props.editing || !(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 's' || event.altKey || event.isComposing) return
  if (document.querySelector('[role="dialog"], [role="alertdialog"]')) return
  event.preventDefault()
  if (canSave.value && props.dirty && !event.repeat) emit('save')
}
function listen() { window.addEventListener('keydown', shortcut) }
function stop() { window.removeEventListener('keydown', shortcut) }
onMounted(listen); onActivated(listen); onDeactivated(stop); onBeforeUnmount(stop)
</script>

<template>
  <section class="admin-section xhs-workflow" :aria-label="title" :aria-busy="loading">
    <header class="workflow-heading" :class="{ 'workflow-heading-editing': editing }">
      <div class="workflow-heading-copy"><span class="workflow-eyebrow">{{ editing ? '内容编辑' : '内容管理' }}</span><h2>{{ title }}</h2><p>{{ description }}</p></div>
      <div class="workflow-actions">
        <template v-if="editing">
          <span class="workflow-save-state" :class="{ 'is-dirty': dirty }" role="status"><span></span>{{ busy ? '正在保存…' : saveDisabled && saveHint ? saveHint : dirty ? '有未保存的修改' : '可继续编辑' }}</span>
          <UButton label="返回列表" icon="i-lucide-arrow-left" color="neutral" variant="outline" :disabled="busy" @click="emit('back')" />
          <UButton v-permission="adminRoute.tab + ':' + saveAction" label="保存" icon="i-lucide-check" title="保存（Ctrl / ⌘ + S）" :loading="busy" :disabled="!canSave" @click="emit('save')" />
        </template>
        <UButton v-else v-permission="adminRoute.tab + ':create'" :label="createLabel || '新建'" icon="i-lucide-plus" :disabled="busy" @click="emit('open')" />
      </div>
    </header>
    <UAlert v-if="error" :title="error" color="error" role="alert" class="mb-4" />
    <UAlert v-if="notice" :title="notice" color="success" role="status" class="mb-4" />
    <template v-if="!editing">
      <slot name="list-tools" />
      <slot name="list">
        <form class="workflow-filters" role="search" @submit.prevent="emit('search')">
          <UInput v-model="q" class="workflow-search" icon="i-lucide-search" placeholder="搜索标题，按 Enter 查找" aria-label="搜索标题" maxlength="120" />
          <USelect v-model="selectedFilter" :items="[{ label: '全部进行中', value: '__all__' }, ...statuses.map(value => ({ value, label: workflowStatus(value) }))]" aria-label="筛选状态" />
          <UButton label="搜索" type="submit" color="neutral" variant="outline" :loading="loading" />
          <UButton label="清空筛选" variant="ghost" :disabled="!filtered" @click="emit('reset')" />
        </form>
        <slot name="guide" />
        <div class="workflow-list-meta" role="status"><span>{{ loading ? '正在读取内容…' : '共 ' + total + ' 条内容' }}</span><span v-if="total > 0 && !loading">第 {{ page }} / {{ Math.max(1, Math.ceil(total / 20)) }} 页</span></div>
        <div class="workflow-list" :inert="loading">
          <div v-if="loading" class="workflow-skeletons" aria-hidden="true"><div v-for="index in 3" :key="index" class="workflow-skeleton"><span></span><div><span></span><span></span></div></div></div>
          <template v-else>
            <button v-for="item in items" :key="item.id" type="button" class="workflow-list-item" @click="emit('open', item.id)">
              <span class="workflow-item-icon" aria-hidden="true"><UIcon :name="workflowIcons[item.kind]" class="size-5" /></span>
              <span class="workflow-item-copy"><strong>{{ item.title }}</strong><span class="workflow-item-summary">{{ workflowSummary(item) }}</span><small>更新于 {{ formatWorkflowDate(item.updated_at) }}</small></span>
              <span class="workflow-status" :data-status="item.status">{{ workflowStatus(item.status) }}</span>
              <UIcon name="i-lucide-chevron-right" class="size-4 workflow-item-arrow" aria-hidden="true" />
            </button>
          </template>
        </div>
        <div v-if="!loading && !items.length" class="workflow-empty-state">
          <UIcon :name="error ? 'i-lucide-cloud-off' : filtered ? 'i-lucide-search' : 'i-lucide-notebook-pen'" class="size-8" aria-hidden="true" />
          <h3>{{ error ? '内容暂时未能加载' : filtered ? '没有找到匹配的内容' : '从第一条内容开始' }}</h3>
          <p>{{ error ? '可以重新读取，继续处理你的内容。' : filtered ? '试试其他标题关键词，或清空状态筛选。' : '点击新建，也可以从上一个制作阶段带入已有内容。' }}</p>
          <UButton v-if="error" label="重新加载" variant="outline" icon="i-lucide-refresh-cw" @click="emit('search')" />
          <UButton v-else-if="filtered" label="清空筛选" variant="outline" @click="emit('reset')" />
          <UButton v-else v-permission="adminRoute.tab + ':create'" :label="createLabel || '新建'" icon="i-lucide-plus" @click="emit('open')" />
        </div>
        <div v-if="total > 20" class="workflow-pagination"><UPagination :page="page" :total="total" :items-per-page="20" :disabled="loading" @update:page="emit('page', $event)" /></div>
      </slot>
    </template>
    <div v-else-if="loading" class="workflow-editor-loading" role="status"><UIcon name="i-lucide-loader-circle" class="size-5" />正在读取编辑内容…</div>
    <div v-else class="workflow-editor" :inert="busy"><XhsDraftRecovery v-if="backup" :backup="backup" /><div :inert="!!backup?.recovery.value"><slot /></div></div>
  </section>
</template>

<style src="../xhs-workflow.css"></style>
