<script setup lang="ts">
import { onMounted } from 'vue'
import { NCheckbox, NForm, NFormItem, NInput, NSelect } from 'naive-ui'
import ConfigFormShell from '../ConfigFormShell.vue'
import ServerTreeEditor from '../ServerTreeEditor.vue'
import { useResourceForm } from '../../composables/resourceForm'
import type { AuthMode, McGlobalConfig, McGroupConfig, StatusApiSource } from '../../api/types'

const props = defineProps<{ groupId?: string }>()
const path = () => props.groupId ? `/api/groups/${encodeURIComponent(props.groupId)}/config/mc_status` : '/api/global/config/mc_status'
const form = useResourceForm<McGroupConfig | McGlobalConfig>(path)
const sourceOptions = [
  { label: '自动选择', value: 'auto' }, { label: '自动（API 优先）', value: 'auto_api_first' },
  { label: '原生协议', value: 'protocol' }, { label: '上海交大 API', value: 'sjtu' },
  { label: '江苏大学 API', value: 'jsu' }, { label: '自定义 API', value: 'custom' }
]
const groupSourceOptions = [{ label: '继承全局设置', value: '' }, ...sourceOptions]
const authOptions = [
  { label: '未配置 / 继承', value: '' }, { label: '正版', value: 'official' }, { label: 'MUA', value: 'mua' },
  { label: '西电统一认证', value: 'xdu' }, { label: 'Yggdrasil', value: 'yggdrasil' },
  { label: '离线', value: 'offline' }, { label: '混合', value: 'mixed' }
]
function groupDraft(config: McGroupConfig | McGlobalConfig): config is McGroupConfig { return 'servers' in config }
onMounted(form.load)
</script>

<template>
  <ConfigFormShell :form-id="groupId ? `mc-${groupId}` : 'mc-global'" :title="groupId ? 'MC 状态 · 本群设置' : 'MC 状态 · 全局设置'" :description="groupId ? '服务器树与本群显示、认证和状态源设置。空状态源/URL 表示继承全局。' : '全局状态查询数据源。'" :loading="form.loading.value" :saving="form.saving.value" :dirty="form.dirty.value" :stale="form.stale.value" :errors="form.errors.value" @save="form.save" @discard="form.discard" @reload="form.load">
    <NForm v-if="form.draft.value" label-placement="top">
      <div class="form-grid">
        <NFormItem label="状态 API 来源">
          <NSelect v-model:value="form.draft.value.status_api_source" :options="groupId ? groupSourceOptions : sourceOptions" />
        </NFormItem>
        <NFormItem label="状态 API URL">
          <NInput v-model:value="form.draft.value.status_api_url" placeholder="https://…；本群留空继承全局" />
        </NFormItem>
        <template v-if="groupDraft(form.draft.value)">
          <NFormItem label="页脚文字"><NInput v-model:value="form.draft.value.footer" placeholder="留空不显示" /></NFormItem>
          <NFormItem label="默认认证模式"><NSelect v-model:value="form.draft.value.default_auth_mode" :options="authOptions" /></NFormItem>
          <NFormItem><NCheckbox v-model:checked="form.draft.value.show_offline_by_default">默认显示离线服务器</NCheckbox></NFormItem>
          <NFormItem><NCheckbox v-model:checked="form.draft.value.auth_detect">自动检测认证模式</NCheckbox></NFormItem>
          <NFormItem><NCheckbox v-model:checked="form.draft.value.quiet_admin_replies">管理命令使用安静回复</NCheckbox></NFormItem>
          <NFormItem class="span-all" label="服务器树"><ServerTreeEditor v-model="form.draft.value.servers" /></NFormItem>
        </template>
      </div>
    </NForm>
  </ConfigFormShell>
</template>
