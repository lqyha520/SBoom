<script setup lang="ts">
import { ref } from 'vue'
import { onPageScroll, onLoad, onShow, onHide, onPullDownRefresh, onReachBottom, onShareAppMessage } from '@dcloudio/uni-app'
import CatalogList from '../../components/CatalogList.vue'
import { shareCard } from '../../services/return-route'
const id = ref('missing'), list = ref<InstanceType<typeof CatalogList> | null>(null)
onLoad(options => { id.value = /^[a-zA-Z0-9_-]{1,64}$/.test(String(options?.id || '')) ? String(options!.id) : 'missing' })
onShow(() => list.value?.activate()); onHide(() => list.value?.deactivate())
onPullDownRefresh(() => list.value?.refresh()); onReachBottom(() => list.value?.loadMore())
onShareAppMessage(() => shareCard('topic', id.value, list.value?.shareTitle))
onPageScroll(event => list.value?.rememberScroll(event.scrollTop))
</script>
<template><CatalogList ref="list" :topic-id="id" /></template>
