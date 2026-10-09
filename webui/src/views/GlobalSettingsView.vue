<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { NAlert, NButton, NEmpty, NSelect, NSpin, NTab, NTabs } from 'naive-ui'
import { apiGet } from '../api/client'
import type { PluginDescriptor, PluginsResponse } from '../api/types'
import PluginCard from '../components/PluginCard.vue'
import SchemaSettingsForm from '../components/SchemaSettingsForm.vue'
import FeatureDefaults from '../components/FeatureDefaults.vue'
import { connectionState, lastGroupSelection } from '../state'

const route = useRoute()
const router = useRouter()
const plugins = ref<PluginDescriptor[]>([])
const loading = ref(false)
const error = ref('')
const warnings = ref<string[]>([])
let generation = 0
onUnmounted(() => { generation++ })
const section = computed(() => route.params.section === 'features' ? 'features' : route.params.section === 'startup' ? 'startup' : 'runtime')
const scope = computed(() => section.value === 'startup' ? 'startup' : 'global')
const availablePlugins = computed(() => plugins.value.filter((plugin) => plugin.resources[scope.value] || (scope.value === 'global' && plugin.control)))
const requestedPlugin = computed(() => typeof route.query.plugin === 'string' ? route.query.plugin : '')
const activePlugin = computed(() => availablePlugins.value.find((plugin) => plugin.short_name === requestedPlugin.value) ?? availablePlugins.value[0])
const options = computed(() => availablePlugins.value.map((plugin) => ({ label: `${plugin.name}${plugin.loaded ? '' : '（未加载）'}`, value: plugin.short_name })))
const returnGroup = computed(() => typeof route.query.returnGroup === 'string' && /^[1-9]\d*$/.test(route.query.returnGroup) ? route.query.returnGroup : lastGroupSelection.groupId)
const returnPlugin = computed(() => typeof route.query.returnPlugin === 'string' ? route.query.returnPlugin : lastGroupSelection.plugin)
const returnPath = computed(() => returnGroup.value ? `/groups/${encodeURIComponent(returnGroup.value)}${returnPlugin.value ? `/${encodeURIComponent(returnPlugin.value)}` : ''}` : '/groups')
async function load(): Promise<boolean> {
  const token = ++generation
  loading.value = true
  error.value = ''
  try {
    const result = await apiGet<PluginsResponse>('/api/plugins')
    if (token !== generation) return false
    plugins.value = result.plugins
    warnings.value = result.warnings ?? []
    return true
  } catch (caught) {
    if (token === generation) error.value = caught instanceof Error ? caught.message : '读取全局设置目录失败'
    return false
  } finally {
    if (token === generation) loading.value = false
  }
}
function navigate(nextSection: string | number, plugin?: string | number | null): void {
  void router.push({ name: 'settings', params: { section: String(nextSection) }, query: { ...route.query, plugin: plugin === null || plugin === undefined || plugin === '' ? undefined : String(plugin) } })
}
async function saved(): Promise<void> {
  await load()
  const token = generation
  // Refresh the process-wide banner from authoritative overview, not from a single resource.
  try {
    const result = await apiGet<{ restart_required: boolean }>('/api/overview')
    if (token === generation) connectionState.restartRequired = result.restart_required
  } catch { /* A missing refresh is not evidence that pending changes were applied. */ }
}
watch(() => route.name, () => { void load() }, { immediate: true })
</script>

<template>
  <main class="page settings-page">
    <div class="settings-intro"><div><h1 class="page-heading">全局与系统设置</h1><p class="page-subtitle">这里管理跨群的全局值和下次启动值。每次只编辑、保存一个插件的一项声明资源。</p></div><NButton :loading="loading" @click="load">刷新插件目录</NButton><RouterLink :to="returnPath"><NButton secondary>{{ returnGroup ? '返回上次选择的群与插件' : '返回群列表' }}</NButton></RouterLink></div>
    <NAlert v-if="returnGroup" type="info" class="settings-warning">返回目标是 QQ 群 {{ returnGroup }}；当前页面的全局设置不是该群的专属覆盖。</NAlert>
    <NAlert v-if="error" type="error" class="settings-warning">{{ error }}<NButton size="small" @click="load">重试</NButton></NAlert>
    <NAlert v-for="warning in warnings" :key="warning" type="warning" class="settings-warning">{{ warning }}</NAlert>
    <NTabs type="line" :value="section" @update:value="navigate($event, activePlugin?.short_name ?? requestedPlugin)"><NTab name="runtime">运行期全局设置</NTab><NTab name="features">群功能全局默认</NTab><NTab name="startup">部署期设置</NTab></NTabs>
    <FeatureDefaults v-if="section === 'features'" :plugins="plugins" :loading="loading" class="settings-content" />
    <NSpin v-else :show="loading">
      <NAlert v-if="section === 'startup'" type="warning" class="settings-content">部署期配置只保存待启动值。当前客户端、缓存与连接不会自动替换，面板不提供重启按钮。</NAlert>
      <div class="settings-workspace">
        <aside class="settings-rail" aria-label="声明了当前作用域的插件"><PluginCard v-for="plugin in availablePlugins" :key="plugin.id" :plugin="plugin" :selected="activePlugin?.id === plugin.id" @select="navigate(section, $event)" /></aside>
        <div class="mobile-settings-picker"><label for="setting-picker">选择插件</label><NSelect id="setting-picker" :value="activePlugin?.short_name" :options="options" @update:value="navigate(section, $event)" /></div>
        <section class="settings-form">
          <template v-if="activePlugin">
            <PluginCard :key="`${section}/${activePlugin.id}`" :plugin="activePlugin" :compact="false" :controls="scope === 'global'" scope="global" :refresh="load" />
            <SchemaSettingsForm v-if="activePlugin.resources[scope]" :key="activePlugin.resources[scope]!.path" :descriptor="activePlugin.resources[scope]!" :media="activePlugin.media" :title="`${activePlugin.name} · ${scope === 'startup' ? '部署期设置' : '全局设置'}`" @saved="saved" />
            <NAlert v-else :show-icon="false">此插件只声明了全局总开关，没有声明当前作用域的参数表单。</NAlert>
          </template>
          <NEmpty v-else-if="!loading" :description="requestedPlugin ? '此插件没有声明当前作用域的设置，请重新选择或切换作用域。' : '没有插件声明当前作用域的设置'" />
        </section>
      </div>
    </NSpin>
  </main>
</template>
<style scoped>
.settings-page { width:min(1260px,100%); }.settings-intro { display:flex; justify-content:space-between; align-items:flex-start; gap:16px; flex-wrap:wrap; }.settings-warning { margin-bottom:12px; }.settings-workspace { display:grid; grid-template-columns:260px minmax(0,1fr); align-items:start; gap:18px; margin-top:18px; }.settings-rail { position:sticky; top:78px; max-height:calc(100vh - 96px); overflow:auto; padding:8px; border:1px solid color-mix(in srgb,currentColor 12%,transparent); border-radius:12px; }.settings-form { min-width:0; display:flex; flex-direction:column; gap:16px; }.settings-content { margin-top:18px; }.mobile-settings-picker { display:none; }
@media(max-width:799px) { .settings-intro { flex-direction:column; }.settings-intro .page-subtitle { margin-bottom:0; }.settings-workspace { display:block; }.settings-rail { display:none; }.mobile-settings-picker { display:flex; flex-direction:column; gap:7px; margin-bottom:14px; }.mobile-settings-picker label { font-size:13px; font-weight:650; } }
</style>
