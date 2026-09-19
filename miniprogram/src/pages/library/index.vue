<script setup lang="ts">
import { ref } from 'vue'
import { onShareAppMessage, onPageScroll, onHide, onPullDownRefresh, onReachBottom, onShow, onUnload } from '@dcloudio/uni-app'
import { catalogShare } from '../../services/return-route'
import CatalogList from '../../components/CatalogList.vue'
const list = ref<InstanceType<typeof CatalogList> | null>(null)
onShow(() => { void list.value?.activate() })
onHide(() => list.value?.deactivate())
onUnload(() => list.value?.deactivate())
onPullDownRefresh(() => { void list.value?.reload() })
onReachBottom(() => { void list.value?.loadMore() })
onPageScroll(event => list.value?.rememberScroll(event.scrollTop))
onShareAppMessage(event => catalogShare(event))
</script>

<template><CatalogList ref="list" /></template>
