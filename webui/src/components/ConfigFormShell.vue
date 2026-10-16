<script setup lang="ts">
import { onUnmounted, watch } from 'vue'
import { NAlert, NButton, NCard, NCollapse, NCollapseItem, NIcon, NSpin, useDialog } from 'naive-ui'
import { ArrowUndoOutline, RefreshOutline, SaveOutline } from '@vicons/ionicons5'
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
    <template v-if="!embedded" #header-extra>
      <span class="dirty-badge" :class="{ 'dirty-badge--visible': dirty }" :aria-hidden="!dirty">未保存</span>
    </template>
    <p v-if="description" class="muted form-description">{{ description }}</p>
    <NAlert v-if="stale" type="warning" class="form-alert">
      配置已被 QQ 或其他页面修改。草稿已保留，不能直接覆盖；请比较差异，或明确放弃后重新加载。
      <slot name="conflict" />
      <div class="stale-actions">
        <NButton size="small" :disabled="saving || loading" @click="confirmReload">放弃草稿并读取最新值</NButton>
      </div>
    </NAlert>
    <NAlert v-if="errors.resource && !stale" type="error" class="form-alert">{{ Array.isArray(errors.resource) ? errors.resource.join('；') : errors.resource }}</NAlert>
    <NCollapse v-if="Object.keys(errors).length" class="form-alert">
      <NCollapseItem title="请求或字段问题" name="errors">
        <ul class="error-list"><li v-for="(value, field) in errors" :key="field"><strong>{{ field }}</strong>：{{ Array.isArray(value) ? value.join('；') : value }}</li></ul>
      </NCollapseItem>
    </NCollapse>
    <NSpin :show="loading"><slot /></NSpin>
    <template #footer>
      <div class="form-actions" :class="{ 'form-actions--dirty': dirty }">
        <div class="form-actions-utility">
          <NButton quaternary :disabled="saving || loading" @click="confirmReload">
            <template #icon><NIcon :component="RefreshOutline" /></template>重新加载
          </NButton>
        </div>
        <div class="form-actions-submit">
          <NButton v-if="dirty" :disabled="saving || loading" @click="requestDiscard">
            <template #icon><NIcon :component="ArrowUndoOutline" /></template>放弃更改
          </NButton>
          <NButton class="form-save" type="primary" :loading="saving" :disabled="disabled || !dirty || loading || saving || stale" @click="requestSave">
            <template #icon><NIcon :component="SaveOutline" /></template>{{ saveText }}
          </NButton>
        </div>
      </div>
    </template>
  </NCard>
</template>
<style scoped>
.form-description { margin-top: 0; }
.form-alert { margin-bottom: 16px; }
.stale-actions { margin-top: 8px; }
.dirty-badge {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  font-weight: 500;
  color: color-mix(in srgb, currentColor 35%, #d9822b);
  background: color-mix(in srgb, #d9822b 14%, transparent);
  border: 1px solid color-mix(in srgb, #d9822b 35%, transparent);
  padding: 1px 7px;
  border-radius: 9999px;
  opacity: 0;
  pointer-events: none;
  transition: opacity .15s ease-in-out;
  white-space: nowrap;
  user-select: none;
}
.dirty-badge--visible {
  opacity: 1;
  pointer-events: auto;
}
.error-list { margin: 0; padding-left: 20px; overflow-wrap: anywhere; }
.form-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}
.form-actions-utility {
  display: flex;
  align-items: center;
}
.form-actions-submit {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}
@media (max-width: 599px) {
  .form-actions {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }
  .form-actions-utility,
  .form-actions-submit {
    display: contents;
  }
  .form-actions .n-button {
    min-height: 40px;
    width: 100%;
    white-space: nowrap;
  }
  .form-actions--dirty .form-save {
    grid-column: 1 / -1;
  }
}
</style>
