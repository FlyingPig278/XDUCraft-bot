<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NAlert, NButton, NCard, NCollapse, NCollapseItem, NSpace, useDialog, useMessage } from 'naive-ui'
import type { JsonSchema, SchemaContext } from '../../api/schema'
import { branchIndex, creatable, effectiveSchema, hasRedactedSecret, makeDefault, safeLabel, variants } from '../../schema/schema'
import SchemaField from './SchemaField.vue'

const props = defineProps<{ schema: JsonSchema; modelValue: unknown[]; context: SchemaContext; path: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown[]] }>()
const dialog = useDialog()
const message = useMessage()
const keys = ref<string[]>([])
let sequence = 0
watch(() => props.modelValue.length, (length) => {
  if (keys.value.length !== length) keys.value = Array.from({ length }, () => `item-${++sequence}`)
}, { immediate: true })
const itemSchema = computed<JsonSchema>(() => ({ ...(props.schema.items ?? {}), ...(props.schema['x-ui-item-widget'] ? { 'x-ui-widget': props.schema['x-ui-item-widget'] } : {}) }))
const branches = computed(() => variants(itemSchema.value, props.context.rootSchema))
const createOptions = computed(() => branches.value.length > 1 ? branches.value.map((schema, index) => ({ schema, index })).filter(({ schema }) => creatable(schema)) : creatable(effectiveSchema(itemSchema.value, props.context.rootSchema)) ? [{ schema: itemSchema.value, index: 0 }] : [])
const canAdd = computed(() => !props.context.readonly && (props.schema.maxItems === undefined || props.modelValue.length < props.schema.maxItems))
const isObjectList = computed(() => effectiveSchema(itemSchema.value, props.context.rootSchema).type === 'object' && branches.value.length < 2)
function add(schema: JsonSchema): void {
  if (!canAdd.value) return
  const value = makeDefault(schema, props.context.rootSchema)
  if (value !== undefined) {
    keys.value.push(`item-${++sequence}`)
    emit('update:modelValue', [...props.modelValue, value])
  }
}
function replace(index: number, value: unknown): void {
  if (props.context.readonly) return
  const list = [...props.modelValue]
  list[index] = value
  emit('update:modelValue', list)
}
function move(index: number, offset: number): void {
  const destination = index + offset
  if (props.context.readonly || destination < 0 || destination >= props.modelValue.length) return
  if (!props.schema['x-ui-key-field'] && hasRedactedSecret(props.modelValue, props.schema, props.context, props.path)) {
    message.warning('此列表含有按位置隐藏的秘密字段。请先重新输入已配置的秘密字段，再调整顺序。')
    return
  }
  const list = [...props.modelValue]
  ;[list[index], list[destination]] = [list[destination], list[index]]
  ;[keys.value[index], keys.value[destination]] = [keys.value[destination]!, keys.value[index]!]
  emit('update:modelValue', list)
}
function remove(index: number): void {
  if (props.context.readonly) return
  if (!props.schema['x-ui-key-field'] && hasRedactedSecret(props.modelValue, props.schema, props.context, props.path) && index < props.modelValue.length - 1) {
    message.warning('删除会改变后续秘密字段的位置。请先重新输入已配置的秘密字段。')
    return
  }
  dialog.warning({ title: '删除列表项', content: '此项及其包含的内容将从草稿中移除，是否继续？', positiveText: '删除', negativeText: '取消', onPositiveClick: () => {
    keys.value.splice(index, 1)
    emit('update:modelValue', props.modelValue.filter((_, position) => position !== index))
  } })
}
function itemTitle(value: unknown, index: number): string {
  const metadata = props.schema['x-ui-label-field'] ?? itemSchema.value['x-ui-label-field']
  const label = safeLabel(value, itemSchema.value, metadata, props.context.rootSchema)
  if (label) return label
  const branch = branches.value[branchIndex(branches.value, value, itemSchema.value.discriminator?.propertyName)]
  return branch?.title ?? `第 ${index + 1} 项`
}
</script>

<template>
  <div class="schema-list">
    <NAlert v-if="!schema.items" type="warning">数组未声明 items schema；已有内容保留，无法编辑。</NAlert>
    <template v-else>
      <NCard v-for="(item, index) in modelValue" :key="keys[index]" size="small" :title="itemTitle(item, index)">
        <div class="list-actions">
          <NButton size="tiny" :disabled="context.readonly || index === 0" :aria-label="`上移第 ${index + 1} 项`" @click="move(index, -1)">上移</NButton>
          <NButton size="tiny" :disabled="context.readonly || index === modelValue.length - 1" :aria-label="`下移第 ${index + 1} 项`" @click="move(index, 1)">下移</NButton>
          <NButton size="tiny" type="error" :disabled="context.readonly || (schema.minItems !== undefined && modelValue.length <= schema.minItems)" :aria-label="`删除第 ${index + 1} 项`" @click="remove(index)">删除</NButton>
        </div>
        <NCollapse v-if="isObjectList">
          <NCollapseItem title="编辑内容" :name="index">
            <SchemaField :schema="itemSchema" :model-value="item" :context="context" :path="`${path}.${index}`" :root="true" @update:model-value="replace(index, $event)" />
          </NCollapseItem>
        </NCollapse>
        <SchemaField v-else :schema="itemSchema" :model-value="item" :context="context" :path="`${path}.${index}`" :root="true" @update:model-value="replace(index, $event)" />
      </NCard>
      <NSpace>
        <NButton v-for="option in createOptions" :key="option.index" dashed :disabled="!canAdd" @click="add(option.schema)">添加{{ option.schema.title || (branches.length > 1 ? `类型 ${option.index + 1}` : '项目') }}</NButton>
      </NSpace>
      <p class="list-count">{{ modelValue.length }} 项<span v-if="schema.minItems !== undefined">，最少 {{ schema.minItems }}</span><span v-if="schema.maxItems !== undefined">，最多 {{ schema.maxItems }}</span><span v-if="schema.uniqueItems">；项目不可重复</span></p>
      <NAlert v-if="!createOptions.length" type="info" :show-icon="false">声明中没有允许新建的内容类型；已有只读项可保留、移动或删除。</NAlert>
    </template>
  </div>
</template>

<style scoped>
.schema-list { display: flex; flex-direction: column; gap: 12px; width: 100%; min-width: 0; }
.list-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.list-count { font-size: 12px; opacity: .7; margin: 0; }
.schema-list :deep(.n-card) { min-width: 0; width: 100%; }
.schema-list :deep(.n-card__content) { min-width: 0; }
.schema-list :deep(.n-card-header__main) { overflow-wrap: anywhere; min-width: 0; }
</style>
