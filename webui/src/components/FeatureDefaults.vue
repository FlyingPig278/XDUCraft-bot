<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { NAlert, NButton, NCard, NEmpty, NSwitch, NTag, useDialog } from 'naive-ui'
import { ApiError, apiGet, apiWrite } from '../api/client'
import type { FeatureConfig, FeatureMeta, PluginDescriptor, Resource } from '../api/types'

const props = defineProps<{ plugins: PluginDescriptor[]; loading?: boolean }>()
interface DefaultRow {
  key: string
  label: string
  description?: string
  owner: string
  resource?: Resource<FeatureConfig, FeatureMeta>
  saving: boolean
  error: string
  stale: boolean
}
const rows = ref<DefaultRow[]>([])
const loading = ref(false)
const dialog = useDialog()
let generation = 0
onUnmounted(() => { generation++ })

const candidates = computed(() => props.plugins.flatMap((plugin) => plugin.features
  .filter((feature) => feature.scope !== 'system' && feature.global_configurable === true)
  .map((feature) => ({ key: feature.key, label: feature.name ?? feature.key, description: feature.description, owner: plugin.name }))))

async function reload(row: DefaultRow): Promise<void> {
  const token = generation
  row.saving = true
  try {
    const resource = await apiGet<Resource<FeatureConfig, FeatureMeta>>(`/api/global/features/${encodeURIComponent(row.key)}`)
    if (token !== generation) return
    row.resource = resource
    row.error = ''
    row.stale = false
  } catch (error) {
    if (token === generation) row.error = error instanceof Error ? error.message : '读取失败'
  } finally {
    if (token === generation) row.saving = false
  }
}
async function load(): Promise<void> {
  generation++
  loading.value = true
  rows.value = [...new Map(candidates.value.map((item) => [item.key, { ...item, saving: false, error: '', stale: false } as DefaultRow])).values()]
  const token = generation
  await Promise.all(rows.value.map(reload))
  if (token === generation) loading.value = false
}
function requestChange(row: DefaultRow, enabled: boolean): void {
  dialog.warning({
    title: '修改全局功能默认',
    content: `所有选择“跟随全局”的群将采用“${row.label}”的${enabled ? '开启' : '关闭'}偏好。已有“本群独立定制”不会被清除，插件全局总开关仍可暂停全部群。`,
    positiveText: '确认修改',
    negativeText: '取消',
    onPositiveClick: async () => {
      if (!row.resource || row.saving || row.stale) return
      row.saving = true
      const token = generation
      try {
        const resource = await apiWrite<Resource<FeatureConfig, FeatureMeta>>(`/api/global/features/${encodeURIComponent(row.key)}`, 'PUT', { enabled }, row.resource.revision)
        if (token !== generation) return
        row.resource = resource
        row.error = ''
      } catch (error) {
        if (token !== generation) return
        row.error = error instanceof Error ? error.message : '保存失败'
        row.stale = error instanceof ApiError && error.status === 409 && error.code === 'stale_config'
      } finally {
        if (token === generation) row.saving = false
      }
    }
  })
}
watch(candidates, () => { void load() }, { immediate: true })
</script>

<template>
  <NCard title="群功能的全局默认偏好">
    <template #header-extra><NButton size="small" :loading="loading || props.loading" :disabled="rows.some(row => row.saving)" @click="load">重新读取</NButton></template>
    <NAlert type="info" class="defaults-notice">
      群功能默认只决定选择“跟随全局”的群。它不会删除任何“本群独立定制”，也不能绕过插件的全局总开关；全局总开关关闭时，全部群都会暂停实际生效。
    </NAlert>
    <div v-for="row in rows" :key="row.key" class="default-row">
      <div class="default-copy">
        <strong>{{ row.label }}</strong>
        <span v-if="row.description">{{ row.description }}</span>
        <span>{{ row.owner }}</span>
        <div v-if="row.resource" class="default-status">
          <NTag size="small">全局默认偏好：{{ row.resource.config.enabled ? '开启' : '关闭' }}</NTag>
          <NTag v-if="typeof row.resource.meta.effective === 'boolean'" size="small" :type="row.resource.meta.effective ? 'success' : 'warning'">当前实际：{{ row.resource.meta.effective ? '生效' : '未生效' }}</NTag>
        </div>
        <NAlert v-if="row.error" :type="row.stale ? 'warning' : 'error'" class="row-error">
          {{ row.stale ? '配置已被 QQ 或其他页面修改，本次没有覆盖。请重新读取后再决定。' : row.error }}
          <NButton size="small" :disabled="row.saving" @click="reload(row)">重新读取此项</NButton>
        </NAlert>
      </div>
      <NSwitch :value="row.resource?.config.enabled ?? false" :loading="row.saving" :disabled="row.saving || !row.resource || row.stale || row.resource.meta.available === false" :aria-label="`${row.label}的全局默认偏好`" @update:value="requestChange(row, $event)" />
    </div>
    <NEmpty v-if="!rows.length" :description="loading || props.loading ? '正在发现已声明的群功能…' : '没有功能声明可编辑的全局默认偏好'" />
  </NCard>
</template>

<style scoped>
.defaults-notice { margin-bottom: 8px; }
.default-row { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:16px 0; border-bottom:1px solid color-mix(in srgb,currentColor 12%,transparent); }
.default-copy { display:flex; min-width:0; flex:1; flex-direction:column; gap:5px; overflow-wrap:anywhere; }
.default-copy > span { font-size:12px; opacity:.7; }
.default-status { display:flex; flex-wrap:wrap; gap:6px; margin-top:3px; }
.row-error { margin-top:6px; }
.default-row > .n-switch { flex:0 0 auto; }
@media(max-width:599px) { .default-row { align-items:stretch; flex-direction:column; }.default-row > .n-switch { align-self:flex-end; } }
</style>
