export type DecimalId = string

export interface ErrorEnvelope {
  error: { code: string; message: string; fields?: Record<string, string | string[]> }
}
export interface SessionInfo { authenticated: true; csrf_token: string; expires_at: number }
export interface Resource<TConfig, TMeta = Record<string, unknown>> {
  config: TConfig
  meta: TMeta
  revision: string
}

export interface BotOverview { bot_id: DecimalId; connected: boolean; nickname?: string }
export interface PluginOverview { id: string; name: string; loaded: boolean; reason?: string | null }
export interface OverviewFeature { key: string; name: string; passive: boolean; enabled: boolean }
export interface Overview { bots: BotOverview[]; plugins: PluginOverview[]; features: OverviewFeature[]; restart_required: boolean }
export interface GroupSummary {
  group_id: DecimalId
  name: string
  bot_ids: DecimalId[]
  connected: boolean
  stale: boolean
}
export interface GroupsResponse { groups: GroupSummary[]; warnings: string[] }

export interface FeatureState {
  key: string
  name?: string
  enabled: boolean
  effective?: boolean
  source?: string
  resettable?: boolean
  superuser_only?: boolean
  scope?: 'group' | 'global' | 'system'
  revision?: string
  active_whitelist_match?: boolean
  actual_effective?: boolean
  unavailable_reason?: string
}
export interface GroupPlugin {
  id: string
  short_name: string
  name: string
  loaded: boolean
  unavailable_reason?: string
  features: FeatureState[]
  group_config: boolean
  global_config: boolean
  invite?: GroupInviteSummary
}
export interface GroupInviteSummary {
  applicable: boolean
  initialized?: boolean
  initialized_at?: number | null
  configuration_complete?: boolean
  bound_group_id: DecimalId | null
  enabled?: boolean
}
export interface GroupPluginsResponse { plugins: GroupPlugin[]; warnings?: string[] }
export interface FeatureConfig { enabled: boolean }
export interface FeatureMeta { source: string; resettable: boolean; superuser_only: boolean; passive?: boolean }

export type AuthMode = '' | 'official' | 'mua' | 'xdu' | 'yggdrasil' | 'offline' | 'mixed'
export type StatusApiSource = 'protocol' | 'sjtu' | 'jsu' | 'custom' | 'auto' | 'auto_api_first'
export interface McServerNode {
  ip: string
  comment: string
  tag: string
  tag_color: string
  ignore_in_list: boolean
  hide_ip: boolean
  display_name: string
  auth_mode: AuthMode
  priority?: number
  children: McServerNode[]
}
export interface McGroupConfig {
  servers: McServerNode[]
  footer: string
  show_offline_by_default: boolean
  status_api_source: '' | StatusApiSource
  status_api_url: string
  default_auth_mode: AuthMode
  auth_detect: boolean
  quiet_admin_replies: boolean
}
export interface McGlobalConfig { status_api_source: StatusApiSource; status_api_url: string }

export interface TextSegment { type: 'text'; text: string }
export interface ImageSegment { type: 'image'; name: string }
export interface FaceSegment { type: 'face'; id: string }
export interface AtSegment { type: 'at'; qq: DecimalId | 'all' }
export interface OpaqueSegment {
  type: 'opaque'
  ref: { reply_index: number; segment_index: number }
  label: string
}
export type ReplySegment = TextSegment | ImageSegment | FaceSegment | AtSegment | OpaqueSegment
export type ReplyMessage = ReplySegment[]
export type KeywordMatch = 'contains' | 'exact' | 'prefix' | 'regex'
export interface KeywordRule {
  id: string | null
  keywords: string[]
  match: KeywordMatch
  enabled: boolean
  cooldown: number
  replies: ReplyMessage[]
  created_at?: number
}
export interface KeywordGroupConfig { rules: KeywordRule[]; join_replies: ReplyMessage[]; default_cooldown: number | null }
export interface KeywordGlobalConfig { rules: KeywordRule[]; default_cooldown: number }
export interface KeywordMeta { rule_created_at: Record<string, number>; effective_default_cooldown: number }

export interface HappyConfig { emoji_id: string | null }
export interface HappyMeta { effective_emoji_id: string }
export interface PigConfig { max_forward_results: number }
export interface WordcloudConfig {
  ban_user_ids: DecimalId[]
  min_word_length: number
  max_words: number
  retention_days: number
  additional_stopwords: string[]
  footer_subtitle: string
  footer_branding_enabled: boolean
  footer_branding_text: string
}
export interface AntiRecallConfig {
  cache_retention_hours: number
  recall_retention_days: number
  max_query_results: number
  save_media: boolean
  max_media_mb: number
  include_self: boolean
  exempt_user_ids: DecimalId[]
}
export interface InviteConfig { enabled: boolean }
export interface InviteMeta {
  initialized: boolean
  initialized_at: number | null
  configuration_complete: boolean
  bound?: boolean
  locked?: boolean
  unavailable_reason?: string
}

export interface DeploymentPublicConfig {
  mcs_brand: string | null
  mcs_title: string | null
  mcs_credit: string | null
  mcs_show_generated_at: boolean | null
  mcs_texture: string | null
  mcs_width: number | null
  mcs_scale: 2 | 4 | null
  mcs_min_height: number | null
  invite_group_id: DecimalId | null
  invite_api_url: string | null
  invite_api_secret_configured: boolean | null
  auto_accept_friend_group_ids: DecimalId[] | null
}
export interface DeploymentConfig { pending: DeploymentPublicConfig }
export type DeploymentSetKey = Exclude<keyof DeploymentPublicConfig, 'invite_api_secret_configured'> | 'invite_api_secret'
export interface DeploymentMeta {
  active: DeploymentPublicConfig
  overridden: DeploymentSetKey[]
  restart_required: boolean
  changed_keys: DeploymentSetKey[]
  textures: string[]
  unavailable: string[]
  invite_group_locked?: boolean
}
export interface DeploymentWrite {
  set: Partial<Record<DeploymentSetKey, string | number | boolean | string[]>>
  unset: DeploymentSetKey[]
}
