<script setup lang="ts">
import { onMounted } from 'vue'
import { NCheckbox, NDynamicTags, NForm, NFormItem, NInputNumber } from 'naive-ui'
import ConfigFormShell from '../ConfigFormShell.vue'
import { useResourceForm } from '../../composables/resourceForm'
import type { AntiRecallConfig } from '../../api/types'

const form = useResourceForm<AntiRecallConfig>(() => '/api/global/config/anti_recall')
onMounted(form.load)
</script>
<template>
  <ConfigFormShell form-id="anti-recall-global" title="防撤回 · 全局参数" description="保留期修改会在下一次 04:17 定时清理时生效。" :loading="form.loading.value" :saving="form.saving.value" :dirty="form.dirty.value" :stale="form.stale.value" :errors="form.errors.value" @save="form.save" @discard="form.discard" @reload="form.load">
    <NForm v-if="form.draft.value" label-placement="top"><div class="form-grid">
      <NFormItem label="缓存保留小时"><NInputNumber v-model:value="form.draft.value.cache_retention_hours" :min="1" :max="720" :precision="0" /></NFormItem>
      <NFormItem label="撤回记录保留天数"><NInputNumber v-model:value="form.draft.value.recall_retention_days" :min="1" :max="365" :precision="0" /></NFormItem>
      <NFormItem label="查询最多结果"><NInputNumber v-model:value="form.draft.value.max_query_results" :min="1" :max="100" :precision="0" /></NFormItem>
      <NFormItem label="单个媒体上限（MiB）"><NInputNumber v-model:value="form.draft.value.max_media_mb" :min="1" :max="200" :precision="0" /></NFormItem>
      <NFormItem><NCheckbox v-model:checked="form.draft.value.save_media">保存媒体文件</NCheckbox></NFormItem>
      <NFormItem><NCheckbox v-model:checked="form.draft.value.include_self">包含机器人自身消息</NCheckbox></NFormItem>
      <NFormItem label="豁免用户 QQ 号" class="span-all"><NDynamicTags v-model:value="form.draft.value.exempt_user_ids" /></NFormItem>
    </div></NForm>
  </ConfigFormShell>
</template>
