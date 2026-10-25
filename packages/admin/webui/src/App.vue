<script setup lang="ts">
import { computed, h, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import {
  darkTheme, dateZhCN, NButton, NConfigProvider, NDialogProvider, NDrawer, NDrawerContent,
  NIcon, NLayout, NLayoutContent, NLayoutHeader, NLayoutSider, NMenu, NMessageProvider, NSpace,
  zhCN, type MenuOption
} from 'naive-ui'
import { AppsOutline, ChatbubblesOutline, ContrastOutline, LogOutOutline, MenuOutline, SettingsOutline } from '@vicons/ionicons5'
import { authState, clearDrafts, confirmDiscardDrafts, connectionState, hasDirtyForms, intendedRoute } from './state'
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
watch(resolvedTheme, (theme) => {
  document.documentElement.dataset.theme = theme ? 'dark' : 'light'
}, { immediate: true })
const authenticatedLayout = computed(() => route.name !== 'login' && authState.authenticated)
const connectionChecked = ref(false)
const activeMenu = computed(() => route.path.startsWith('/groups') ? 'groups' : route.path.startsWith('/plugins') ? 'plugins' : 'system')

const menuOptions: MenuOption[] = [
  { label: () => h(RouterLink, { to: '/groups' }, { default: () => '群聊' }), key: 'groups', icon: () => h(NIcon, { component: ChatbubblesOutline }) },
  { label: () => h(RouterLink, { to: '/plugins' }, { default: () => '插件' }), key: 'plugins', icon: () => h(NIcon, { component: AppsOutline }) },
  { label: () => h(RouterLink, { to: '/system' }, { default: () => '系统' }), key: 'system', icon: () => h(NIcon, { component: SettingsOutline }) }
]

function resize(): void { narrow.value = window.innerWidth < 800 }
function mediaChange(event: MediaQueryListEvent): void { systemDark.value = event.matches }
function cycleTheme(): void {
  themeMode.value = themeMode.value === 'system' ? 'light' : themeMode.value === 'light' ? 'dark' : 'system'
  localStorage.setItem('xducraft-theme', themeMode.value)
}
async function signOut(): Promise<void> {
  if (!confirmDiscardDrafts()) return
  try { await logout() } catch { /* server expiry still means local logout */ }
  clearSessionToken()
  clearDrafts()
  authState.authenticated = false
  authState.expiresAt = null
  authState.sessionExpired = false
  await router.replace('/login')
}
function closeDrawer(): void { drawerOpen.value = false }
function beforeUnload(event: BeforeUnloadEvent): void {
  if (!hasDirtyForms.value) return
  event.preventDefault()
  event.returnValue = ''
}
function sessionExpired(): void {
  if (!authState.authenticated) return
  intendedRoute.value = route.fullPath
  clearSessionToken()
  authState.authenticated = false
  authState.expiresAt = null
  authState.sessionExpired = true
  void router.replace('/login')
}
watch(() => route.fullPath, () => { drawerOpen.value = false })

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
          <NLayoutSider v-if="!narrow" bordered :width="208" content-style="padding: 18px 10px">
            <div class="brand"><span>XDUCraft</span><small>Bot 管理</small></div>
            <NMenu :value="activeMenu" :options="menuOptions" />
          </NLayoutSider>
          <NLayout>
            <NLayoutHeader bordered class="app-header">
              <NSpace align="center" justify="space-between" :wrap="false">
                <NSpace align="center" :wrap="false">
                  <NButton v-if="narrow" quaternary aria-label="打开导航" @click="drawerOpen = true"><NIcon :component="MenuOutline" size="20" /></NButton>
                  <span class="header-status">
                    <span class="header-dot" :class="{ online: connectionChecked && connectionState.connectedBots > 0 }" />
                    {{ !connectionChecked ? (narrow ? '待确认' : '连接状态待确认') : connectionState.connectedBots > 0 ? (narrow ? `${connectionState.connectedBots} 在线` : `${connectionState.connectedBots} 个 Bot 在线`) : (narrow ? '未连接' : 'Bot 未连接') }}
                  </span>
                  <RouterLink v-if="connectionState.restartRequired" class="restart-link" to="/plugins">{{ narrow ? '待重启' : '有设置等待重启' }}</RouterLink>
                </NSpace>
                <NSpace :wrap="false">
                  <NButton quaternary :aria-label="`切换主题，当前${themeMode === 'system' ? '跟随系统' : themeMode === 'light' ? '浅色' : '深色'}`" @click="cycleTheme"><template #icon><NIcon :component="ContrastOutline" /></template>{{ narrow ? '' : `主题：${themeMode === 'system' ? '跟随系统' : themeMode === 'light' ? '浅色' : '深色'}` }}</NButton>
                  <NButton quaternary @click="signOut"><template #icon><NIcon :component="LogOutOutline" /></template>退出</NButton>
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
          <NDrawerContent title="XDUCraft Bot 管理" closable>
            <NMenu :value="activeMenu" :options="menuOptions" @update:value="closeDrawer" />
          </NDrawerContent>
        </NDrawer>
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>
