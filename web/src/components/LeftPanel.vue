<script setup lang="ts">
import { computed } from 'vue'
import { useExamStore } from '../stores/exam'
import { DIFF_NAME } from '../constants'
import type { Difficulty } from '../types'

const store = useExamStore()
const grades = computed(() => Object.keys(store.available))
const knowledgeGroups = computed(() => {
  if (!store.scope) return []
  const groups: { label: string; items: { label: string; value: string }[] }[] = []
  for (const semester of ['上册', '下册'] as const) {
    const items = store.scope.semesters?.[semester]
    if (items?.length) groups.push({ label: semester, items: items.map(k => ({ label: k, value: semester + '·' + k })) })
  }
  const semesterItems = new Set(groups.flatMap(g => g.items.map(i => i.label)))
  const remaining = store.scope.allowed.filter(k => !semesterItems.has(k))
  if (remaining.length) groups.push({ label: groups.length ? '其他知识点' : '知识范围', items: remaining.map(k => ({ label: k, value: k })) })
  return groups
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
        <div v-if="store.scopeLoading" class="mt-4 space-y-3" role="status" aria-label="正在加载知识点"><USkeleton v-for="i in 5" :key="i" class="h-4 w-full" /></div>
        <template v-else-if="store.grade && store.subject">
          <div v-for="group in knowledgeGroups" :key="group.label">
            <p class="section-caption">{{ group.label }}</p>
            <div class="knowledge-list" :aria-label="group.label">
              <button v-for="item in group.items" :key="item.value" class="knowledge-option" :class="{ selected: store.selectedTags.includes(item.value) }" :aria-pressed="store.selectedTags.includes(item.value)" @click="store.toggleTag(item.value)">
                <span aria-hidden="true"><UIcon v-if="store.selectedTags.includes(item.value)" name="i-lucide-check" class="size-3" /></span>
                <span>{{ item.label }}</span>
              </button>
            </div>
          </div>
          <p v-if="!knowledgeGroups.length" class="section-caption">暂无知识点清单</p>
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
