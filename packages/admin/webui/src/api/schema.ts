export type ConfigValues = Record<string, unknown>
export type SchemaScope = 'group' | 'global' | 'startup'
export interface AssetCapability {
  upload_url: string
  read_url_prefix: string
  max_bytes: number
  mime_types: string[]
}
export interface JsonSchema {
  $ref?: string
  $defs?: Record<string, JsonSchema>
  definitions?: Record<string, JsonSchema>
  type?: string | string[]
  title?: string
  description?: string
  default?: unknown
  const?: unknown
  enum?: unknown[]
  properties?: Record<string, JsonSchema>
  required?: string[]
  items?: JsonSchema
  additionalProperties?: boolean | JsonSchema
  anyOf?: JsonSchema[]
  oneOf?: JsonSchema[]
  allOf?: JsonSchema[]
  discriminator?: { propertyName: string; mapping?: Record<string, string> }
  readOnly?: boolean
  writeOnly?: boolean
  minimum?: number
  maximum?: number
  exclusiveMinimum?: number
  exclusiveMaximum?: number
  multipleOf?: number
  minLength?: number
  maxLength?: number
  pattern?: string
  format?: string
  minItems?: number
  maxItems?: number
  uniqueItems?: boolean
  [key: string]: unknown
}
export type SchemaErrors = Record<string, string | string[]>
export type SecretFields = string[] | Record<string, boolean | { configured: boolean }>
export interface SchemaContext {
  rootSchema: JsonSchema
  rootValue: ConfigValues
  scope: SchemaScope
  readonly: boolean
  errors: SchemaErrors
  defaults: ConfigValues
  overrideFields?: string[]
  secretFields: SecretFields
  choices: Record<string, unknown[]>
  media?: AssetCapability
}
