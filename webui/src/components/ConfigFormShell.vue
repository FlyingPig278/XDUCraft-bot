<script setup lang="ts">
import { onUnmounted, watch } from 'vue'
import { NAlert, NButton, NCard, NCollapse, NCollapseItem, NSpace, NSpin, useDialog } from 'naive-ui'
import { registerDirtyForm } from '../state'

const props = withDefaults(defineProps<{
  formId: string; title: string; description?: string; loading?: boolean; saving?: boolean;
  dirty?: boolean; stale?: boolean; disabled?: boolean; errors?: Record<string, string | string[]>;
  confirmMessage?: string; saveText?: string; embedded?: boolean
}>(), { description: '', loading: false, saving: false, dirty: false, stale: false, disabled: false, errors: () => ({}), confirmMessage: '', saveText: '保存' })
const emit = defineEmits<{ save: []; discard: []; reload: [] }>()
const dialog = useDialog()
function confirmReload(): void {
  if (!props.dirty && !props.stale) { emit('reload'); return }
  dialog.warning({ title: '放弃草稿并重新加载', content: '重新加载会丢弃当前草稿并读取最新版本；不会覆盖服务器中的配置。', positiveText: '放弃并重新加载', negativeText: '保留草稿', onPositiveClick: () => emit('reload') })
}
function requestSave(): void {
  if (!props.confirmMessage) { emit('save'); return }
  dialog.warning({ title: '确认影响范围', content: props.confirmMessage, positiveText: '确认并保存', negativeText: '继续检查', onPositiveClick: () => emit('save') })
}
function requestDiscard(): void {
  dialog.warning({ title: '放弃本地更改', content: '恢复到本页最近读取的值，不修改服务器配置。', positiveText: '放弃更改', negativeText: '保留草稿', onPositiveClick: () => emit('discard') })
}
let unregister: (() => void) | null = null
watch(() => [props.formId, props.dirty, props.saving] as const, () => {
  unregister?.()
  unregister = props.dirty || props.saving ? registerDirtyForm(props.formId, () => emit('discard'), () => props.saving) : null
}, { immediate: true })
onUnmounted(() => unregister?.())
</script>

<template>
  <NCard :title="embedded ? undefined : title" :bordered="!embedded" :content-style="embedded ? { padding:'0' } : undefined" :footer-style="embedded ? { padding:'16px 0 0' } : undefined">
    <template v-if="!embedded && dirty" #header-extra><span class="dirty-mark">未保存</span></template>
    <p v-if="embedded && dirty" class="dirty-mark">未保存</p>
    <p v-if="description" class="muted form-description">{{ description }}</p>
    <NAlert v-if="stale" type="warning" class="form-alert">
      配置已被 QQ 或其他页面修改。草稿已保留，不能直接覆盖；请比较差异，或明确放弃后重新加载。
      <slot name="conflict" />
      <NButton size="small" :disabled="saving || loading" @click="confirmReload">放弃草稿并读取最新值</NButton>
    </NAlert>
    <NAlert v-if="errors.resource && !stale" type="error" class="form-alert">{{ Array.isArray(errors.resource) ? errors.resource.join('；') : errors.resource }}</NAlert>
    <NCollapse v-if="Object.keys(errors).length" class="form-alert">
      <NCollapseItem title="请求或字段问题" name="errors">
        <ul class="error-list"><li v-for="(value, field) in errors" :key="field"><strong>{{ field }}</strong>：{{ Array.isArray(value) ? value.join('；') : value }}</li></ul>
      </NCollapseItem>
    </NCollapse>
    <NSpin :show="loading"><slot /></NSpin>
    <template #footer>
      <NSpace class="form-actions" justify="end">
        <NButton :disabled="saving || loading" @click="confirmReload">重新加载</NButton>
        <NButton :disabled="!dirty || saving || loading" @click="requestDiscard">放弃更改</NButton>
        <NButton type="primary" :loading="saving" :disabled="disabled || !dirty || loading || saving || stale" @click="requestSave">{{ saveText }}</NButton>
      </NSpace>
    </template>
  </NCard>
</template>
<style scoped>
.form-description { margin-top: 0; }
.form-alert { margin-bottom: 16px; }
.dirty-mark { color: #f0a020; font-size: 13px; }
.error-list { margin: 0; padding-left: 20px; overflow-wrap: anywhere; }
@media (max-width: 599px) { .form-actions { width: 100%; } .form-actions :deep(.n-space__item), .form-actions .n-button { width: 100%; } }
</style>
