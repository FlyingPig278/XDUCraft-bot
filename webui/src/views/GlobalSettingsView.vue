<script setup lang="ts">
import { computed, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NTabs, NTab } from 'naive-ui'
import AntiRecallForm from '../components/forms/AntiRecallForm.vue'
import DeploymentForm from '../components/forms/DeploymentForm.vue'
import FeatureDefaultsForm from '../components/forms/FeatureDefaultsForm.vue'
import KeywordConfigForm from '../components/forms/KeywordConfigForm.vue'
import McStatusForm from '../components/forms/McStatusForm.vue'
import PigBotForm from '../components/forms/PigBotForm.vue'
import WordcloudForm from '../components/forms/WordcloudForm.vue'
import { connectionState } from '../state'

const route = useRoute()
const router = useRouter()
const section = computed(() => ['runtime', 'features', 'deployment'].includes(String(route.params.section)) ? String(route.params.section) : 'runtime')
function changeSection(value: string): void { router.push(`/settings/${value}`) }
watch(() => route.query.plugin, async (plugin) => {
  if (typeof plugin !== 'string') return
  await nextTick()
  document.getElementById(`global-${plugin}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}, { immediate: true })
</script>

<template>
  <main class="page">
    <h1 class="page-heading">全局设置</h1><p class="page-subtitle">运行期参数立即由业务插件读取；部署期参数仅在下一次启动应用。</p>
    <NTabs type="line" :value="section" @update:value="changeSection">
      <NTab name="runtime">运行期设置</NTab><NTab name="features">功能默认开关</NTab><NTab name="deployment">部署期设置</NTab>
    </NTabs>
    <div v-if="section === 'runtime'" class="section-stack settings-content">
      <section id="global-mc_status"><McStatusForm /></section>
      <section id="global-keyword"><KeywordConfigForm /></section>
      <section id="global-wordcloud"><WordcloudForm /></section>
      <section id="global-anti_recall"><AntiRecallForm /></section>
      <section id="global-pig_bot"><PigBotForm /></section>
    </div>
    <div v-else-if="section === 'features'" class="settings-content"><FeatureDefaultsForm /></div>
    <div v-else class="settings-content"><DeploymentForm @restart="connectionState.restartRequired = $event" /></div>
  </main>
</template>
<style scoped>.settings-content { margin-top:18px; }</style>
