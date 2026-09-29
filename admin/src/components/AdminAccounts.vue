<script setup lang="ts">
import AccountManager from './AccountManager.vue'
import type { UserInfo } from '../api'
defineProps<{ user: UserInfo }>()
</script>
<template><AccountManager :user="user" role="admin" /></template>
