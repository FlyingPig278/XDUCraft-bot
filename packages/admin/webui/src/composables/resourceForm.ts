import { computed, onScopeDispose, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { ApiError, apiGet, apiWrite } from '../api/client'
import type { ConfigValues, SchemaErrors } from '../api/schema'
import type { Resource, ResourceDescriptor, ResourceMeta } from '../api/types'
import { clone as snapshot, own } from '../schema/schema'
import { forgetResourceDraft, getResourceDraft, rememberResourceDraft } from '../state'

function canonical(value: unknown): string {
  return JSON.stringify(value, (_key, item: unknown) => item && typeof item === 'object' && !Array.isArray(item)
    ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b))) : item) ?? 'undefined'
}
function fieldErrors(error: ApiError): SchemaErrors {
  const result: SchemaErrors = {}
  function visit(value: unknown, path: string): void {
    if (typeof value === 'string') { result[path || 'resource'] = value; return }
    if (Array.isArray(value) && value.every((item) => typeof item === 'string')) {
      result[path || 'resource'] = value as string[]
      return
    }
    if (value && typeof value === 'object') {
      for (const [key, child] of Object.entries(value)) visit(child, path ? `${path}.${key}` : key)
      return
    }
    if (value !== undefined && value !== null) result[path || 'resource'] = String(value)
  }
  visit(error.fields, '')
  result.resource = error.message
  return result
}
function isConfig(value: unknown): value is ConfigValues {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}
function isMeta(value: unknown): value is ResourceMeta {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}

