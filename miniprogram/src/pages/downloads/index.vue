<script setup lang="ts">
import { captureScroll } from '../../services/page-lifecycle'
import { ref } from 'vue'
import { onShareAppMessage, onHide, onPullDownRefresh, onReachBottom, onShow, onUnload } from '@dcloudio/uni-app'
import { catalogShare } from '../../services/return-route'
import CatalogList from '../../components/CatalogList.vue'
const list = ref<InstanceType<typeof CatalogList> | null>(null)
onShow(() => { void list.value?.activate() })
onHide(() => { captureScroll(top => list.value?.rememberScroll(top)); list.value?.deactivate() })
onUnload(() => list.value?.deactivate())
onPullDownRefresh(() => { void list.value?.reload() })
onReachBottom(() => { void list.value?.loadMore() })
onShareAppMessage(event => catalogShare(event))
</script>

<template><CatalogList ref="list" view="downloads" /></template>
