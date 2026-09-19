<script setup lang="ts">
import type { Topic } from '../services/experience'
import { openTopic } from '../services/growth'

defineProps<{ topic: Topic; index: number }>()
</script>

<template>
  <button class="topic-card collection-card" :class="'tone-' + (index % 3)" role="button" :aria-label="topic.title + '，' + topic.paper_count + ' 份练习'" hover-class="control-pressed" @click="openTopic(topic.id)">
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
.topic-card { --cover-bg:#e8f2ed;--cover-ink:#285743;--cover-accent:#cddfd3;display:block;flex:none;overflow:hidden;width:260px;max-width:calc(100vw - 56px);margin:0;padding:0;text-align:left;white-space:normal;border:1px solid var(--lc-card-line);border-radius:var(--lc-radius-card);background:var(--lc-surface);line-height:1.5;box-shadow:var(--lc-card-shadow-soft); }
.tone-1 { --cover-bg:#e8eff8;--cover-ink:#35577c;--cover-accent:#d4e0ef; }
.tone-2 { --cover-bg:#f8efdf;--cover-ink:#725733;--cover-accent:#edddc0; }
.topic-cover { position:relative;overflow:hidden;min-height:130px;padding:16px;background:var(--cover-bg);color:var(--cover-ink); }
.cover-orbit { position:absolute;right:-18px;bottom:-30px;width:130px;height:130px;border-radius:50%;background:var(--cover-accent); }
.cover-notebook { position:absolute;right:-7px;bottom:-7px;width:115px;height:115px; }
.topic-kicker { position:relative;display:block;font-size:12px;line-height:1.5; }
.topic-title { position:relative;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;max-width:65%;margin-top:14px;font-size:19px;font-weight:650;line-height:1.4;overflow-wrap:anywhere; }
.topic-body { padding:14px 16px 12px; }
.topic-description { display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:39px;color:var(--lc-secondary);font-size:13px;line-height:1.5; }
.topic-bottom { display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:12px;color:var(--cover-ink);font-size:12px; }
.topic-arrow { display:flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:50%;background:var(--cover-bg); }
@media (hover:hover) { .topic-card:hover { box-shadow:var(--lc-card-shadow); }.topic-card:hover .topic-arrow { background:var(--cover-accent); } }
</style>
