<script setup lang="ts">
import { computed, ref } from 'vue'
import { NAlert, NButton, NCard, NIcon, NSwitch, NTag, useDialog } from 'naive-ui'
import { RouterLink } from 'vue-router'
import { OptionsOutline, SettingsOutline } from '@vicons/ionicons5'
import { ApiError, apiWrite } from '../api/client'
import type { FeatureConfig, FeatureMeta, FeatureState, PluginDescriptor, Resource } from '../api/types'

const props = withDefaults(defineProps<{
  plugin: PluginDescriptor
  groupId?: string
  scope?: 'group' | 'global'
  variant?: 'group-list' | 'global-list' | 'detail'
  refresh?: () => Promise<boolean | void>
}>(), { scope: 'group', variant: 'detail' })
const emit = defineEmits<{ configure: [scope: 'group' | 'global' | 'startup'] }>()
const busy = ref<Record<string, boolean>>({})
const failure = ref('')
const stale = ref(false)
const dialog = useDialog()
const controlMeta = computed(() => props.plugin.control?.meta ?? {})
const savedEnabled = computed(() => props.plugin.control?.config.enabled === true)
const globallyPaused = computed(() => props.scope === 'group' && controlMeta.value.global_enabled === false)
const visibleFeatures = computed(() => {
  const features = props.plugin.features.filter(feature => feature.scope !== 'system')
  return features.length > 1 ? features : []
})
const contextRows = computed(() => {
  const details = props.plugin.context?.details
  return Array.isArray(details)
    ? details.filter((item): item is { label: string; value: unknown } => Boolean(item) && typeof item === 'object' && typeof item.label === 'string' && 'value' in item)
    : []
})
const icon = computed(() => {
  const declared = props.plugin.context?.icon
  if (typeof declared === 'string' && declared.trim()) return Array.from(declared.trim()).slice(0, 2).join('')
  return Array.from(props.plugin.name.trim() || '插').slice(0, 1).join('')
})
function displayContext(value: unknown): string {
  if (value === null || value === undefined) return '未提供'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (Array.isArray(value)) return value.map(displayContext).join('、') || '无'
  if (typeof value === 'object') return '已提供'
  return String(value)
}

function endpoint(target: 'control' | FeatureState): string {
  const plugin = encodeURIComponent(props.plugin.short_name)
  if (target === 'control') return props.scope === 'group' && props.groupId
    ? `/api/groups/${encodeURIComponent(props.groupId)}/plugins/${plugin}/enabled`
    : `/api/plugins/${plugin}/enabled`
  return `/api/groups/${encodeURIComponent(props.groupId ?? '')}/features/${encodeURIComponent(target.key)}`
}
async function change(target: 'control' | FeatureState, enabled: boolean): Promise<void> {
  const key = target === 'control' ? 'control' : target.key
  const revision = target === 'control' ? props.plugin.control?.revision : target.revision
  if (!revision || busy.value[key] || stale.value) return
  busy.value = { ...busy.value, [key]: true }
  failure.value = ''
  let wrote = false
  try {
    await apiWrite<Resource<FeatureConfig, FeatureMeta>>(endpoint(target), 'PUT', { enabled }, revision)
    wrote = true
    const refreshed = await props.refresh?.()
    if (refreshed === false) {
      stale.value = true
      failure.value = '已保存，但回读失败。请刷新后确认实际状态。'
    }
  } catch (error) {
    failure.value = wrote ? '已保存，但回读失败。请刷新后确认实际状态。' : error instanceof Error ? error.message : '开关保存失败'
    stale.value = wrote || (error instanceof ApiError && error.status === 409 && error.code === 'stale_config')
  } finally {
    busy.value = { ...busy.value, [key]: false }
  }
}
function requestControl(enabled: boolean): void {
  if (props.scope === 'global' && !enabled) {
    dialog.warning({
      title: '暂停此插件的全局运行',
      content: '关闭后会暂停所有群的实际运行，但保留每个群已保存的开关和配置。之后仍可编辑这些本地选择。',
      positiveText: '确认暂停', negativeText: '取消',
      onPositiveClick: () => change('control', false)
    })
    return
  }
  void change('control', enabled)
}
async function reload(): Promise<void> {
  failure.value = ''
  try {
    const refreshed = await props.refresh?.()
    stale.value = refreshed === false
    if (refreshed === false) failure.value = '回读失败，当前显示可能已过期。'
  } catch (error) {
    stale.value = true
    failure.value = error instanceof Error ? error.message : '回读失败'
  }
}
</script>

