<script setup lang="ts">
import { NButton, NCard, NDivider, NEmpty, NSpace, NSwitch, NTag, NTooltip } from 'naive-ui'
import type { GroupPlugin } from '../api/types'

withDefaults(defineProps<{ plugin: GroupPlugin; groupId?: string; groupName?: string; busyKeys?: Record<string, boolean> }>(), { groupId: '', groupName: '', busyKeys: () => ({}) })
const emit = defineEmits<{
  toggle: [key: string, enabled: boolean]
  reset: [key: string]
  edit: [shortName: string]
  global: [shortName: string]
  invite: []
}>()
</script>

<template>
  <NCard size="small">
    <template #header>
      <NSpace align="center">
        <strong>{{ plugin.name }}</strong>
        <NTag size="small" :type="plugin.loaded ? 'success' : 'error'">{{ plugin.loaded ? '已加载' : '不可用' }}</NTag>
      </NSpace>
    </template>
    <NEmpty v-if="!plugin.loaded" :description="plugin.unavailable_reason || '插件未加载'" size="small" />
    <template v-else>
      <div v-for="feature in plugin.features" :key="feature.key" class="feature-row">
        <div>
          <div>{{ feature.name || feature.key }}</div>
          <NSpace size="small">
            <span class="muted">{{ feature.source ? `来源：${feature.source}` : feature.scope === 'system' ? '系统功能，始终启用' : '' }}</span>
            <NTag v-if="feature.active_whitelist_match !== undefined" size="tiny" :type="feature.active_whitelist_match ? 'success' : 'default'">
              当前白名单{{ feature.active_whitelist_match ? '命中' : '未命中' }}
            </NTag>
            <NTag v-if="feature.actual_effective !== undefined" size="tiny" :type="feature.actual_effective ? 'success' : 'warning'">
              实际{{ feature.actual_effective ? '生效' : '未生效' }}
            </NTag>
          </NSpace>
        </div>
        <NSpace align="center" :wrap="false">
          <NTooltip v-if="feature.resettable"><template #trigger><NButton quaternary size="tiny" :aria-label="`${groupName || `群 ${groupId}`}的${feature.name || feature.key}：恢复默认`" :disabled="busyKeys[feature.key]" @click="emit('reset', feature.key)">恢复默认</NButton></template>删除本群覆盖，重新继承全局默认</NTooltip>
          <NSwitch :value="feature.effective ?? feature.enabled" :aria-label="`${groupName || `群 ${groupId}`}的${feature.name || feature.key}开关`" :loading="busyKeys[feature.key]" :disabled="feature.scope === 'system' || Boolean(feature.unavailable_reason)" @update:value="emit('toggle', feature.key, $event)" />
        </NSpace>
      </div>
      <NDivider v-if="plugin.invite || plugin.group_config || plugin.global_config" />
      <NSpace>
        <NButton v-if="plugin.group_config" size="small" @click="emit('edit', plugin.short_name)">编辑本群参数</NButton>
        <NButton v-if="plugin.global_config" size="small" secondary @click="emit('global', plugin.short_name)">参数为全局设置</NButton>
        <NButton v-if="plugin.invite?.applicable" size="small" @click="emit('invite')">邀请码自助：{{ plugin.invite.enabled ? '已开启' : '已关闭' }}</NButton>
        <NTag v-if="plugin.invite?.applicable && !plugin.invite.initialized" size="small" type="warning">需先在 QQ 使用 /invite init 初始化</NTag>
        <NTag v-if="plugin.invite?.applicable && plugin.invite.initialized && !plugin.invite.configuration_complete" size="small" type="warning">部署参数不完整</NTag>
        <NTag v-else-if="plugin.invite && !plugin.invite.applicable" size="small">仅绑定群 {{ plugin.invite.bound_group_id || '未配置' }} 可用</NTag>
      </NSpace>
    </template>
  </NCard>
</template>

<style scoped>
.feature-row { min-height: 48px; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
</style>
