<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NAlert, NButton, NCard, NCollapse, NCollapseItem, NEmpty, NInput, NSpace, NSpin, NTag, useMessage } from 'naive-ui'
import { apiGet } from '../api/client'
import type { GroupSummary, GroupsResponse } from '../api/types'
import GroupIdentity from '../components/GroupIdentity.vue'

const router = useRouter()
const message = useMessage()
const groups = ref<GroupSummary[]>([])
const warnings = ref<string[]>([])
const error = ref('')
const search = ref('')
const manualId = ref('')
const loading = ref(false)
const matchingGroups = computed(() => {
  const query = search.value.trim().toLocaleLowerCase()
  return query ? groups.value.filter((group) => group.group_id.includes(query) || group.name.toLocaleLowerCase().includes(query)) : groups.value
})
const currentGroups = computed(() => matchingGroups.value.filter((group) => group.connected || group.stale))
const historicalGroups = computed(() => matchingGroups.value.filter((group) => !group.connected && !group.stale))

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const response = await apiGet<GroupsResponse>('/api/groups')
    groups.value = response.groups
    warnings.value = response.warnings
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '读取群列表失败'
    message.error(error.value)
  } finally {
    loading.value = false
  }
}
function openGroup(groupId: string): void { router.push(`/groups/${encodeURIComponent(groupId)}`) }
function openManual(): void {
  const value = manualId.value.trim()
  if (!/^[1-9]\d*$/.test(value)) { message.warning('请输入正整数群号'); return }
  openGroup(value)
}
function statusLabel(group: GroupSummary): string {
  return group.connected ? '当前在线' : group.stale ? '最近连接（缓存）' : '仅历史配置'
}
onMounted(load)
</script>

<template>
  <main class="page">
    <h1 class="page-heading">群管理</h1>
    <p class="page-subtitle">已加入和最近连接的 QQ 群会自动显示；历史配置群单独列出。</p>
    <NAlert v-if="error" type="error" class="group-warning">
      {{ error }}
      <NButton size="small" @click="load">重试</NButton>
    </NAlert>
    <NAlert v-for="warning in warnings" :key="warning" type="warning" class="group-warning">{{ warning }}</NAlert>

    <NCard class="group-tools">
      <div class="toolbar">
        <NInput v-model:value="search" clearable placeholder="按群号或群名搜索" aria-label="搜索 QQ 群" class="search-input" />
        <NButton secondary :loading="loading" @click="load">刷新群列表</NButton>
      </div>
      <NCollapse>
        <NCollapseItem title="高级：打开未出现在列表中的群" name="manual">
          <p class="muted advanced-help">仅在群暂未被 Bot 或现有配置发现时使用。</p>
          <NSpace class="manual-row">
            <NInput v-model:value="manualId" placeholder="输入 QQ 群号" aria-label="手动输入 QQ 群号" @keyup.enter="openManual" />
            <NButton @click="openManual">打开群</NButton>
          </NSpace>
        </NCollapseItem>
      </NCollapse>
    </NCard>

    <NSpin :show="loading">
      <section aria-labelledby="current-groups-heading" class="group-section">
        <div class="section-heading">
          <div>
            <h2 id="current-groups-heading">当前与最近连接的群</h2>
            <p class="muted">在线群优先显示；暂时离线时保留最近成功获取的群名。</p>
          </div>
          <NTag>{{ currentGroups.length }} 个群</NTag>
        </div>
        <div v-if="currentGroups.length" class="group-grid">
          <NCard v-for="group in currentGroups" :key="group.group_id" size="small" class="group-card" role="article">
            <GroupIdentity :group-id="group.group_id" :name="group.name" name-tag="h3" />
            <div class="card-meta">
              <NTag size="small" :type="group.connected ? 'success' : 'warning'">{{ statusLabel(group) }}</NTag>
              <span class="muted bot-list">关联 Bot：{{ group.bot_ids.join('、') || '—' }}</span>
            </div>
            <NButton block secondary :aria-label="`管理群 ${group.name}（${group.group_id}）`" @click="openGroup(group.group_id)">管理此群</NButton>
          </NCard>
        </div>
        <NEmpty v-else :description="search ? '没有匹配的当前或缓存群' : '尚未发现当前或缓存群'" />
      </section>

      <section aria-labelledby="historical-groups-heading" class="group-section historical-section">
        <div class="section-heading">
          <div>
            <h2 id="historical-groups-heading">历史配置群</h2>
            <p class="muted">这些群仅来自已有插件配置，目前没有在线或缓存的 Bot 群记录。</p>
          </div>
          <NTag type="default">{{ historicalGroups.length }} 个群</NTag>
        </div>
        <div v-if="historicalGroups.length" class="group-grid">
          <NCard v-for="group in historicalGroups" :key="group.group_id" size="small" class="group-card historical-card" role="article">
            <GroupIdentity :group-id="group.group_id" :name="group.name" name-tag="h3" />
            <div class="card-meta">
              <NTag size="small">{{ statusLabel(group) }}</NTag>
              <span class="muted">修改前请确认群号。</span>
            </div>
            <NButton block tertiary :aria-label="`管理历史配置群 ${group.name}（${group.group_id}）`" @click="openGroup(group.group_id)">查看已有配置</NButton>
          </NCard>
        </div>
        <NEmpty v-else :description="search ? '没有匹配的历史配置群' : '没有历史配置群'" />
      </section>
    </NSpin>
  </main>
</template>

<style scoped>
.group-warning { margin-bottom: 10px; }
.group-tools { margin-bottom: 22px; }
.search-input { width: min(420px, 100%); }
.advanced-help { margin: 0 0 10px; }
.manual-row { width: min(460px, 100%); }
.manual-row :deep(.n-input) { min-width: min(280px, 100%); }
.group-section { min-width: 0; }
.historical-section { margin-top: 30px; padding-top: 24px; border-top: 1px solid color-mix(in srgb, currentColor 14%, transparent); }
.section-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
.section-heading h2 { margin: 0 0 4px; font-size: 19px; }
.section-heading p { margin: 0; }
.group-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(300px, 100%), 1fr)); gap: 14px; min-width: 0; }
.group-card { min-width: 0; }
.historical-card { border-style: dashed; }
.card-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; min-width: 0; margin: 16px 0; }
.bot-list { min-width: 0; overflow-wrap: anywhere; }
@media (max-width: 599px) {
  .group-grid { grid-template-columns: minmax(0, 1fr); }
  .section-heading { align-items: center; }
  .manual-row { display: flex; flex-direction: column; align-items: stretch; }
  .manual-row :deep(.n-space__item) { width: 100%; }
}
</style>
