<script setup lang="ts">
import { computed, ref } from 'vue'
import { NAlert, NButton, NCard, NSwitch, NTag, useDialog } from 'naive-ui'
import { ApiError, apiWrite } from '../api/client'
import type { FeatureConfig, FeatureMeta, FeatureState, PluginDescriptor, Resource } from '../api/types'

const props = withDefaults(defineProps<{ plugin: PluginDescriptor; selected?: boolean; compact?: boolean; controls?: boolean; groupId?: string; scope?: 'group' | 'global'; refresh?: () => Promise<boolean | void> }>(), { selected: false, compact: true, controls: true, scope: 'group' })
const emit = defineEmits<{ select: [shortName: string] }>()
const busy = ref<Record<string, boolean>>({})
const failure = ref('')
const stale = ref(false)
const dialog = useDialog()
const controlMeta = computed(() => props.plugin.control?.meta ?? {})
const effective = computed(() => props.plugin.control?.meta.effective)
const summary = computed(() => {
  if (!props.plugin.loaded) return '未加载'
  if (!props.plugin.managed) return '信息与系统服务'
  if (controlMeta.value.global_enabled === false && props.scope === 'group') return '被插件全局总开关暂停'
  if (controlMeta.value.ready === false) return '尚未就绪'
  if (effective.value !== undefined) return effective.value ? '插件允许运行' : '插件已暂停'
  return props.plugin.features.length && props.plugin.features.every(feature => feature.effective !== undefined) ? `${props.plugin.features.filter(feature => feature.effective === true).length} 项功能实际生效` : '查看配置与状态'
})
function sourceLabel(source: string | undefined, followsGlobal = true): string {
  if (props.scope === 'global') return '全局总开关'
  if (!source) return '服务端未说明偏好来源'
  const normalized = source.toLowerCase()
  if (normalized.includes('group') || normalized.includes('override') || normalized.includes('local')) return '本群独立定制'
  if (normalized.includes('global') || normalized.includes('inherit')) return '跟随全局'
  if (normalized.includes('default')) return followsGlobal ? '跟随全局（未另设时采用插件声明默认）' : '插件声明默认（没有可编辑的全局值）'
  return '偏好来源未识别'
}
const contextRows = computed(() => {
  const details = props.plugin.context?.details
  return Array.isArray(details) ? details.filter((item): item is { label: string; value: unknown } => Boolean(item) && typeof item === 'object' && typeof item.label === 'string' && 'value' in item) : []
})
function displayContext(value: unknown): string {
  if (value === null || value === undefined) return '未提供'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (Array.isArray(value)) return value.map(displayContext).join('；') || '无'
  if (typeof value === 'object') return Object.entries(value).filter(([key]) => !/secret|password|token/i.test(key)).map(([key, item]) => `${key}：${displayContext(item)}`).join('；')
  return String(value)
}
async function change(target: 'control' | FeatureState, enabled?: boolean): Promise<void> {
  const key = target === 'control' ? 'control' : target.key
  const resourceRevision = target === 'control' ? props.plugin.control?.revision : target.revision
  if (!resourceRevision || busy.value[key] || stale.value) return
  const group = props.groupId
  const plugin = props.plugin.short_name
  const prefix = props.scope === 'group' && group ? `/api/groups/${encodeURIComponent(group)}` : '/api'
  const path = target === 'control'
    ? `${prefix}/plugins/${encodeURIComponent(plugin)}/enabled`
    : `${props.scope === 'group' && group ? prefix : '/api/global'}/features/${encodeURIComponent(target.key)}`
  busy.value = { ...busy.value, [key]: true }
  failure.value = ''
  let wrote = false
  try {
    await apiWrite<Resource<FeatureConfig, FeatureMeta>>(path, enabled === undefined ? 'DELETE' : 'PUT', enabled === undefined ? undefined : { enabled }, resourceRevision)
    wrote = true
    const refreshed = await props.refresh?.()
    if (refreshed === false) {
      failure.value = '设置已写入，但服务器回读失败；请重新读取后确认实际状态与来源。'
      stale.value = true
    }
  } catch (error) {
    failure.value = wrote ? '设置已写入，但服务器回读失败；请重新读取后确认实际状态与来源。' : error instanceof Error ? error.message : '开关保存失败'
    stale.value = wrote || (error instanceof ApiError && error.status === 409 && error.code === 'stale_config')
  } finally { busy.value = { ...busy.value, [key]: false } }
}
function requestChange(target: 'control' | FeatureState, enabled?: boolean): void {
  const followsGlobal = target === 'control' || target.global_configurable === true
  if (props.scope === 'global' || enabled === undefined) {
    dialog.warning({ title: enabled === undefined ? (followsGlobal ? '改为跟随全局' : '恢复插件声明默认') : '修改插件全局总开关', content: enabled === undefined ? (followsGlobal ? '保存后，本群不再保留此项独立偏好，将采用当前全局设置。其它功能偏好不受影响。' : '保存后，本群不再保留此项独立偏好，将采用插件声明的默认行为。') : '关闭插件全局总开关会暂停全部群的实际生效，但保留各群和各功能的偏好。确定继续？', positiveText: '确认', negativeText: '取消', onPositiveClick: () => change(target, enabled) })
  } else void change(target, enabled)
}
async function reload(): Promise<void> {
  failure.value = ''
  try {
    const refreshed = await props.refresh?.()
    stale.value = refreshed === false
    if (refreshed === false) failure.value = '服务器回读失败，当前显示值可能已经过期。'
  } catch (error) {
    stale.value = true
    failure.value = error instanceof Error ? error.message : '服务器回读失败'
  }
}
</script>

