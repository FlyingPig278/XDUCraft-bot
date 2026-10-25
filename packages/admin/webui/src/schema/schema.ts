import type { ConfigValues, JsonSchema, SchemaContext } from '../api/schema'

export const own = (value: object, key: string): boolean => Object.prototype.hasOwnProperty.call(value, key)
export function isObject(value: unknown): value is ConfigValues { return value !== null && typeof value === 'object' && !Array.isArray(value) }
export function clone<T>(value: T): T {
  if (Array.isArray(value)) return value.map((item) => clone(item)) as T
  if (isObject(value)) return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, clone(item)])) as T
  return value
}
export function atPath(value: unknown, path: string): unknown {
  return path.split('.').filter(Boolean).reduce<unknown>((current, key) => isObject(current) || Array.isArray(current) ? (current as ConfigValues)[key] : undefined, value)
}
export function resolve(schema: JsonSchema, root: JsonSchema, seen = new Set<string>()): JsonSchema {
  let result = schema
  if (schema.$ref) {
    if (!schema.$ref.startsWith('#/')) return { ...schema, 'x-ui-unsupported': '仅支持本地 schema 引用' }
    if (seen.has(schema.$ref)) return { ...schema, 'x-ui-unsupported': '循环引用没有可编辑的实体结构' }
    const next = new Set(seen).add(schema.$ref)
    const target = schema.$ref.slice(2).split('/').reduce<unknown>((current, part) => isObject(current) ? current[part.replace(/~1/g, '/').replace(/~0/g, '~')] : undefined, root)
    if (!isObject(target)) return { ...schema, 'x-ui-unsupported': `无法解析引用 ${schema.$ref}` }
    const { $ref: _ref, ...local } = schema
    result = { ...resolve(target as JsonSchema, root, next), ...local }
  }
  if (result.allOf) {
    const { allOf, ...base } = result
    result = allOf.reduce<JsonSchema>((merged, branch) => {
      const item = resolve(branch, root, seen)
      return { ...merged, ...item, properties: { ...merged.properties, ...item.properties }, required: [...new Set([...(merged.required ?? []), ...(item.required ?? [])])] }
    }, base)
  }
  return result
}
export function schemaType(schema: JsonSchema): string | undefined {
  const type = Array.isArray(schema.type) ? schema.type.find((item) => item !== 'null') : schema.type
  return type ?? (schema.properties ? 'object' : schema.items ? 'array' : schema.const !== undefined ? typeof schema.const : undefined)
}
export function nullable(schema: JsonSchema, root: JsonSchema): boolean {
  const item = resolve(schema, root)
  return item.type === 'null' || (Array.isArray(item.type) && item.type.includes('null')) || Boolean((item.anyOf ?? item.oneOf)?.some((branch) => resolve(branch, root).type === 'null'))
}
export function variants(schema: JsonSchema, root: JsonSchema): JsonSchema[] {
  const item = resolve(schema, root)
  return (item.oneOf ?? item.anyOf ?? []).map((branch) => resolve(branch, root)).filter((branch) => branch.type !== 'null')
}
export function effectiveSchema(schema: JsonSchema, root: JsonSchema): JsonSchema {
  const item = resolve(schema, root)
  const branches = variants(item, root)
  if (branches.length === 1) {
    const { anyOf: _any, oneOf: _one, ...base } = item
    return { ...base, ...branches[0] }
  }
  return item
}
export function branchIndex(branches: JsonSchema[], value: unknown, discriminator?: string): number {
  return branches.findIndex((branch) => {
    if (own(branch, 'const')) return Object.is(branch.const, value)
    if (branch.enum) return branch.enum.some((item) => Object.is(item, value))
    if (isObject(value) && branch.properties) {
      const literals = Object.entries(branch.properties).filter(([key, field]) => own(field, 'const') && (!discriminator || key === discriminator))
      return literals.length > 0 && literals.every(([key, field]) => Object.is(field.const, value[key]))
    }
    const type = schemaType(branch)
    return type === 'object' ? isObject(value) : type === 'array' ? Array.isArray(value) : type === 'integer' ? typeof value === 'number' && Number.isInteger(value) : typeof value === type
  })
}
export function creatable(schema: JsonSchema): boolean { return !schema.readOnly && schema['x-ui-creatable'] !== false && schema['x-ui-readonly'] !== true }
export function makeDefault(schema: JsonSchema, root: JsonSchema, refs = new Set<string>()): unknown {
  if (schema.$ref && refs.has(schema.$ref)) return undefined
  const nextRefs = new Set(refs)
  if (schema.$ref) nextRefs.add(schema.$ref)
  const item = effectiveSchema(schema, root)
  if (item.writeOnly || item['x-ui-secret']) return undefined
  if (own(item, 'const')) return clone(item.const)
  if (own(item, 'default')) return clone(item.default)
  const branches = variants(item, root)
  if (branches.length > 1) {
    const branch = branches.find(creatable)
    return branch ? makeDefault(branch, root, nextRefs) : undefined
  }
  if (item.enum?.length) return clone(item.enum[0])
  switch (schemaType(item)) {
    case 'object': {
      const value: ConfigValues = {}
      for (const [key, property] of Object.entries(item.properties ?? {})) {
        const resolved = resolve(property, root)
        if (!own(resolved, 'default') && !own(resolved, 'const') && !item.required?.includes(key)) continue
        const initial = makeDefault(property, root, nextRefs)
        if (initial !== undefined) value[key] = initial
      }
      return value
    }
    case 'array': return []
    case 'boolean': return false
    case 'integer': case 'number': {
      const bounds = numericBounds(item)
      let value = Math.min(bounds.max ?? Infinity, Math.max(bounds.min ?? -Infinity, 0))
      if (item.multipleOf && item.multipleOf > 0) {
        value = Math.ceil(value / item.multipleOf) * item.multipleOf
        if (bounds.max !== undefined && value > bounds.max) value = Math.floor(bounds.max / item.multipleOf) * item.multipleOf
      }
      if (schemaType(item) === 'number' && item.exclusiveMinimum !== undefined && value <= item.exclusiveMinimum) value = item.exclusiveMinimum + ((bounds.max ?? item.exclusiveMinimum + 2) - item.exclusiveMinimum) / 2
      if (schemaType(item) === 'number' && item.exclusiveMaximum !== undefined && value >= item.exclusiveMaximum) value = item.exclusiveMaximum - (item.exclusiveMaximum - (bounds.min ?? item.exclusiveMaximum - 2)) / 2
      return value
    }
    case 'string': return ''
    case 'null': return null
    default: return undefined
  }
}
export function visible(schema: JsonSchema, context: SchemaContext, parent?: unknown): boolean {
  if (schema['x-ui-hidden']) return false
  const scope = schema['x-ui-scope']
  if (scope === 'group_only' && context.scope !== 'group') return false
  if (scope === 'global_only' && context.scope === 'group') return false
  const condition = schema['x-ui-condition']
  if (!isObject(condition)) return true
  const path = String(condition.field ?? condition.path ?? '')
  const source = own(condition, 'field') ? parent : context.rootValue
  const actual = atPath(source, path)
  if (condition.operator === 'eq') return Object.is(actual, condition.value)
  if (condition.operator === 'neq') return !Object.is(actual, condition.value)
  return true
}
export function orderedFields(schema: JsonSchema, root: JsonSchema): Array<[string, JsonSchema]> {
  return Object.entries(schema.properties ?? {}).map(([key, field]) => [key, resolve(field, root)] as [string, JsonSchema]).sort((a, b) => Number(a[1]['x-ui-order'] ?? 0) - Number(b[1]['x-ui-order'] ?? 0))
}
const supportedWidgets: Record<string, true> = { tree: true, ordered_object_list: true, message_segments: true, reply_variants: true, image: true, asset: true, textarea: true, multiline: true, 'id-list': true, tags: true, id: true, color: true }
export function unsupported(schema: JsonSchema): string | undefined {
  if (schema['x-ui-unsupported']) return String(schema['x-ui-unsupported'])
  const widget = schema['x-ui-widget']
  if (widget !== undefined && (typeof widget !== 'string' || !own(supportedWidgets, widget))) return `不支持的 widget：${String(widget)}`
  for (const key of ['not', 'if', 'then', 'else', 'patternProperties', 'prefixItems', 'dependentSchemas']) if (own(schema, key)) return `不支持的 schema 条件：${key}`
  if (Array.isArray(schema.items)) return '不支持元组型数组'
  const condition = schema['x-ui-condition']
  if (condition !== undefined && (!isObject(condition) || !(typeof condition.field === 'string' || typeof condition.path === 'string') || !own(condition, 'value') || !['eq', 'neq'].includes(String(condition.operator)))) return '不支持的显示条件（仅支持 field/path、operator: eq/neq 和 value）'
  return undefined
}
export function errorText(context: SchemaContext, path: string): string | undefined {
  const error = context.errors[path] ?? context.errors[path ? `config.${path}` : 'config']
  return Array.isArray(error) ? error.join('；') : error
}
export function configured(context: SchemaContext, path: string): boolean {
  if (Array.isArray(context.secretFields)) return context.secretFields.includes(path)
  const value = context.secretFields[path]
  return typeof value === 'boolean' ? value : Boolean(value?.configured)
}

