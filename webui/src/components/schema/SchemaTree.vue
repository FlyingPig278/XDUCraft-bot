<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NAlert, NButton, NDrawer, NDrawerContent, NSelect, NSpace, NTree, useDialog, useMessage, type TreeOption } from 'naive-ui'
import type { ConfigValues, JsonSchema, SchemaContext } from '../../api/schema'
import { effectiveSchema, hasRedactedSecret, isObject, makeDefault, own, safeLabel } from '../../schema/schema'
import SchemaField from './SchemaField.vue'

type Entry = { key: string; value: ConfigValues; children: Entry[] }
type Location = { node: Entry; parent: Entry | null; container: Entry[]; depth: number; path: string }
type DropInfo = { node: TreeOption; dragNode: TreeOption; dropPosition: 'before' | 'inside' | 'after' }
const props = defineProps<{ schema: JsonSchema; modelValue: unknown[]; context: SchemaContext; path: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown[]] }>()
const dialog = useDialog()
const message = useMessage()
const metadata = computed<ConfigValues>(() => isObject(props.schema['x-ui-tree']) ? props.schema['x-ui-tree'] : {})
const childrenKey = computed(() => typeof metadata.value.children === 'string' ? metadata.value.children : undefined)
const labelKey = computed(() => typeof metadata.value.label === 'string' ? metadata.value.label : undefined)
const orderKey = computed(() => typeof metadata.value.order === 'string' ? metadata.value.order : undefined)
const defaultOrder = computed(() => Number(metadata.value['default-order'] ?? 0))
const maxDepth = computed(() => typeof metadata.value['max-depth'] === 'number' ? metadata.value['max-depth'] : Infinity)
const valid = computed(() => Boolean(childrenKey.value && labelKey.value && props.schema.items) && maxDepth.value > 0 && validNodes(props.modelValue))
const reorderingAllowed = computed(() => Boolean(props.schema['x-ui-key-field']) || !hasRedactedSecret(props.modelValue, props.schema, props.context, props.path))
const roots = ref<Entry[]>([])
const selectedKey = ref<string | null>(null)
const draggingKey = ref<string | null>(null)
const drawerOpen = ref(false)
let sequence = 0
function validNodes(nodes: unknown[]): boolean {
  const key = childrenKey.value
  return nodes.every((value) => {
    if (!isObject(value)) return false
    if (!key || !own(value, key)) return true
    const children = value[key]
    return Array.isArray(children) && validNodes(children)
  })
}
function wrap(nodes: unknown[]): Entry[] {
  return nodes.filter(isObject).map((value) => ({ key: `node-${++sequence}`, value: { ...value }, children: childrenKey.value && Array.isArray(value[childrenKey.value]) ? wrap(value[childrenKey.value] as unknown[]) : [] }))
}
function domain(nodes: Entry[]): ConfigValues[] {
  return nodes.map((entry) => {
    const value = { ...entry.value }
    if (childrenKey.value && (own(value, childrenKey.value) || entry.children.length)) value[childrenKey.value] = domain(entry.children)
    return value
  })
}
watch(() => props.modelValue, (value) => {
  if (JSON.stringify(value) === JSON.stringify(domain(roots.value))) return
  roots.value = wrap(value)
  selectedKey.value = null
}, { immediate: true })
function publish(): void { emit('update:modelValue', domain(roots.value)) }
function walk(nodes: Entry[], parent: Entry | null = null, depth = 0, prefix = props.path): Location[] {
  return nodes.flatMap((node, index) => {
    const path = `${prefix}.${index}`
    return [{ node, parent, container: nodes, depth, path }, ...walk(node.children, node, depth + 1, `${path}.${childrenKey.value}`)]
  })
}
function height(node: Entry): number { return node.children.length ? 1 + Math.max(...node.children.map(height)) : 0 }
const flat = computed(() => walk(roots.value))
const selected = computed(() => flat.value.find(({ node }) => node.key === selectedKey.value))
function sorted(nodes: Entry[]): Entry[] {
  const key = orderKey.value
  return key ? [...nodes].sort((a, b) => Number(a.value[key] ?? defaultOrder.value) - Number(b.value[key] ?? defaultOrder.value)) : [...nodes]
}
function treeOptions(nodes: Entry[]): TreeOption[] {
  return sorted(nodes).map((node) => ({ key: node.key, label: safeLabel(node.value, props.schema.items ?? {}, labelKey.value, props.context.rootSchema) ?? '未命名节点', children: treeOptions(node.children) }))
}
const treeData = computed(() => treeOptions(roots.value))
const nodeSchema = computed(() => {
  const schema = effectiveSchema(props.schema.items ?? {}, props.context.rootSchema)
  const properties = { ...schema.properties }
  if (childrenKey.value) delete properties[childrenKey.value]
  return { ...schema, properties, required: schema.required?.filter((key) => key !== childrenKey.value) }
})
const nodeValue = computed(() => {
  const value = { ...selected.value?.node.value }
  if (childrenKey.value) delete value[childrenKey.value]
  return value
})
const parentOptions = computed(() => {
  if (!selected.value) return []
  const blocked = new Set(walk([selected.value.node]).map(({ node }) => node.key))
  return [{ label: '根节点', value: '__root__' }, ...flat.value.filter((entry) => !blocked.has(entry.node.key) && entry.depth + 1 + height(selected.value!.node) < maxDepth.value).map(({ node }) => ({ label: safeLabel(node.value, props.schema.items ?? {}, labelKey.value, props.context.rootSchema) ?? '未命名节点', value: node.key }))]
})
function normalizeOrder(container: Entry[]): void {
  const key = orderKey.value
  if (key) container.forEach((entry, index) => { entry.value[key] = index })
}
function capacity(parent: Entry | null): number {
  if (!parent) return props.schema.maxItems ?? Infinity
  const schema = effectiveSchema(props.schema.items ?? {}, props.context.rootSchema)
  const childSchema = childrenKey.value ? schema.properties?.[childrenKey.value] : undefined
  return childSchema ? effectiveSchema(childSchema, props.context.rootSchema).maxItems ?? Infinity : Infinity
}
function add(parent: Entry | null): void {
  if (props.context.readonly || !valid.value) return
  const entry = parent ? flat.value.find(({ node }) => node === parent) : undefined
  if (entry && entry.depth + 1 >= maxDepth.value) { message.error('添加后会超过声明的最大深度'); return }
  const initial = makeDefault(props.schema.items!, props.context.rootSchema)
  if (!isObject(initial)) { message.error('树节点 schema 必须声明对象'); return }
  const node: Entry = { key: `node-${++sequence}`, value: initial, children: [] }
  const container = parent?.children ?? roots.value
  if (container.length >= capacity(parent)) { message.error('节点数量达到上限'); return }
  container.push(node)
  if (parent && childrenKey.value && !own(parent.value, childrenKey.value)) parent.value[childrenKey.value] = []
  selectedKey.value = node.key
  drawerOpen.value = true
  publish()
}
function patch(value: unknown): void {
  if (!selected.value || props.context.readonly || !isObject(value)) return
  const previous = selected.value.node.value
  selected.value.node.value = { ...value }
  if (childrenKey.value && own(previous, childrenKey.value)) selected.value.node.value[childrenKey.value] = previous[childrenKey.value]
  publish()
}
function moveSibling(offset: number): void {
  if (!selected.value || props.context.readonly) return
  const container = selected.value.container
  const list = sorted(container)
  const index = list.indexOf(selected.value.node)
  const target = index + offset
  if (target < 0 || target >= list.length) return
  if (!reorderingAllowed.value) { message.warning('请重新输入隐藏的秘密字段后再调整树的顺序。'); return }
  ;[list[index], list[target]] = [list[target]!, list[index]!]
  container.splice(0, container.length, ...list)
  normalizeOrder(container)
  publish()
}
function canMove(node: Entry, target: Location | undefined, inside: boolean): boolean {
  if (!reorderingAllowed.value) return false
  const parent = target ? inside ? target.node : target.parent : null
  const container = parent?.children ?? roots.value
  if (!container.includes(node) && container.length >= capacity(parent)) return false
  if (!target) return height(node) < maxDepth.value
  if (walk([node]).some((entry) => entry.node === target.node)) return false
  return target.depth + (inside ? 1 : 0) + height(node) < maxDepth.value
}
function reparent(parentKey: string): void {
  if (!selected.value || props.context.readonly) return
  const source = selected.value
  const target = parentKey === '__root__' ? undefined : flat.value.find(({ node }) => node.key === parentKey)
  if (parentKey !== '__root__' && !target) return
  if (!canMove(source.node, target, true)) { message.error('不能形成循环或超过最大深度'); return }
  const destination = target?.node.children ?? roots.value
  if (destination === source.container) return
  const orderedSource = sorted(source.container).filter((node) => node !== source.node)
  const orderedDestination = sorted(destination)
  source.container.splice(0, source.container.length, ...orderedSource)
  destination.splice(0, destination.length, ...orderedDestination, source.node)
  normalizeOrder(source.container)
  normalizeOrder(destination)
  publish()
}
function remove(): void {
  if (!selected.value || props.context.readonly) return
  const entry = selected.value
  const count = walk(entry.node.children).length
  if (!reorderingAllowed.value && entry.container.indexOf(entry.node) < entry.container.length - 1) {
    message.warning('删除会改变隐藏秘密字段的位置，请先重新输入。')
    return
  }
  dialog.warning({ title: '删除树节点', content: count ? `此节点包含 ${count} 个后代，删除将一并移除。是否继续？` : '是否删除此节点？', positiveText: '删除', negativeText: '取消', onPositiveClick: () => {
    const index = entry.container.indexOf(entry.node)
    if (index < 0) return
    entry.container.splice(index, 1)
    selectedKey.value = null
    drawerOpen.value = false
    publish()
  } })
}
function allowDrop(info: { node: TreeOption; dropPosition: 'before' | 'inside' | 'after' }): boolean {
  const source = flat.value.find(({ node }) => node.key === draggingKey.value)
  const target = flat.value.find(({ node }) => node.key === String(info.node.key))
  return !props.context.readonly && Boolean(source && target && canMove(source.node, target, info.dropPosition === 'inside'))
}
function drop(info: DropInfo): void {
  if (props.context.readonly) return
  const source = flat.value.find(({ node }) => node.key === String(info.dragNode.key))
  const target = flat.value.find(({ node }) => node.key === String(info.node.key))
  if (!source || !target || !canMove(source.node, target, info.dropPosition === 'inside')) return
  const destination = info.dropPosition === 'inside' ? target.node.children : target.container
  const sourceList = sorted(source.container).filter((node) => node !== source.node)
  const destinationList = destination === source.container ? sourceList : sorted(destination)
  const position = info.dropPosition === 'inside' ? destinationList.length : destinationList.indexOf(target.node) + (info.dropPosition === 'after' ? 1 : 0)
  destinationList.splice(position, 0, source.node)
  if (destination !== source.container) source.container.splice(0, source.container.length, ...sourceList)
  destination.splice(0, destination.length, ...destinationList)
  normalizeOrder(source.container)
  if (destination !== source.container) normalizeOrder(destination)
  selectedKey.value = source.node.key
  publish()
}
</script>

