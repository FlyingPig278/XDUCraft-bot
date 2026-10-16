<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NAlert, NButton, NCheckbox, NFormItem, NInput, NInputNumber, NSelect, NSpace, NTag, NUpload, useDialog, useMessage, type UploadCustomRequestOptions } from 'naive-ui'
import type { ConfigValues, JsonSchema, SchemaContext } from '../../api/schema'
import { assetUrl, uploadAsset } from '../../api/client'
import { atPath, branchIndex, configured, creatable, effectiveSchema, errorText, isObject, makeDefault, numericBounds, orderedFields, own, resolve, safeLabel, schemaType, unsupported, variants, visible } from '../../schema/schema'
import SchemaArray from './SchemaArray.vue'
import SchemaTree from './SchemaTree.vue'
import SchemaPrimitiveList from './SchemaPrimitiveList.vue'
import SchemaColor from './SchemaColor.vue'

const props = withDefaults(defineProps<{ schema: JsonSchema; modelValue: unknown; context: SchemaContext; path: string; root?: boolean; topLevel?: boolean; parentValue?: unknown; required?: boolean }>(), { root: false, topLevel: false, required: false })
const emit = defineEmits<{ 'update:modelValue': [value: unknown]; 'update:overrideFields': [value: string[]] }>()
const dialog = useDialog()
const message = useMessage()
const modifyingSecret = ref(false)
const draftSecret = ref('')
const mapKey = ref('')
const legacyIndependent = ref(false)
const declared = computed(() => resolve(props.schema, props.context.rootSchema))
const schema = computed(() => effectiveSchema(declared.value, props.context.rootSchema))
const branches = computed(() => variants(declared.value, props.context.rootSchema))
const type = computed(() => schemaType(schema.value))
const bounds = computed(() => numericBounds(schema.value))
const constraintHint = computed(() => {
  const item = schema.value
  if (type.value === 'integer' || type.value === 'number') {
    const { min, max } = bounds.value
    const lowerOpen = type.value !== 'integer' && item.exclusiveMinimum !== undefined && (item.minimum === undefined || item.exclusiveMinimum >= item.minimum)
    const upperOpen = type.value !== 'integer' && item.exclusiveMaximum !== undefined && (item.maximum === undefined || item.exclusiveMaximum <= item.maximum)
    if (min !== undefined && max !== undefined) return lowerOpen || upperOpen
      ? `${lowerOpen ? '(' : '['}${min}, ${max}${upperOpen ? ')' : ']'}`
      : `${min}–${max}`
    if (min !== undefined) return `${lowerOpen ? '>' : '≥'} ${min}`
    if (max !== undefined) return `${upperOpen ? '<' : '≤'} ${max}`
  }
  if (type.value === 'string') {
    if (item.minLength !== undefined && item.maxLength !== undefined) return `${item.minLength}–${item.maxLength} 字符`
    if (item.minLength !== undefined) return `至少 ${item.minLength} 字符`
    if (item.maxLength !== undefined) return `最多 ${item.maxLength} 字符`
  }
  return ''
})
const isSecret = computed(() => Boolean(schema.value.writeOnly || schema.value['x-ui-secret']))
watch(() => props.modelValue, (next) => {
  if (isSecret.value && next === undefined) { modifyingSecret.value = false; draftSecret.value = '' }
})
const disabled = computed(() => props.context.readonly || Boolean(schema.value.readOnly || schema.value['x-ui-readonly']) || inherited.value || Boolean(branches.value[selectedBranch.value]?.readOnly || branches.value[selectedBranch.value]?.['x-ui-readonly']))
const nativeOverride = computed(() => props.context.scope !== 'group' && props.topLevel && props.context.overrideFields !== undefined)
const inheritKey = computed(() => props.context.scope !== 'group' && own(declared.value, 'x-ui-inherit-value') ? 'x-ui-inherit-value' : undefined)
const inherited = computed(() => nativeOverride.value ? !props.context.overrideFields!.includes(props.path) : Boolean(inheritKey.value && !legacyIndependent.value && Object.is(props.modelValue, declared.value[inheritKey.value])))
const value = computed(() => inherited.value ? atPath(props.context.defaults, props.path) : props.modelValue)
const selectedBranch = computed(() => branchIndex(branches.value, value.value, declared.value.discriminator?.propertyName))
const unsupportedReason = computed(() => unsupported(declared.value) ?? unsupported(schema.value))
const fieldError = computed(() => errorText(props.context, props.path))
const fields = computed(() => orderedFields(schema.value, props.context.rootSchema).filter(([, field]) => visible(field, props.context, value.value)))
const groups = computed(() => {
  const result: Array<{ name: string; fields: Array<[string, JsonSchema]> }> = []
  for (const field of fields.value) {
    const metadata = field[1]['x-ui-group']
    const name = typeof metadata === 'string' ? metadata : isObject(metadata) ? String(metadata.title ?? metadata.name ?? '') : ''
    let group = result.find((item) => item.name === name)
    if (!group) { group = { name, fields: [] }; result.push(group) }
    group.fields.push(field)
  }
  return result
})
const enumOptions = computed(() => {
  const values = props.context.choices[props.path] ?? schema.value.enum ?? (own(schema.value, 'const') ? [schema.value.const] : [])
  const labels = schema.value['x-ui-enum-labels']
  return values.map((item, index) => {
    const option = isObject(item) && own(item, 'value') ? item : { value: item, label: Array.isArray(labels) ? labels[index] : isObject(labels) ? labels[String(item)] : undefined }
    return { label: String(option.label ?? option.value), value: index }
  })
})
const enumValues = computed(() => (props.context.choices[props.path] ?? schema.value.enum ?? (own(schema.value, 'const') ? [schema.value.const] : [])).map((item) => isObject(item) && own(item, 'value') ? item.value : item))
const dynamicKeys = computed(() => isObject(value.value) ? Object.keys(value.value).filter((key) => !own(schema.value.properties ?? {}, key)) : [])
const additionalSchema = computed(() => isObject(schema.value.additionalProperties) ? schema.value.additionalProperties as JsonSchema : undefined)
const isOpaque = computed(() => schema.value.readOnly && type.value === 'object')
const opaqueLabel = computed(() => {
  if (!isObject(value.value)) return schema.value.title ?? '只读内容'
  const labelKey = schema.value['x-ui-label-field']
  const declaredLabel = safeLabel(value.value, schema.value, labelKey, props.context.rootSchema)
  if (declaredLabel) return declaredLabel
  const safe = Object.entries(schema.value.properties ?? {}).filter(([, field]) => !own(field, 'const')).map(([key]) => safeLabel(value.value, schema.value, key, props.context.rootSchema)).find(Boolean)
  return safe ?? schema.value.title ?? '只读内容'
})
const fieldLabel = computed(() => declared.value.title || (props.path ? props.path.split('.').at(-1) : '') || '启用')
const isBooleanField = computed(() =>
  type.value === 'boolean' &&
  !unsupportedReason.value &&
  !isSecret.value &&
  branches.value.length <= 1 &&
  !enumOptions.value.length
)
function update(next: unknown): void { if (!disabled.value) emit('update:modelValue', next) }
function patch(key: string, next: unknown): void {
  const object: ConfigValues = isObject(value.value) ? { ...value.value } : {}
  if (next === undefined) delete object[key]
  else object[key] = next
  update(object)
}
function independent(): void {
  const inheritedValue = value.value
  if (nativeOverride.value) emit('update:overrideFields', [...new Set([...(props.context.overrideFields ?? []), props.path])])
  else legacyIndependent.value = true
  const source = { ...schema.value }
  if (inheritKey.value && Object.is(source.default, declared.value[inheritKey.value])) delete source.default
  const initial = inheritedValue === undefined || (inheritKey.value && Object.is(inheritedValue, declared.value[inheritKey.value])) ? makeDefault(source, props.context.rootSchema) : inheritedValue
  emit('update:modelValue', initial)
}
function inherit(): void {
  dialog.warning({ title: '改用基础配置', content: '当前网页设置会从草稿中移除，保存后改用插件或启动环境提供的基础值。是否继续？', positiveText: '改用基础配置', negativeText: '取消', onPositiveClick: () => {
    if (nativeOverride.value) emit('update:overrideFields', props.context.overrideFields!.filter((field) => field !== props.path))
    else if (inheritKey.value) { legacyIndependent.value = false; emit('update:modelValue', declared.value[inheritKey.value]) }
  } })
}
function chooseBranch(index: number): void {
  const branch = branches.value[index]
  if (!branch || !creatable(branch)) return
  dialog.warning({ title: '更换类型', content: '更换类型将替换当前内容。是否继续？', positiveText: '更换', negativeText: '取消', onPositiveClick: () => update(makeDefault(branch, props.context.rootSchema)) })
}
async function upload(options: UploadCustomRequestOptions): Promise<void> {
  const file = options.file.file
  if (!file || !props.context.media) { options.onError(); return }
  try {
    if (file.size > props.context.media.max_bytes) throw new Error(`文件超过允许大小（${props.context.media.max_bytes} 字节）`)
    if (!props.context.media.mime_types.includes(file.type)) throw new Error('此文件的 MIME 类型不在资源允许列表中')
    const result = await uploadAsset(props.context.media, file)
    update(result.name)
    options.onFinish()
  } catch (error) { options.onError(); message.error(error instanceof Error ? error.message : '上传失败') }
}
function addMapKey(): void {
  if (!mapKey.value || !additionalSchema.value || (isObject(value.value) && own(value.value, mapKey.value))) return
  patch(mapKey.value, makeDefault(additionalSchema.value, props.context.rootSchema))
  mapKey.value = ''
}
</script>

