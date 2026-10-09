import { computed, ref, toRaw, type Ref } from 'vue'
import { useMessage } from 'naive-ui'
import { ApiError, apiGet, apiWrite } from '../api/client'
import type { Resource } from '../api/types'

export interface ResourceForm<TConfig, TMeta> {
  draft: Ref<TConfig | null>
  meta: Ref<TMeta | null>
  loading: Ref<boolean>
  saving: Ref<boolean>
  stale: Ref<boolean>
  errors: Ref<Record<string, string | string[]>>
  dirty: Readonly<Ref<boolean>>
  load: () => Promise<void>
  save: () => Promise<boolean>
  discard: () => void
}

export function useResourceForm<TConfig, TMeta = Record<string, unknown>>(path: () => string): ResourceForm<TConfig, TMeta> {
  const message = useMessage()
  const draft = ref<TConfig | null>(null) as Ref<TConfig | null>
  const saved = ref<TConfig | null>(null) as Ref<TConfig | null>
  const meta = ref<TMeta | null>(null) as Ref<TMeta | null>
  const revision = ref('')
  const loading = ref(false)
  const saving = ref(false)
  const stale = ref(false)
  const errors = ref<Record<string, string | string[]>>({})
  const dirty = computed(() => draft.value !== null && saved.value !== null && JSON.stringify(draft.value) !== JSON.stringify(saved.value))

  async function load(): Promise<void> {
    loading.value = true
    errors.value = {}
    try {
      const resource = await apiGet<Resource<TConfig, TMeta>>(path())
      saved.value = structuredClone(resource.config)
      draft.value = structuredClone(resource.config)
      meta.value = resource.meta
      revision.value = resource.revision
      stale.value = false
    } catch (error) {
      const text = error instanceof Error ? error.message : '读取配置失败'
      errors.value = { resource: text }
      message.error(text)
    } finally { loading.value = false }
  }

  async function save(): Promise<boolean> {
    if (!draft.value || !revision.value) return false
    saving.value = true
    errors.value = {}
    try {
      const resource = await apiWrite<Resource<TConfig, TMeta>>(path(), 'PUT', draft.value, revision.value)
      saved.value = structuredClone(resource.config)
      draft.value = structuredClone(resource.config)
      meta.value = resource.meta
      revision.value = resource.revision
      stale.value = false
      message.success('配置已保存')
      return true
    } catch (error) {
      if (error instanceof ApiError) {
        errors.value = error.fields
        if (error.status === 409 && error.code === 'stale_config') stale.value = true
      }
      message.error(error instanceof Error ? error.message : '保存失败')
      return false
    } finally { saving.value = false }
  }

  function discard(): void {
    if (saved.value) draft.value = structuredClone(toRaw(saved.value))
    errors.value = {}
    stale.value = false
  }

  return { draft, meta, loading, saving, stale, errors, dirty, load, save, discard }
}
