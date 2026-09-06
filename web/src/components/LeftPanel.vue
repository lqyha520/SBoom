<script setup lang="ts">
import { computed } from 'vue'
import { useExamStore } from '../stores/exam'
import { DIFF_NAME } from '../constants'
import type { Difficulty } from '../types'

const store = useExamStore()

const grades = computed(() => Object.keys(store.available))
</script>

<template>
  <div class="card left-panel">
    <div class="card-body left-scroll">
      <!-- 难度 -->
      <div class="fgroup" style="margin-bottom: 16px;">
        <div class="fgroup-label">难度</div>
        <div class="seg">
          <button
            v-for="(name, d) in DIFF_NAME"
            :key="d"
            :class="{ on: store.difficulty === d }"
            @click="store.difficulty = d as Difficulty"
          >{{ name }}</button>
        </div>
      </div>

      <!-- 年级 -->
      <div class="fgroup" style="margin-bottom: 16px;">
        <div class="fgroup-label">年级</div>
        <div v-if="store.availableLoading" class="scope-empty">加载中…</div>
        <div v-else-if="store.availableError" class="scope-empty" style="color: var(--red);">{{ store.availableError }}</div>
        <div v-else class="pill-row">
          <button
            v-for="g in grades"
            :key="g"
            class="pill"
            :class="{ on: store.grade === g }"
            @click="store.selectGrade(g)"
          >{{ g.replace('小学', '').replace('初中', '初') }}</button>
        </div>
      </div>

      <!-- 科目 -->
      <div class="fgroup" style="margin-bottom: 16px;">
        <div class="fgroup-label">科目</div>
        <div v-if="!store.grade" class="scope-empty">请先选择年级</div>
        <div v-else-if="!store.subjects.length" class="scope-empty">该年级暂无可选科目</div>
        <div v-else class="pill-row">
          <button
            v-for="s in store.subjects"
            :key="s"
            class="pill"
            :class="{ on: store.subject === s }"
            @click="store.selectSubject(s)"
          >{{ s }}</button>
        </div>
      </div>

      <!-- 知识点 -->
      <div class="fgroup" style="margin-bottom: 0;">
        <div class="fgroup-label">
          知识点
          <span v-if="store.grade && store.subject" style="font-weight: 500; color: var(--primary); font-size: 12px;">{{ store.grade }}·{{ store.subject }}</span>
          <span v-else style="font-weight: 400; color: var(--ink3); font-size: 11px;">选好年级科目后显示</span>
        </div>
        <template v-if="store.grade && store.subject">
          <input
            class="input"
            maxlength="100"
            placeholder="手动输入或点选下方标签"
            :value="store.keyword"
            @input="store.setKeyword(($event.target as HTMLInputElement).value)"
          >
          <div class="scope-box">
            <div v-if="store.scopeLoading" class="scope-empty">加载中…</div>
            <template v-else-if="store.scope">
              <div v-if="store.scope.semesters?.['上册']">
                <div class="semester-label">上册</div>
                <span
                  v-for="k in store.scope.semesters['上册']"
                  :key="'up' + k"
                  class="tag"
                  :class="{ on: store.selectedTags.includes('上册·' + k) }"
                  @click="store.toggleTag('上册·' + k)"
                >{{ k }}（上）</span>
              </div>
              <div v-if="store.scope.semesters?.['下册']">
                <div class="semester-label">下册</div>
                <span
                  v-for="k in store.scope.semesters['下册']"
                  :key="'down' + k"
                  class="tag"
                  :class="{ on: store.selectedTags.includes('下册·' + k) }"
                  @click="store.toggleTag('下册·' + k)"
                >{{ k }}（下）</span>
              </div>
              <span
                v-for="k in store.scope.allowed"
                :key="k"
                class="tag"
                :class="{ on: store.selectedTags.includes(k) }"
                @click="store.toggleTag(k)"
              >{{ k }}</span>
            </template>
            <div v-else class="scope-empty">暂无知识点清单，可直接输入关键词</div>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.scope-box { margin-top: 8px; }
</style>
