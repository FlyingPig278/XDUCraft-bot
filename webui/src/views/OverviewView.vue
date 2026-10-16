<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { NAlert, NButton, NCard, NEmpty, NIcon, NList, NListItem, NSkeleton, NSpace, NTag, useMessage } from 'naive-ui'
import { AppsOutline, ChatbubblesOutline, RefreshOutline } from '@vicons/ionicons5'
import { apiGet } from '../api/client'
import type { Overview, PluginsResponse } from '../api/types'
import { connectionState } from '../state'

const overview = ref<Overview | null>(null)
const catalog = ref<PluginsResponse | null>(null)
const loading = ref(false)
const errorText = ref('')
let generation = 0
onUnmounted(() => { generation++ })
const message = useMessage()
const serviceIds = computed(() => new Set((catalog.value?.plugins ?? []).filter(plugin => !plugin.managed).map(plugin => plugin.id)))
const services = computed(() => overview.value?.plugins.filter(plugin => serviceIds.value.has(plugin.id)) ?? [])

async function load(): Promise<void> {
  const token = ++generation
  errorText.value = ''
  loading.value = true
  const [overviewResult, catalogResult] = await Promise.allSettled([
    apiGet<Overview>('/api/overview'),
    apiGet<PluginsResponse>('/api/plugins')
  ])
  if (token !== generation) return
  if (overviewResult.status === 'fulfilled') {
    overview.value = overviewResult.value
    connectionState.connectedBots = overviewResult.value.bots.filter(bot => bot.connected).length
    connectionState.restartRequired = overviewResult.value.restart_required
  }
  if (catalogResult.status === 'fulfilled') catalog.value = catalogResult.value
  if (overviewResult.status === 'rejected' || catalogResult.status === 'rejected') {
    errorText.value = overviewResult.status === 'rejected'
      ? (overviewResult.reason instanceof Error ? overviewResult.reason.message : '读取系统状态失败')
      : '系统服务目录暂时不可用；为避免混入业务插件，暂不显示服务列表。'
    message.error(errorText.value)
  }
  loading.value = false
}
onMounted(load)
</script>

<template>
  <main class="page system-page">
    <div class="page-intro"><div><h1 class="page-heading">系统</h1><p class="page-subtitle">账号连接与基础服务</p></div><NButton secondary :loading="loading" @click="load"><template #icon><NIcon :component="RefreshOutline" /></template>刷新</NButton></div>
    <NAlert v-if="errorText" type="error" class="page-alert">{{ errorText }}；{{ overview ? '已保留上次成功读取的主机状态。' : '当前状态尚未确认。' }}</NAlert>
    <NAlert v-if="overview?.restart_required" type="warning" class="page-alert">有启动参数已经保存，需要在合适时间手动重启后生效。</NAlert>
    <NSkeleton v-if="loading && !overview" text :repeat="6" />
    <div v-else-if="overview" class="system-grid">
      <NCard title="Bot 连接">
        <NEmpty v-if="!overview.bots.length" description="当前没有 Bot 连接" />
        <NList v-else>
          <NListItem v-for="bot in overview.bots" :key="bot.bot_id">
            <NSpace justify="space-between" align="center">
              <div class="bot-info">
                <div class="bot-avatar">{{ Array.from(bot.nickname || 'Bot').slice(0, 1).join('') }}</div>
                <div>
                  <strong>{{ bot.nickname || '昵称暂不可用' }}</strong>
                  <span class="bot-id">QQ {{ bot.bot_id }}</span>
                </div>
              </div>
              <NTag :type="bot.connected ? 'success' : 'warning'" :bordered="false" round>{{ bot.connected ? '已连接' : '未连接' }}</NTag>
            </NSpace>
          </NListItem>
        </NList>
      </NCard>
      <NCard title="基础服务">
        <NEmpty v-if="catalog && !services.length" description="没有单独报告的基础服务" />
        <NEmpty v-else-if="!catalog" description="服务目录尚未确认" />
        <NList v-else><NListItem v-for="service in services" :key="service.id"><NSpace justify="space-between" align="center"><span>{{ service.name }}</span><NTag :type="service.loaded ? 'success' : 'error'" :bordered="false" round>{{ service.loaded ? '运行中' : '不可用' }}</NTag></NSpace><div v-if="service.reason" class="muted">{{ service.reason }}</div></NListItem></NList>
      </NCard>
    </div>
    <NSpace class="system-actions"><RouterLink to="/groups"><NButton type="primary"><template #icon><NIcon :component="ChatbubblesOutline" /></template>管理群聊</NButton></RouterLink><RouterLink to="/plugins"><NButton><template #icon><NIcon :component="AppsOutline" /></template>管理插件</NButton></RouterLink></NSpace>
  </main>
</template>

<style scoped>
.system-page { width:min(980px,100%); }.page-intro { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }.page-alert { margin-bottom:14px; }.system-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; }.bot-id { display:block; margin-top:2px; opacity:.58; font-family:ui-monospace,SFMono-Regular,Consolas,monospace; font-size:12px; }.system-actions { margin-top:20px; }
.bot-info { display: flex; align-items: center; gap: 12px; }
.bot-avatar { display: grid; width: 36px; height: 36px; place-items: center; border-radius: 9px; background: color-mix(in srgb, #2080f0 14%, transparent); color: #2080f0; font-weight: 700; font-size: 14px; user-select: none; }
@media(max-width:699px) { .page-intro { align-items:stretch; flex-direction:column; }.system-grid { grid-template-columns:minmax(0,1fr); } }
</style>
