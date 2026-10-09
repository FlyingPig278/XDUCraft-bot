<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NDrawer, NDrawerContent, NForm, NFormItem, NInput, NInputNumber, NSelect, NSpace, NSwitch } from 'naive-ui'
import ReplyEditor from './ReplyEditor.vue'
import type { KeywordMatch, KeywordRule } from '../api/types'

const props = defineProps<{ show: boolean; modelValue: KeywordRule | null }>()
const emit = defineEmits<{ 'update:show': [value: boolean]; 'update:modelValue': [value: KeywordRule]; confirm: [] }>()
const rule = computed(() => props.modelValue)
const matchOptions = [
  { label: '包含', value: 'contains' }, { label: '完全匹配', value: 'exact' },
  { label: '前缀', value: 'prefix' }, { label: '正则表达式', value: 'regex' }
]
function patch(changes: Partial<KeywordRule>): void {
  if (rule.value) emit('update:modelValue', { ...rule.value, ...changes })
}
function changeKeyword(index: number, value: string): void {
  if (!rule.value) return
  const keywords = [...rule.value.keywords]
  keywords[index] = value
  patch({ keywords })
}
function removeKeyword(index: number): void { if (rule.value) patch({ keywords: rule.value.keywords.filter((_, current) => current !== index) }) }
function addKeyword(): void { if (rule.value) patch({ keywords: [...rule.value.keywords, ''] }) }
</script>

<template>
  <NDrawer :show="show" placement="right" width="min(620px, 100vw)" @update:show="emit('update:show', $event)">
    <NDrawerContent :title="rule?.id ? '编辑关键词规则' : '新增关键词规则'" closable>
      <NForm v-if="rule" label-placement="top">
        <NFormItem label="关键词">
          <div class="keyword-list">
            <NSpace v-for="(keyword, index) in rule.keywords" :key="index" :wrap="false">
              <NInput :value="keyword" maxlength="64" show-count placeholder="1–64 个字符" @update:value="changeKeyword(index, $event)" />
              <NButton type="error" secondary @click="removeKeyword(index)">删除</NButton>
            </NSpace>
            <NButton dashed :disabled="rule.keywords.length >= 200" @click="addKeyword">添加关键词</NButton>
          </div>
        </NFormItem>
        <div class="form-grid">
          <NFormItem label="匹配方式"><NSelect :value="rule.match" :options="matchOptions" @update:value="patch({ match: $event as KeywordMatch })" /></NFormItem>
          <NFormItem label="启用"><NSwitch :value="rule.enabled" @update:value="patch({ enabled: $event })" /></NFormItem>
          <NFormItem label="冷却（秒，0 表示继承默认）"><NInputNumber :value="rule.cooldown" :min="0" :max="86400" :precision="0" @update:value="patch({ cooldown: $event ?? 0 })" /></NFormItem>
        </div>
        <NFormItem label="回复内容"><ReplyEditor :model-value="rule.replies" @update:model-value="patch({ replies: $event })" /></NFormItem>
      </NForm>
      <template #footer><NSpace justify="end"><NButton @click="emit('update:show', false)">取消</NButton><NButton type="primary" @click="emit('confirm')">应用到草稿</NButton></NSpace></template>
    </NDrawerContent>
  </NDrawer>
</template>

<style scoped>.keyword-list { width: 100%; display: flex; flex-direction: column; gap: 8px; }</style>
