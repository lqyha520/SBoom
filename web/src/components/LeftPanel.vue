<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useExamStore } from '../stores/exam'
import { DIFF_NAME } from '../constants'
import type { Difficulty } from '../types'
import { textbookGroups } from '../knowledge-points'

const store = useExamStore()
const knowledgeSearch = ref('')
const expandedGroups = ref<Record<string, boolean>>({ '上册': true, '知识范围': true })
watch(() => [store.grade, store.subject], () => {
  knowledgeSearch.value = ''
  expandedGroups.value = { '上册': true, '知识范围': true }
})
const grades = computed(() => Object.keys(store.available))
const knowledgeGroups = computed(() => textbookGroups(store.scope))
const filteredGroups = computed(() => {
  const query = knowledgeSearch.value.trim().toLocaleLowerCase()
  return knowledgeGroups.value.map(group => ({ ...group, items: group.items.filter(item => !query || item.label.toLocaleLowerCase().includes(query)) })).filter(group => group.items.length)
})
const names: Record<string, string> = { banner: '卷头横幅', title: '标题', subline: '副标题', inforow: '姓名班级栏', notice: '注意事项', reward: '奖励区', footer: '页脚' }
</script>

<template>
  <section class="workspace-panel conditions-panel" aria-labelledby="conditions-title">
    <div class="panel-heading">
      <h2 id="conditions-title"><UIcon name="i-lucide-sliders-horizontal" class="size-4" />出题条件</h2>
      <UBadge color="neutral" variant="soft" size="xs">01</UBadge>
    </div>
    <fieldset class="panel-scroll" :disabled="store.generating">
      <div class="field-section">
        <div class="field-label" id="grade-label">年级</div>
        <div v-if="store.availableLoading" class="grid grid-cols-3 gap-2" role="status" aria-label="正在加载年级"><USkeleton v-for="i in 9" :key="i" class="h-8 rounded-md" /></div>
        <UAlert v-else-if="store.availableError" color="error" variant="soft" :title="store.availableError" :actions="[{ label: '重试', onClick: () => store.init() }]" />
        <div v-else class="selection-grid" role="group" aria-labelledby="grade-label">
          <button v-for="g in grades" :key="g" class="selection-button" :class="{ selected: store.grade === g }" :aria-pressed="store.grade === g" :aria-label="g" @click="store.selectGrade(g)">{{ g.replace('小学', '').replace('初中', '初') }}</button>
        </div>
      </div>
      <div class="field-section">
        <div class="field-label" id="subject-label">科目</div>
        <p v-if="!store.grade" class="text-xs text-muted">尚未选择年级</p>
        <p v-else-if="!store.subjects.length" class="text-xs text-muted">该年级暂无可用科目</p>
        <div v-else class="selection-grid subjects" role="group" aria-labelledby="subject-label">
          <button v-for="s in store.subjects" :key="s" class="selection-button" :class="{ selected: store.subject === s }" :aria-pressed="store.subject === s" @click="store.selectSubject(s)">{{ s }}</button>
        </div>
      </div>
      <div class="field-section">
        <div class="field-label" id="difficulty-label">难度</div>
        <div class="segment-control" role="group" aria-labelledby="difficulty-label">
          <button v-for="(name, d) in DIFF_NAME" :key="d" :class="{ selected: store.difficulty === d }" :aria-pressed="store.difficulty === d" @click="store.difficulty = d as Difficulty">{{ name }}</button>
        </div>
      </div>
      <div class="field-section">
        <UFormField label="知识点" name="keyword">
          <UTextarea :model-value="store.keyword" :rows="2" :maxrows="4" autoresize maxlength="100" placeholder="例如：分数初步认识" :disabled="!store.subject" @update:model-value="store.setKeyword(String($event))" />
        </UFormField>
        <p v-for="book in store.scope?.books || []" :key="book.id" class="section-caption mt-2">
          <a :href="book.source_url" target="_blank" rel="noopener noreferrer">{{ book.series }} · {{ book.semester }}</a>
        </p>
        <div v-if="store.scopeLoading" class="mt-4 space-y-3" role="status" aria-label="正在加载知识点"><USkeleton v-for="i in 5" :key="i" class="h-4 w-full" /></div>
        <template v-else-if="store.grade && store.subject">
          <div v-if="knowledgeGroups.length" class="knowledge-search">
            <UInput v-model="knowledgeSearch" icon="i-lucide-search" placeholder="查找知识点" aria-label="查找知识点" />
            <p class="section-caption" role="status">已选 {{ store.selectedTags.length }} 个知识点</p>
            <div v-if="store.selectedTags.length" class="knowledge-selected">
              <UButton v-for="tag in store.selectedTags" :key="tag" :label="tag" trailing-icon="i-lucide-x" :aria-label="'取消选择：' + tag" variant="soft" size="xs" @click="store.toggleTag(tag)" />
            </div>
          </div>
          <UCollapsible v-for="group in filteredGroups" :key="group.label" :open="!!knowledgeSearch.trim() || !!expandedGroups[group.label]" :disabled="!!knowledgeSearch.trim()" @update:open="expandedGroups[group.label] = $event">
            <button class="knowledge-group-toggle">
              <span>{{ group.label }} · {{ group.items.length }} 项</span><UIcon :name="knowledgeSearch.trim() || expandedGroups[group.label] ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'" class="size-3.5" />
            </button>
            <template #content><div class="knowledge-list" :aria-label="group.label">
              <button v-for="item in group.items" :key="item.value" class="knowledge-option" :class="{ selected: store.selectedTags.includes(item.value) }" :aria-pressed="store.selectedTags.includes(item.value)" @click="store.toggleTag(item.value)">
                <span aria-hidden="true"><UIcon v-if="store.selectedTags.includes(item.value)" name="i-lucide-check" class="size-3" /></span>
                <span>{{ item.label }}</span>
              </button>
            </div></template>
          </UCollapsible>
          <p v-if="knowledgeGroups.length && !filteredGroups.length" class="section-caption">没有匹配的知识点，试试更短的关键词</p>
          <p v-if="!knowledgeGroups.length" class="section-caption">该教材目录尚未核实</p>
        </template>
      </div>
      <div v-if="store.hiddenElements.length" class="field-section border-t border-default pt-4">
        <div class="field-label">已隐藏的卷面元素</div>
        <div class="flex flex-wrap gap-2">
          <UButton v-for="key in store.hiddenElements" :key="key" icon="i-lucide-undo-2" color="neutral" variant="outline" size="xs" @click="store.toggleHiddenElement(key)">{{ names[key] || key }}</UButton>
        </div>
      </div>
    </fieldset>
  </section>
</template>

<style scoped>
.knowledge-search { margin-top: 12px; }
.knowledge-selected { display: flex; flex-wrap: wrap; gap: 6px; }
.knowledge-selected button { white-space: normal; text-align: left; }
.knowledge-group-toggle { display: flex; align-items: center; justify-content: space-between; width: 100%; min-height: 40px; margin-top: 8px; padding: 6px 0; font-size: 12px; color: var(--ui-text-toned); }
</style>
