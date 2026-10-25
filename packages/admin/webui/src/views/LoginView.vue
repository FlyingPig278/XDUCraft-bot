<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { NAlert, NButton, NCard, NForm, NFormItem, NInput, useMessage } from 'naive-ui'
import { ApiError, login } from '../api/client'
import { applySession, authState, intendedRoute } from '../state'

const router = useRouter()
const message = useMessage()
const password = ref('')
const loading = ref(false)
const errorText = ref('')

async function submit(): Promise<void> {
  if (!password.value || loading.value) return
  loading.value = true
  errorText.value = ''
  try {
    const session = await login(password.value)
    applySession(session)
    password.value = ''
    const destination = intendedRoute.value ?? '/groups'
    intendedRoute.value = null
    await router.replace(destination)
    message.success('登录成功')
  } catch (error) {
    errorText.value = error instanceof ApiError && error.status === 401 ? '管理口令错误' : error instanceof Error ? error.message : '登录失败'
  } finally { loading.value = false }
}
</script>

<template>
  <NCard title="XDUCraft 管理面板" class="login-card" :bordered="true">
    <p class="muted">仅供机器人所有者通过本机或 SSH 隧道访问。</p>
    <NAlert v-if="authState.sessionExpired" type="warning" :show-icon="true" class="login-error">会话已过期。未保存草稿只保留在当前浏览器内存中；重新登录后将返回原页面并核对服务器版本。</NAlert>
    <NAlert v-if="errorText" type="error" :show-icon="true" class="login-error">{{ errorText }}</NAlert>
    <NForm @submit.prevent="submit">
      <NFormItem label="管理口令">
        <NInput v-model:value="password" type="password" show-password-on="click" autofocus autocomplete="current-password" @keyup.enter="submit" />
      </NFormItem>
      <NButton type="primary" block attr-type="submit" :loading="loading" :disabled="!password">登录</NButton>
    </NForm>
  </NCard>
</template>

<style scoped>
.login-card { width: min(420px, 100%); }
.login-error { margin-bottom: 16px; }
</style>
