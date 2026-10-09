<script setup lang="ts">
import { computed, h, onUnmounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { NAlert, NButton, NEmpty, NSelect, NSpin, type SelectOption } from 'naive-ui'
import { apiGet } from '../api/client'
import type { GroupSummary, GroupsResponse, Overview, PluginsResponse } from '../api/types'
import GroupIdentity from '../components/GroupIdentity.vue'
import PluginCard from '../components/PluginCard.vue'
import SchemaSettingsForm from '../components/SchemaSettingsForm.vue'
import { connectionState, rememberGroupSelection } from '../state'

const route = useRoute()
const router = useRouter()
const response = ref<PluginsResponse | null>(null)
const groups = ref<GroupSummary[]>([])
const warnings = ref<string[]>([])
const error = ref('')
const loading = ref(false)
let generation = 0
let responseGroup = ''
onUnmounted(() => { generation++ })
const groupId = computed(() => String(route.params.groupId))
const selectedPlugin = computed(() => typeof route.params.plugin === 'string' ? route.params.plugin : '')
const plugins = computed(() => response.value?.plugins ?? [])
const activePlugin = computed(() => plugins.value.find((plugin) => plugin.short_name === selectedPlugin.value))
const group = computed(() => groups.value.find((item) => item.group_id === groupId.value))
const groupName = computed(() => group.value?.name ?? `群 ${groupId.value}`)
const groupOptions = computed(() => groups.value.map((item) => ({ label: `${item.name} · ${item.group_id}`, value: item.group_id })))
const pluginOptions = computed(() => plugins.value.map((plugin) => ({ label: `${plugin.name}${plugin.loaded ? '' : '（未加载）'}`, value: plugin.short_name })))
function renderGroup(option: SelectOption) {
  const item = groups.value.find((entry) => entry.group_id === option.value)
  return item ? h(GroupIdentity, { groupId: item.group_id, name: item.name, size: 30 }) : String(option.label ?? '')
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
    warnings.value = ['群目录暂时不可用，当前群身份未能确认。请刷新目录，不会把查询失败当成群不存在。']
  }
  if (overviewResult.status === 'fulfilled' && overviewResult.value) {
    connectionState.connectedBots = overviewResult.value.bots.filter((bot) => bot.connected).length
    connectionState.restartRequired = overviewResult.value.restart_required
  }
  loading.value = false
  if (pluginResult.status !== 'fulfilled') return false
  if ((!selectedPlugin.value || !plugins.value.some((plugin) => plugin.short_name === selectedPlugin.value)) && plugins.value[0]) {
    await router.replace(`/groups/${encodeURIComponent(requestedGroup)}/${encodeURIComponent(plugins.value[0].short_name)}`)
  }
  return true
}
function selectPlugin(value: string | number | null): void {
  if (value === null) return
  void router.push(`/groups/${encodeURIComponent(groupId.value)}/${encodeURIComponent(String(value))}`)
}
function switchGroup(value: string | number | null): void {
  if (!groups.value.some(item => item.group_id === value)) return
  void router.push(`/groups/${encodeURIComponent(String(value))}${selectedPlugin.value ? `/${encodeURIComponent(selectedPlugin.value)}` : ''}`)
}
function sharedLink(scope: 'global' | 'startup') {
  return { name: 'settings', params: { section: scope === 'global' ? 'runtime' : 'startup' }, query: { plugin: selectedPlugin.value, returnGroup: groupId.value, returnPlugin: selectedPlugin.value } }
}
watch([groupId, selectedPlugin], ([nextGroup, nextPlugin], [previousGroup]) => {
  if (nextPlugin) rememberGroupSelection(nextGroup, nextPlugin)
  if (nextGroup !== previousGroup) void load(true)
}, { immediate: true })
</script>

