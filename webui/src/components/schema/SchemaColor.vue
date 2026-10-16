<script setup lang="ts">
import { computed } from 'vue'
import { NInput } from 'naive-ui'
import type { JsonSchema } from '../../api/schema'

const props = defineProps<{ schema: JsonSchema; modelValue: unknown; disabled: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const preview = computed(() => {
  if (typeof props.modelValue !== 'string') return '#000000'
  const value = props.modelValue.startsWith('#') ? props.modelValue : `#${props.modelValue}`
  return /^#[a-f0-9]{6}$/i.test(value) ? value : '#000000'
})
function pick(event: Event): void {
  if (props.disabled || !(event.target instanceof HTMLInputElement)) return
  const pattern = props.schema.pattern ?? ''
  const bareHex = (typeof props.modelValue === 'string' && /^[a-f0-9]{6}$/i.test(props.modelValue)) || (!pattern.includes('#') && (pattern.includes('{6}') || props.schema.maxLength === 6))
  emit('update:modelValue', bareHex ? event.target.value.slice(1) : event.target.value)
}
</script>

<template>
  <div class="color-control">
    <input type="color" :value="preview" :disabled="disabled" :aria-label="schema.title || '选择颜色'" @input="pick" />
    <NInput :value="typeof modelValue === 'string' ? modelValue : ''" :maxlength="schema.maxLength" :disabled="disabled" placeholder="未配置颜色；也可直接输入色值" @update:value="emit('update:modelValue', $event)" />
  </div>
</template>

<style scoped>
.color-control { display: flex; align-items: center; gap: 10px; min-width: 0; width: 100%; }
.color-control input[type='color'] { flex: 0 0 38px; width: 38px; height: 32px; padding: 2px; border: 1px solid #8886; border-radius: 4px; background: transparent; cursor: pointer; }
.color-control :deep(.n-input) { min-width: 0; flex: 1 1 auto; }
</style>
