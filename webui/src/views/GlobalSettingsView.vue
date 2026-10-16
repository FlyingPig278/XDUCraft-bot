<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { NAlert, NButton, NEmpty, NIcon, NSpin } from 'naive-ui'
import { RefreshOutline } from '@vicons/ionicons5'
import { apiGet } from '../api/client'
import type { PluginDescriptor, PluginsResponse } from '../api/types'
import PluginCard from '../components/PluginCard.vue'
import PluginSettingsModal from '../components/PluginSettingsModal.vue'
import { connectionState } from '../state'

const plugins = ref<PluginDescriptor[]>([])
const route = useRoute()
const focusedPlugin = computed(() => typeof route.query.plugin === 'string' ? route.query.plugin : '')
const loading = ref(false)
const error = ref('')
const warnings = ref<string[]>([])
const modalPlugin = ref<PluginDescriptor | null>(null)
const modalScope = ref<'global' | 'startup'>('global')
let generation = 0
onUnmounted(() => { generation++ })
const managedPlugins = computed(() => plugins.value.filter(plugin => plugin.managed))

async function load(): Promise<boolean> {
  const token = ++generation
  loading.value = true
  error.value = ''
  try {
    const result = await apiGet<PluginsResponse>('/api/plugins')
    if (token !== generation) return false
    plugins.value = result.plugins
    warnings.value = result.warnings ?? []
    if (modalPlugin.value) modalPlugin.value = result.plugins.find(plugin => plugin.id === modalPlugin.value?.id) ?? null
    return true
  } catch (caught) {
    if (token === generation) error.value = caught instanceof Error ? caught.message : '读取插件目录失败'
    return false
  } finally {
    if (token === generation) loading.value = false
  }
}
function openSettings(plugin: PluginDescriptor, scope: 'global' | 'startup'): void {
  modalPlugin.value = plugin
  modalScope.value = scope
}
async function saved(): Promise<void> {
  await load()
  const token = generation
  try {
    const result = await apiGet<{ restart_required: boolean }>('/api/overview')
    if (token === generation) connectionState.restartRequired = result.restart_required
  } catch { /* A failed banner refresh must not misreport applied state. */ }
}
async function focusPlugin(): Promise<void> {
  if (!focusedPlugin.value) return
  await nextTick()
  const target = document.getElementById(`plugin-${focusedPlugin.value}`)
  target?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  target?.focus({ preventScroll: true })
}
watch([focusedPlugin, managedPlugins], () => { void focusPlugin() })
onMounted(load)
</script>

<template>
  <main class="page plugins-page">
    <div class="page-intro">
      <div><h1 class="page-heading">插件</h1><p class="page-subtitle">全局总开关 · 关闭后所有群暂停运行<span v-if="managedPlugins.length"> · 共 {{ managedPlugins.length }} 个业务插件</span></p></div>
      <NButton secondary :loading="loading" @click="load"><template #icon><NIcon :component="RefreshOutline" /></template>刷新</NButton>
    </div>
    <NAlert v-if="error" type="error" class="page-alert">{{ error }} <NButton size="small" @click="load">重试</NButton></NAlert>
    <NAlert v-for="warning in warnings" :key="warning" type="warning" class="page-alert">{{ warning }}</NAlert>
    <NSpin :show="loading" :class="{ 'spin-container-min': loading && !managedPlugins.length }">
      <div v-if="managedPlugins.length" class="plugin-grid">
        <PluginCard
          v-for="plugin in managedPlugins"
          :key="plugin.id"
          :id="`plugin-${plugin.short_name}`"
          :class="{ 'focused-plugin': focusedPlugin === plugin.short_name }"
          tabindex="-1"
          :plugin="plugin"
          scope="global"
          variant="global-list"
          :refresh="load"
          @configure="scope => openSettings(plugin, scope === 'startup' ? 'startup' : 'global')"
        />
      </div>
      <NEmpty v-else-if="!loading" description="当前没有可管理的业务插件" class="empty-state" />
    </NSpin>
    <PluginSettingsModal :show="Boolean(modalPlugin)" :plugin="modalPlugin" :initial-scope="modalScope" @close="modalPlugin = null" @saved="saved" />
  </main>
</template>

<style scoped>
.plugins-page { width:min(1040px,100%); }
.page-intro { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }
.page-alert { margin-bottom:12px; }
.plugin-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }
.empty-state { padding:48px 0; }
.focused-plugin { outline: 2px solid #2080f0; outline-offset: 3px; border-radius: var(--n-border-radius, 8px); }
@media(max-width:699px) { .page-intro { align-items:stretch; flex-direction:column; }.plugin-grid { grid-template-columns:minmax(0,1fr); } }
</style>
