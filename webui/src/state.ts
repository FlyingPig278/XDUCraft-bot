import { computed, reactive, ref } from 'vue'
import type { RouteLocationNormalizedLoaded } from 'vue-router'
import type { SessionInfo } from './api/types'
import { clone } from './schema/schema'

export const authState = reactive<{
  checked: boolean
  authenticated: boolean
  expiresAt: number | null
  sessionExpired: boolean
}>({ checked: false, authenticated: false, expiresAt: null, sessionExpired: false })

export const connectionState = reactive({ connectedBots: 0, restartRequired: false })
export const intendedRoute = ref<string | null>(null)


export interface MemoryResourceDraft {
  path: string
  draft: unknown
  saved: unknown
  meta: unknown
  revision: string
  overrideFields: string[]
  savedOverrides: string[]
}

const resourceDrafts = reactive(new Map<string, MemoryResourceDraft>())

export function rememberResourceDraft(snapshot: MemoryResourceDraft): void {
  resourceDrafts.set(snapshot.path, clone(snapshot))
}

export function getResourceDraft(path: string): MemoryResourceDraft | undefined {
  const snapshot = resourceDrafts.get(path)
  return snapshot ? clone(snapshot) : undefined
}

export function forgetResourceDraft(path: string): void {
  resourceDrafts.delete(path)
}


const dirtyForms = reactive(new Map<string, { discard: () => void; saving: () => boolean }>())
export const hasDirtyForms = computed(() => dirtyForms.size > 0 || resourceDrafts.size > 0)

export function registerDirtyForm(id: string, discard: () => void, saving: () => boolean = () => false): () => void {
  dirtyForms.set(id, { discard, saving })
  return () => dirtyForms.delete(id)
}

export function clearDrafts(): void {
  for (const entry of dirtyForms.values()) entry.discard()
  dirtyForms.clear()
  resourceDrafts.clear()
}

export function confirmDiscardDrafts(): boolean {
  const entries = [...dirtyForms.entries()]
  if (!entries.length && !resourceDrafts.size) return true
  if (entries.some(([, entry]) => entry.saving())) {
    window.alert('当前配置正在保存或应用，请等待请求结束后再离开。')
    return false
  }
  if (!window.confirm('当前区域有尚未保存的修改，确定放弃吗？')) return false
  for (const [id, entry] of entries) {
    entry.discard()
    dirtyForms.delete(id)
  }
  resourceDrafts.clear()
  return true
}

export function applySession(session: SessionInfo | null): void {
  authState.checked = true
  authState.authenticated = Boolean(session?.authenticated)
  authState.expiresAt = session?.expires_at ?? null
  if (session) authState.sessionExpired = false
}

export function rememberRoute(route: RouteLocationNormalizedLoaded | { fullPath: string }): void {
  if (route.fullPath !== '/login') intendedRoute.value = route.fullPath
}
