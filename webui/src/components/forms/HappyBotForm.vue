<script setup lang="ts">
import { onMounted } from 'vue'
import { NAlert, NButton, NForm, NFormItem, NInput, NSpace } from 'naive-ui'
import ConfigFormShell from '../ConfigFormShell.vue'
import { useResourceForm } from '../../composables/resourceForm'
import type { HappyConfig, HappyMeta } from '../../api/types'

const props = defineProps<{ groupId: string }>()
const form = useResourceForm<HappyConfig, HappyMeta>(() => `/api/groups/${encodeURIComponent(props.groupId)}/config/happy_bot`)
function restoreDefault(): void { if (form.draft.value) form.draft.value.emoji_id = null }
onMounted(form.load)
</script>

<template>
  <ConfigFormShell :form-id="`happy-${groupId}`" title="Happy Bot · 本群表情" :description="`所有保存都只作用于群 ${groupId}，不会修改其它群或默认表情。`" :loading="form.loading.value" :saving="form.saving.value" :dirty="form.dirty.value" :stale="form.stale.value" :errors="form.errors.value" @save="form.save" @discard="form.discard" @reload="form.load">
    <NAlert type="info" class="happy-alert">当前有效表情 ID：<strong>{{ form.meta.value?.effective_emoji_id || '—' }}</strong><span v-if="form.draft.value?.emoji_id === null">（默认表情）</span></NAlert>
    <NForm v-if="form.draft.value" label-placement="top">
      <NFormItem label="本群表情 ID"><NInput :value="form.draft.value.emoji_id ?? ''" placeholder="数字字符串；恢复默认后为空" @update:value="form.draft.value.emoji_id = $event" /></NFormItem>
      <NSpace><NButton :disabled="form.draft.value.emoji_id === null" @click="restoreDefault">恢复默认表情</NButton></NSpace>
    </NForm>
  </ConfigFormShell>
</template>
<style scoped>.happy-alert { margin-bottom: 16px; }</style>
