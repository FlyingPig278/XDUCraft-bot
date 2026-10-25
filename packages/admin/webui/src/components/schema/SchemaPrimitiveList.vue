<script setup lang="ts">
import { computed, ref } from 'vue'
import { NAlert, NButton, NInput, NSpace, NTag } from 'naive-ui'
import type { JsonSchema, SchemaContext } from '../../api/schema'
import { effectiveSchema, errorText } from '../../schema/schema'

const props = defineProps<{ schema: JsonSchema; modelValue: unknown[]; context: SchemaContext; path: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown[]] }>()
const draft = ref('')
const editing = ref<number | null>(null)
const itemSchema = computed(() => effectiveSchema(props.schema.items ?? {}, props.context.rootSchema))
const supported = computed(() => itemSchema.value.type === 'string' && !itemSchema.value.writeOnly && !itemSchema.value['x-ui-secret'] && props.modelValue.every((value) => typeof value === 'string'))
const canAdd = computed(() => !props.context.readonly && (props.schema.maxItems === undefined || props.modelValue.length < props.schema.maxItems))
const canCommit = computed(() => supported.value && !props.context.readonly && !itemSchema.value.readOnly && !itemSchema.value['x-ui-readonly'] && (editing.value !== null || canAdd.value) && (itemSchema.value.minLength === undefined || draft.value.length >= itemSchema.value.minLength) && (itemSchema.value.maxLength === undefined || draft.value.length <= itemSchema.value.maxLength) && (!props.schema.uniqueItems || !props.modelValue.some((value, index) => index !== editing.value && value === draft.value)))
function commit(): void {
  if (!canCommit.value) return
  const values = [...props.modelValue]
  if (editing.value === null) values.push(draft.value)
  else values[editing.value] = draft.value
  emit('update:modelValue', values)
  editing.value = null
  draft.value = ''
}
function edit(index: number): void {
  if (props.context.readonly || itemSchema.value.readOnly || itemSchema.value['x-ui-readonly']) return
  editing.value = index
  draft.value = String(props.modelValue[index])
}
function remove(index: number): void {
  if (props.context.readonly || (props.schema.minItems !== undefined && props.modelValue.length <= props.schema.minItems)) return
  emit('update:modelValue', props.modelValue.filter((_, position) => position !== index))
  editing.value = null
  draft.value = ''
}
function move(index: number, offset: number): void {
  const destination = index + offset
  if (props.context.readonly || destination < 0 || destination >= props.modelValue.length) return
  const values = [...props.modelValue]
  ;[values[index], values[destination]] = [values[destination], values[index]]
  emit('update:modelValue', values)
  editing.value = null
  draft.value = ''
}
</script>

<template>
  <div class="primitive-list">
    <NAlert v-if="!supported" type="warning">此紧凑列表需要字符串 items；现有值保持不变。</NAlert>
    <template v-else>
      <div v-for="(value, index) in modelValue" :key="index" class="primitive-row">
        <div class="primitive-value">
          <NTag :type="errorText(context, `${path}.${index}`) ? 'error' : 'default'">{{ value === '' ? '空字符串' : value }}</NTag>
          <p v-if="errorText(context, `${path}.${index}`)" class="item-error">{{ errorText(context, `${path}.${index}`) }}</p>
        </div>
        <NSpace size="small">
          <NButton size="tiny" :disabled="context.readonly || itemSchema.readOnly || Boolean(itemSchema['x-ui-readonly'])" @click="edit(index)">编辑</NButton>
          <NButton size="tiny" :disabled="context.readonly || index === 0" :aria-label="`上移第 ${index + 1} 项`" @click="move(index, -1)">↑</NButton>
          <NButton size="tiny" :disabled="context.readonly || index === modelValue.length - 1" :aria-label="`下移第 ${index + 1} 项`" @click="move(index, 1)">↓</NButton>
          <NButton size="tiny" type="error" :disabled="context.readonly || (schema.minItems !== undefined && modelValue.length <= schema.minItems)" @click="remove(index)">删除</NButton>
        </NSpace>
      </div>
      <div v-if="!context.readonly" class="primitive-create">
        <NInput v-model:value="draft" :input-props="{ ...(schema['x-ui-widget'] === 'id-list' ? { inputmode: 'numeric' } : {}), 'aria-label': editing === null ? (itemSchema.title || '输入新项目') : '编辑所选项目' }" :maxlength="itemSchema.maxLength" :placeholder="editing === null ? itemSchema.title || '输入新项目' : '编辑所选项目'" @keydown.enter.prevent="commit" />
        <NSpace><NButton :disabled="!canCommit" @click="commit">{{ editing === null ? '添加' : '更新' }}</NButton><NButton v-if="editing !== null" @click="editing = null; draft = ''">取消编辑</NButton></NSpace>
      </div>
      <p class="list-help">{{ modelValue.length }} 项<span v-if="schema.minItems !== undefined">，最少 {{ schema.minItems }}</span><span v-if="schema.maxItems !== undefined">，最多 {{ schema.maxItems }}</span><span v-if="schema.uniqueItems">；项目不可重复</span></p>
    </template>
  </div>
</template>

<style scoped>
.primitive-list { display: flex; flex-direction: column; gap: 10px; width: 100%; min-width: 0; }
.primitive-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; justify-content: space-between; }
.primitive-value { min-width: 0; max-width: 100%; flex: 1 1 auto; }
.primitive-value :deep(.n-tag) { max-width: 100%; height: auto; min-height: 28px; white-space: normal; overflow-wrap: anywhere; }
.primitive-create { display: flex; flex-direction: column; gap: 8px; }
.list-help, .item-error { margin: 0; font-size: 12px; overflow-wrap: anywhere; }
.list-help { opacity: .7; }
.item-error { color: #d03050; }
</style>
