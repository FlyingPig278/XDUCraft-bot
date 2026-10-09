<script setup lang="ts">
import { computed, onMounted, ref, toRaw } from 'vue'
import {
  NAlert, NButton, NDynamicTags, NForm, NFormItem, NInput, NInputNumber, NSelect, NSpace, NSwitch,
  NTag, useDialog, useMessage
} from 'naive-ui'
import ConfigFormShell from '../ConfigFormShell.vue'
import { ApiError, apiGet, apiWrite } from '../../api/client'
import type { DeploymentConfig, DeploymentMeta, DeploymentPublicConfig, DeploymentSetKey, DeploymentWrite, Resource } from '../../api/types'

const emit = defineEmits<{ restart: [value: boolean] }>()
const dialog = useDialog()
const message = useMessage()
const draft = ref<DeploymentPublicConfig | null>(null)
const saved = ref<DeploymentPublicConfig | null>(null)
const meta = ref<DeploymentMeta | null>(null)
const revision = ref('')
const loading = ref(false)
const saving = ref(false)
const stale = ref(false)
const errors = ref<Record<string, string | string[]>>({})
const unsetKeys = ref<DeploymentSetKey[]>([])
const secret = ref('')
const clearSecret = ref(false)
const publicKeys: Array<Exclude<keyof DeploymentPublicConfig, 'invite_api_secret_configured'>> = [
  'mcs_brand', 'mcs_title', 'mcs_credit', 'mcs_show_generated_at', 'mcs_texture', 'mcs_width', 'mcs_scale',
  'mcs_min_height', 'invite_group_id', 'invite_api_url', 'auto_accept_friend_group_ids'
]
const dirty = computed(() => Boolean(draft.value && saved.value && (JSON.stringify(draft.value) !== JSON.stringify(saved.value) || unsetKeys.value.length || secret.value || clearSecret.value)))
const textureOptions = computed(() => [
  { label: '随机材质', value: 'random' }, { label: '不使用材质', value: 'none' }, { label: '渲染器默认', value: '' },
  ...(meta.value?.textures ?? []).map((value) => ({ label: value, value }))
])
const unavailableMc = computed(() => meta.value?.unavailable.includes('mc_status') || meta.value?.unavailable.includes('mc'))
const active = computed(() => meta.value?.active)

function display(value: unknown): string {
  if (value === null || value === undefined) return '不可用'
  if (Array.isArray(value)) return value.length ? value.join('、') : '空列表'
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value) || '空字符串'
}
function isChanged(key: DeploymentSetKey): boolean { return meta.value?.changed_keys.includes(key) ?? false }
function isOverridden(key: DeploymentSetKey): boolean { return meta.value?.overridden.includes(key) ?? false }
function fieldClass(key: DeploymentSetKey): string { return isChanged(key) ? 'deployment-field difference' : 'deployment-field' }
function fieldHint(key: Exclude<keyof DeploymentPublicConfig, 'invite_api_secret_configured'>): string {
  const current = active.value?.[key]
  return `当前运行：${display(current)} · ${isOverridden(key) ? '网页覆盖' : '环境/默认值'}`
}
function restoreEnvironment(key: DeploymentSetKey): void {
  if (!unsetKeys.value.includes(key)) unsetKeys.value.push(key)
}
function cancelRestore(key: DeploymentSetKey): void { unsetKeys.value = unsetKeys.value.filter((item) => item !== key) }
function askClearSecret(): void {
  dialog.warning({ title: '清空邀请码 API 密钥', content: '保存后，下次重启会使用空密钥。确定加入本次修改吗？', positiveText: '清空', negativeText: '取消', onPositiveClick: () => { clearSecret.value = true; secret.value = ''; cancelRestore('invite_api_secret') } })
}
function restoreSecret(): void { restoreEnvironment('invite_api_secret'); secret.value = ''; clearSecret.value = false }

