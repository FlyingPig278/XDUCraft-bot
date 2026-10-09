<script setup lang="ts">
import { computed, h, ref, watch } from 'vue'
import {
  NAlert, NButton, NCheckbox, NDrawer, NDrawerContent, NForm, NFormItem, NInput, NInputNumber,
  NSelect, NSpace, NTree, useDialog, useMessage, type TreeOption
} from 'naive-ui'
import type { AuthMode, McServerNode } from '../api/types'

type UiNode = McServerNode & { _key: string; children: UiNode[] }
type DropInfo = { node: TreeOption; dragNode: TreeOption; dropPosition: 'before' | 'inside' | 'after' }

const props = defineProps<{ modelValue: McServerNode[]; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: McServerNode[]] }>()
const dialog = useDialog()
const message = useMessage()
let keySequence = 0
const roots = ref<UiNode[]>([])
const selectedKey = ref<string | null>(null)
const draggingKey = ref<string | null>(null)
const drawerOpen = ref(false)
const authOptions = [
  { label: '未配置 / 继承', value: '' }, { label: '正版', value: 'official' }, { label: 'MUA', value: 'mua' },
  { label: '西电统一认证', value: 'xdu' }, { label: 'Yggdrasil', value: 'yggdrasil' }, { label: '离线', value: 'offline' }, { label: '混合', value: 'mixed' }
]

function cloneForUi(nodes: McServerNode[]): UiNode[] {
  return [...nodes].sort((a, b) => (a.priority ?? 100) - (b.priority ?? 100)).map((node) => ({ ...node, _key: `server-${++keySequence}`, children: cloneForUi(node.children ?? []) }))
}
function toDomain(nodes: UiNode[]): McServerNode[] {
  return nodes.map(({ _key: _unused, children, ...node }) => ({ ...node, children: toDomain(children) }))
}
watch(() => props.modelValue, (value) => {
  if (JSON.stringify(value) === JSON.stringify(toDomain(roots.value))) return
  roots.value = cloneForUi(value)
  selectedKey.value = null
}, { immediate: true, deep: false })
function publish(): void { emit('update:modelValue', toDomain(roots.value)) }
function walk(nodes: UiNode[], parent: UiNode | null = null, depth = 0): Array<{ node: UiNode; parent: UiNode | null; depth: number }> {
  return nodes.flatMap((node) => [{ node, parent, depth }, ...walk(node.children, node, depth + 1)])
}
function subtreeHeight(node: UiNode): number { return node.children.length ? 1 + Math.max(...node.children.map(subtreeHeight)) : 0 }
const flat = computed(() => walk(roots.value))
const selected = computed(() => flat.value.find((entry) => entry.node._key === selectedKey.value) ?? null)
const treeData = computed<TreeOption[]>(() => roots.value as unknown as TreeOption[])
const parentOptions = computed(() => {
  if (!selected.value) return []
  const blocked = new Set(walk([selected.value.node]).map((entry) => entry.node._key))
  return [{ label: '根节点', value: '__root__' }, ...flat.value.filter((entry) => !blocked.has(entry.node._key) && entry.depth + 1 + subtreeHeight(selected.value!.node) <= 12).map((entry) => ({ label: entry.node.comment || entry.node.display_name || entry.node.ip || '未命名节点', value: entry.node._key }))]
})
const displayMode = computed(() => {
  const node = selected.value?.node
  if (!node) return 'original'
  if (!node.hide_ip) return 'original'
  return node.display_name ? 'custom' : 'hidden'
})

