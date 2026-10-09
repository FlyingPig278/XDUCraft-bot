import { computed, reactive, ref } from 'vue'
import type { RouteLocationNormalizedLoaded } from 'vue-router'
import type { SessionInfo } from './api/types'

export const authState = reactive<{
  checked: boolean
  authenticated: boolean
  expiresAt: number | null
}>({ checked: false, authenticated: false, expiresAt: null })

export const connectionState = reactive({ connectedBots: 0, restartRequired: false })
export const intendedRoute = ref<string | null>(null)

const dirtyForms = reactive(new Map<string, () => void>())
export const hasDirtyForms = computed(() => dirtyForms.size > 0)

export function registerDirtyForm(id: string, discard: () => void): () => void {
  dirtyForms.set(id, discard)
  return () => dirtyForms.delete(id)
}

export function clearDrafts(): void {
  for (const discard of dirtyForms.values()) discard()
  dirtyForms.clear()
}

export function confirmDiscardDrafts(): boolean {
  if (!dirtyForms.size) return true
  if (!window.confirm('当前页面有尚未保存的修改，确定放弃并离开吗？')) return false
  clearDrafts()
  return true
}

export function applySession(session: SessionInfo | null): void {
  authState.checked = true
  authState.authenticated = Boolean(session?.authenticated)
  authState.expiresAt = session?.expires_at ?? null
}

export function rememberRoute(route: RouteLocationNormalizedLoaded | { fullPath: string }): void {
  if (route.fullPath !== '/login') intendedRoute.value = route.fullPath
}
