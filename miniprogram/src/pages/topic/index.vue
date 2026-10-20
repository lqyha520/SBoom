<script setup lang="ts">
import { captureScroll } from '../../services/page-lifecycle'
import { ref } from 'vue'
import { onLoad, onShow, onHide, onPullDownRefresh, onReachBottom, onShareAppMessage, onShareTimeline } from '@dcloudio/uni-app'
import CatalogList from '../../components/CatalogList.vue'
import { shareCard, catalogShare, shareTimeline } from '../../services/return-route'
const id = ref('missing'), list = ref<InstanceType<typeof CatalogList> | null>(null)
onLoad(options => { id.value = /^[a-zA-Z0-9_-]{1,64}$/.test(String(options?.id || '')) ? String(options!.id) : 'missing' })
onShow(() => list.value?.activate()); onHide(() => { captureScroll(top => list.value?.rememberScroll(top)); list.value?.deactivate() })
onPullDownRefresh(() => list.value?.reload()); onReachBottom(() => list.value?.loadMore())
onShareAppMessage(event => catalogShare(event, shareCard('topic', id.value, list.value?.shareTitle)))
onShareTimeline(() => shareTimeline(shareCard('topic', id.value, list.value?.shareTitle)))
</script>
<template><CatalogList ref="list" :topic-id="id" /></template>