<template>
  <NFormItem
    v-if="visible(declared, context, parentValue)"
    :required="required"
    :validation-status="fieldError ? 'error' : undefined"
    :feedback="fieldError"
    :show-feedback="Boolean(fieldError)"
    :show-label="!root && !isBooleanField"
    class="schema-field"
    :class="{ 'schema-field--root': root, 'schema-field--boolean': isBooleanField, 'schema-field--disabled': disabled }"
  >
    <template v-if="!root && !isBooleanField" #label>
      <span class="field-label">{{ declared.title || path.split('.').at(-1) }}<span v-if="constraintHint" class="constraint-hint">{{ constraintHint }}</span></span>
    </template>
    <div class="field-content" :class="{ 'field-content--boolean': isBooleanField }">
      <template v-if="isBooleanField">
        <div class="boolean-control-row">
          <NCheckbox
            :checked="value === true"
            :disabled="disabled"
            :aria-label="fieldLabel"
            :aria-required="required || undefined"
            @update:checked="update"
          >
            <span class="boolean-label">
              <span v-if="required" class="boolean-required" aria-hidden="true">*</span>
              {{ fieldLabel }}
              <span v-if="constraintHint" class="constraint-hint">{{ constraintHint }}</span>
            </span>
          </NCheckbox>
          <NSpace v-if="nativeOverride || inheritKey" class="mode-controls" size="small" align="center">
            <span class="mode-source">{{ inherited ? (context.scope === 'startup' ? '使用启动配置' : '使用默认值') : '已自定义' }}</span>
            <NButton text size="small" :disabled="context.readonly || declared.readOnly" @click="inherited ? independent() : inherit()">{{ inherited ? '自定义' : (context.scope === 'startup' ? '改用启动配置' : '恢复默认') }}</NButton>
          </NSpace>
        </div>
        <p v-if="declared.description" class="field-help boolean-help">{{ declared.description }}</p>
      </template>
      <template v-else>
        <p v-if="declared.description" class="field-help">{{ declared.description }}</p>
        <NAlert v-if="unsupportedReason" type="warning" :show-icon="false">{{ unsupportedReason }}。原始值保留，请使用受支持的管理入口编辑。</NAlert>
        <template v-else>
          <NSpace v-if="nativeOverride || inheritKey" class="mode-controls">
            <span class="mode-source">{{ inherited ? (context.scope === 'startup' ? '使用启动配置' : '使用默认值') : '已自定义' }}</span>
            <NButton text size="small" :disabled="context.readonly || declared.readOnly" @click="inherited ? independent() : inherit()">{{ inherited ? '自定义' : (context.scope === 'startup' ? '改用启动配置' : '恢复默认') }}</NButton>
          </NSpace>
          <template v-if="isSecret">
            <NTag size="small">{{ configured(context, path) ? '已配置' : '未配置' }}</NTag>
            <NSpace v-if="!disabled" size="small">
              <NButton size="small" @click="modifyingSecret = true">修改</NButton>
              <NButton size="small" type="warning" @click="dialog.warning({ title: '清空秘密字段', content: '保存后会清空此字段，是否继续？', positiveText: '清空', negativeText: '取消', onPositiveClick: () => { modifyingSecret = true; draftSecret = ''; update('') } })">清空</NButton>
            </NSpace>
            <NInput v-if="modifyingSecret" :value="draftSecret" type="password" show-password-on="click" autocomplete="new-password" :disabled="disabled" placeholder="输入新值（不会读取已有值）" @update:value="draftSecret = $event; update($event)" />
          </template>
          <template v-else>
            <template v-if="branches.length > 1">
              <NSelect :value="selectedBranch < 0 ? null : selectedBranch" :disabled="disabled || (selectedBranch >= 0 && !creatable(branches[selectedBranch]!))" placeholder="选择内容类型" :options="branches.map((branch, index) => ({ label: branch.title || `类型 ${index + 1}`, value: index, disabled: !creatable(branch) }))" @update:value="chooseBranch(Number($event))" />
              <SchemaField v-if="selectedBranch >= 0" :schema="branches[selectedBranch]!" :model-value="value" :context="context" :path="path" :root="true" @update:model-value="update" />
              <NAlert v-else type="warning">现有值不匹配已声明类型，原值保持不变。</NAlert>
            </template>
            <NAlert v-else-if="isOpaque" type="info" :show-icon="false">{{ opaqueLabel }}（只读内容，可在列表中保留、移动或删除）</NAlert>
            <div v-else-if="type === 'object'" class="object-fields">
              <NButton v-if="value === undefined" size="small" :disabled="disabled" @click="update(makeDefault(schema, context.rootSchema))">设置此配置块</NButton>
              <template v-else>
                <section v-for="group in groups" :key="group.name" class="field-group">
                  <h3 v-if="group.name">{{ group.name }}</h3>
                  <SchemaField v-for="[key, field] in group.fields" :key="key" :schema="field" :model-value="isObject(value) ? value[key] : undefined" :context="{ ...context, readonly: disabled }" :path="path ? `${path}.${key}` : key" :parent-value="value" :top-level="root && !path" :required="schema.required?.includes(key)" @update:model-value="patch(key, $event)" @update:override-fields="emit('update:overrideFields', $event)" />
                </section>
                <template v-if="additionalSchema">
                  <div v-for="key in dynamicKeys" :key="key" class="dynamic-field-row">
                    <SchemaField :schema="additionalSchema" :model-value="isObject(value) ? value[key] : undefined" :context="{ ...context, readonly: disabled }" :path="path ? `${path}.${key}` : key" @update:model-value="patch(key, $event)" />
                    <NButton size="tiny" type="error" :disabled="disabled" @click="patch(key, undefined)">删除 {{ key }}</NButton>
                  </div>
                  <NSpace class="dynamic-field-add"><NInput v-model:value="mapKey" :disabled="disabled" placeholder="新字段名" /><NButton :disabled="disabled || !mapKey" @click="addMapKey">添加字段</NButton></NSpace>
                </template>
                <NAlert v-else-if="dynamicKeys.length" type="warning" :show-icon="false">保留了 schema 未声明的字段：{{ dynamicKeys.join('、') }}；此处不修改这些字段。</NAlert>
              </template>
            </div>
            <SchemaTree v-else-if="type === 'array' && schema['x-ui-tree']" :schema="schema" :model-value="Array.isArray(value) ? value : []" :context="{ ...context, readonly: disabled }" :path="path" @update:model-value="update" />
            <SchemaPrimitiveList v-else-if="type === 'array' && (schema['x-ui-widget'] === 'id-list' || schema['x-ui-widget'] === 'tags')" :schema="schema" :model-value="Array.isArray(value) ? value : []" :context="{ ...context, readonly: disabled }" :path="path" @update:model-value="update" />
            <SchemaArray v-else-if="type === 'array'" :schema="schema" :model-value="Array.isArray(value) ? value : []" :context="{ ...context, readonly: disabled }" :path="path" @update:model-value="update" />
            <NSelect v-else-if="enumOptions.length" :value="enumValues.findIndex((item) => Object.is(item, value)) < 0 ? null : enumValues.findIndex((item) => Object.is(item, value))" :options="enumOptions" :disabled="disabled || own(schema, 'const')" @update:value="update(enumValues[Number($event)])" />
            <NCheckbox v-else-if="type === 'boolean'" :checked="value === true" :disabled="disabled" :aria-label="fieldLabel" @update:checked="update" />
            <NInputNumber v-else-if="type === 'integer' || type === 'number'" :value="typeof value === 'number' ? value : null" :input-props="{ 'aria-label': declared.title || path.split('.').at(-1) }" :precision="type === 'integer' ? 0 : undefined" :step="schema.multipleOf || (type === 'integer' ? 1 : 0.1)" :min="bounds.min" :max="bounds.max" :disabled="disabled" @update:value="update($event === null ? undefined : $event)" />
            <div v-else-if="type === 'string' && (schema['x-ui-widget'] === 'image' || schema['x-ui-widget'] === 'asset')" class="asset-field">
              <img v-if="context.media && typeof value === 'string' && value" :src="assetUrl(context.media, value)" :alt="schema.title || '图片'" />
              <span v-if="typeof value === 'string'">{{ value }}</span>
              <NUpload v-if="context.media" :show-file-list="false" :accept="context.media.mime_types.join(',')" :disabled="disabled" :custom-request="upload"><NButton :disabled="disabled">上传图片</NButton></NUpload>
              <NAlert v-else type="warning">此资源未声明可用的媒体能力。</NAlert>
            </div>
            <SchemaColor v-else-if="type === 'string' && schema['x-ui-widget'] === 'color'" :schema="schema" :model-value="value" :disabled="disabled" @update:model-value="update" />
            <NInput v-else-if="type === 'string'" :value="typeof value === 'string' ? value : ''" :type="schema['x-ui-widget'] === 'textarea' || schema['x-ui-widget'] === 'multiline' ? 'textarea' : 'text'" :input-props="schema['x-ui-widget'] === 'id' ? { inputmode: 'numeric' } : undefined" :autosize="{ minRows: 2, maxRows: 12 }" :maxlength="schema.maxLength" :disabled="disabled" @update:value="update" />
            <NTag v-else-if="type === 'null'">未设置</NTag>
            <NAlert v-else type="warning">不支持的 schema 类型或 widget，原始值保留，无法在此编辑。</NAlert>
          </template>
        </template>
      </template>
    </div>
  </NFormItem>
