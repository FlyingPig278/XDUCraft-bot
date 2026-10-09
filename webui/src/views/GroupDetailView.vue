<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { NAlert, NButton, NBreadcrumb, NBreadcrumbItem, NCard, NEmpty, NSpace, NSpin, NTag, useDialog, useMessage } from 'naive-ui'
import PluginCard from '../components/PluginCard.vue'
import GroupIdentity from '../components/GroupIdentity.vue'
import HappyBotForm from '../components/forms/HappyBotForm.vue'
import KeywordConfigForm from '../components/forms/KeywordConfigForm.vue'
import McStatusForm from '../components/forms/McStatusForm.vue'
import { ApiError, apiGet, apiWrite } from '../api/client'
import type { FeatureConfig, FeatureMeta, GroupPluginsResponse, GroupSummary, GroupsResponse, InviteConfig, InviteMeta, Resource } from '../api/types'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const response = ref<GroupPluginsResponse | null>(null)
const groupName = ref('')
const groupSummary = ref<GroupSummary | null>(null)
const loading = ref(false)
const busyKeys = ref<Record<string, boolean>>({})
const groupId = computed(() => String(route.params.groupId))
const selectedPlugin = computed(() => typeof route.params.plugin === 'string' ? route.params.plugin : '')
const title = computed(() => `${groupName.value || `群 ${groupId.value}`} · ${groupId.value}`)

async function load(): Promise<void> {
  loading.value = true
  try {
    response.value = await apiGet<GroupPluginsResponse>(`/api/groups/${encodeURIComponent(groupId.value)}/plugins`)
    try {
      const all = await apiGet<GroupsResponse>('/api/groups')
      groupSummary.value = all.groups.find((group) => group.group_id === groupId.value) ?? null
      groupName.value = groupSummary.value?.name ?? ''
    } catch { groupSummary.value = null; groupName.value = '' }
  } catch (error) { message.error(error instanceof Error ? error.message : '读取群插件失败') }
  finally { loading.value = false }
}
function editPlugin(shortName: string): void { router.push(`/groups/${encodeURIComponent(groupId.value)}/${shortName}`) }
function openGlobal(shortName: string): void { router.push(`/settings/runtime?plugin=${encodeURIComponent(shortName)}`) }
async function toggleFeature(key: string, enabled: boolean): Promise<void> {
  busyKeys.value = { ...busyKeys.value, [key]: true }
  const path = `/api/groups/${encodeURIComponent(groupId.value)}/features/${encodeURIComponent(key)}`
  try {
    const current = await apiGet<Resource<FeatureConfig, FeatureMeta>>(path)
    await apiWrite<Resource<FeatureConfig, FeatureMeta>>(path, 'PUT', { enabled }, current.revision)
    message.success(`${enabled ? '已开启' : '已关闭'} ${key}`)
    await load()
  } catch (error) { message.error(error instanceof Error ? error.message : '开关保存失败') }
  finally { const next = { ...busyKeys.value }; delete next[key]; busyKeys.value = next }
}
async function resetFeature(key: string): Promise<void> {
  busyKeys.value = { ...busyKeys.value, [key]: true }
  const path = `/api/groups/${encodeURIComponent(groupId.value)}/features/${encodeURIComponent(key)}`
  try {
    const current = await apiGet<Resource<FeatureConfig, FeatureMeta>>(path)
    await apiWrite<Resource<FeatureConfig, FeatureMeta>>(path, 'DELETE', undefined, current.revision)
    message.success('已恢复全局默认')
    await load()
  } catch (error) { message.error(error instanceof Error ? error.message : '恢复失败') }
  finally { const next = { ...busyKeys.value }; delete next[key]; busyKeys.value = next }
}
async function manageInvite(): Promise<void> {
  const path = `/api/groups/${encodeURIComponent(groupId.value)}/invite`
  try {
    const current = await apiGet<Resource<InviteConfig, InviteMeta>>(path)
    const enabled = !current.config.enabled
    dialog.warning({
      title: `${enabled ? '开启' : '关闭'}邀请码自助`,
      content: enabled && !current.meta.initialized ? '邀请码尚未通过 QQ /invite init 初始化，无法开启。' : `确定${enabled ? '开启' : '关闭'}本群邀请码自助吗？`,
      positiveText: '确认', negativeText: '取消', positiveButtonProps: { disabled: enabled && !current.meta.initialized },
      onPositiveClick: async () => {
        try { await apiWrite(path, 'PUT', { enabled }, current.revision); message.success('邀请码设置已保存'); await load() }
        catch (error) { message.error(error instanceof Error ? error.message : '保存邀请码设置失败') }
      }
    })
  } catch (error) {
    const text = error instanceof ApiError && error.code === 'invite_group_not_bound' ? '当前群不是邀请码绑定群' : error instanceof Error ? error.message : '读取邀请码设置失败'
    message.error(text)
  }
}
watch(groupId, load)
onMounted(load)
</script>

