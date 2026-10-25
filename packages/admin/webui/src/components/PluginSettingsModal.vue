<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton, NCard, NIcon, NModal, NTab, NTabs } from 'naive-ui'
import { CloseOutline } from '@vicons/ionicons5'
import type { PluginDescriptor } from '../api/types'
import SchemaSettingsForm from './SchemaSettingsForm.vue'

const props = withDefaults(defineProps<{
  show: boolean
  plugin: PluginDescriptor | null
  initialScope?: 'global' | 'startup'
}>(), { initialScope: 'global' })
const emit = defineEmits<{ close: []; saved: [] }>()
const formSaving = ref(false)
const formDirty = ref(false)
const scope = ref<'global' | 'startup'>('global')
const scopes = computed(() => (['global', 'startup'] as const).filter(item => Boolean(props.plugin?.resources[item])))
const descriptor = computed(() => props.plugin?.resources[scope.value])
const scopeName = computed(() => scope.value === 'global' ? '全局运行参数' : '启动参数')

watch(() => [props.show, props.plugin?.id, props.initialScope] as const, ([show]) => {
  if (!show) return
  formDirty.value = false
  formSaving.value = false
  scope.value = props.plugin?.resources[props.initialScope] ? props.initialScope : scopes.value[0] ?? 'global'
}, { immediate: true })

function selectScope(value: string | number): void {
  if (value === 'global' || value === 'startup') {
    formDirty.value = false
    scope.value = value
  }
}
function handleState(state: { dirty: boolean; saving: boolean }): void {
  formDirty.value = state.dirty
  formSaving.value = state.saving
}
function requestClose(): void {
  if (!formSaving.value) emit('close')
}
function saved(): void { emit('saved') }
</script>

<template>
  <NModal :show="show" :mask-closable="false" :close-on-esc="false" @update:show="value => { if (!value) requestClose() }">
    <NCard class="settings-modal-card" role="dialog" aria-modal="true" :aria-label="plugin ? `${plugin.name}的全局设置` : '插件全局设置'">
      <template #header>
        <div class="modal-header-title">
          <span class="modal-title-text">{{ plugin?.name }} · 全局设置</span>
          <span class="dirty-badge" :class="{ 'dirty-badge--visible': formDirty }" :aria-hidden="!formDirty">未保存</span>
        </div>
      </template>
      <template #header-extra>
        <NButton quaternary :disabled="formSaving" aria-label="关闭全局设置" @click="requestClose">
          <template #icon><NIcon :component="CloseOutline" /></template>关闭
        </NButton>
      </template>
      <NTabs v-if="scopes.length > 1" type="segment" :value="scope" class="scope-tabs" @update:value="selectScope">
        <NTab v-if="plugin?.resources.global" name="global" :disabled="formSaving">全局运行参数</NTab>
        <NTab v-if="plugin?.resources.startup" name="startup" :disabled="formSaving">启动参数</NTab>
      </NTabs>
      <p v-if="scope !== 'startup' && !descriptor?.schema.description?.includes('对所有群生效')" class="scope-copy">对所有群生效。</p>
      <SchemaSettingsForm
        v-if="plugin && descriptor"
        :key="descriptor.path"
        :descriptor="descriptor"
        :media="plugin.media"
        embedded
        :title="scopeName"
        @saved="saved"
        @state="handleState"
      />
    </NCard>
  </NModal>
</template>

<style scoped>
.settings-modal-card {
  width: min(860px, calc(100vw - 28px));
  max-height: calc(100vh - 28px);
  overflow: auto;
}
.modal-header-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 28px;
  line-height: 1.5;
  min-width: 0;
}
.modal-title-text {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
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
  flex-shrink: 0;
}
.dirty-badge--visible {
  opacity: 1;
  pointer-events: auto;
}
.scope-tabs {
  margin-bottom: 12px;
}
.scope-copy {
  margin: 0 0 14px;
  opacity: .7;
  line-height: 1.55;
  font-size: 13px;
}
@media (max-width: 599px) {
  .settings-modal-card {
    width: calc(100vw - 16px);
    max-height: calc(100vh - 16px);
  }
}
</style>