</template>

<style scoped>
.field-content, .object-fields, .field-group { width: 100%; min-width: 0; }
.field-content { display: flex; flex-direction: column; gap: 8px; }
.field-content--boolean { gap: 4px; }
.field-group h3 { font-size: 15px; margin: 8px 0 16px; font-weight: 600; }
.field-group:not(:last-child) { margin-bottom: 24px; }
.field-help { margin: 0; opacity: .72; font-size: 12px; white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.5; }
.field-label { display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.constraint-hint { border-radius: 4px; padding: 1px 6px; background: color-mix(in srgb, currentColor 6%, transparent); font-size: 11px; font-weight: 400; opacity: .65; }
.mode-source { font-size: 12px; opacity: .6; }
.mode-controls { min-width: 0; }
.boolean-control-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px 12px;
  min-height: 24px;
  width: 100%;
}
.boolean-control-row :deep(.n-checkbox) {
  display: inline-flex;
  align-items: flex-start;
  min-width: 0;
  max-width: 100%;
}
.boolean-control-row :deep(.n-checkbox .n-checkbox-box-wrapper) {
  padding-top: 2px;
}
.boolean-control-row :deep(.n-checkbox .n-checkbox__label) {
  white-space: normal;
  overflow-wrap: anywhere;
  min-width: 0;
}
.boolean-label {
  display: inline-flex;
  align-items: center;
  gap: 6px 8px;
  flex-wrap: wrap;
  font-size: 14px;
  font-weight: 500;
  line-height: 1.4;
  overflow-wrap: anywhere;
}
.boolean-required {
  color: var(--n-asterisk-color, #d03050);
  margin-right: 2px;
}
.boolean-help {
  margin: 0;
  padding-left: 24px;
}
.asset-field { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; min-width: 0; overflow-wrap: anywhere; }
.asset-field img { max-width: 100%; width: 160px; max-height: 120px; object-fit: contain; }
.asset-field span { min-width: 0; max-width: 100%; overflow-wrap: anywhere; }
.schema-field:not(.schema-field--root) {
  margin-bottom: 20px;
}
.schema-field:not(.schema-field--root):last-child {
  margin-bottom: 0;
}
.schema-field--disabled .field-help {
  opacity: .5;
}
.schema-field :deep(.n-form-item-blank) { min-width: 0; width: 100%; }
.schema-field :deep(.n-input), .schema-field :deep(.n-input-number), .schema-field :deep(.n-select) { min-width: 0; width: 100%; }
.dynamic-field-row { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
.dynamic-field-add { margin-top: 8px; }
</style>
