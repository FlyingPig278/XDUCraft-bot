<script setup lang="ts">
import { computed } from 'vue'
import { NForm } from 'naive-ui'
import type { AssetCapability, ConfigValues, JsonSchema, SchemaContext, SchemaErrors, SchemaScope, SecretFields } from '../../api/schema'
import SchemaField from './SchemaField.vue'

const props = withDefaults(defineProps<{
  schema: JsonSchema
  modelValue: ConfigValues
  scope: SchemaScope
  readonly?: boolean
  errors?: SchemaErrors
  defaults?: ConfigValues
  overrideFields?: string[]
  secretFields?: SecretFields
  choices?: Record<string, unknown[]>
  media?: AssetCapability
}>(), { readonly: false, errors: () => ({}), defaults: () => ({}), secretFields: () => ({}), choices: () => ({}) })
const emit = defineEmits<{ 'update:modelValue': [value: ConfigValues]; 'update:overrideFields': [value: string[]] }>()
const context = computed<SchemaContext>(() => ({ rootSchema: props.schema, rootValue: props.modelValue, scope: props.scope, readonly: props.readonly, errors: props.errors, defaults: props.defaults, overrideFields: props.overrideFields, secretFields: props.secretFields, choices: props.choices, media: props.media }))
function update(value: unknown): void {
  if (value && typeof value === 'object' && !Array.isArray(value)) emit('update:modelValue', value as ConfigValues)
}
</script>

<template>
  <NForm label-placement="top" class="schema-form">
    <SchemaField :schema="schema" :model-value="modelValue" :context="context" path="" :root="true" @update:model-value="update" @update:override-fields="emit('update:overrideFields', $event)" />
  </NForm>
</template>

<style scoped>
.schema-form { min-width: 0; width: 100%; overflow-wrap: anywhere; }
.schema-form :deep(.n-form-item-blank), .schema-form :deep(.n-input), .schema-form :deep(.n-input-number), .schema-form :deep(.n-select) { min-width: 0; width: 100%; }
</style>
