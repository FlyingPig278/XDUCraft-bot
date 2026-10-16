<script setup lang="ts">
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NAlert, NButton, NEmpty, NIcon, NRadioButton, NRadioGroup, NSpin, NTag } from 'naive-ui'
import { ArrowBackOutline, RefreshOutline, SettingsOutline } from '@vicons/ionicons5'
import { apiGet } from '../api/client'
import type { GroupSummary, GroupsResponse, Overview, PluginDescriptor, PluginsResponse } from '../api/types'
import GroupIdentity from '../components/GroupIdentity.vue'
import PluginCard from '../components/PluginCard.vue'
import PluginSettingsModal from '../components/PluginSettingsModal.vue'
import SchemaSettingsForm from '../components/SchemaSettingsForm.vue'
import { connectionState } from '../state'

const route = useRoute()
const router = useRouter()
const response = ref<PluginsResponse | null>(null)
const groups = ref<GroupSummary[]>([])
const warnings = ref<string[]>([])
const error = ref('')
const loading = ref(false)
const filter = ref<'all' | 'enabled'>('all')
const modalOpen = ref(false)
const modalScope = ref<'global' | 'startup'>('global')
let generation = 0
let responseGroup = ''
onUnmounted(() => { generation++ })

const groupId = computed(() => String(route.params.groupId))
const selectedPluginName = computed(() => typeof route.params.plugin === 'string' ? route.params.plugin : '')
const isPluginDetail = computed(() => Boolean(selectedPluginName.value))
const plugins = computed(() => (response.value?.plugins ?? []).filter(plugin => plugin.managed))
const activePlugin = computed(() => plugins.value.find(plugin => plugin.short_name === selectedPluginName.value))
const globalEntryLabel = computed(() => {
  const hasGlobal = Boolean(activePlugin.value?.resources.global)
  const hasStartup = Boolean(activePlugin.value?.resources.startup)
  if (hasGlobal && hasStartup) return '全局与启动设置'
  if (hasStartup) return '启动设置'
  return '全局设置'
})
const group = computed(() => groups.value.find(item => item.group_id === groupId.value))
const groupName = computed(() => group.value?.name ?? `群 ${groupId.value}`)
const groupsQuery = computed(() => typeof route.query.groups === 'string' ? route.query.groups : '')
const shownPlugins = computed(() => filter.value === 'enabled' ? plugins.value.filter(plugin => plugin.control?.config.enabled === true) : plugins.value)
const filterOptions = [{ label: '全部插件', value: 'all' }, { label: '本群已启用', value: 'enabled' }]
const filterStorageKey = computed(() => `xducraft-group-plugin-filter:${groupId.value}`)
const scrollStorageKey = computed(() => `xducraft-group-plugin-scroll:${groupId.value}`)

