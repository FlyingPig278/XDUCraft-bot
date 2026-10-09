<script setup lang="ts">
import { onUnmounted, watch } from 'vue'
import { NAlert, NButton, NCard, NCollapse, NCollapseItem, NSpace, NSpin, useDialog } from 'naive-ui'
import { registerDirtyForm } from '../state'

const props = withDefaults(defineProps<{
  formId: string
  title: string
  description?: string
  loading?: boolean
  saving?: boolean
  dirty?: boolean
  stale?: boolean
  errors?: Record<string, string | string[]>
}>(), { description: '', loading: false, saving: false, dirty: false, stale: false, errors: () => ({}) })
const emit = defineEmits<{ save: []; discard: []; reload: [] }>()
const dialog = useDialog()
function confirmReload(): void {
  dialog.warning({
    title: '重新加载配置', content: '重新加载将放弃当前草稿。确定继续吗？',
    positiveText: '重新加载', negativeText: '保留草稿', onPositiveClick: () => emit('reload')
  })
}
let unregister: (() => void) | null = null

watch(() => props.dirty, (dirty) => {
  if (dirty && !unregister) unregister = registerDirtyForm(props.formId, () => emit('discard'))
  if (!dirty && unregister) { unregister(); unregister = null }
}, { immediate: true })
onUnmounted(() => unregister?.())
</script>

<template>
  <NCard :title="title">
    <template #header-extra><span v-if="dirty" class="dirty-mark">有未保存修改</span></template>
    <p v-if="description" class="muted form-description">{{ description }}</p>
    <NAlert v-if="stale" type="warning" class="form-alert">
      配置已被 QQ 或其他页面修改。当前草稿仍保留，请确认后重新加载。
      <NButton size="small" @click="confirmReload">重新加载</NButton>
    </NAlert>
    <NCollapse v-if="Object.keys(errors).length" class="form-alert">
      <NCollapseItem title="请修正表单中的问题" name="errors">
        <ul class="error-list">
          <li v-for="(value, field) in errors" :key="field"><strong>{{ field }}</strong>：{{ Array.isArray(value) ? value.join('；') : value }}</li>
        </ul>
      </NCollapseItem>
    </NCollapse>
    <NSpin :show="loading">
      <slot />
    </NSpin>
    <template #footer>
      <NSpace justify="end">
        <NButton :disabled="!dirty || saving" @click="emit('discard')">放弃更改</NButton>
        <NButton type="primary" :loading="saving" :disabled="!dirty || loading || stale" @click="emit('save')">保存</NButton>
      </NSpace>
    </template>
  </NCard>
</template>

<style scoped>
.form-description { margin-top: 0; }
.form-alert { margin-bottom: 16px; }
.dirty-mark { color: #f0a020; font-size: 13px; }
.error-list { margin: 0; padding-left: 20px; overflow-wrap: anywhere; }
</style>