<template>
  <button v-if="compact" type="button" class="plugin-choice" :class="{ selected, unavailable: !plugin.loaded }" :aria-current="selected ? 'page' : undefined" :aria-label="`${plugin.name}，${summary}`" @click="emit('select', plugin.short_name)">
    <span class="plugin-copy"><strong>{{ plugin.name }}</strong><span>{{ summary }}</span></span>
    <span class="status-dot" :class="{ ok: plugin.loaded, paused: effective === false }" aria-hidden="true" />
  </button>
  <NCard v-else>
    <div class="plugin-heading"><div><h2>{{ plugin.name }}</h2><p v-if="plugin.description" class="muted">{{ plugin.description }}</p><small class="muted">{{ plugin.id }}</small></div><NTag :type="plugin.loaded ? 'success' : 'error'">{{ plugin.loaded ? '已加载' : '未加载' }}</NTag></div>
    <NAlert v-if="plugin.context?.available === false && plugin.context.reason" type="warning" class="status-alert">{{ plugin.context.reason }}</NAlert>
    <NAlert v-for="(notice, index) in plugin.context?.notices || []" :key="index" :type="notice.type === 'error' ? 'error' : notice.type === 'warning' ? 'warning' : 'info'" class="status-alert">{{ notice.message }}</NAlert>
    <NAlert v-if="failure" :type="stale ? 'warning' : 'error'" class="status-alert">{{ stale ? '设置已被 QQ 或其它页面修改，没有覆盖新值。' : failure }}<NButton size="small" @click="reload">重新读取状态</NButton></NAlert>
    <section v-if="controls && plugin.managed && plugin.control" class="control-section">
      <div class="feature-row"><div class="feature-copy"><strong>{{ scope === 'group' ? '本群插件偏好' : '插件全局总开关' }}</strong><span>{{ summary }}</span><span>保存的偏好：{{ plugin.control.config.enabled ? '开启' : '关闭' }} · {{ sourceLabel(controlMeta.source) }}</span></div>
        <div class="feature-actions"><NButton v-if="controlMeta.resettable && scope === 'group'" text :disabled="busy.control || stale" @click="requestChange('control')">改为跟随全局</NButton><NSwitch :value="plugin.control.config.enabled" :loading="busy.control" :disabled="busy.control || controlMeta.available === false || !plugin.control.revision || stale" :aria-label="`${plugin.name}的${scope === 'group' ? '本群插件偏好' : '全局总开关'}`" @update:value="requestChange('control', $event)" /></div>
      </div>
      <NAlert v-if="scope === 'global'" type="info" :show-icon="false">这是插件的全局总开关。关闭会暂停全部群的实际生效，但不会删除群功能默认或“本群独立定制”。</NAlert>
      <NAlert v-if="scope === 'group' && controlMeta.global_enabled === false" type="warning">插件全局总开关已关闭，因此本群当前不会生效。本群保存的偏好会保留，但不能绕过全局暂停。</NAlert>
      <NAlert v-if="controlMeta.ready === false" type="warning">插件尚未就绪。{{ controlMeta.reason || '保存的开关偏好不等于当前实际生效，请查看状态与前置条件。' }}</NAlert>
    </section>
    <NAlert v-else-if="controls && !plugin.managed" :show-icon="false" class="status-alert">此插件仅提供信息，不支持面板管理总开关。系统服务不会被伪装为可关闭的业务功能。</NAlert>
    <section v-if="controls && scope === 'group' && plugin.managed && plugin.features.length" class="control-section">
      <h3>本群功能偏好</h3>
      <NAlert type="info" :show-icon="false">声明了全局默认的功能可选择“跟随全局”；其它功能只显示插件声明默认或“本群独立定制”。无论哪种偏好，插件全局总开关关闭时都会暂停实际生效。</NAlert>
      <div v-for="feature in plugin.features" :key="feature.key" class="feature-row"><div class="feature-copy"><strong>{{ feature.name || feature.key }}</strong><span v-if="feature.description">{{ feature.description }}</span><span>保存的偏好：{{ feature.enabled ? '开启' : '关闭' }} · {{ feature.effective === undefined ? '实际状态未提供' : feature.effective ? '当前实际生效' : '当前实际未生效' }} · {{ sourceLabel(feature.source, feature.global_configurable === true) }}</span><span v-if="feature.unavailable_reason">{{ feature.unavailable_reason }}</span><span v-if="feature.superuser_only">此功能仍受机器人超级用户权限限制</span><span v-if="feature.eligible === false || feature.ready === false">当前不满足启用条件</span></div>
        <div class="feature-actions"><NButton v-if="feature.resettable" text :disabled="busy[feature.key] || stale" @click="requestChange(feature)">{{ feature.global_configurable === true ? '改为跟随全局' : '恢复插件默认' }}</NButton><NSwitch :value="feature.enabled" :loading="busy[feature.key]" :disabled="busy[feature.key] || !feature.revision || feature.scope === 'system' || feature.available === false || ((feature.eligible === false || feature.ready === false) && !feature.enabled) || stale" :aria-label="`${feature.name || feature.key}的本群功能偏好`" @update:value="requestChange(feature, $event)" /></div>
      </div>
    </section>
    <dl v-if="contextRows.length" class="plugin-context"><template v-for="(item, index) in contextRows" :key="index"><dt>{{ item.label }}</dt><dd>{{ displayContext(item.value) }}</dd></template></dl>
  </NCard>