async function load(): Promise<void> {
  loading.value = true
  errors.value = {}
  try {
    const resource = await apiGet<Resource<DeploymentConfig, DeploymentMeta>>('/api/deployment')
    saved.value = structuredClone(resource.config.pending)
    draft.value = structuredClone(resource.config.pending)
    meta.value = resource.meta
    revision.value = resource.revision
    unsetKeys.value = []
    secret.value = ''
    clearSecret.value = false
    stale.value = false
    emit('restart', resource.meta.restart_required)
  } catch (error) {
    const text = error instanceof Error ? error.message : '读取部署设置失败'
    errors.value = { resource: text }
    message.error(text)
  }
  finally { loading.value = false }
}
function discard(): void {
  draft.value = saved.value ? structuredClone(toRaw(saved.value)) : null
  unsetKeys.value = []
  secret.value = ''
  clearSecret.value = false
  errors.value = {}
  stale.value = false
}
async function save(): Promise<void> {
  if (!draft.value || !saved.value || !revision.value) return
  const body: DeploymentWrite = { set: {}, unset: [...unsetKeys.value] }
  for (const key of publicKeys) {
    if (unsetKeys.value.includes(key)) continue
    if (JSON.stringify(draft.value[key]) !== JSON.stringify(saved.value[key]) && draft.value[key] !== null) {
      ;(body.set as Record<DeploymentSetKey, string | number | boolean | string[]>)[key] = draft.value[key] as string | number | boolean | string[]
    }
  }
  if (!unsetKeys.value.includes('invite_api_secret')) {
    if (clearSecret.value) body.set.invite_api_secret = ''
    else if (secret.value) body.set.invite_api_secret = secret.value
  }
  saving.value = true
  errors.value = {}
  try {
    const resource = await apiWrite<Resource<DeploymentConfig, DeploymentMeta>>('/api/deployment', 'PUT', body, revision.value)
    saved.value = structuredClone(resource.config.pending)
    draft.value = structuredClone(resource.config.pending)
    meta.value = resource.meta
    revision.value = resource.revision
    unsetKeys.value = []
    secret.value = ''
    clearSecret.value = false
    stale.value = false
    emit('restart', resource.meta.restart_required)
    message.success(resource.meta.restart_required ? '已保存，重启机器人后生效' : '部署覆盖已保存')
  } catch (error) {
    if (error instanceof ApiError) {
      errors.value = error.fields
      if (error.status === 409 && error.code === 'stale_config') stale.value = true
    }
    message.error(error instanceof Error ? error.message : '保存部署设置失败')
  } finally { saving.value = false }
}
onMounted(load)
</script>