export function hasRedactedSecret(value: unknown, schema: JsonSchema, context: SchemaContext, path: string): boolean {
  let item = effectiveSchema(schema, context.rootSchema)
  const branches = variants(item, context.rootSchema)
  if (branches.length > 1) item = branches[branchIndex(branches, value, item.discriminator?.propertyName)] ?? item
  if ((item.writeOnly || item['x-ui-secret']) && configured(context, path)) return value === undefined
  if (isObject(value)) {
    return Object.entries(item.properties ?? {}).some(([key, field]) => hasRedactedSecret(value[key], field, context, path ? `${path}.${key}` : key))
  }
  if (Array.isArray(value) && item.items) return value.some((entry, index) => hasRedactedSecret(entry, item.items!, context, `${path}.${index}`))
  return false
}

export function safeLabel(value: unknown, schema: JsonSchema, key: unknown, root: JsonSchema): string | undefined {
  if (typeof key !== 'string') return undefined
  let field = effectiveSchema(schema, root)
  const branches = variants(field, root)
  if (branches.length > 1) field = branches[branchIndex(branches, value, field.discriminator?.propertyName)] ?? field
  for (const part of key.split('.')) {
    if (field.writeOnly || field['x-ui-secret']) return undefined
    const child = field.properties?.[part]
    if (!child) return undefined
    field = effectiveSchema(child, root)
  }
  const items = field.items ? effectiveSchema(field.items, root) : undefined
  if (field.writeOnly || field['x-ui-secret'] || items?.writeOnly || items?.['x-ui-secret']) return undefined
  const label = atPath(value, key)
  if (Array.isArray(label) && label.every((item) => typeof item === 'string' || typeof item === 'number')) return label.map(String).join('、') || undefined
  return typeof label === 'string' || typeof label === 'number' || typeof label === 'boolean' ? String(label) || undefined : undefined
}

export function numericBounds(schema: JsonSchema): { min?: number; max?: number } {
  const integer = schemaType(schema) === 'integer'
  const lower = schema.minimum === undefined ? -Infinity : integer ? Math.ceil(schema.minimum) : schema.minimum
  const upper = schema.maximum === undefined ? Infinity : integer ? Math.floor(schema.maximum) : schema.maximum
  const minimum = Math.max(lower, schema.exclusiveMinimum === undefined ? -Infinity : integer ? Math.floor(schema.exclusiveMinimum) + 1 : schema.exclusiveMinimum)
  const maximum = Math.min(upper, schema.exclusiveMaximum === undefined ? Infinity : integer ? Math.ceil(schema.exclusiveMaximum) - 1 : schema.exclusiveMaximum)
  return { min: minimum === -Infinity ? undefined : minimum, max: maximum === Infinity ? undefined : maximum }
}
