<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NAlert, NButton, NCollapse, NCollapseItem, NEmpty, NSpace, useDialog } from 'naive-ui'
import type { AssetCapability, JsonSchema, SchemaContext } from '../api/schema'
import type { ResourceDescriptor } from '../api/types'
import { effectiveSchema, isObject, own, resolve, variants, visible } from '../schema/schema'
import { useResourceForm } from '../composables/resourceForm'
import ConfigFormShell from './ConfigFormShell.vue'
import SchemaFormRenderer from './schema/SchemaFormRenderer.vue'

const props = defineProps<{ descriptor: ResourceDescriptor; title: string; media?: AssetCapability; readonly?: boolean; embedded?: boolean }>()
const emit = defineEmits<{ saved: []; state: [value: { dirty: boolean; saving: boolean }] }>()
const form = useResourceForm(() => props.descriptor)
const { draft, saved, meta, overrideFields, loading, saving, stale, conflict, errors, dirty } = form
const dialog = useDialog()
const expandedSections = ref<string[]>([])
const fields = computed(() => {
  const root = props.descriptor.schema
  const item = effectiveSchema(root, root)
  const forms = [item, ...variants(item, root)]
  const properties = Object.assign({}, ...forms.map(form => form.properties ?? {})) as Record<string, JsonSchema>
  const context: SchemaContext = {
    rootSchema: root, rootValue: draft.value ?? {}, scope: props.descriptor.scope,
    readonly: true, errors: errors.value, defaults: meta.value.defaults ?? {},
    secretFields: meta.value.secret_fields ?? {}, choices: meta.value.choices ?? {}, media: props.media
  }
  return Object.fromEntries(Object.entries(properties).filter(([, field]) => visible(resolve(field, root), context)).map(([key, field]) => {
    const secret = forms.some(form => {
      const declared = form.properties?.[key]
      if (!declared) return false
      const resolved = effectiveSchema(declared, root)
      return resolved.writeOnly || Boolean(resolved['x-ui-secret'])
    })
    return [key, secret ? { ...field, 'x-ui-secret': true } : field]
  })) as Record<string, JsonSchema>
})
function markReadonly(field: JsonSchema, path: string[]): JsonSchema {
  const root = props.descriptor.schema
  const item = resolve(field, root)
  if (!path.length) return { ...item, readOnly: true }
  if (item.items) return { ...item, items: markReadonly(item.items, /^\d+$|^\*$/.test(path[0] ?? '') ? path.slice(1) : path) }
  const [key, ...rest] = path
  if (key && item.properties?.[key]) return { ...item, properties: { ...item.properties, [key]: markReadonly(item.properties[key], rest) } }
  if (item.anyOf) return { ...item, anyOf: item.anyOf.map(branch => markReadonly(branch, path)) }
  if (item.oneOf) return { ...item, oneOf: item.oneOf.map(branch => markReadonly(branch, path)) }
  return item
}
const schema = computed(() => (meta.value.readonly_fields ?? []).reduce((root, path) => markReadonly(root, path.split('.')), props.descriptor.schema))
const unavailable = computed(() => props.readonly || meta.value.available === false)
const applying = computed(() => meta.value.apply_status === 'applying')
const sharedApplyFailure = computed(() => Boolean(meta.value.apply_scope && meta.value.apply_scope !== props.descriptor.scope))
function overrideLabel(overridden: boolean): string {
  if (props.descriptor.scope === 'startup') return overridden ? '网页部署覆盖' : '跟随环境或基础配置'
  return overridden ? '此资源独立值' : '跟随声明的默认值'
}
const confirmation = computed(() => {
  if (props.descriptor.scope === 'group') return ''
  const reset = (meta.value.overridden ?? []).filter((key) => !overrideFields.value.includes(key))
  return props.descriptor.write_mode === 'patch' && reset.length
    ? `${reset.length} 个配置项将恢复为基础值，确认保存？` : ''
})
function redact(value: unknown, field: JsonSchema, path: string): unknown {
  const root = props.descriptor.schema
  const item = effectiveSchema(field, root)
  const branches = variants(item, root)
  const secrets = meta.value.secret_fields ?? {}
  const secretPaths = Array.isArray(secrets) ? secrets : Object.keys(secrets)
  if (item.writeOnly || item['x-ui-secret'] || branches.some(branch => branch.writeOnly || branch['x-ui-secret']) || secretPaths.some(secret => secret === path || secret === path.replace(/\.\d+(?=\.|$)/g, '.*'))) return '〔密钥内容已隐藏〕'
  if (value === undefined) return '〔未设置〕'
  if (Array.isArray(value)) return value.map((entry, index) => item.items ? redact(entry, item.items, `${path}.${index}`) : '〔未声明内容已隐藏〕')
  if (isObject(value)) {
    const properties = Object.assign({}, item.properties, ...branches.map(branch => branch.properties ?? {})) as Record<string, JsonSchema>
    return Object.fromEntries(Object.entries(value).map(([key, entry]) => {
      const declared = [item.properties?.[key], ...branches.map(branch => branch.properties?.[key])].filter((field): field is JsonSchema => Boolean(field))
      if (declared.some(field => { const resolved = effectiveSchema(field, root); return resolved.writeOnly || Boolean(resolved['x-ui-secret']) })) return [key, '〔密钥内容已隐藏〕']
      return [key, properties[key] ? redact(entry, properties[key], `${path}.${key}`) : '〔未声明内容已隐藏〕']
    }))
  }
  return value
}
function format(value: unknown, key: string): string {
  const field = fields.value[key]
  if (!field) return '〔未声明内容已隐藏〕'
  const safe = redact(value, field, key)
  if (safe === null || safe === undefined) return '未设置'
  if (typeof safe === 'boolean') return safe ? '开启' : '关闭'
  if (typeof safe === 'string' || typeof safe === 'number') return String(safe)
  if (Array.isArray(safe)) return `${safe.length} 项`
  return '已配置'
}
const valueRows = computed(() => {
  const secretFields = meta.value.secret_fields ?? {}
  const secretPaths = Array.isArray(secretFields) ? secretFields : Object.keys(secretFields)
  return Object.entries(fields.value).map(([key, field]) => {
    const running = meta.value.active && own(meta.value.active, key) ? meta.value.active : meta.value.applied
    const hasActive = Boolean(running && own(running, key))
    const hasBase = Boolean(meta.value.defaults && own(meta.value.defaults, key))
    const sensitive = secretPaths.some(path => path === key || path.startsWith(`${key}.`)) || Boolean(field.writeOnly) || Boolean(field['x-ui-secret'])
    return {
      key, label: resolve(field, props.descriptor.schema).title ?? key,
      hasActive, hasBase, hasEffective: isObject(meta.value.effective) && own(meta.value.effective, key),
      runningMatchesSaved: hasActive && !sensitive && JSON.stringify(running?.[key]) === JSON.stringify(saved.value?.[key]),
      baseMatchesSaved: hasBase && !sensitive && JSON.stringify(meta.value.defaults?.[key]) === JSON.stringify(saved.value?.[key]),
      draftChanged: JSON.stringify(draft.value?.[key]) !== JSON.stringify(saved.value?.[key]),
      active: format(running?.[key], key), pending: format(saved.value?.[key], key),
      draft: format(draft.value?.[key], key), inherited: format(meta.value.defaults?.[key], key),
      effective: format(isObject(meta.value.effective) ? meta.value.effective[key] : undefined, key)
    }
  })
})
const changedRows = computed(() => valueRows.value.filter((row) =>
  JSON.stringify(saved.value?.[row.key]) !== JSON.stringify(draft.value?.[row.key]) ||
  (meta.value.overridden ?? []).includes(row.key) !== overrideFields.value.includes(row.key) ||
  conflict.value && (JSON.stringify(conflict.value.config[row.key]) !== JSON.stringify(draft.value?.[row.key]) || props.descriptor.write_mode === 'patch' && (conflict.value.meta.overridden ?? []).includes(row.key) !== overrideFields.value.includes(row.key)) ||
  (meta.value.changed_keys ?? []).includes(row.key) || (meta.value.changed_startup_fields ?? []).includes(row.key)
))
const hasRuntimeDiagnostics = computed(() => Boolean(meta.value.active || meta.value.applied || isObject(meta.value.effective)))
const filteredNotices = computed(() => {
  if (props.descriptor.scope === 'group') return []
  const desc = props.descriptor.schema.description?.trim()
  return (meta.value.notices ?? []).map(notice).filter(item => item && item !== desc)
})
const showStartupScopeNote = computed(() => {
  if (props.descriptor.scope !== 'startup' || meta.value.restart_required) return false
  const desc = props.descriptor.schema.description ?? ''
  return !desc.includes('对所有群生效') && !desc.includes('重启')
})
function notice(value: unknown): string {
  if (typeof value === 'string') return value
  if (isObject(value)) return String(value.message ?? value.reason ?? value.code ?? '请检查插件提供的状态说明')
  return '请检查插件提供的状态说明'
}
function hasItems(value: unknown): boolean {
  return Array.isArray(value) ? value.length > 0 : isObject(value) ? Object.keys(value).length > 0 : Boolean(value)
}
async function save(): Promise<void> { if (await form.save()) emit('saved') }
async function retry(): Promise<void> { if (await form.retry()) emit('saved') }
function reload(): void {
  form.discard()
  void form.load()
}
function restoreApplied(): void {
  dialog.warning({ title: '恢复上次已应用配置', content: '将调用插件的恢复接口，恢复其最后成功应用的状态。此操作也需要当前版本匹配；不会强制覆盖其他页面的更新。', positiveText: '确认恢复', negativeText: '取消', onPositiveClick: async () => { if (await form.rollback()) emit('saved') } })
}
watch(() => props.descriptor.path, () => {
  expandedSections.value = []
  void form.load()
}, { immediate: true })
watch([dirty, saving], ([isDirty, isSaving]) => emit('state', { dirty: isDirty, saving: isSaving }), { immediate: true })
</script>