export function useResourceForm(descriptor: () => ResourceDescriptor) {
  const message = useMessage()
  const draft = ref<ConfigValues | null>(null)
  const saved = ref<ConfigValues | null>(null)
  const meta = ref<ResourceMeta>({})
  const revision = ref('')
  const overrideFields = ref<string[]>([])
  const savedOverrides = ref<string[]>([])
  const loading = ref(false)
  const saving = ref(false)
  const stale = ref(false)
  const conflict = ref<Resource | null>(null)
  const errors = ref<SchemaErrors>({})
  let generation = 0
  let loadedPath = ''
  onScopeDispose(() => { generation++ })

  const dirty = computed(() => draft.value !== null && saved.value !== null && (
    canonical(draft.value) !== canonical(saved.value) || canonical([...overrideFields.value].sort()) !== canonical([...savedOverrides.value].sort())
  ))

  function accept(resource: Resource): void {
    saved.value = snapshot(resource.config)
    draft.value = snapshot(resource.config)
    meta.value = snapshot(resource.meta)
    revision.value = resource.revision
    overrideFields.value = [...(resource.meta.overridden ?? [])]
    savedOverrides.value = [...overrideFields.value]
    stale.value = false
    conflict.value = null
    errors.value = {}
    forgetResourceDraft(descriptor().path)
  }

  function restoreCached(path: string, latest: Resource): boolean {
    const cached = getResourceDraft(path)
    if (!cached || !isConfig(cached.draft) || !isConfig(cached.saved) || !isMeta(cached.meta) || !cached.revision) return false
    saved.value = snapshot(cached.saved)
    draft.value = snapshot(cached.draft)
    meta.value = cached.revision === latest.revision ? snapshot(latest.meta) : snapshot(cached.meta)
    revision.value = cached.revision
    overrideFields.value = [...cached.overrideFields]
    savedOverrides.value = [...cached.savedOverrides]
    stale.value = cached.revision !== latest.revision
    conflict.value = stale.value ? snapshot(latest) : null
    errors.value = stale.value ? { resource: '登录期间配置已发生变化。草稿已保留，请比较后重新加载。' } : {}
    return true
  }

  async function load(): Promise<void> {
    const token = ++generation
    const path = descriptor().path
    const switching = loadedPath !== path
    loadedPath = path
    loading.value = true
    errors.value = {}
    if (switching) {
      draft.value = null
      saved.value = null
      meta.value = {}
      revision.value = ''
      overrideFields.value = []
      savedOverrides.value = []
      stale.value = false
      conflict.value = null
    }
    try {
      const resource = await apiGet<Resource>(path)
      if (token !== generation || path !== descriptor().path) return
      if (!restoreCached(path, resource)) accept(resource)
    } catch (error) {
      if (token !== generation || path !== descriptor().path) return
      errors.value = error instanceof ApiError ? fieldErrors(error) : { resource: error instanceof Error ? error.message : '读取配置失败' }
    } finally {
      if (token === generation) loading.value = false
    }
  }

  function payload(): ConfigValues | { set: ConfigValues; unset: string[] } {
    if (descriptor().write_mode === 'replace') return snapshot(draft.value ?? {})
    const values = draft.value ?? {}
    const set: ConfigValues = {}
    for (const field of overrideFields.value) {
      if (!own(values, field)) {
        if (!savedOverrides.value.includes(field)) throw new ApiError(422, 'missing_override_value', '新启用的独立字段需要明确值', { [field]: '请填写独立值；密钥不能从已隐藏的原值自动复制' })
        continue
      }
      if (!savedOverrides.value.includes(field) || canonical(values[field]) !== canonical(saved.value?.[field])) set[field] = snapshot(values[field])
    }
    return { set, unset: savedOverrides.value.filter((field) => !overrideFields.value.includes(field)) }
  }

  async function mutate(action: 'save' | 'apply' | 'rollback'): Promise<boolean> {
    if (!draft.value || !revision.value || saving.value || loading.value || stale.value) return false
    const current = descriptor()
    const path = current.path
    const token = generation
    saving.value = true
    errors.value = {}
    try {
      const resource = await apiWrite<Resource>(action === 'save' ? path : `${path}/${action}`, action === 'save' ? 'PUT' : 'POST', action === 'save' ? payload() : {}, revision.value)
      if (token !== generation || path !== descriptor().path) return false
      accept(resource)
      if (['failed', 'invalid', 'applying'].includes(resource.meta.apply_status ?? '')) {
        message.warning(resource.meta.apply_scope && resource.meta.apply_scope !== current.scope
          ? '本群配置已保存；共享配置仍待修复，请打开全局设置处理'
          : resource.meta.apply_status === 'applying' ? '配置已保存，正在应用；请刷新确认最终状态' : '配置已保存，但没有成功应用。请检查状态后重试或恢复')
      } else if (current.scope === 'startup' || resource.meta.restart_required) {
        message.success('设置已保存为下次启动值；当前进程未改变')
      } else {
        message.success(action === 'rollback' ? '已请求恢复，请查看实际应用状态' : '配置已保存并完成服务器回读')
      }
      return true
    } catch (error) {
      if (token !== generation || path !== descriptor().path) return false
      errors.value = error instanceof ApiError ? fieldErrors(error) : { resource: error instanceof Error ? error.message : '请求失败' }
      if (error instanceof ApiError && error.status === 409 && error.code === 'stale_config') {
        stale.value = true
        try {
          const latest = await apiGet<Resource>(path)
          if (token === generation && path === descriptor().path) conflict.value = latest
        } catch { /* Retain the draft and original revision when comparison cannot load. */ }
      }
      return false
    } finally {
      if (token === generation) saving.value = false
    }
  }

  function discard(): void {
    if (saved.value) draft.value = snapshot(saved.value)
    overrideFields.value = [...savedOverrides.value]
    errors.value = {}
    forgetResourceDraft(descriptor().path)
    // Discarding local edits does not make an obsolete revision current.
  }

  watch([draft, saved, meta, revision, overrideFields, savedOverrides, dirty], () => {
    const path = descriptor().path
    if (!dirty.value || !draft.value || !saved.value || !revision.value) {
      if (!saving.value) forgetResourceDraft(path)
      return
    }
    rememberResourceDraft({
      path,
      draft: snapshot(draft.value),
      saved: snapshot(saved.value),
      meta: snapshot(meta.value),
      revision: revision.value,
      overrideFields: [...overrideFields.value],
      savedOverrides: [...savedOverrides.value]
    })
  }, { deep: true, flush: 'sync' })

  return { draft, saved, meta, revision, overrideFields, loading, saving, stale, conflict, errors, dirty, load, discard, save: () => mutate('save'), retry: () => mutate('apply'), rollback: () => mutate('rollback') }
}