<template>
  <main class="page">
    <NBreadcrumb><NBreadcrumbItem><RouterLink to="/groups">群管理</RouterLink></NBreadcrumbItem><NBreadcrumbItem>{{ title }}</NBreadcrumbItem></NBreadcrumb>
    <div class="group-title">
      <GroupIdentity :group-id="groupId" :name="groupName || `群 ${groupId}`" :size="68" name-tag="h1" eager />
      <NSpace v-if="groupSummary" class="group-status">
        <NTag size="small" :type="groupSummary.connected ? 'success' : groupSummary.stale ? 'warning' : 'default'">
          {{ groupSummary.connected ? '当前在线' : groupSummary.stale ? '最近连接（缓存）' : '仅历史配置' }}
        </NTag>
        <span v-if="groupSummary.bot_ids.length" class="muted">关联 Bot：{{ groupSummary.bot_ids.join('、') }}</span>
      </NSpace>
    </div>
    <p class="page-subtitle">每次保存只修改上方这个群或明确标记的全局资源。</p>
    <NAlert v-for="warning in response?.warnings" :key="warning" type="warning" class="detail-warning">{{ warning }}</NAlert>
    <NSpace v-if="selectedPlugin" class="back-row"><NButton @click="router.push(`/groups/${encodeURIComponent(groupId)}`)">← 返回插件列表</NButton></NSpace>
    <NSpin :show="loading">
      <div v-if="!selectedPlugin" class="card-grid">
        <PluginCard v-for="plugin in response?.plugins" :key="plugin.id" :plugin="plugin" :group-id="groupId" :group-name="groupName || `群 ${groupId}`" :busy-keys="busyKeys" @toggle="toggleFeature" @reset="resetFeature" @edit="editPlugin" @global="openGlobal" @invite="manageInvite" />
        <NEmpty v-if="response && !response.plugins.length" description="没有插件信息" />
      </div>
      <McStatusForm v-else-if="selectedPlugin === 'mc_status'" :key="`mc-${groupId}`" :group-id="groupId" />
      <KeywordConfigForm v-else-if="selectedPlugin === 'keyword'" :key="`keyword-${groupId}`" :group-id="groupId" />
      <HappyBotForm v-else-if="selectedPlugin === 'happy_bot'" :key="`happy-${groupId}`" :group-id="groupId" />
      <NCard v-else><NEmpty description="此插件没有本群参数表单"><template #extra><NButton @click="router.push(`/groups/${encodeURIComponent(groupId)}`)">返回</NButton></template></NEmpty></NCard>
    </NSpin>
  </main>
</template>
<style scoped>
.group-title { display: flex; align-items: center; justify-content: space-between; gap: 16px; min-width: 0; margin: 16px 0 10px; }
.group-status { flex: 0 1 auto; justify-content: flex-end; }
.detail-warning { margin-bottom: 10px; }
.back-row { margin-bottom: 16px; }
@media (max-width: 599px) {
  .group-title { align-items: flex-start; flex-direction: column; }
  .group-status { justify-content: flex-start; }
}
</style>
