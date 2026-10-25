<script setup lang="ts">
import type { Topic } from '../services/experience'
import { openTopic } from '../services/growth'

defineProps<{ topic: Topic; index: number }>()
</script>

<template>
  <button class="topic-card collection-card" :class="'tone-' + (index % 3)" role="button" :aria-label="topic.title + '，' + topic.paper_count + ' 份练习'" hover-class="control-pressed" :hover-start-time="0" :hover-stay-time="80" @click="openTopic(topic.id)">
    <view class="topic-cover">
      <view class="cover-orbit" aria-hidden="true" />
      <image class="cover-notebook" src="/static/illustrations/notebook.png" mode="aspectFit" aria-hidden="true" />
      <text class="topic-kicker">学习专题 · {{ String(index + 1).padStart(2, '0') }}</text>
      <text class="topic-title">{{ topic.title }}</text>
    </view>
    <view class="topic-body">
      <text class="topic-description">{{ topic.description || '围绕一个主题，找到合适的练习' }}</text>
      <view class="topic-bottom"><text>{{ topic.paper_count }} 份练习</text><view class="topic-arrow"><wd-icon name="arrow-right" size="16px" /></view></view>
    </view>
  </button>
</template>

<style scoped>
.topic-card { --cover-bg:#e8f2ed;--cover-ink:#285743;--cover-accent:#cddfd3;display:block;flex:none;overflow:hidden;width:250px;max-width:calc(100vw - 64px);margin:0;padding:0;text-align:left;white-space:normal;border:1px solid var(--lc-card-line);border-radius:16px;background:var(--lc-surface);line-height:1.5;box-shadow:var(--lc-card-shadow-soft);transition:box-shadow .18s ease,transform .18s ease; }
.tone-1 { --cover-bg:#e8eff8;--cover-ink:#35577c;--cover-accent:#d4e0ef; }
.tone-2 { --cover-bg:#f8efdf;--cover-ink:#725733;--cover-accent:#edddc0; }
.topic-cover { position:relative;overflow:hidden;min-height:120px;padding:16px;background:linear-gradient(135deg,var(--cover-bg) 0%,var(--cover-bg) 62%,var(--cover-accent) 160%);color:var(--cover-ink); }
.cover-orbit { position:absolute;right:-20px;bottom:-34px;width:124px;height:124px;border-radius:50%;background:var(--cover-accent);opacity:.85; }
.cover-notebook { position:absolute;right:-6px;bottom:-8px;width:108px;height:108px; }
.topic-kicker { position:relative;display:block;font-size:11px;font-weight:600;line-height:1.5;letter-spacing:.4px;opacity:.72; }
.topic-title { position:relative;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;max-width:68%;margin-top:12px;font-size:18px;font-weight:650;line-height:1.4;overflow-wrap:anywhere; }
.topic-body { padding:13px 16px 12px; }
.topic-description { display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:38px;color:var(--lc-secondary);font-size:12.5px;line-height:1.5; }
.topic-bottom { display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:11px;color:var(--cover-ink);font-size:12px; }
.topic-arrow { display:flex;align-items:center;justify-content:center;width:30px;height:30px;border-radius:50%;background:var(--cover-bg);transition:background-color .18s ease,transform .18s ease; }
@media (hover:hover) { .topic-card:hover { box-shadow:var(--lc-card-shadow);transform:translateY(-1px); }.topic-card:hover .topic-arrow { background:var(--cover-accent);transform:translateX(1px); } }
@media (prefers-reduced-motion:reduce) { .topic-card,.topic-arrow { transition:none; }.topic-card:hover,.topic-card:hover .topic-arrow { transform:none; } }
</style>