</template>
<style scoped>
.plugin-choice { width:100%; display:flex; align-items:center; justify-content:space-between; gap:12px; padding:13px 14px; border:1px solid transparent; border-radius:10px; color:inherit; background:transparent; text-align:left; cursor:pointer; }
.plugin-choice:hover { background:color-mix(in srgb,currentColor 7%,transparent); }
.plugin-choice.selected { border-color:color-mix(in srgb,#2080f0 42%,transparent); background:color-mix(in srgb,#2080f0 11%,transparent); }
.plugin-choice:focus-visible { outline:2px solid #2080f0; outline-offset:2px; }
.plugin-choice.unavailable { opacity:.62; }
.plugin-copy { display:flex; min-width:0; flex-direction:column; gap:3px; }
.plugin-copy strong,.plugin-copy span { overflow-wrap:anywhere; }
.plugin-copy span { font-size:12px; opacity:.68; }
.status-dot { flex:0 0 auto; width:8px; height:8px; border-radius:50%; background:#d03050; }.status-dot.ok { background:#18a058; }.status-dot.paused { background:#f0a020; }
.plugin-heading { display:flex; justify-content:space-between; gap:12px; }.plugin-heading h2 { margin:0; }.plugin-heading p { margin:6px 0; }
.status-alert { margin-top:14px; }.control-section { margin-top:18px; padding-top:14px; border-top:1px solid color-mix(in srgb,currentColor 12%,transparent); }.control-section h3 { margin:0 0 8px; font-size:15px; }
.feature-row { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:12px 0; }.feature-copy { display:flex; flex-direction:column; gap:4px; min-width:0; }.feature-copy span { font-size:12px; opacity:.7; }.feature-actions { display:flex; align-items:center; gap:8px; flex-shrink:0; }
.plugin-context { display:grid; grid-template-columns:minmax(90px,auto) minmax(0,1fr); gap:8px 14px; margin-bottom:0; font-size:13px; }.plugin-context dt { opacity:.65; }.plugin-context dd { margin:0; overflow-wrap:anywhere; }
@media(max-width:799px) { .feature-row { align-items:stretch; flex-direction:column; }.feature-actions { justify-content:flex-end; flex-wrap:wrap; }.plugin-context { grid-template-columns:minmax(0,1fr); gap:3px; }.plugin-context dd { margin-bottom:9px; } }
</style>