<template>
  <main class="page group-workspace">
    <div class="workspace-topbar"><RouterLink to="/groups"><NButton text>← 全部群</NButton></RouterLink><NButton :loading="loading" @click="load(true)">刷新目录</NButton><NSelect :value="groupId" :options="groupOptions" :render-label="renderGroup" filterable aria-label="切换正在管理的群" placeholder="搜索已发现的群" class="group-switcher" @update:value="switchGroup" /></div>
    <header class="group-header"><GroupIdentity :group-id="groupId" :name="groupName" :size="64" name-tag="h1" eager /><span class="connection-copy">{{ !group ? '群目录身份待确认' : group.connected ? '当前可连接' : group.stale ? '使用最近成功获取的群信息' : '当前未连接，来自已有配置' }}</span></header>
    <NAlert v-if="error" type="error" class="detail-warning">{{ error }}<NButton size="small" @click="load(true)">重新读取</NButton></NAlert>
    <NAlert v-for="warning in [...warnings, ...(response?.warnings ?? [])]" :key="warning" type="warning" class="detail-warning">{{ warning }}</NAlert>
    <NSpin :show="loading">
      <div class="mobile-plugin-picker"><label for="plugin-picker">选择插件</label><NSelect id="plugin-picker" :value="selectedPlugin" :options="pluginOptions" @update:value="selectPlugin" /></div>
      <div class="workspace-layout">
        <aside class="plugin-rail" aria-label="当前群的插件"><div class="rail-heading">插件与系统服务</div><PluginCard v-for="plugin in plugins" :key="plugin.id" :plugin="plugin" :selected="plugin.short_name === selectedPlugin" @select="selectPlugin" /></aside>
        <section class="plugin-workspace">
          <template v-if="activePlugin">
            <PluginCard :key="`${groupId}/${activePlugin.id}`" :plugin="activePlugin" :compact="false" :group-id="groupId" scope="group" :refresh="() => load()" />
            <SchemaSettingsForm v-if="activePlugin.resources.group" :key="activePlugin.resources.group.path" :descriptor="activePlugin.resources.group" :media="activePlugin.media" :title="`${activePlugin.name} · ${groupName}的本群配置`" @saved="load()" />
            <NAlert v-else :show-icon="false">{{ activePlugin.managed ? '此插件没有声明本群参数表单；功能偏好与总开关独立管理。' : '此插件提供信息说明，不会创建虚构的群设置表单。' }}</NAlert>
            <section v-if="activePlugin.resources.global || activePlugin.resources.startup" class="shared-context">
              <h3>全局与部署期设置</h3><p class="muted">这里不嵌入跨群表单。全局设置影响所有选择“跟随全局”的群；部署期设置只在下次启动后生效。前往独立页面后可返回当前群和插件。</p>
              <div class="shared-links"><RouterLink v-if="activePlugin.resources.global" :to="sharedLink('global')"><NButton secondary>前往 {{ activePlugin.name }} 的全局设置</NButton></RouterLink><RouterLink v-if="activePlugin.resources.startup" :to="sharedLink('startup')"><NButton secondary>前往 {{ activePlugin.name }} 的部署期设置</NButton></RouterLink></div>
            </section>
          </template>
          <NEmpty v-else-if="!loading" description="该插件不在当前发现目录中，请从插件列表选择。" />
        </section>
      </div>
    </NSpin>
  </main>
</template>
<style scoped>
.group-workspace { width:min(1320px,100%); }.workspace-topbar { display:flex; align-items:center; justify-content:space-between; gap:14px; margin-bottom:12px; }.group-switcher { width:min(420px,100%); }.group-header { position:sticky; z-index:3; top:60px; display:flex; align-items:center; justify-content:space-between; gap:20px; margin:0 -8px 18px; padding:12px 8px; border-bottom:1px solid color-mix(in srgb,currentColor 10%,transparent); background:var(--n-color,Canvas); }.connection-copy { color:#888; font-size:13px; }.detail-warning { margin-bottom:12px; }.workspace-layout { display:grid; grid-template-columns:260px minmax(0,1fr); align-items:start; gap:18px; }.plugin-rail { position:sticky; top:154px; min-width:0; max-height:calc(100vh - 170px); overflow:auto; padding:10px; border:1px solid color-mix(in srgb,currentColor 12%,transparent); border-radius:12px; }.rail-heading { padding:7px 12px 9px; font-size:12px; font-weight:700; opacity:.6; }.plugin-workspace { min-width:0; display:flex; flex-direction:column; gap:16px; }.mobile-plugin-picker { display:none; }.shared-context { padding:18px; border:1px solid color-mix(in srgb,currentColor 12%,transparent); border-radius:12px; }.shared-context h3 { margin:0; }.shared-links { display:flex; flex-wrap:wrap; gap:10px; margin:16px 0 0; }
@media(max-width:799px) { .workspace-topbar,.group-header { align-items:stretch; flex-direction:column; }.group-switcher { width:100%; }.workspace-layout { display:block; }.plugin-rail { display:none; }.mobile-plugin-picker { display:flex; flex-direction:column; gap:7px; margin-bottom:14px; }.shared-links { flex-direction:column; }.shared-links a,.shared-links .n-button { width:100%; }.shared-context { padding:12px; } }
.group-switcher :deep(.n-base-selection-label) { min-height: 50px; height: auto; }
.group-switcher :deep(.group-name) { font-size: 13px; }
.group-switcher :deep(.group-number) { font-size: 11px; }
</style>
