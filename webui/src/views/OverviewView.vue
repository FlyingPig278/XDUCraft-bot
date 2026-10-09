<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { NAlert, NButton, NCard, NEmpty, NList, NListItem, NSkeleton, NSpace, NTag, useMessage } from 'naive-ui'
import { apiGet } from '../api/client'
import type { Overview } from '../api/types'
import { connectionState } from '../state'

const overview = ref<Overview | null>(null)
const loading = ref(false)
const errorText = ref('')
let generation = 0
onUnmounted(() => { generation++ })
const message = useMessage()
async function load(): Promise<void> {
  const token = ++generation
  errorText.value = ''
  loading.value = true
  try {
    const result = await apiGet<Overview>('/api/overview')
    if (token !== generation) return
    overview.value = result
    connectionState.connectedBots = result.bots.filter((bot) => bot.connected).length
    connectionState.restartRequired = result.restart_required
  } catch (error) {
    if (token !== generation) return
    errorText.value = error instanceof Error ? error.message : '读取概览失败'
    message.error(errorText.value)
  }
  finally { if (token === generation) loading.value = false }
}
onMounted(load)
</script>

<template>
  <main class="page">
    <h1 class="page-heading">运行概况</h1><p class="page-subtitle">这里只确认连接与可用性；业务管理从“选择群”开始。</p>
    <NAlert v-if="errorText" type="error" class="overview-alert">{{ errorText }}；{{ overview ? '下方保留的是上次成功读取的状态，不是本次实时结果。' : '当前运行状态尚未确认。' }}</NAlert>
    <NAlert v-if="overview?.restart_required" type="warning" class="overview-alert">有设置已经保存，需在合适时间手动重启机器人后生效。</NAlert>
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
      <RouterLink to="/groups"><NButton type="primary">选择群并管理插件</NButton></RouterLink>
      <RouterLink to="/settings"><NButton>全局与系统设置</NButton></RouterLink>
      <NButton secondary @click="load">刷新状态</NButton>
    </NSpace>
  </main>
</template>
<style scoped>.overview-alert { margin-bottom:16px; }.overview-actions { margin-top:20px; }</style>
