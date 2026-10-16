<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NAlert, NButton, NEmpty, NIcon, NInput, NSpin, useMessage } from 'naive-ui'
import { RefreshOutline, SearchOutline } from '@vicons/ionicons5'
import { apiGet } from '../api/client'
import type { GroupSummary, GroupsResponse } from '../api/types'
import GroupIdentity from '../components/GroupIdentity.vue'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const groups = ref<GroupSummary[]>([])
const warnings = ref<string[]>([])
const error = ref('')
const search = ref(typeof route.query.q === 'string' ? route.query.q : '')
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
    await nextTick()
    const savedScroll = Number(sessionStorage.getItem('xducraft-groups-scroll') ?? '0')
    if (Number.isFinite(savedScroll) && savedScroll > 0) window.scrollTo({ top: savedScroll })
  } catch (caught) {
    if (token !== generation) return
    error.value = caught instanceof Error ? caught.message : '读取群列表失败'
    message.error(error.value)
  } finally {
    if (token === generation) loading.value = false
  }
}
function openGroup(groupId: string): void {
  sessionStorage.setItem('xducraft-groups-scroll', String(window.scrollY))
  void router.push({ name: 'group-plugins', params: { groupId }, query: search.value.trim() ? { groups: search.value.trim() } : {} })
}
function connectionText(group: GroupSummary): string {
  if (error.value) return '连接未确认'
  if (group.connected) return '在线'
  if (group.stale) return '最近连接'
  return '离线'
}
watch(search, value => {
  const query = value.trim()
  void router.replace({ name: 'groups', query: query ? { q: query } : {} })
})
watch(() => route.query.q, (newQ) => {
  const val = typeof newQ === 'string' ? newQ : ''
  if (val !== search.value) search.value = val
})
onMounted(load)
</script>

<template>
  <main class="page groups-page">
    <div class="page-intro">
      <div>
        <h1 class="page-heading">群聊</h1>
      </div>
      <NButton secondary :loading="loading" @click="load"><template #icon><NIcon :component="RefreshOutline" /></template>刷新群列表</NButton>
    </div>

    <NAlert v-if="error" type="error" class="group-warning">
      {{ error }}
      <NButton size="small" @click="load">重试</NButton>
    </NAlert>
    <NAlert v-for="warning in warnings" :key="warning" type="warning" class="group-warning">{{ warning }}</NAlert>

    <div class="group-finder">
      <NInput id="group-search" v-model:value="search" clearable aria-label="搜索群聊" placeholder="搜索群名或群号">
        <template #prefix><NIcon :component="SearchOutline" /></template>
      </NInput>
    </div>

    <NSpin :show="loading" :class="{ 'spin-container-min': loading && !groups.length }">
      <section v-if="currentGroups.length" class="group-section" aria-labelledby="recent-groups">
        <div class="section-heading">
          <div>
            <h2 id="recent-groups">{{ currentGroups.some(group => group.connected) ? '已连接' : '最近群聊' }}</h2>
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
            <span class="row-action" aria-hidden="true">→</span>
          </button>
        </div>
      </section>

      <section v-if="configuredGroups.length" class="group-section configured-section" aria-labelledby="configured-groups">
        <div class="section-heading">
          <div>
            <h2 id="configured-groups">历史配置 · 未连接</h2>
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
            <span class="row-action" aria-hidden="true">→</span>
          </button>
        </div>
      </section>
      <NEmpty v-if="!loading && !matchingGroups.length" :description="search ? '没有匹配的群聊' : '尚未获取群聊，请连接 QQ 后刷新'">
        <template v-if="search" #extra><NButton size="small" secondary @click="search = ''">清空搜索条件</NButton></template>
      </NEmpty>
    </NSpin>
  </main>
</template>

<style scoped>
.groups-page { width: min(980px, 100%); }
.page-intro, .section-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.page-intro { align-items: flex-start; }
.group-warning { margin-bottom: 10px; }
.group-finder { margin-bottom:20px; }
.group-section { min-width: 0; }
.group-section + .configured-section { margin-top:24px; padding-top:20px; border-top:1px solid color-mix(in srgb,currentColor 12%,transparent); }
.section-heading { align-items: flex-start; margin-bottom: 12px; }
.section-heading h2 { margin: 0; font-size: 18px; }
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
.configured-row .row-action { grid-column: 3; }
.row-status { display: flex; align-items: center; gap: 7px; opacity: .72; font-size: 12px; }
.connection-dot { flex: 0 0 auto; width: 8px; height: 8px; border-radius: 50%; background: color-mix(in srgb, currentColor 32%, transparent); }
.connection-dot.online { background: #18a058; }
.row-action { color: #2080f0; font-weight: 600; white-space: nowrap; }
@media (max-width: 699px) {
  .page-intro { align-items:center; }
  .group-row { grid-template-columns:minmax(0,1fr) auto; gap:6px 12px; padding:13px; }
  .row-status { grid-column:1; grid-row:2; margin-left:70px; }
  .configured-row .row-action { grid-column: 2; grid-row: 1; }
  .row-action { grid-column:2; grid-row:1 / span 2; }
}
</style>
