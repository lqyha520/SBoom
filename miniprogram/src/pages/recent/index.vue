<script setup lang="ts">
import { ref } from 'vue'
import { onShow, onHide, onUnload, onPullDownRefresh, onReachBottom } from '@dcloudio/uni-app'
import CatalogList from '../../components/CatalogList.vue'
const list = ref<InstanceType<typeof CatalogList> | null>(null)
onShow(() => { void list.value?.activate() })
onHide(() => list.value?.deactivate())
onUnload(() => list.value?.deactivate())
onPullDownRefresh(() => { void list.value?.refresh() })
onReachBottom(() => { void list.value?.loadMore() })
</script>
<template><CatalogList ref="list" view="recent" /></template>
