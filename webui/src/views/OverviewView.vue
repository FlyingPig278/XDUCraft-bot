<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { NAlert, NButton, NCard, NEmpty, NList, NListItem, NSkeleton, NSpace, NTag, useMessage } from 'naive-ui'
import { apiGet } from '../api/client'
import type { Overview } from '../api/types'
import { connectionState } from '../state'

const overview = ref<Overview | null>(null)
const loading = ref(false)
const message = useMessage()
async function load(): Promise<void> {
  loading.value = true
  try {
    overview.value = await apiGet<Overview>('/api/overview')
    connectionState.connectedBots = overview.value.bots.filter((bot) => bot.connected).length
    connectionState.restartRequired = overview.value.restart_required
  } catch (error) { message.error(error instanceof Error ? error.message : '读取概览失败') }
  finally { loading.value = false }
}
onMounted(load)
</script>

<template>
  <main class="page">
    <h1 class="page-heading">概览</h1><p class="page-subtitle">连接和插件状态，不包含聊天内容与运行日志。</p>
    <NAlert v-if="overview?.restart_required" type="warning" class="overview-alert">部署设置有待生效变更。请在合适时间手动重启机器人。</NAlert>
    <NSkeleton v-if="loading && !overview" text :repeat="6" />
    <div v-else-if="overview" class="card-grid">
      <NCard title="Bot 连接">
        <NEmpty v-if="!overview.bots.length" description="当前没有 Bot 连接" />
        <NList v-else><NListItem v-for="bot in overview.bots" :key="bot.bot_id"><NSpace justify="space-between"><span class="mono">{{ bot.bot_id }}</span><NTag :type="bot.connected ? 'success' : 'warning'">{{ bot.connected ? '已连接' : '未连接' }}</NTag></NSpace></NListItem></NList>
      </NCard>
      <NCard title="插件状态">
        <NList><NListItem v-for="plugin in overview.plugins" :key="plugin.id"><NSpace justify="space-between"><span>{{ plugin.name }}</span><NTag :type="plugin.loaded ? 'success' : 'error'">{{ plugin.loaded ? '已加载' : '不可用' }}</NTag></NSpace><div v-if="plugin.reason" class="muted">{{ plugin.reason }}</div></NListItem></NList>
      </NCard>
    </div>
    <NSpace class="overview-actions">
      <RouterLink to="/groups"><NButton type="primary">进入群管理</NButton></RouterLink>
      <RouterLink to="/settings"><NButton>打开全局设置</NButton></RouterLink>
      <NButton secondary @click="load">刷新</NButton>
    </NSpace>
  </main>
</template>
<style scoped>.overview-alert { margin-bottom:16px; }.overview-actions { margin-top:20px; }</style>