function readFilter(): 'all' | 'enabled' {
  const query = route.query.filter
  if (query === 'enabled' || query === 'all') return query
  return localStorage.getItem(filterStorageKey.value) === 'enabled' ? 'enabled' : 'all'
}
async function restoreScroll(): Promise<void> {
  if (isPluginDetail.value) return
  await nextTick()
  const value = Number(sessionStorage.getItem(scrollStorageKey.value) ?? '0')
  if (Number.isFinite(value) && value > 0) window.scrollTo({ top: value })
}
async function load(includeGroups = false): Promise<boolean> {
  const token = ++generation
  const requestedGroup = groupId.value
  loading.value = true
  error.value = ''
  if (responseGroup !== requestedGroup) response.value = null
  const [pluginResult, groupResult, overviewResult] = await Promise.allSettled([
    apiGet<PluginsResponse>(`/api/groups/${encodeURIComponent(requestedGroup)}/plugins`),
    includeGroups ? apiGet<GroupsResponse>('/api/groups') : Promise.resolve(null),
    includeGroups ? apiGet<Overview>('/api/overview') : Promise.resolve(null)
  ])
  if (token !== generation || requestedGroup !== groupId.value) return false
  if (pluginResult.status === 'fulfilled') {
    response.value = pluginResult.value
    responseGroup = requestedGroup
  } else {
    error.value = pluginResult.reason instanceof Error ? pluginResult.reason.message : '读取群插件失败'
  }
  if (groupResult.status === 'fulfilled' && groupResult.value) {
    groups.value = groupResult.value.groups
    warnings.value = groupResult.value.warnings
  } else if (groupResult.status === 'rejected') {
    warnings.value = ['群目录暂时不可用，当前群身份未能确认。']
  }
  if (overviewResult.status === 'fulfilled' && overviewResult.value) {
    connectionState.connectedBots = overviewResult.value.bots.filter(bot => bot.connected).length
    connectionState.restartRequired = overviewResult.value.restart_required
  }
  loading.value = false
  if (pluginResult.status === 'fulfilled') await restoreScroll()
  return pluginResult.status === 'fulfilled'
}
function groupRouteQuery(includeFilter = true): Record<string, string> {
  const query: Record<string, string> = {}
  if (groupsQuery.value) query.groups = groupsQuery.value
  if (includeFilter) query.filter = filter.value
  return query
}
function backToGroups(): void {
  void router.push({ name: 'groups', query: groupsQuery.value ? { q: groupsQuery.value } : {} })
}
function setFilter(value: string | number): void {
  if (value !== 'all' && value !== 'enabled') return
  filter.value = value
  localStorage.setItem(filterStorageKey.value, value)
  void router.replace({ name: 'group-plugins', params: { groupId: groupId.value }, query: groupRouteQuery() })
}
function openPlugin(plugin: PluginDescriptor): void {
  sessionStorage.setItem(scrollStorageKey.value, String(window.scrollY))
  void router.push({ name: 'group-plugin-settings', params: { groupId: groupId.value, plugin: plugin.short_name }, query: groupRouteQuery() })
}
function backToPlugins(): void {
  void router.push({ name: 'group-plugins', params: { groupId: groupId.value }, query: groupRouteQuery() })
}
function openGlobal(scope: 'global' | 'startup'): void {
  modalScope.value = scope
  modalOpen.value = true
}
function showAll(): void { setFilter('all') }
async function globalSaved(): Promise<void> {
  await load()
  const token = generation
  try {
    const result = await apiGet<Overview>('/api/overview')
    if (token === generation) connectionState.restartRequired = result.restart_required
  } catch { /* The saved resource remains authoritative even if the banner refresh fails. */ }
}

watch(groupId, (next, previous) => {
  filter.value = readFilter()
  if (next !== previous) void load(true)
}, { immediate: true })
watch(selectedPluginName, (next, previous) => {
  if (previous && !next) void restoreScroll()
})
watch(() => route.query.filter, value => {
  if (value === 'all' || value === 'enabled') filter.value = value
})
</script>

