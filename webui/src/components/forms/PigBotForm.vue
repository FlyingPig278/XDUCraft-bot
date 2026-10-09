<script setup lang="ts">
import { onMounted } from 'vue'
import { NForm, NFormItem, NInputNumber } from 'naive-ui'
import ConfigFormShell from '../ConfigFormShell.vue'
import { useResourceForm } from '../../composables/resourceForm'
import type { PigConfig } from '../../api/types'

const form = useResourceForm<PigConfig>(() => '/api/global/config/pig_bot')
onMounted(form.load)
</script>
<template>
  <ConfigFormShell form-id="pig-global" title="Pig Bot · 全局参数" :loading="form.loading.value" :saving="form.saving.value" :dirty="form.dirty.value" :stale="form.stale.value" :errors="form.errors.value" @save="form.save" @discard="form.discard" @reload="form.load">
    <NForm v-if="form.draft.value" label-placement="top"><NFormItem label="合并转发最多结果"><NInputNumber v-model:value="form.draft.value.max_forward_results" :min="1" :precision="0" /></NFormItem></NForm>
  </ConfigFormShell>
</template>
