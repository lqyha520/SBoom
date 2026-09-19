<script setup lang="ts">
import type { PaperSummary } from '../types'
import { paperAccess } from '../presentation'

defineProps<{ paper: Pick<PaperSummary, 'required_view' | 'required_download' | 'download_mode'> }>()
</script>

<template>
  <view class="access-badge" :class="{ 'is-free': paper.required_view !== 'vip' && paper.required_download !== 'vip' }">
    <text>{{ paperAccess(paper) }}</text>
  </view>
</template>
