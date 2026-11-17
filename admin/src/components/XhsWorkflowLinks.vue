<script setup lang="ts">
import { computed } from 'vue'
import { canAdmin } from '../permissions'
import { goWorkflow, workflowTabs, workflowLabels, type BaseData, type WorkflowRecord } from '../xhs-workflow'
const props = defineProps<{ record: WorkflowRecord<BaseData> | null; parent?: WorkflowRecord<BaseData> | null }>()
const visibleChildren = computed(() => props.record?.children?.filter(child => canAdmin(workflowTabs[child.kind])) || [])
</script>
<template><div v-if="parent || record?.children?.length" class="workflow-step"><div v-if="parent && canAdmin(workflowTabs[parent.kind])" class="workflow-actions"><span>关联{{ workflowLabels[parent.kind] }}：</span><UButton :label="parent.title" variant="link" @click="goWorkflow(parent.kind, parent.id)" /></div><div v-if="record?.children?.length" class="workflow-actions"><span>已创建的后续内容（点击继续编辑）：</span><UButton v-for="child in visibleChildren" :key="child.id" :label="`${workflowLabels[child.kind]} · ${child.title}`" variant="link" @click="goWorkflow(child.kind, child.id)" /></div></div></template>