function defaultNode(): UiNode {
  return { _key: `server-${++keySequence}`, ip: '', comment: '', tag: '', tag_color: '', ignore_in_list: false, hide_ip: false, display_name: '', auth_mode: '', priority: 100, children: [] }
}
function addRoot(): void { const node = defaultNode(); roots.value.push(node); selectedKey.value = node._key; drawerOpen.value = true; publish() }
function addChild(): void {
  if (!selected.value) return
  if (selected.value.depth >= 12) { message.error('服务器树最多 13 层（根深度 0）'); return }
  const node = defaultNode()
  selected.value.node.children.push(node)
  selectedKey.value = node._key
  drawerOpen.value = true
  publish()
}
function findContainer(key: string): { container: UiNode[]; index: number } | null {
  const search = (nodes: UiNode[]): { container: UiNode[]; index: number } | null => {
    const index = nodes.findIndex((node) => node._key === key)
    if (index >= 0) return { container: nodes, index }
    for (const node of nodes) { const found = search(node.children); if (found) return found }
    return null
  }
  return search(roots.value)
}
function moveSibling(offset: number): void {
  if (!selectedKey.value) return
  const location = findContainer(selectedKey.value)
  if (!location) return
  const target = location.index + offset
  if (target < 0 || target >= location.container.length) return
  ;[location.container[location.index], location.container[target]] = [location.container[target], location.container[location.index]]
  location.container.forEach((node, index) => { node.priority = index })
  publish()
}
function requestDelete(): void {
  if (!selected.value) return
  const descendants = walk(selected.value.node.children).length
  dialog.warning({
    title: '删除服务器节点',
    content: descendants ? `该节点包含 ${descendants} 个后代，删除会一并移除。确定继续吗？` : '确定删除这个服务器节点吗？',
    positiveText: '删除', negativeText: '取消',
    onPositiveClick: () => {
      const location = selectedKey.value ? findContainer(selectedKey.value) : null
      if (!location) return
      location.container.splice(location.index, 1)
      selectedKey.value = null
      drawerOpen.value = false
      publish()
    }
  })
}
function patchNode(changes: Partial<McServerNode>): void {
  if (!selected.value) return
  Object.assign(selected.value.node, changes)
  publish()
}
function changeDisplayMode(mode: string): void {
  if (mode === 'original') patchNode({ hide_ip: false, display_name: '' })
  else if (mode === 'hidden') patchNode({ hide_ip: true, display_name: '' })
  else patchNode({ hide_ip: true, display_name: selected.value?.node.display_name || '自定义地址' })
}
function moveToParent(parentKey: string): void {
  if (!selectedKey.value || !selected.value) return
  const location = findContainer(selectedKey.value)
  if (!location) return
  const destinationEntry = parentKey === '__root__' ? null : flat.value.find((entry) => entry.node._key === parentKey)
  const destinationDepth = destinationEntry ? destinationEntry.depth + 1 : 0
  if (destinationDepth + subtreeHeight(selected.value.node) > 12) {
    message.error('移动后会超过服务器树最大深度')
    return
  }
  const [node] = location.container.splice(location.index, 1)
  const destination = destinationEntry?.node.children ?? roots.value
  destination.push(node)
  location.container.forEach((item, index) => { item.priority = index })
  destination.forEach((item, index) => { item.priority = index })
  publish()
}
function allowDrop(info: { node: TreeOption; dropPosition: 'before' | 'inside' | 'after'; phase: 'drag' | 'drop' }): boolean {
  const target = flat.value.find((entry) => entry.node._key === String(info.node._key))
  const dragged = flat.value.find((entry) => entry.node._key === draggingKey.value)
  if (!target || !dragged || walk([dragged.node]).some((entry) => entry.node._key === target.node._key)) return false
  const destinationDepth = info.dropPosition === 'inside' ? target.depth + 1 : target.depth
  return destinationDepth + subtreeHeight(dragged.node) <= 12
}
function handleDrop(info: DropInfo): void {
  const dragKey = String(info.dragNode._key)
  const targetKey = String(info.node._key)
  const source = findContainer(dragKey)
  const target = findContainer(targetKey)
  if (!source || !target) return
  const [dragged] = source.container.splice(source.index, 1)
  const refreshedTarget = findContainer(targetKey)
  if (!refreshedTarget) { source.container.splice(source.index, 0, dragged); return }
  const destination = info.dropPosition === 'inside' ? refreshedTarget.container[refreshedTarget.index].children : refreshedTarget.container
  if (info.dropPosition === 'inside') destination.push(dragged)
  else destination.splice(refreshedTarget.index + (info.dropPosition === 'after' ? 1 : 0), 0, dragged)
  const containers = new Set([source.container, destination])
  for (const container of containers) container.forEach((node, index) => { node.priority = index })
  selectedKey.value = dragKey
  publish()
}
function renderLabel({ option }: { option: TreeOption }): ReturnType<typeof h> {
  const node = option as unknown as UiNode
  return h('span', {}, `${node.comment || node.display_name || node.ip || '未命名服务器'} · ${node.ip || '未填写地址'}`)
}
</script>