<template>
  <ConfigFormShell form-id="deployment" title="部署期设置" description="保存只写入待生效覆盖，不会热更新当前客户端、字体、纹理或密钥。" :loading="loading" :saving="saving" :dirty="dirty" :stale="stale" :errors="errors" @save="save" @discard="discard" @reload="load">
    <NAlert v-if="meta?.restart_required" type="warning" class="deployment-alert">已保存的值与当前运行值不同，请在合适时间手动重启机器人。面板不提供重启操作。</NAlert>
    <NAlert v-if="meta?.unavailable.length" type="warning" class="deployment-alert">不可用插件：{{ meta.unavailable.join('、') }}。相应运行值可能无法显示，但仍可保存明确覆盖（材质候选除外）。</NAlert>
    <NAlert v-if="unsetKeys.length" type="info" class="deployment-alert">
      将恢复环境值：{{ unsetKeys.join('、') }}
      <NSpace><NButton v-for="key in unsetKeys" :key="key" size="tiny" @click="cancelRestore(key)">撤销 {{ key }}</NButton></NSpace>
    </NAlert>
    <NForm v-if="draft" label-placement="top"><div class="form-grid">
      <NFormItem label="MC 品牌" :class="fieldClass('mcs_brand')"><NInput :value="draft.mcs_brand ?? ''" @update:value="draft.mcs_brand = $event" /><template #feedback>{{ fieldHint('mcs_brand') }} <NButton v-if="isOverridden('mcs_brand')" text type="primary" @click="restoreEnvironment('mcs_brand')">恢复环境值</NButton><NTag v-if="unsetKeys.includes('mcs_brand')" size="tiny">待恢复 <span @click="cancelRestore('mcs_brand')">撤销</span></NTag></template></NFormItem>
      <NFormItem label="MC 标题" :class="fieldClass('mcs_title')"><NInput :value="draft.mcs_title ?? ''" @update:value="draft.mcs_title = $event" /><template #feedback>{{ fieldHint('mcs_title') }} <NButton v-if="isOverridden('mcs_title')" text type="primary" @click="restoreEnvironment('mcs_title')">恢复环境值</NButton></template></NFormItem>
      <NFormItem label="MC 署名" :class="fieldClass('mcs_credit')"><NInput :value="draft.mcs_credit ?? ''" @update:value="draft.mcs_credit = $event" /><template #feedback>{{ fieldHint('mcs_credit') }} <NButton v-if="isOverridden('mcs_credit')" text type="primary" @click="restoreEnvironment('mcs_credit')">恢复环境值</NButton></template></NFormItem>
      <NFormItem label="MC 材质" :class="fieldClass('mcs_texture')"><NSelect v-model:value="draft.mcs_texture" :options="textureOptions" :disabled="unavailableMc" /><template #feedback>{{ unavailableMc ? 'MC 插件未加载，无法校验材质文件' : fieldHint('mcs_texture') }} <NButton v-if="isOverridden('mcs_texture')" text type="primary" @click="restoreEnvironment('mcs_texture')">恢复环境值</NButton></template></NFormItem>
      <NFormItem label="渲染宽度（480–1600）" :class="fieldClass('mcs_width')"><NInputNumber v-model:value="draft.mcs_width" :min="480" :max="1600" :precision="0" /><template #feedback>{{ fieldHint('mcs_width') }} <NButton v-if="isOverridden('mcs_width')" text type="primary" @click="restoreEnvironment('mcs_width')">恢复环境值</NButton></template></NFormItem>
      <NFormItem label="渲染倍率" :class="fieldClass('mcs_scale')"><NSelect v-model:value="draft.mcs_scale" :options="[{label:'2×',value:2},{label:'4×',value:4}]" /><template #feedback>{{ fieldHint('mcs_scale') }} <NButton v-if="isOverridden('mcs_scale')" text type="primary" @click="restoreEnvironment('mcs_scale')">恢复环境值</NButton></template></NFormItem>
      <NFormItem label="最小高度" :class="fieldClass('mcs_min_height')"><NInputNumber v-model:value="draft.mcs_min_height" :min="0" :precision="0" /><template #feedback>{{ fieldHint('mcs_min_height') }} <NButton v-if="isOverridden('mcs_min_height')" text type="primary" @click="restoreEnvironment('mcs_min_height')">恢复环境值</NButton></template></NFormItem>
      <NFormItem label="显示生成时间" :class="fieldClass('mcs_show_generated_at')"><NSwitch :value="draft.mcs_show_generated_at ?? false" @update:value="draft.mcs_show_generated_at = $event" /><template #feedback>{{ fieldHint('mcs_show_generated_at') }} <NButton v-if="isOverridden('mcs_show_generated_at')" text type="primary" @click="restoreEnvironment('mcs_show_generated_at')">恢复环境值</NButton></template></NFormItem>
      <NFormItem label="邀请码绑定群号（0 表示未配置）" :class="fieldClass('invite_group_id')"><NInput :value="draft.invite_group_id ?? ''" :disabled="Boolean(meta?.invite_group_locked)" @update:value="draft.invite_group_id = $event" /><template #feedback>{{ meta?.invite_group_locked ? '邀请码已初始化，为保护既有资格，绑定群不可迁移' : fieldHint('invite_group_id') }} <NButton v-if="isOverridden('invite_group_id') && !meta?.invite_group_locked" text type="primary" @click="restoreEnvironment('invite_group_id')">恢复环境值</NButton></template></NFormItem>
      <NFormItem label="邀请码 API URL" :class="fieldClass('invite_api_url')"><NInput :value="draft.invite_api_url ?? ''" placeholder="https://…" @update:value="draft.invite_api_url = $event" /><template #feedback>{{ fieldHint('invite_api_url') }} <NButton v-if="isOverridden('invite_api_url')" text type="primary" @click="restoreEnvironment('invite_api_url')">恢复环境值</NButton></template></NFormItem>
      <NFormItem label="邀请码 API 密钥" :class="fieldClass('invite_api_secret')"><NInput v-model:value="secret" type="password" show-password-on="click" placeholder="留空不提交、不改变现有密钥" /><template #feedback>当前运行：{{ active?.invite_api_secret_configured ? '已配置' : '未配置' }}；待生效：{{ draft.invite_api_secret_configured ? '已配置' : '未配置' }}。密钥不会从服务器返回。</template><NSpace><NButton size="small" @click="askClearSecret">清空密钥</NButton><NButton v-if="isOverridden('invite_api_secret')" size="small" @click="restoreSecret">恢复环境值</NButton><NTag v-if="clearSecret" type="warning">待清空</NTag></NSpace></NFormItem>
      <NFormItem label="自动同意好友群白名单" class="span-all" :class="fieldClass('auto_accept_friend_group_ids')"><NDynamicTags v-if="draft.auto_accept_friend_group_ids !== null" v-model:value="draft.auto_accept_friend_group_ids" /><NButton v-else dashed @click="draft.auto_accept_friend_group_ids = []">设置明确覆盖</NButton><template #feedback>{{ fieldHint('auto_accept_friend_group_ids') }} <NButton v-if="isOverridden('auto_accept_friend_group_ids')" text type="primary" @click="restoreEnvironment('auto_accept_friend_group_ids')">恢复环境值</NButton></template></NFormItem>
    </div></NForm>
  </ConfigFormShell>
</template>

<style scoped>.deployment-alert { margin-bottom: 14px; }.deployment-field :deep(.n-form-item-feedback-wrapper) { min-height: 24px; }.deployment-field :deep(.n-tag) { margin-left: 8px; }</style>