<template>
  <NCard size="small" class="plugin-card" :class="[`plugin-card--${variant}`, { 'plugin-card--paused': globallyPaused && savedEnabled }]">
    <div class="card-layout">
    <div v-if="variant !== 'detail'" class="card-heading">
      <div class="plugin-identity">
        <span class="plugin-icon" aria-hidden="true">{{ icon }}</span>
        <div class="plugin-name"><strong>{{ plugin.name }}</strong></div>
      </div>
      <NTag v-if="globallyPaused && savedEnabled" size="small" type="warning">待全局开启</NTag>
      <NTag v-else-if="!plugin.loaded" size="small" type="error">不可用</NTag>
      <NTag v-else-if="controlMeta.ready === false" size="small">待配置</NTag>
    </div>
    <div v-if="plugin.control" class="primary-control">
      <strong v-if="variant === 'detail'">{{ scope === 'group' ? '本群启用' : '全局运行' }}</strong>
      <NSwitch
        :value="savedEnabled"
        :loading="busy.control"
        :disabled="busy.control || stale || (controlMeta.available === false && !globallyPaused) || !plugin.control.revision || !plugin.loaded"
        :aria-label="`${plugin.name}${scope === 'group' ? '本群启用' : '全局运行'}`"
        @update:value="requestControl"
      />
    </div>

    <template v-if="variant === 'detail'">
      <p v-if="plugin.description" class="plugin-description">{{ plugin.description }}</p>
      <NAlert v-if="globallyPaused && savedEnabled" type="warning" class="status-alert">
        本群已启用，但全局开关尚未开启。
        <RouterLink :to="{ name: 'plugins', query: { plugin: plugin.short_name } }">前往全局开关 →</RouterLink>
      </NAlert>
      <NAlert v-if="plugin.context?.available === false && plugin.context.reason" type="warning" class="status-alert">{{ plugin.context.reason }}</NAlert>
      <template v-for="(notice, index) in plugin.context?.notices || []" :key="index">
        <NAlert v-if="notice.type === 'error' || notice.type === 'warning'" :type="notice.type === 'error' ? 'error' : 'warning'" class="status-alert">{{ notice.message }}</NAlert>
        <p v-else class="status-note">{{ notice.message }}</p>
      </template>
    </template>
    <dl v-if="variant === 'detail' && contextRows.length" class="context-list"><template v-for="(item, index) in contextRows" :key="index"><dt>{{ item.label }}</dt><dd>{{ displayContext(item.value) }}</dd></template></dl>
    <NAlert v-if="failure" :type="stale ? 'warning' : 'error'" class="status-alert">{{ failure }} <NButton size="tiny" @click="reload">重新读取</NButton></NAlert>


    <div v-if="variant === 'group-list'" class="card-actions">
      <NButton type="primary" secondary :disabled="!plugin.loaded" @click="emit('configure', 'group')"><template #icon><NIcon :component="OptionsOutline" /></template>配置</NButton>
    </div>
    <div v-else-if="variant === 'global-list'" class="card-actions">
      <NButton v-if="plugin.resources.global || plugin.resources.startup" quaternary :aria-label="`${plugin.name}设置`" @click="emit('configure', plugin.resources.global ? 'global' : 'startup')"><template #icon><NIcon :component="SettingsOutline" /></template>设置</NButton>
    </div>

    <section v-if="variant === 'detail' && visibleFeatures.length" class="feature-section">
      <h3>功能选项</h3>
      <div v-for="feature in visibleFeatures" :key="feature.key" class="feature-row">
        <div><strong>{{ feature.name || feature.key }}</strong><span v-if="feature.description">{{ feature.description }}</span><span v-if="feature.effective !== undefined && feature.effective !== feature.enabled" class="feature-status-diff">{{ feature.enabled ? '已保存开启，当前尚未生效' : '已保存关闭，但当前仍在运行' }}</span></div>
        <NSwitch
          :value="feature.enabled"
          :loading="busy[feature.key]"
          :disabled="busy[feature.key] || stale || !feature.revision || (feature.available === false && !globallyPaused)"
          :aria-label="`${feature.name || feature.key}的本群选项`"
          @update:value="change(feature, $event)"
        />
      </div>
    </section>
    </div>
  </NCard>
