<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NAlert, NButton, NCard, NEmpty, NInput, NSpin, useMessage } from 'naive-ui'
import { apiGet } from '../api/client'
import type { GroupSummary, GroupsResponse } from '../api/types'
import GroupIdentity from '../components/GroupIdentity.vue'

const router = useRouter()
const message = useMessage()
const groups = ref<GroupSummary[]>([])
const warnings = ref<string[]>([])
const error = ref('')
const search = ref('')
const loading = ref(false)
let generation = 0
onUnmounted(() => { generation++ })
const matchingGroups = computed(() => {
  const query = search.value.trim().toLocaleLowerCase()
  return query
    ? groups.value.filter((group) => group.group_id.includes(query) || group.name.toLocaleLowerCase().includes(query))
    : groups.value
})
const currentGroups = computed(() => matchingGroups.value.filter((group) => group.connected || group.stale))
const configuredGroups = computed(() => matchingGroups.value.filter((group) => !group.connected && !group.stale))

async function load(): Promise<void> {
  const token = ++generation
  loading.value = true
  error.value = ''
  try {
    const response = await apiGet<GroupsResponse>('/api/groups')
    if (token !== generation) return
    groups.value = response.groups
    warnings.value = response.warnings
  } catch (caught) {
    if (token !== generation) return
    error.value = caught instanceof Error ? caught.message : '读取群列表失败'
    message.error(error.value)
  } finally {
    if (token === generation) loading.value = false
  }
}
function openGroup(groupId: string): void {
  router.push(`/groups/${encodeURIComponent(groupId)}`)
}
function connectionText(group: GroupSummary): string {
  if (error.value) return '上次成功的目录，当前连接未确认'
  if (group.connected) return '当前可连接'
  if (group.stale) return '使用最近一次获取的群信息'
  return '当前未连接，来自已有配置'
}
onMounted(load)
</script>

<template>
  <main class="page groups-page">
    <div class="page-intro">
      <div>
        <h1 class="page-heading">选择一个群开始管理</h1>
        <p class="page-subtitle">进入群工作台后，可直接在插件之间切换，不必反复返回此页。</p>
      </div>
      <NButton secondary :loading="loading" @click="load">刷新群列表</NButton>
    </div>

    <NAlert v-if="error" type="error" class="group-warning">
      {{ error }}
      <NButton size="small" @click="load">重试</NButton>
    </NAlert>
    <NAlert v-for="warning in warnings" :key="warning" type="warning" class="group-warning">{{ warning }}</NAlert>

    <NCard class="group-finder">
      <div class="finder-fields">
        <div class="finder-field">
          <label for="group-search">搜索已发现的群</label>
          <NInput id="group-search" v-model:value="search" clearable placeholder="输入群名或群号" />
        </div>
      </div>
    </NCard>

    <NSpin :show="loading">
      <section class="group-section" aria-labelledby="recent-groups">
        <div class="section-heading">
          <div>
            <h2 id="recent-groups">当前与最近连接</h2>
            <p>优先显示 Bot 当前能识别的群；断开后仍保留最近成功获取的名称。</p>
          </div>
          <span>{{ currentGroups.length }} 个</span>
        </div>
        <div v-if="currentGroups.length" class="group-list">
          <button
            v-for="group in currentGroups"
            :key="group.group_id"
            type="button"
            class="group-row"
            :aria-label="`打开${group.name}的插件工作台`"
            @click="openGroup(group.group_id)"
          >
            <GroupIdentity :group-id="group.group_id" :name="group.name" />
            <span class="row-status">
              <span class="connection-dot" :class="{ online: group.connected && !error }" />
              {{ connectionText(group) }}
            </span>
            <span class="row-action">管理插件 →</span>
          </button>
        </div>
        <NEmpty v-else :description="search ? '没有匹配的当前或最近连接群' : '尚未发现可连接的群'" />
      </section>

      <section class="group-section configured-section" aria-labelledby="configured-groups">
        <div class="section-heading">
          <div>
            <h2 id="configured-groups">仅有历史配置</h2>
            <p>这些群目前没有连接信息；打开前请核对灰色群号。</p>
          </div>
          <span>{{ configuredGroups.length }} 个</span>
        </div>
        <div v-if="configuredGroups.length" class="group-list">
          <button
            v-for="group in configuredGroups"
            :key="group.group_id"
            type="button"
            class="group-row configured-row"
            :aria-label="`查看${group.name}的已有配置`"
            @click="openGroup(group.group_id)"
          >
            <GroupIdentity :group-id="group.group_id" :name="group.name" />
            <span class="row-status"><span class="connection-dot" />{{ connectionText(group) }}</span>
            <span class="row-action">查看配置 →</span>
          </button>
        </div>
        <NEmpty v-else :description="search ? '没有匹配的历史配置群' : '没有仅含历史配置的群'" />
      </section>
    </NSpin>
  </main>
</template>

<style scoped>
.groups-page { width: min(980px, 100%); }
.page-intro, .section-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.page-intro { align-items: flex-start; }
.group-warning { margin-bottom: 10px; }
.group-finder { margin-bottom: 26px; }
.finder-fields { align-items: flex-end; }
.finder-field { min-width: 0; flex: 1; }
.finder-field label { display: block; margin-bottom: 7px; font-size: 13px; font-weight: 650; }
.group-section { min-width: 0; }
.configured-section { margin-top: 30px; padding-top: 26px; border-top: 1px solid color-mix(in srgb, currentColor 12%, transparent); }
.section-heading { align-items: flex-start; margin-bottom: 12px; }
.section-heading h2 { margin: 0; font-size: 18px; }
.section-heading p { margin: 5px 0 0; opacity: .66; }
.section-heading > span { flex: 0 0 auto; opacity: .55; }
.group-list { overflow: hidden; border: 1px solid color-mix(in srgb, currentColor 13%, transparent); border-radius: 12px; }
.group-row {
  width: 100%;
  display: grid;
  grid-template-columns: minmax(220px, 1fr) minmax(180px, auto) auto;
  align-items: center;
  gap: 18px;
  padding: 15px 17px;
  border: 0;
  color: inherit;
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.group-row + .group-row { border-top: 1px solid color-mix(in srgb, currentColor 10%, transparent); }
.group-row:hover { background: color-mix(in srgb, #2080f0 7%, transparent); }
.group-row:focus-visible { outline: 2px solid #2080f0; outline-offset: -2px; }
.configured-row { background: color-mix(in srgb, currentColor 2%, transparent); }
.row-status { display: flex; align-items: center; gap: 7px; color: #888; font-size: 12px; }
.connection-dot { flex: 0 0 auto; width: 8px; height: 8px; border-radius: 50%; background: #aaa; }
.connection-dot.online { background: #18a058; }
.row-action { color: #2080f0; font-weight: 600; white-space: nowrap; }
@media (max-width: 699px) {
  .page-intro { align-items: stretch; flex-direction: column; }
  .group-row { grid-template-columns: minmax(0, 1fr); gap: 9px; }
  .row-action { justify-self: start; }
}
</style>