<template>
  <div class="schema-tree">
    <NAlert v-if="!valid" type="warning">树的 children / label / 节点 schema 元数据缺失或现有节点不是对象；原始值保留，无法编辑。</NAlert>
    <template v-else>
      <NAlert type="info" :show-icon="false">拖拽可调整层级与顺序；仅移动时更新受影响的同级排序。<span v-if="Number.isFinite(maxDepth)">最多 {{ maxDepth }} 层。</span></NAlert>
      <NSpace>
        <NButton size="small" :disabled="context.readonly" @click="add(null)">添加根节点</NButton>
        <NButton size="small" :disabled="context.readonly || !selected || selected.depth + 1 >= maxDepth" @click="selected && add(selected.node)">添加子节点</NButton>
        <NButton size="small" :disabled="!selected" @click="drawerOpen = true">{{ context.readonly ? '查看' : '编辑' }}</NButton>
        <NButton size="small" :disabled="context.readonly || !selected" @click="moveSibling(-1)">上移</NButton>
        <NButton size="small" :disabled="context.readonly || !selected" @click="moveSibling(1)">下移</NButton>
        <NButton size="small" type="error" :disabled="context.readonly || !selected" @click="remove">删除</NButton>
      </NSpace>
      <NTree block-line :data="treeData" :draggable="!context.readonly" :selected-keys="selectedKey ? [selectedKey] : []" :allow-drop="allowDrop" :on-drop="drop" @dragstart="draggingKey = String($event.node.key)" @dragend="draggingKey = null" @update:selected-keys="selectedKey = $event.length ? String($event[0]) : null" />
      <NDrawer v-model:show="drawerOpen" placement="right" width="min(540px, 100vw)">
        <NDrawerContent :title="nodeSchema.title || '节点内容'" closable>
          <template v-if="selected">
            <SchemaField :key="selected.node.key" :schema="nodeSchema" :model-value="nodeValue" :context="context" :path="selected.path" :root="true" @update:model-value="patch" />
            <label class="parent-label">移动到父节点</label>
            <NSelect :value="selected.parent?.key || '__root__'" :options="parentOptions" :disabled="context.readonly || !reorderingAllowed" @update:value="reparent(String($event))" />
          </template>
        </NDrawerContent>
      </NDrawer>
    </template>
  </div>
</template>

<style scoped>
.schema-tree { display: flex; flex-direction: column; gap: 12px; width: 100%; min-width: 0; }
.schema-tree :deep(.n-tree-node-content__text) { white-space: normal; overflow-wrap: anywhere; }
.schema-tree :deep(.n-tree-node-content) { min-width: 0; }
.parent-label { display: block; margin: 12px 0 8px; }
</style>
