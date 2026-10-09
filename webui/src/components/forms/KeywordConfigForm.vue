<script setup lang="ts">
import { computed, h, onMounted, ref, type VNodeChild } from 'vue'
import { RouterLink } from 'vue-router'
import { NAlert, NButton, NDataTable, NForm, NFormItem, NInputNumber, NTag, useDialog, type DataTableColumns } from 'naive-ui'
import ConfigFormShell from '../ConfigFormShell.vue'
import KeywordRuleEditor from '../KeywordRuleEditor.vue'
import ReplyEditor from '../ReplyEditor.vue'
import { apiGet } from '../../api/client'
import { useResourceForm } from '../../composables/resourceForm'
import type { KeywordGlobalConfig, KeywordGroupConfig, KeywordMeta, KeywordRule, Resource } from '../../api/types'

const props = defineProps<{ groupId?: string }>()
const dialog = useDialog()
const path = () => props.groupId ? `/api/groups/${encodeURIComponent(props.groupId)}/config/keyword` : '/api/global/config/keyword'
const form = useResourceForm<KeywordGroupConfig | KeywordGlobalConfig, KeywordMeta>(path)
const editorOpen = ref(false)
const editorRule = ref<KeywordRule | null>(null)
const editorIndex = ref<number | null>(null)
const globalRules = ref<KeywordRule[]>([])
const globalRulesError = ref('')
function groupDraft(config: KeywordGroupConfig | KeywordGlobalConfig): config is KeywordGroupConfig { return 'join_replies' in config }
function newRule(): KeywordRule { return { id: null, keywords: [''], match: 'contains', enabled: true, cooldown: 0, replies: [[{ type: 'text', text: '' }]] } }
function copyRule(rule: KeywordRule): KeywordRule { return JSON.parse(JSON.stringify(rule)) }
const dirty = computed(() => form.dirty.value || Boolean(
  editorOpen.value && editorRule.value &&
  JSON.stringify(editorRule.value) !== JSON.stringify(
    editorIndex.value === null ? newRule() : form.draft.value?.rules[editorIndex.value]
  )
))
function discard(): void { editorOpen.value = false; form.discard() }
function openRule(index: number | null): void {
  if (!form.draft.value) return
  editorIndex.value = index
  editorRule.value = copyRule(index === null ? newRule() : form.draft.value.rules[index])
  editorOpen.value = true
}
function applyRule(): void {
  if (!form.draft.value || !editorRule.value) return
  if (editorIndex.value === null) form.draft.value.rules.push(copyRule(editorRule.value))
  else form.draft.value.rules[editorIndex.value] = copyRule(editorRule.value)
  editorOpen.value = false
}
function moveRule(index: number, offset: number): void {
  if (!form.draft.value) return
  const target = index + offset
  if (target < 0 || target >= form.draft.value.rules.length) return
  ;[form.draft.value.rules[index], form.draft.value.rules[target]] = [form.draft.value.rules[target], form.draft.value.rules[index]]
}
function removeRule(index: number): void {
  dialog.warning({ title: '删除关键词规则', content: '删除后将在保存整份配置时生效，确定从草稿移除吗？', positiveText: '删除', negativeText: '取消', onPositiveClick: () => form.draft.value?.rules.splice(index, 1) })
}
const columns = computed<DataTableColumns<KeywordRule>>(() => [
  { title: '优先级', key: 'order', width: 72, render: (_, index) => String(index + 1) },
  { title: '关键词', key: 'keywords', render: (row) => row.keywords.join('、') || '未填写' },
  { title: '方式', key: 'match', width: 90 },
  { title: '状态', key: 'enabled', width: 80, render: (row) => row.enabled ? '启用' : '停用' },
  { title: '创建时间', key: 'created_at', width: 170, render: (row) => row.id && form.meta.value?.rule_created_at[row.id] ? new Date(form.meta.value.rule_created_at[row.id] * 1000).toLocaleString() : '新规则' },
  { title: '操作', key: 'actions', width: 250, render: (_, index) => [
    hButton('编辑', () => openRule(index)), hButton('↑', () => moveRule(index, -1), index === 0),
    hButton('↓', () => moveRule(index, 1), index === (form.draft.value?.rules.length ?? 0) - 1), hButton('删除', () => removeRule(index), false, true)
  ] }
])
function hButton(label: string, action: () => void, disabled = false, danger = false): VNodeChild {
  return h(NButton, { size: 'tiny', tertiary: true, type: danger ? 'error' : 'default', disabled, onClick: action }, { default: () => label })
}
onMounted(async () => {
  await form.load()
  if (!props.groupId) return
  try {
    const resource = await apiGet<Resource<KeywordGlobalConfig, KeywordMeta>>('/api/global/config/keyword')
    globalRules.value = resource.config.rules
  } catch (error) { globalRulesError.value = error instanceof Error ? error.message : '读取全局规则失败' }
})
</script>

<template>
  <ConfigFormShell :form-id="groupId ? `keyword-${groupId}` : 'keyword-global'" :title="groupId ? '关键词 · 本群内容' : '关键词 · 全局内容'" description="规则按当前顺序匹配；保存会整体替换当前作用域，不影响其它群。" :loading="form.loading.value" :saving="form.saving.value" :dirty="dirty" :stale="form.stale.value" :errors="form.errors.value" @save="form.save" @discard="discard" @reload="form.load">
    <template v-if="form.draft.value">
      <NForm label-placement="top">
        <NFormItem :label="groupId ? '本群默认冷却（秒，留空继承全局）' : '全局默认冷却（秒）'">
          <NInputNumber v-model:value="form.draft.value.default_cooldown" :min="0" :max="3600" :precision="0" clearable />
          <NTag v-if="groupId" class="effective-tag">当前有效：{{ form.meta.value?.effective_default_cooldown ?? '—' }} 秒</NTag>
        </NFormItem>
        <NFormItem label="规则">
          <div class="rules-table">
            <NDataTable :columns="columns" :data="form.draft.value.rules" :row-key="(row: KeywordRule) => row.id || form.draft.value!.rules.indexOf(row)" :scroll-x="720" />
            <NButton dashed block :disabled="form.draft.value.rules.length >= 200" @click="openRule(null)">新增规则（{{ form.draft.value.rules.length }}/200）</NButton>
          </div>
        </NFormItem>
        <NFormItem v-if="groupDraft(form.draft.value)" label="入群欢迎"><ReplyEditor v-model="form.draft.value.join_replies" welcome /></NFormItem>
        <NFormItem v-if="groupId" label="全局规则（只读，本群规则会优先匹配）">
          <div class="rules-table">
            <NAlert v-if="globalRulesError" type="warning">{{ globalRulesError }}</NAlert>
            <NDataTable v-else :columns="columns.filter((column) => !('key' in column) || (column.key !== 'actions' && column.key !== 'created_at'))" :data="globalRules" :row-key="(row: KeywordRule) => row.id || globalRules.indexOf(row)" :scroll-x="520" />
            <RouterLink to="/settings/runtime?plugin=keyword"><NButton text type="primary">前往全局设置编辑</NButton></RouterLink>
          </div>
        </NFormItem>
      </NForm>
    </template>
    <KeywordRuleEditor v-model:show="editorOpen" v-model="editorRule" @confirm="applyRule" />
  </ConfigFormShell>
</template>

<style scoped>.rules-table { width: 100%; display: flex; flex-direction: column; gap: 10px; }.effective-tag { margin-left: 12px; }</style>