<template>
  <div class="tree-editor">
    <NAlert type="info" :show-icon="false">拖拽节点可调整层级与顺序；移动会将受影响同级节点的 priority 重排为 0…n-1。</NAlert>
    <NSpace>
      <NButton type="primary" secondary :disabled="disabled" @click="addRoot">添加根节点</NButton>
      <NButton :disabled="disabled || !selected || selected.depth >= 12" @click="addChild">添加子节点</NButton>
      <NButton :disabled="disabled || !selected" @click="drawerOpen = true">编辑所选</NButton>
      <NButton :disabled="disabled || !selected" @click="moveSibling(-1)">上移</NButton>
      <NButton :disabled="disabled || !selected" @click="moveSibling(1)">下移</NButton>
      <NButton type="error" secondary :disabled="disabled || !selected" @click="requestDelete">删除</NButton>
    </NSpace>
    <NTree block-line :draggable="!disabled" :data="treeData" key-field="_key" :selected-keys="selectedKey ? [selectedKey] : []" :render-label="renderLabel" :allow-drop="allowDrop" :on-drop="handleDrop" @dragstart="draggingKey = String($event.node._key)" @dragend="draggingKey = null" @update:selected-keys="selectedKey = String($event[0] || '') || null" />
    <NDrawer v-model:show="drawerOpen" placement="right" width="min(520px, 100vw)">
      <NDrawerContent title="服务器节点" closable>
        <NForm v-if="selected" label-placement="top">
          <NFormItem label="服务器地址"><NInput :value="selected.node.ip" placeholder="host:port" @update:value="patchNode({ ip: $event })" /></NFormItem>
          <NFormItem label="备注"><NInput :value="selected.node.comment" @update:value="patchNode({ comment: $event })" /></NFormItem>
          <div class="form-grid">
            <NFormItem label="标签"><NInput :value="selected.node.tag" @update:value="patchNode({ tag: $event })" /></NFormItem>
            <NFormItem label="标签颜色（6 位 HEX）"><NInput :value="selected.node.tag_color" maxlength="6" placeholder="如 FFCC00" @update:value="patchNode({ tag_color: $event.toUpperCase() })" /></NFormItem>
            <NFormItem label="认证模式"><NSelect :value="selected.node.auth_mode" :options="authOptions" @update:value="patchNode({ auth_mode: $event as AuthMode })" /></NFormItem>
            <NFormItem label="优先级"><NInputNumber :value="selected.node.priority ?? 100" :precision="0" @update:value="patchNode({ priority: $event ?? 100 })" /></NFormItem>
            <NFormItem label="显示地址方式"><NSelect :value="displayMode" :options="[{label:'显示原地址',value:'original'},{label:'显示自定义地址',value:'custom'},{label:'完全隐藏地址',value:'hidden'}]" @update:value="changeDisplayMode" /></NFormItem>
            <NFormItem v-if="displayMode === 'custom'" label="自定义显示地址"><NInput :value="selected.node.display_name" @update:value="patchNode({ display_name: $event })" /></NFormItem>
            <NFormItem label="移动到父节点"><NSelect :value="selected.parent?._key || '__root__'" :options="parentOptions" @update:value="moveToParent" /></NFormItem>
            <NFormItem label="列表显示"><NCheckbox :checked="!selected.node.ignore_in_list" @update:checked="patchNode({ ignore_in_list: !$event })">出现在服务器列表中</NCheckbox></NFormItem>
          </div>
        </NForm>
      </NDrawerContent>
    </NDrawer>
  </div>
</template>

<style scoped>
.tree-editor { display: flex; flex-direction: column; gap: 14px; }
.tree-editor :deep(.n-tree) { min-height: 100px; border: 1px solid var(--n-border-color); border-radius: 6px; padding: 8px; }
</style>