</template>

<style scoped>
.plugin-card { height:100%; transition: border-color .2s ease, box-shadow .2s ease; }
.card-heading,.plugin-identity,.primary-control,.feature-row { display:flex; align-items:center; }
.card-heading,.primary-control,.feature-row { justify-content:space-between; gap:14px; }
.plugin-identity { min-width:0; gap:11px; }
.plugin-icon { display:grid; flex:0 0 38px; width:38px; height:38px; place-items:center; border-radius:10px; background:color-mix(in srgb,#2080f0 14%,transparent); color:#2080f0; font-size:18px; font-weight:750; }
.plugin-name { display:flex; min-width:0; flex-direction:column; gap:2px; }
.plugin-name strong { font-size:15px; overflow-wrap:anywhere; }
.feature-row span { font-size:12px; opacity:.68; }
.plugin-description { margin:14px 0 0; opacity:.72; line-height:1.55; }
.status-note { margin:10px 0 0; opacity:.72; font-size:13px; }
.status-alert { margin-top:12px; }
.primary-control { margin:0; padding:0; }
.plugin-card--detail .primary-control { padding: 2px 0 12px; border-bottom: 1px solid color-mix(in srgb, currentColor 10%, transparent); }
.feature-row > div:first-child { display:flex; min-width:0; flex-direction:column; gap:3px; }
.card-actions { display:flex; align-items:center; justify-content:flex-end; gap:8px; margin-top:13px; flex-wrap:wrap; }
.feature-section { margin-top:18px; padding-top:14px; border-top:1px solid color-mix(in srgb,currentColor 11%,transparent); }
.context-list { display:grid; grid-template-columns:minmax(90px,auto) minmax(0,1fr); gap:6px 14px; margin:14px 0 0; font-size:13px; }.context-list dt { opacity:.64; }.context-list dd { margin:0; overflow-wrap:anywhere; }
.feature-section h3 { margin:0 0 4px; font-size:15px; }
.feature-row { padding:11px 0; }
.plugin-card--paused { border-color:color-mix(in srgb,#f0a020 42%,transparent); }
.plugin-card:not(.plugin-card--detail) .card-layout { display:grid; grid-template-columns:minmax(0,1fr) auto auto; align-items:center; gap:12px; }
.plugin-card:not(.plugin-card--detail) .card-heading { grid-column:1; grid-row:1; align-items:flex-start; flex-direction:column; gap:6px; }
.plugin-card:not(.plugin-card--detail) .card-heading > .n-tag { margin-left:49px; }
.plugin-card:not(.plugin-card--detail) .primary-control { grid-column:2; grid-row:1; }
.plugin-card:not(.plugin-card--detail) .card-actions { grid-column:3; grid-row:1; margin:0; }
.plugin-card:not(.plugin-card--detail) .status-alert { grid-column:1/-1; margin:0; }
.plugin-card.plugin-card--global-list .primary-control { grid-column:3; }
.plugin-card.plugin-card--global-list .card-actions { grid-column:2; grid-row:1; }
@media(max-width:460px) { .feature-row { align-items:flex-start; } }
</style>