<template>
  <main class="page group-page">
    <template v-if="!isPluginDetail">
      <div class="top-actions"><NButton text @click="backToGroups"><template #icon><NIcon :component="ArrowBackOutline" /></template>全部群聊</NButton><NButton :loading="loading" @click="load(true)"><template #icon><NIcon :component="RefreshOutline" /></template>刷新</NButton></div>
      <header class="group-header">
        <GroupIdentity :group-id="groupId" :name="groupName" :size="58" name-tag="h1" eager />
        <div v-if="group" class="header-status-badge">
          <NTag v-if="group.connected" size="small" type="success" :bordered="false" round>在线</NTag>
          <NTag v-else-if="group.stale" size="small" type="warning" :bordered="false" round>最近连接</NTag>
          <NTag v-else size="small" :bordered="false" round>未连接</NTag>
        </div>
      </header>
      <NAlert v-if="error" type="error" class="page-alert">{{ error }} <NButton size="small" @click="load(true)">重试</NButton></NAlert>
      <NAlert v-for="warning in [...warnings, ...(response?.warnings ?? [])]" :key="warning" type="warning" class="page-alert">{{ warning }}</NAlert>
      <div class="plugin-toolbar">
        <NRadioGroup :value="filter" name="group-plugin-filter" aria-label="筛选群插件" @update:value="setFilter">
          <NRadioButton v-for="option in filterOptions" :key="option.value" :value="option.value">{{ option.label }}</NRadioButton>
        </NRadioGroup>
        <span>{{ shownPlugins.length }} 个插件</span>
      </div>
      <NSpin :show="loading" :class="{ 'spin-container-min': loading && !shownPlugins.length }">
        <div v-if="shownPlugins.length" class="plugin-grid">
          <PluginCard v-for="plugin in shownPlugins" :key="plugin.id" :plugin="plugin" :group-id="groupId" scope="group" variant="group-list" :refresh="() => load()" @configure="openPlugin(plugin)" />
        </div>
        <NEmpty v-else-if="!loading && filter === 'enabled'" description="本群还没有已启用的插件" class="empty-state">
          <template #extra><NButton type="primary" secondary @click="showAll">查看全部插件</NButton></template>
        </NEmpty>
        <NEmpty v-else-if="!loading" description="当前没有可管理的业务插件" class="empty-state" />
      </NSpin>
    </template>

    <template v-else>
      <div class="top-actions"><NButton text @click="backToPlugins"><template #icon><NIcon :component="ArrowBackOutline" /></template>返回插件列表</NButton><NButton :loading="loading" @click="load(true)"><template #icon><NIcon :component="RefreshOutline" /></template>刷新</NButton></div>
      <header class="detail-header"><div><div class="detail-eyebrow">{{ groupName }}</div><h1 class="page-heading">{{ activePlugin?.name ?? selectedPluginName }}</h1></div></header>
      <NAlert v-if="error" type="error" class="page-alert">{{ error }} <NButton size="small" @click="load(true)">重试</NButton></NAlert>
      <NSpin :show="loading" :class="{ 'spin-container-min': loading && !activePlugin }">
        <div v-if="activePlugin" class="detail-stack">
          <PluginCard :plugin="activePlugin" :group-id="groupId" scope="group" variant="detail" :refresh="() => load()" />
          <section v-if="activePlugin.resources.global || activePlugin.resources.startup" class="global-entry">
            <NButton secondary size="small" @click="openGlobal(activePlugin.resources.global ? 'global' : 'startup')"><template #icon><NIcon :component="SettingsOutline" /></template>{{ globalEntryLabel }}</NButton>
          </section>
          <SchemaSettingsForm v-if="activePlugin.resources.group" :key="activePlugin.resources.group.path" :descriptor="activePlugin.resources.group" :media="activePlugin.media" title="本群配置" @saved="load()" />
        </div>
        <NEmpty v-else-if="!loading" description="此业务插件不在当前群目录中">
          <template #extra><NButton @click="backToPlugins">返回插件列表</NButton></template>
        </NEmpty>
      </NSpin>
      <PluginSettingsModal :show="modalOpen" :plugin="activePlugin ?? null" :initial-scope="modalScope" @close="modalOpen = false" @saved="globalSaved" />
    </template>
  </main>
</template>

<style scoped>
.group-page { width:min(1040px,100%); }
.top-actions,.group-header,.plugin-toolbar,.global-entry { display:flex; align-items:center; }
.top-actions { justify-content:space-between; margin-bottom:14px; }
.group-header { justify-content:space-between; gap:18px; margin-bottom:10px; }
.page-alert { margin-bottom:12px; }
.plugin-toolbar { justify-content:space-between; gap:12px; margin:18px 0 14px; }
.plugin-toolbar > span { opacity:.6; font-size:13px; }
.plugin-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }
.empty-state { padding:48px 0; }
.detail-header { margin-bottom:18px; }
.detail-header p { margin:5px 0 0; opacity:.65; }
.detail-eyebrow { margin-bottom:5px; color:#2080f0; font-size:13px; font-weight:700; }
.detail-stack { display:flex; flex-direction:column; gap:16px; }
.global-entry { justify-content:flex-end; }
@media(max-width:699px) {
  .group-header,.global-entry { align-items:stretch; flex-direction:column; }
  .plugin-grid { grid-template-columns:minmax(0,1fr); }
  .plugin-toolbar { align-items:flex-start; flex-direction:column; }
}
</style>
