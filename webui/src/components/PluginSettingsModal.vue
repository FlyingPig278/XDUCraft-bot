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
const scope = ref<'global' | 'startup'>('global')
const formSaving = ref(false)
const scopes = computed(() => (['global', 'startup'] as const).filter(item => Boolean(props.plugin?.resources[item])))
const descriptor = computed(() => props.plugin?.resources[scope.value])
const scopeName = computed(() => scope.value === 'global' ? '全局运行参数' : '启动参数')

watch(() => [props.show, props.plugin?.id, props.initialScope] as const, ([show]) => {
  if (!show) return
  scope.value = props.plugin?.resources[props.initialScope] ? props.initialScope : scopes.value[0] ?? 'global'
}, { immediate: true })

function selectScope(value: string | number): void {
  if (value === 'global' || value === 'startup') scope.value = value
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
        <div>
          <div>{{ plugin?.name }} · 全局设置</div>
        </div>
      </template>
      <template #header-extra><NButton quaternary :disabled="formSaving" aria-label="关闭全局设置" @click="requestClose"><template #icon><NIcon :component="CloseOutline" /></template>关闭</NButton></template>
      <p v-if="scope !== 'startup'" class="scope-copy">对所有群生效。</p>
      <NTabs v-if="scopes.length > 1" type="segment" :value="scope" @update:value="selectScope">
        <NTab v-if="plugin?.resources.global" name="global" :disabled="formSaving">全局运行参数</NTab>
        <NTab v-if="plugin?.resources.startup" name="startup" :disabled="formSaving">启动参数</NTab>
      </NTabs>
      <SchemaSettingsForm
        v-if="plugin && descriptor"
        :key="descriptor.path"
        :descriptor="descriptor"
        :media="plugin.media"
        embedded
        :title="scopeName"
        @saved="saved"
        @state="formSaving = $event.saving"
      />
    </NCard>
  </NModal>
</template>

<style scoped>
.settings-modal-card { width:min(860px, calc(100vw - 28px)); max-height:calc(100vh - 28px); overflow:auto; }
.scope-copy { margin:0 0 14px; opacity:.7; line-height:1.55; }
:deep(.n-tabs) { margin-bottom:14px; }
@media(max-width:599px) { .settings-modal-card { width:calc(100vw - 16px); max-height:calc(100vh - 16px); } }
</style>
