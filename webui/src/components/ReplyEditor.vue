<script setup lang="ts">
import { computed } from 'vue'
import {
  NAlert, NButton, NCard, NInput, NSelect, NSpace, NTag, NUpload, useMessage,
  type UploadCustomRequestOptions
} from 'naive-ui'
import { keywordMediaUrl, uploadKeywordImage } from '../api/client'
import type { ReplyMessage, ReplySegment } from '../api/types'

const props = withDefaults(defineProps<{ modelValue: ReplyMessage[]; welcome?: boolean; disabled?: boolean }>(), { welcome: false, disabled: false })
const emit = defineEmits<{ 'update:modelValue': [value: ReplyMessage[]] }>()
const message = useMessage()
const replies = computed(() => props.modelValue)
const segmentOptions = [
  { label: '文字', value: 'text' }, { label: 'QQ 表情', value: 'face' }, { label: '@ 成员', value: 'at' }
]

function update(next: ReplyMessage[]): void { emit('update:modelValue', next) }
function addReply(): void { update([...replies.value, [{ type: 'text', text: '' }]]) }
function removeReply(index: number): void { update(replies.value.filter((_, current) => current !== index)) }
function moveReply(index: number, offset: number): void {
  const next = replies.value.map((reply) => [...reply])
  const target = index + offset
  if (target < 0 || target >= next.length) return
  ;[next[index], next[target]] = [next[target], next[index]]
  update(next)
}
function makeSegment(type: string): ReplySegment {
  if (type === 'face') return { type: 'face', id: '0' }
  if (type === 'at') return { type: 'at', qq: 'all' }
  return { type: 'text', text: '' }
}
function addSegment(replyIndex: number, type: string): void {
  const next = replies.value.map((reply) => [...reply])
  next[replyIndex].push(makeSegment(type))
  update(next)
}
function replaceSegment(replyIndex: number, segmentIndex: number, segment: ReplySegment): void {
  const next = replies.value.map((reply) => [...reply])
  next[replyIndex][segmentIndex] = segment
  update(next)
}
function removeSegment(replyIndex: number, segmentIndex: number): void {
  const next = replies.value.map((reply) => [...reply])
  next[replyIndex].splice(segmentIndex, 1)
  update(next)
}
function moveSegment(replyIndex: number, segmentIndex: number, offset: number): void {
  const next = replies.value.map((reply) => [...reply])
  const target = segmentIndex + offset
  if (target < 0 || target >= next[replyIndex].length) return
  ;[next[replyIndex][segmentIndex], next[replyIndex][target]] = [next[replyIndex][target], next[replyIndex][segmentIndex]]
  update(next)
}
async function uploadImage(replyIndex: number, options: UploadCustomRequestOptions): Promise<void> {
  const raw = options.file.file
  if (!(raw instanceof File)) { options.onError(); return }
  try {
    const uploaded = await uploadKeywordImage(raw)
    const next = replies.value.map((reply) => [...reply])
    next[replyIndex].push({ type: 'image', name: uploaded.name })
    update(next)
    options.onFinish()
    message.success('图片已上传并加入回复')
  } catch (error) {
    options.onError()
    message.error(error instanceof Error ? error.message : '图片上传失败')
  }
}
</script>

<template>
  <div class="reply-editor">
    <NAlert v-if="welcome" type="info" :show-icon="false">发送首条入群欢迎时，机器人会自动 @ 新成员；无需在这里重复添加。</NAlert>
    <NCard v-for="(reply, replyIndex) in replies" :key="replyIndex" size="small" :title="`第 ${replyIndex + 1} 条回复`">
      <template #header-extra>
        <NSpace>
          <NButton size="tiny" quaternary :disabled="replyIndex === 0 || disabled" @click="moveReply(replyIndex, -1)">上移</NButton>
          <NButton size="tiny" quaternary :disabled="replyIndex === replies.length - 1 || disabled" @click="moveReply(replyIndex, 1)">下移</NButton>
          <NButton size="tiny" quaternary type="error" :disabled="disabled" @click="removeReply(replyIndex)">删除</NButton>
        </NSpace>
      </template>
      <div v-for="(segment, segmentIndex) in reply" :key="segmentIndex" class="segment-row">
        <NTag size="small">{{ segment.type === 'text' ? '文字' : segment.type === 'image' ? '图片' : segment.type === 'face' ? 'QQ 表情' : segment.type === 'at' ? '@' : '原始消息段' }}</NTag>
        <NInput v-if="segment.type === 'text'" :value="segment.text" type="textarea" autosize :disabled="disabled" placeholder="文字（[CQ:...] 会按普通文字发送）" @update:value="replaceSegment(replyIndex, segmentIndex, { type: 'text', text: $event })" />
        <div v-else-if="segment.type === 'image'" class="image-segment">
          <img :src="keywordMediaUrl(segment.name)" alt="已上传图片" />
          <span class="mono">{{ segment.name }}</span>
        </div>
        <NInput v-else-if="segment.type === 'face'" :value="segment.id" :disabled="disabled" placeholder="数字表情 ID" @update:value="replaceSegment(replyIndex, segmentIndex, { type: 'face', id: $event })" />
        <NInput v-else-if="segment.type === 'at'" :value="segment.qq" :disabled="disabled" placeholder="QQ 号或 all" @update:value="replaceSegment(replyIndex, segmentIndex, { type: 'at', qq: $event })" />
        <NAlert v-else type="warning" :show-icon="false">{{ segment.label }}（只读，可保留、移动或删除）</NAlert>
        <NSpace vertical size="small" :wrap="false">
          <NButton size="tiny" :disabled="segmentIndex === 0 || disabled" @click="moveSegment(replyIndex, segmentIndex, -1)">↑</NButton>
          <NButton size="tiny" :disabled="segmentIndex === reply.length - 1 || disabled" @click="moveSegment(replyIndex, segmentIndex, 1)">↓</NButton>
          <NButton size="tiny" type="error" :disabled="disabled" @click="removeSegment(replyIndex, segmentIndex)">×</NButton>
        </NSpace>
      </div>
      <NSpace class="segment-actions">
        <NSelect size="small" :options="segmentOptions" placeholder="添加消息段" :disabled="disabled" class="segment-select" @update:value="addSegment(replyIndex, $event)" />
        <NUpload :show-file-list="false" accept="image/png,image/jpeg,image/gif,image/webp" :disabled="disabled" :custom-request="(options) => uploadImage(replyIndex, options)">
          <NButton size="small" :disabled="disabled">上传并添加图片</NButton>
        </NUpload>
      </NSpace>
    </NCard>
    <NButton dashed block :disabled="disabled || replies.length >= 8" @click="addReply">添加回复（{{ replies.length }}/8）</NButton>
  </div>
</template>

<style scoped>
.reply-editor { display: flex; flex-direction: column; gap: 12px; }
.segment-row { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 10px; align-items: start; margin-bottom: 10px; }
.segment-actions { margin-top: 8px; }
.segment-select { width: 150px; }
.image-segment { display: flex; align-items: center; gap: 10px; min-width: 0; overflow-wrap: anywhere; }
.image-segment img { width: 88px; height: 64px; object-fit: contain; border-radius: 4px; background: rgba(128,128,128,.12); }
@media (max-width: 620px) { .segment-row { grid-template-columns: 1fr; } .segment-row > .n-space { flex-direction: row !important; } }
</style>
