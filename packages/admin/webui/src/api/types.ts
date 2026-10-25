import type { AssetCapability, ConfigValues, JsonSchema, SchemaScope, SecretFields } from './schema'
export type { SecretFields } from './schema'

export type DecimalId = string
export type ResourceScope = SchemaScope
export interface ErrorEnvelope { error: { code: string; message: string; fields?: Record<string, unknown> } }
export interface SessionInfo { authenticated: true; csrf_token: string; expires_at: number }
export interface Resource<TConfig = ConfigValues, TMeta = ResourceMeta> { config: TConfig; meta: TMeta; revision: string }
export interface ResourceDescriptor { path: string; schema: JsonSchema; write_mode: 'replace' | 'patch'; scope: ResourceScope }
export interface ResourceMeta {
  [key: string]: unknown
  available?: boolean
  reason?: string
  defaults?: ConfigValues
  effective?: ConfigValues | boolean
  active?: ConfigValues
  applied?: ConfigValues
  overridden?: string[]
  restart_required?: boolean
  changed_keys?: string[]
  changed_startup_fields?: string[]
  choices?: Record<string, unknown[]>
  readonly_fields?: string[]
  secret_fields?: SecretFields
  notices?: unknown[]
  apply_status?: 'active' | 'applied' | 'success' | 'applying' | 'failed' | 'invalid' | string
  apply_scope?: ResourceScope
  apply_error?: unknown
  invalid_fields?: unknown
  orphaned_fields?: unknown
}
export interface FeatureConfig { enabled: boolean }
export interface FeatureMeta extends ResourceMeta {
  source?: string
  resettable?: boolean
  superuser_only?: boolean
  passive?: boolean
  effective?: boolean
  global_enabled?: boolean
  ready?: boolean
}
export interface FeatureState {
  [key: string]: unknown
  key: string
  name?: string
  description?: string
  enabled: boolean
  effective?: boolean
  source?: string
  resettable?: boolean
  global_configurable?: boolean
  superuser_only?: boolean
  scope?: 'group' | 'global' | 'system'
  revision?: string
  ready?: boolean
  available?: boolean
  eligible?: boolean
  unavailable_reason?: string
}
export interface PluginDescriptor {
  id: string
  short_name: string
  name: string
  loaded: boolean
  description?: string
  managed: boolean
  group_config: boolean
  global_config: boolean
  resources: Partial<Record<ResourceScope, ResourceDescriptor>>
  features: FeatureState[]
  context: Record<string, unknown> & {
    icon?: string
    available?: boolean
    reason?: string | null
    notices?: Array<{ type?: string; message: string }>
    details?: Array<{ label: string; value: unknown }>
  }
  control?: Resource<FeatureConfig, FeatureMeta>
  media?: AssetCapability
}
export interface PluginsResponse { plugins: PluginDescriptor[]; warnings?: string[] }
export interface BotOverview { bot_id: DecimalId; connected: boolean; nickname?: string }
export interface PluginOverview { id: string; name: string; loaded: boolean; reason?: string | null; description?: string }
export interface OverviewFeature { key: string; name: string; passive?: boolean; enabled: boolean }
export interface Overview { bots: BotOverview[]; plugins: PluginOverview[]; features?: OverviewFeature[]; restart_required: boolean }
export interface GroupSummary { group_id: DecimalId; name: string; bot_ids: DecimalId[]; connected: boolean; stale: boolean }
export interface GroupsResponse { groups: GroupSummary[]; warnings: string[] }
