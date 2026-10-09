<script setup lang="ts">
import { onMounted } from 'vue'
import { NCheckbox, NDynamicTags, NForm, NFormItem, NInput, NInputNumber } from 'naive-ui'
import ConfigFormShell from '../ConfigFormShell.vue'
import { useResourceForm } from '../../composables/resourceForm'
import type { WordcloudConfig } from '../../api/types'

const form = useResourceForm<WordcloudConfig>(() => '/api/global/config/wordcloud')
onMounted(form.load)
</script>
<template>
  <ConfigFormShell form-id="wordcloud-global" title="词云 · 全局参数" description="这些参数对所有群生效；保留期变化会在下一次定时清理时使用。" :loading="form.loading.value" :saving="form.saving.value" :dirty="form.dirty.value" :stale="form.stale.value" :errors="form.errors.value" @save="form.save" @discard="form.discard" @reload="form.load">
    <NForm v-if="form.draft.value" label-placement="top"><div class="form-grid">
      <NFormItem label="屏蔽用户 QQ 号" class="span-all"><NDynamicTags v-model:value="form.draft.value.ban_user_ids" /></NFormItem>
      <NFormItem label="最短词长"><NInputNumber v-model:value="form.draft.value.min_word_length" :min="1" :precision="0" /></NFormItem>
      <NFormItem label="最多词数"><NInputNumber v-model:value="form.draft.value.max_words" :min="20" :precision="0" /></NFormItem>
      <NFormItem label="消息保留天数"><NInputNumber v-model:value="form.draft.value.retention_days" :min="30" :precision="0" /></NFormItem>
      <NFormItem label="附加停用词"><NDynamicTags v-model:value="form.draft.value.additional_stopwords" /></NFormItem>
      <NFormItem label="页脚副标题"><NInput v-model:value="form.draft.value.footer_subtitle" /></NFormItem>
      <NFormItem label="页脚品牌文字"><NInput v-model:value="form.draft.value.footer_branding_text" /></NFormItem>
      <NFormItem><NCheckbox v-model:checked="form.draft.value.footer_branding_enabled">显示页脚品牌</NCheckbox></NFormItem>
    </div></NForm>
  </ConfigFormShell>
</template>