<template>
  <ConfigFormShell :form-id="descriptor.path" :title="title" :embedded="embedded" :description="descriptor.schema.description" :loading="loading" :saving="saving" :dirty="dirty" :stale="stale" :errors="errors" :disabled="unavailable || applying || !draft" :confirm-message="confirmation" :save-text="descriptor.scope === 'group' ? '保存群配置' : '保存设置'" @save="save" @discard="form.discard" @reload="reload">
    <template #conflict>
      <div v-if="conflict" class="comparison-list"><div v-for="row in changedRows" :key="row.key" class="comparison-row"><strong>{{ row.label }}</strong><span>本页原值：{{ format(saved?.[row.key], row.key) }}</span><span>本地草稿：{{ format(draft?.[row.key], row.key) }}</span><span>服务器最新：{{ format(conflict.config[row.key], row.key) }}</span><span v-if="descriptor.write_mode === 'patch'">原模式：{{ overrideLabel(Boolean(meta.overridden?.includes(row.key))) }} · 草稿模式：{{ overrideLabel(overrideFields.includes(row.key)) }} · 最新模式：{{ overrideLabel(Boolean(conflict.meta.overridden?.includes(row.key))) }}</span></div></div>
      <p v-else>最新值暂时无法读取；原版本与草稿均保留，没有自动重试覆盖。</p>
    </template>
    <NAlert v-if="unavailable" type="warning" class="resource-notice">{{ props.readonly ? '此处只显示声明的配置和状态，不能在当前页面修改。' : meta.reason || '插件声明此资源当前不可编辑；其它资源不受影响。' }}</NAlert>
    <p v-for="(item, index) in filteredNotices" :key="index" class="resource-note">{{ item }}</p>
    <p v-if="showStartupScopeNote" class="resource-note">对所有群生效，保存后需重启机器人。</p>
    <NAlert v-if="meta.restart_required" type="warning" class="resource-notice">设置已保存，重启后生效。</NAlert>
    <NAlert v-if="meta.apply_status && !['active', 'applied', 'success'].includes(meta.apply_status)" :type="['failed','invalid'].includes(meta.apply_status) ? 'error' : 'warning'" class="resource-notice">
      {{ sharedApplyFailure ? '共享配置应用失败，请打开全局设置处理。本群配置仍可独立保存。' : meta.apply_status === 'applying' ? '正在应用已保存配置。' : meta.apply_status === 'failed' ? '已保存配置应用失败，当前仍使用上次成功值。' : meta.apply_status === 'invalid' ? '已保存配置无效，请修正字段后保存。' : `应用状态：${meta.apply_status}` }}<p v-if="meta.apply_error">{{ notice(meta.apply_error) }}</p>
      <NSpace v-if="descriptor.scope !== 'startup' && !sharedApplyFailure && meta.apply_status === 'failed'" wrap :size="[8, 8]"><NButton :loading="saving" :disabled="dirty || stale || loading || unavailable || applying" @click="retry">重试应用已保存值</NButton><NButton :disabled="dirty || saving || stale || loading || unavailable || applying" @click="restoreApplied">恢复上次已应用值</NButton></NSpace>
      <p v-if="dirty">先保存或放弃草稿，再操作已保存配置。</p>
    </NAlert>
    <NAlert v-if="hasItems(meta.invalid_fields) || hasItems(meta.orphaned_fields)" type="warning" class="resource-notice">存在无效或不再声明的字段。{{ hasItems(meta.invalid_fields) ? `无效字段：${Array.isArray(meta.invalid_fields) ? meta.invalid_fields.join('、') : isObject(meta.invalid_fields) ? Object.keys(meta.invalid_fields).join('、') : '请检查字段错误'}` : '' }} {{ hasItems(meta.orphaned_fields) ? `未声明字段：${Array.isArray(meta.orphaned_fields) ? meta.orphaned_fields.join('、') : isObject(meta.orphaned_fields) ? Object.keys(meta.orphaned_fields).join('、') : '请检查插件声明'}` : '' }}</NAlert>
    <SchemaFormRenderer v-if="draft" :schema="schema" :model-value="draft" :scope="descriptor.scope" :readonly="Boolean(unavailable || applying || saving || loading)" :errors="errors" :defaults="meta.defaults ?? {}" :override-fields="descriptor.write_mode === 'patch' ? overrideFields : undefined" :secret-fields="meta.secret_fields ?? {}" :choices="meta.choices ?? {}" :media="media" @update:model-value="draft = $event" @update:override-fields="overrideFields = $event" />
    <NEmpty v-else-if="!loading" description="配置尚未读取，请使用重新加载" />
    <NCollapse v-if="draft && descriptor.scope !== 'group'" v-model:expanded-names="expandedSections" class="resource-comparisons">
      <NCollapseItem title="高级信息" name="diagnostics">
        <div v-if="valueRows.length" class="comparison-list">
          <p v-if="!hasRuntimeDiagnostics && descriptor.scope !== 'startup'" class="diagnostics-hint">此插件当前未单独汇报运行时生效状态，下方仅列出已持久化的全局配置与默认值。</p>
          <div v-for="row in valueRows" :key="row.key" class="comparison-row">
            <div class="comparison-row-header">
              <strong>{{ row.label }}</strong>
              <span v-if="meta.readonly_fields?.includes(row.key)" class="readonly-tag">只读</span>
            </div>
            <span v-if="row.runningMatchesSaved" class="comparison-tag comparison-tag--synced">当前运行与已保存一致：{{ row.active }}</span>
            <template v-else>
              <span v-if="row.hasActive">当前运行：{{ row.active }}</span>
              <span v-else-if="row.hasEffective">当前生效：{{ row.effective }}</span>
              <span>{{ descriptor.scope === 'startup' ? '下次启动' : '已保存' }}：{{ row.pending }}</span>
            </template>
            <span v-if="row.hasBase && !row.baseMatchesSaved">{{ descriptor.scope === 'startup' ? '启动配置' : '默认值' }}：{{ row.inherited }}</span>
            <span v-if="dirty && row.draftChanged" class="comparison-draft">未保存：{{ row.draft }}</span>
          </div>
        </div>
        <NEmpty v-else description="暂无高级字段信息" size="small" class="comparison-empty" />
      </NCollapseItem>
    </NCollapse>
  </ConfigFormShell>
</template>
<style scoped>
.resource-notice { margin-bottom: 14px; }
.resource-note { margin: 0 0 12px; opacity: .72; font-size: 13px; line-height: 1.55; }
.resource-comparisons { margin-top: 20px; }
.comparison-list { display: flex; flex-direction: column; gap: 10px; margin: 12px 0; }
.diagnostics-hint { margin: 0 0 8px; font-size: 12px; opacity: .7; line-height: 1.5; }
.comparison-row {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 10px 12px;
  border-radius: 8px;
  background: color-mix(in srgb, currentColor 5%, transparent);
  font-size: 13px;
  min-width: 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
.comparison-row-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.readonly-tag {
  font-size: 11px;
  padding: 1px 5px;
  border-radius: 4px;
  background: color-mix(in srgb, currentColor 10%, transparent);
  opacity: .8;
}
.comparison-tag--synced {
  opacity: .85;
}
.comparison-draft {
  color: color-mix(in srgb, currentColor 35%, #d9822b);
}
.comparison-empty {
  padding: 16px 0;
}
</style>
