<script setup lang="ts">
import { computed, h, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import {
  darkTheme, dateZhCN, NButton, NConfigProvider, NDialogProvider, NDrawer, NDrawerContent,
  NLayout, NLayoutContent, NLayoutHeader, NLayoutSider, NMenu, NMessageProvider, NSpace, NTag,
  zhCN, type MenuOption
} from 'naive-ui'
import { authState, clearDrafts, connectionState, hasDirtyForms, intendedRoute } from './state'
import { apiGet, clearSessionToken, logout } from './api/client'
import type { Overview } from './api/types'

const route = useRoute()
const router = useRouter()
const narrow = ref(window.innerWidth < 800)
const drawerOpen = ref(false)
const themeMode = ref<'system' | 'light' | 'dark'>((localStorage.getItem('xducraft-theme') as 'system' | 'light' | 'dark') || 'system')
const systemDark = ref(window.matchMedia('(prefers-color-scheme: dark)').matches)
const media = window.matchMedia('(prefers-color-scheme: dark)')
const resolvedTheme = computed(() => (themeMode.value === 'dark' || (themeMode.value === 'system' && systemDark.value)) ? darkTheme : null)
const authenticatedLayout = computed(() => route.name !== 'login' && authState.authenticated)
const connectionChecked = ref(false)
const activeMenu = computed(() => route.path.startsWith('/groups') ? 'groups' : route.path.startsWith('/settings') ? 'settings' : 'overview')

const menuOptions: MenuOption[] = [
  { label: () => h(RouterLink, { to: '/overview' }, { default: () => '概览' }), key: 'overview' },
  { label: () => h(RouterLink, { to: '/groups' }, { default: () => '群管理' }), key: 'groups' },
  { label: () => h(RouterLink, { to: '/settings' }, { default: () => '全局设置' }), key: 'settings' }
]

function resize(): void { narrow.value = window.innerWidth < 800 }
function mediaChange(event: MediaQueryListEvent): void { systemDark.value = event.matches }
function cycleTheme(): void {
  themeMode.value = themeMode.value === 'system' ? 'light' : themeMode.value === 'light' ? 'dark' : 'system'
  localStorage.setItem('xducraft-theme', themeMode.value)
}
async function signOut(): Promise<void> {
  try { await logout() } catch { /* server expiry still means local logout */ }
  clearSessionToken()
  clearDrafts()
  authState.authenticated = false
  authState.expiresAt = null
  await router.replace('/login')
}
function closeDrawer(): void { drawerOpen.value = false }
function beforeUnload(event: BeforeUnloadEvent): void {
  if (!hasDirtyForms.value) return
  event.preventDefault()
  event.returnValue = ''
}
function sessionExpired(): void {
  intendedRoute.value = route.fullPath
  authState.authenticated = false
  authState.expiresAt = null
  router.replace('/login')
}

watch(authenticatedLayout, async (authenticated, _previous, onCleanup) => {
  connectionChecked.value = false
  if (!authenticated) return
  let active = true
  onCleanup(() => { active = false })
  try {
    const overview = await apiGet<Overview>('/api/overview')
    if (!active) return
    connectionState.connectedBots = overview.bots.filter((bot) => bot.connected).length
    connectionState.restartRequired = overview.restart_required
    connectionChecked.value = true
  } catch { /* An unconfirmed connection is not evidence that the bot is offline. */ }
}, { immediate: true })

onMounted(() => {
  window.addEventListener('resize', resize)
  window.addEventListener('beforeunload', beforeUnload)
  window.addEventListener('xducraft:unauthorized', sessionExpired)
  media.addEventListener('change', mediaChange)
})
onUnmounted(() => {
  window.removeEventListener('resize', resize)
  window.removeEventListener('beforeunload', beforeUnload)
  window.removeEventListener('xducraft:unauthorized', sessionExpired)
  media.removeEventListener('change', mediaChange)
})
</script>

<template>
  <NConfigProvider :locale="zhCN" :date-locale="dateZhCN" :theme="resolvedTheme">
    <NMessageProvider>
      <NDialogProvider>
        <NLayout v-if="authenticatedLayout" has-sider class="app-layout">
          <NLayoutSider v-if="!narrow" bordered :width="220" content-style="padding: 18px 10px">
            <div class="brand">XDUCraft</div>
            <NMenu :value="activeMenu" :options="menuOptions" />
          </NLayoutSider>
          <NLayout>
            <NLayoutHeader bordered class="app-header">
              <NSpace align="center" justify="space-between" :wrap="false">
                <NSpace align="center" :wrap="false">
                  <NButton v-if="narrow" quaternary aria-label="打开导航" @click="drawerOpen = true">☰</NButton>
                  <strong v-if="!narrow">管理面板</strong>
                  <NTag size="small" :type="!connectionChecked ? 'default' : connectionState.connectedBots > 0 ? 'success' : 'warning'">
                    {{ !connectionChecked ? (narrow ? '待确认' : '连接待确认') : connectionState.connectedBots > 0 ? (narrow ? `${connectionState.connectedBots} 在线` : `${connectionState.connectedBots} 个 Bot 在线`) : (narrow ? '离线' : 'Bot 未连接') }}
                  </NTag>
                  <NTag v-if="connectionState.restartRequired" size="small" type="warning">{{ narrow ? '待重启' : '设置待重启' }}</NTag>
                </NSpace>
                <NSpace :wrap="false">
                  <NButton quaternary @click="cycleTheme">{{ narrow ? '主题' : `主题：${themeMode === 'system' ? '跟随系统' : themeMode === 'light' ? '浅色' : '深色'}` }}</NButton>
                  <NButton quaternary @click="signOut">退出</NButton>
                </NSpace>
              </NSpace>
            </NLayoutHeader>
            <NLayoutContent class="app-content">
              <RouterView />
            </NLayoutContent>
          </NLayout>
        </NLayout>
        <div v-else class="public-layout"><RouterView /></div>
        <NDrawer v-model:show="drawerOpen" placement="left" :width="250">
          <NDrawerContent title="XDUCraft">
            <NMenu :value="activeMenu" :options="menuOptions" @update:value="closeDrawer" />
          </NDrawerContent>
        </NDrawer>
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>
