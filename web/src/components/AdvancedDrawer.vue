<script setup lang="ts">
import { useExamStore } from '../stores/exam'
import type { PaperStyle } from '../types'

defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const store = useExamStore()

const BG_STYLES: { v: PaperStyle['bg']; label: string }[] = [
  { v: 'none', label: '无' },
  { v: 'dots', label: '彩色圆点' },
  { v: 'grid', label: '浅格线' },
  { v: 'stars', label: '小星星' },
  { v: 'clouds', label: '云朵' },
  { v: 'rainbow', label: '彩虹' },
]
const FRAMES: { v: PaperStyle['frame']; label: string }[] = [
  { v: 'none', label: '无边框' },
  { v: 'rainbow', label: '彩虹花边' },
  { v: 'stars', label: '星星边框' },
  { v: 'crayon', label: '蜡笔粉边' },
  { v: 'dots', label: '蓝色圆点' },
]
</script>

<template>
  <teleport to="body">
    <div class="drawer-mask" :class="{ open }" v-show="open" @click="emit('close')"></div>
    <div class="drawer" :class="{ open }">
      <div class="drawer-head">
        <h3>高级设置</h3>
        <button class="x-btn" @click="emit('close')">✕</button>
      </div>
      <div class="drawer-body">
        <!-- 标题字号 -->
        <div class="fgroup">
          <div class="fgroup-label">标题字号</div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <input
              type="range" min="60" max="200" step="5"
              :value="Math.round((store.style.titleScale ?? 1) * 100)"
              @input="store.setStyle({ titleScale: parseInt(($event.target as HTMLInputElement).value) / 100 })"
              style="flex: 1; accent-color: var(--primary);"
              title="标题字号缩放"
            >
            <span style="font-size: 12px; color: var(--ink3); width: 40px;">{{ Math.round((store.style.titleScale ?? 1) * 100) }}%</span>
          </div>
        </div>

        <!-- 一键风格 -->
        <div class="fgroup">
          <div class="fgroup-label">卷面风格</div>
          <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px;">
            <button class="tpl-card" @click="store.applyStylePreset('standard')"><div class="t">标准</div><div class="d">白底传统卷</div></button>
            <button class="tpl-card" @click="store.applyStylePreset('colorful')"><div class="t">彩色</div><div class="d">背景+彩色标题</div></button>
            <button class="tpl-card" @click="store.applyStylePreset('fun')"><div class="t">童趣</div><div class="d">花边+奖励区</div></button>
          </div>
        </div>

        <!-- 背景图案 -->
        <div class="fgroup">
          <div class="fgroup-label">背景图案</div>
          <select class="input" :value="store.style.bg" @change="store.setStyle({ bg: ($event.target as HTMLSelectElement).value as any })">
            <option v-for="b in BG_STYLES" :key="b.v" :value="b.v">{{ b.label }}</option>
          </select>
          <div v-if="store.style.bg !== 'none'" style="display: flex; align-items: center; gap: 8px; margin-top: 8px;">
            <input type="range" min="10" max="100" :value="store.style.bgOpacity" @input="store.setStyle({ bgOpacity: parseInt(($event.target as HTMLInputElement).value) })" style="flex: 1; accent-color: var(--primary);">
            <span style="font-size: 12px; color: var(--ink3); width: 36px;">{{ store.style.bgOpacity }}%</span>
          </div>
          <label style="display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--ink2); margin-top: 6px; cursor: pointer;">
            <input type="checkbox" :checked="store.style.banner" @change="store.setStyle({ banner: ($event.target as HTMLInputElement).checked })"> 标题横幅
          </label>
          <label style="display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--ink2); margin-top: 4px; cursor: pointer;">
            <input type="checkbox" :checked="store.style.secColor" @change="store.setStyle({ secColor: ($event.target as HTMLInputElement).checked })"> 彩色大题标题
          </label>
        </div>

        <!-- 童趣装饰 -->
        <div class="fgroup">
          <div class="fgroup-label">童趣装饰</div>
          <select class="input" :value="store.style.frame" @change="store.setStyle({ frame: ($event.target as HTMLSelectElement).value as any })">
            <option v-for="f in FRAMES" :key="f.v" :value="f.v">{{ f.label }}</option>
          </select>
          <label style="display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--ink2); margin-top: 8px; cursor: pointer;">
            <input type="checkbox" :checked="store.style.encourage" @change="store.setStyle({ encourage: ($event.target as HTMLInputElement).checked })"> 大题鼓励语
          </label>
          <label style="display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--ink2); margin-top: 4px; cursor: pointer;">
            <input type="checkbox" :checked="store.style.reward" @change="store.setStyle({ reward: ($event.target as HTMLInputElement).checked })"> 卷尾星星奖励区
          </label>
          <div style="margin-top: 8px; font-size: 12px; color: var(--ink2);">
            大字号：
            <button class="btn mini" :style="store.style.kidFont === 'auto' ? 'border-color: var(--primary); color: var(--primary);' : ''" @click="store.setStyle({ kidFont: 'auto' })">自动</button>
            <button class="btn mini" :style="store.style.kidFont === 'on' ? 'border-color: var(--primary); color: var(--primary);' : ''" @click="store.setStyle({ kidFont: 'on' })">开</button>
            <button class="btn mini" :style="store.style.kidFont === 'off' ? 'border-color: var(--primary); color: var(--primary);' : ''" @click="store.setStyle({ kidFont: 'off' })">关</button>
            <span style="color: var(--ink3); margin-left: 6px;">自动 = 一、二年级开</span>
          </div>
        </div>

        <!-- 导出 -->
        <div class="fgroup">
          <div class="fgroup-label">导出</div>
          <label style="display: flex; align-items: center; gap: 4px; font-size: 12px; color: var(--ink2); cursor: pointer;">
            <input type="checkbox" :checked="store.style.exportBg" @change="store.setStyle({ exportBg: ($event.target as HTMLInputElement).checked })">
            导出保留彩色（默认白底省墨）
          </label>
        </div>

        <!-- 自定义题型管理 -->
        <div class="fgroup" v-if="store.customTypes.length">
          <div class="fgroup-label">自定义题型</div>
          <div v-for="t in store.customTypes" :key="t.id" style="display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid var(--border);">
            <b style="font-size: 13px;">{{ t.name }}</b>
            <span style="font-size: 12px; color: var(--ink3); flex: 1;">基于「{{ t.baseType }}」· 默认 {{ t.defaultCount }} 题</span>
            <button class="btn mini danger" @click="store.removeCustomType(t.id)">删除</button>
          </div>
        </div>
      </div>
    </div>
  </teleport>
</template>
