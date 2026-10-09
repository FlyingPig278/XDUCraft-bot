<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { NAlert, NButton, NCard, NEmpty, NSpace, NSwitch, useDialog, useMessage } from 'naive-ui'
import { apiGet, apiWrite } from '../../api/client'
import type { FeatureConfig, FeatureMeta, Overview, Resource } from '../../api/types'

interface DefaultRow { key: string; label: string; passive: boolean; enabled: boolean; revision: string; meta: FeatureMeta; saving: boolean }
const rows = reactive<DefaultRow[]>([])
const loading = ref(false)
const dialog = useDialog()
const message = useMessage()

async function load(): Promise<void> {
  loading.value = true
  rows.splice(0)
  try {
    const overview = await apiGet<Overview>('/api/overview')
    for (const feature of overview.features) {
      try {
        const resource = await apiGet<Resource<FeatureConfig, FeatureMeta>>(`/api/global/features/${feature.key}`)
        rows.push({ key: feature.key, label: feature.name, passive: feature.passive, enabled: resource.config.enabled, revision: resource.revision, meta: resource.meta, saving: false })
      } catch (error) {
        message.warning(`${feature.name}：${error instanceof Error ? error.message : '读取失败'}`)
      }
    }
  } catch (error) { message.error(error instanceof Error ? error.message : '读取功能列表失败') }
  finally { loading.value = false }
}
function requestChange(row: DefaultRow, enabled: boolean): void {
  dialog.warning({
    title: '修改全局默认开关',
    content: `此操作会影响所有没有显式群覆盖的群。确定将“${row.label}”默认设为${enabled ? '开启' : '关闭'}吗？`,
    positiveText: '确认修改', negativeText: '取消',
    onPositiveClick: async () => {
      row.saving = true
      try {
        const resource = await apiWrite<Resource<FeatureConfig, FeatureMeta>>(`/api/global/features/${row.key}`, 'PUT', { enabled }, row.revision)
        row.enabled = resource.config.enabled
        row.revision = resource.revision
        row.meta = resource.meta
        message.success('全局默认已保存')
      } catch (error) { message.error(error instanceof Error ? error.message : '保存失败') }
      finally { row.saving = false }
    }
  })
}
onMounted(load)
</script>

<template>
  <NCard title="群功能全局默认" :segmented="true">
    <template #header-extra><NButton size="small" :loading="loading" :disabled="rows.some(row => row.saving)" @click="load">重新读取</NButton></template>
    <NAlert type="warning" :show-icon="true">默认值只影响没有本群显式覆盖的群。被动响应功能关闭后会立即停止响应。</NAlert>
    <div v-if="rows.length" class="defaults-list">
      <div v-for="row in rows" :key="row.key" class="default-row">
        <div><strong>{{ row.label }}</strong><div class="muted">{{ row.key }}<span v-if="row.passive"> · 被动响应</span></div></div>
        <NSpace align="center"><span>{{ row.enabled ? '默认开启' : '默认关闭' }}</span><NSwitch :value="row.enabled" :loading="row.saving" @update:value="requestChange(row, $event)" /></NSpace>
      </div>
    </div>
    <NEmpty v-else :description="loading ? '正在读取…' : '没有可编辑的共享默认开关'" />
  </NCard>
</template>
<style scoped>.defaults-list { margin-top: 14px; }.default-row { display:flex; align-items:center; justify-content:space-between; gap:14px; padding:12px 0; border-bottom:1px solid var(--n-border-color); }</style>
