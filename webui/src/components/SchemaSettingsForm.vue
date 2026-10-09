<script setup lang="ts">
import { computed, watch } from 'vue'
import { NAlert, NButton, NCollapse, NCollapseItem, NEmpty, NSpace, useDialog } from 'naive-ui'
import type { AssetCapability, JsonSchema, SchemaContext } from '../api/schema'
import type { ResourceDescriptor } from '../api/types'
import { effectiveSchema, isObject, own, resolve, variants, visible } from '../schema/schema'
import { useResourceForm } from '../composables/resourceForm'
import ConfigFormShell from './ConfigFormShell.vue'
import SchemaFormRenderer from './schema/SchemaFormRenderer.vue'

const props = defineProps<{ descriptor: ResourceDescriptor; title: string; media?: AssetCapability; readonly?: boolean }>()
const emit = defineEmits<{ saved: [] }>()
const form = useResourceForm(() => props.descriptor)
const { draft, saved, meta, overrideFields, loading, saving, stale, conflict, errors, dirty } = form
const dialog = useDialog()
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
function overrideLabel(overridden: boolean): string {
  if (props.descriptor.scope === 'group') return overridden ? '本群独立定制' : '跟随全局'
  if (props.descriptor.scope === 'startup') return overridden ? '网页部署覆盖' : '跟随环境或基础配置'
  return overridden ? '此资源独立值' : '跟随声明的默认值'
}
const confirmation = computed(() => {
  if (props.descriptor.scope === 'group') return ''
  const reset = (meta.value.overridden ?? []).filter((key) => !overrideFields.value.includes(key))
  const impact = props.descriptor.scope === 'startup' ? '保存的是下次启动使用的值，不会改变当前进程，也不会自动重启。' : props.descriptor.scope === 'global' ? '这会修改全局设置，并影响所有选择“跟随全局”的群；已有“本群独立定制”不会被清除。' : '这里只保存当前群的配置。'
  return `${impact}${props.descriptor.write_mode === 'patch' && reset.length ? ` ${reset.length} 个完整字段或配置块将恢复跟随上级值；其网页独立值会被移除。` : ''}`.trim()
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
  return typeof safe === 'string' ? safe : JSON.stringify(safe) ?? '〔未设置〕'
}
const valueRows = computed(() => Object.entries(fields.value).map(([key, field]) => ({
  key, label: resolve(field, props.descriptor.schema).title ?? key,
  active: format(meta.value.active && own(meta.value.active, key) ? meta.value.active[key] : meta.value.applied?.[key], key),
  pending: format(saved.value?.[key], key), draft: format(draft.value?.[key], key),
  inherited: format(meta.value.defaults?.[key], key),
  effective: format(isObject(meta.value.effective) ? meta.value.effective[key] : undefined, key)
})))
const changedRows = computed(() => valueRows.value.filter((row) =>
  JSON.stringify(saved.value?.[row.key]) !== JSON.stringify(draft.value?.[row.key]) ||
  (meta.value.overridden ?? []).includes(row.key) !== overrideFields.value.includes(row.key) ||
  conflict.value && (JSON.stringify(conflict.value.config[row.key]) !== JSON.stringify(draft.value?.[row.key]) || props.descriptor.write_mode === 'patch' && (conflict.value.meta.overridden ?? []).includes(row.key) !== overrideFields.value.includes(row.key)) ||
  (meta.value.changed_keys ?? []).includes(row.key) || (meta.value.changed_startup_fields ?? []).includes(row.key)
))
const secretRows = computed(() => {
  const secrets = meta.value.secret_fields ?? {}
  return Array.isArray(secrets) ? secrets.map(path => ({ path, configured: true })) : Object.entries(secrets).map(([path, value]) => ({ path, configured: typeof value === 'boolean' ? value : value.configured }))
})
function notice(value: unknown): string {
  if (typeof value === 'string') return value
  if (isObject(value)) return String(value.message ?? value.reason ?? value.code ?? '请检查插件提供的状态说明')
  return '请检查插件提供的状态说明'
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
watch(() => props.descriptor.path, () => { void form.load() }, { immediate: true })
</script>

<template>
  <ConfigFormShell :form-id="descriptor.path" :title="title" :description="descriptor.schema.description" :loading="loading" :saving="saving" :dirty="dirty" :stale="stale" :errors="errors" :disabled="unavailable || applying || !draft" :confirm-message="confirmation" :save-text="descriptor.scope === 'startup' ? '保存为下次启动值' : descriptor.scope === 'group' ? '保存当前群配置' : '保存全局配置'" @save="save" @discard="form.discard" @reload="reload">
    <template #conflict>
      <div v-if="conflict" class="comparison-list"><div v-for="row in changedRows" :key="row.key" class="comparison-row"><strong>{{ row.label }}</strong><span>本页原值：{{ format(saved?.[row.key], row.key) }}</span><span>本地草稿：{{ format(draft?.[row.key], row.key) }}</span><span>服务器最新：{{ format(conflict.config[row.key], row.key) }}</span><span v-if="descriptor.write_mode === 'patch'">原模式：{{ overrideLabel(Boolean(meta.overridden?.includes(row.key))) }} · 草稿模式：{{ overrideLabel(overrideFields.includes(row.key)) }} · 最新模式：{{ overrideLabel(Boolean(conflict.meta.overridden?.includes(row.key))) }}</span></div></div>
      <p v-else>最新值暂时无法读取；原版本与草稿均保留，没有自动重试覆盖。</p>
    </template>
    <NAlert v-if="unavailable" type="warning" class="resource-notice">{{ props.readonly ? '此处只显示声明的配置和状态，不能在当前页面修改。' : meta.reason || '插件声明此资源当前不可编辑；其它资源不受影响。' }}</NAlert>
    <NAlert v-for="(item, index) in meta.notices ?? []" :key="index" type="info" class="resource-notice">{{ notice(item) }}</NAlert>
    <NAlert v-if="descriptor.scope === 'group' && descriptor.write_mode === 'patch'" type="info" class="resource-notice">每个字段都明确区分“跟随全局”和“本群独立定制”。字段值为 null 时仍是实际值，不代表继承；只有选择“跟随全局”才会移除本群覆盖。</NAlert>
    <NAlert v-if="descriptor.scope === 'startup'" type="info" class="resource-notice">这是部署期设置。“跟随环境或基础配置”与“网页部署覆盖”分别显示；保存只改变下次启动值，不会热替换当前客户端、缓存或连接。</NAlert>
    <NAlert v-if="meta.restart_required" type="warning" class="resource-notice">下次启动值已经保存，当前运行值尚未改变。涉及字段：{{ (meta.changed_keys ?? meta.changed_startup_fields ?? []).map(key => fields[key]?.title ?? key).join('、') || '请查看差异' }}</NAlert>
    <NAlert v-if="meta.apply_status && !['active', 'applied', 'success'].includes(meta.apply_status)" :type="['failed','invalid'].includes(meta.apply_status) ? 'error' : 'warning'" class="resource-notice">
      {{ meta.apply_status === 'applying' ? '正在应用已保存配置，尚不能视为成功。' : meta.apply_status === 'failed' ? '已保存配置应用失败，当前实际状态可能仍是上次成功值。' : meta.apply_status === 'invalid' ? '已保存配置无效，当前没有应用该值。' : `应用状态：${meta.apply_status}` }}<p v-if="meta.apply_error">{{ notice(meta.apply_error) }}</p>
      <NSpace v-if="descriptor.scope !== 'startup'"><NButton :loading="saving" :disabled="dirty || stale || loading || unavailable || applying" @click="retry">重试应用已保存值</NButton><NButton :disabled="dirty || saving || stale || loading || unavailable || applying" @click="restoreApplied">恢复上次已应用值</NButton></NSpace>
      <p v-if="dirty">先保存或放弃草稿，再操作已保存配置。</p>
    </NAlert>
    <NAlert v-if="meta.invalid_fields || meta.orphaned_fields" type="warning" class="resource-notice">存在无效或不再声明的字段，界面不会静默丢弃。{{ meta.invalid_fields ? `无效字段：${Array.isArray(meta.invalid_fields) ? meta.invalid_fields.join('、') : isObject(meta.invalid_fields) ? Object.keys(meta.invalid_fields).join('、') : '请检查字段错误'}` : '' }} {{ meta.orphaned_fields ? `未声明字段：${Array.isArray(meta.orphaned_fields) ? meta.orphaned_fields.join('、') : isObject(meta.orphaned_fields) ? Object.keys(meta.orphaned_fields).join('、') : '请检查插件声明'}` : '' }}</NAlert>
    <SchemaFormRenderer v-if="draft" :schema="schema" :model-value="draft" :scope="descriptor.scope" :readonly="Boolean(unavailable || applying || saving || loading)" :errors="errors" :defaults="meta.defaults ?? {}" :override-fields="descriptor.write_mode === 'patch' ? overrideFields : undefined" :secret-fields="meta.secret_fields ?? {}" :choices="meta.choices ?? {}" :media="media" @update:model-value="draft = $event" @update:override-fields="overrideFields = $event" />
    <NEmpty v-else-if="!loading" description="配置尚未读取，请使用重新加载" />
    <NCollapse v-if="draft" class="resource-comparisons">
      <NCollapseItem v-if="descriptor.scope === 'startup' || meta.active || meta.applied" title="当前运行值与已保存配置（秘密字段已隐藏）" name="active"><div class="comparison-list"><div v-for="row in valueRows" :key="row.key" class="comparison-row"><strong>{{ row.label }}</strong><span>当前运行：{{ row.active }}</span><span>{{ descriptor.scope === 'startup' ? '下次启动值' : '已保存配置' }}：{{ row.pending }}</span><span v-if="dirty">本页草稿：{{ row.draft }}</span><span>草稿模式：{{ overrideLabel(overrideFields.includes(row.key)) }}</span><span v-if="meta.readonly_fields?.includes(row.key)">服务端声明此字段只读</span></div><div v-for="secret in secretRows" :key="secret.path" class="comparison-row"><strong>{{ secret.path }}</strong><span>秘密字段：{{ secret.configured ? '已配置' : '未配置' }}（内容永不返回）</span></div></div></NCollapseItem>
      <NCollapseItem v-if="meta.defaults || isObject(meta.effective)" title="全局默认与当前实际值（只读）" name="defaults"><div class="comparison-list"><div v-for="row in valueRows" :key="row.key" class="comparison-row"><strong>{{ row.label }}</strong><span>全局默认：{{ row.inherited }}</span><span>当前实际：{{ row.effective }}</span></div></div></NCollapseItem>
      <NCollapseItem v-if="dirty" title="未保存差异（秘密字段已隐藏）" name="draft"><div class="comparison-list"><div v-for="row in changedRows" :key="row.key" class="comparison-row"><strong>{{ row.label }}</strong><span>原值：{{ format(saved?.[row.key], row.key) }}</span><span>草稿：{{ row.draft }}</span><span v-if="descriptor.write_mode === 'patch'">草稿模式：{{ overrideLabel(overrideFields.includes(row.key)) }}</span></div></div></NCollapseItem>
    </NCollapse>
  </ConfigFormShell>
</template>
<style scoped>
.resource-notice { margin-bottom:14px; }.resource-comparisons { margin-top:20px; }.comparison-list { display:flex; flex-direction:column; gap:10px; margin:12px 0; }.comparison-row { display:flex; flex-direction:column; gap:5px; padding:10px 12px; border-radius:8px; background:color-mix(in srgb,currentColor 5%,transparent); font-size:13px; min-width:0; overflow-wrap:anywhere; white-space:pre-wrap; }
</style>
