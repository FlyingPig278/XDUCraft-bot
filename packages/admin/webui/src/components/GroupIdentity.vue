<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  groupId: string
  name: string
  size?: number
  nameTag?: 'div' | 'h1' | 'h2' | 'h3'
  eager?: boolean
}>(), {
  size: 56,
  nameTag: 'div',
  eager: false
})

const imageFailed = ref(false)
const avatarUrl = computed(() => `/api/groups/${encodeURIComponent(props.groupId)}/avatar`)
const initials = computed(() => Array.from(props.name.trim() || '群').slice(0, 2).join(''))
const avatarStyle = computed(() => ({
  width: `${props.size}px`,
  height: `${props.size}px`,
  fontSize: `${Math.max(12, Math.round(props.size * 0.36))}px`
}))

watch(() => props.groupId, () => { imageFailed.value = false })
</script>

<template>
  <div class="group-identity">
    <div class="avatar-frame" :style="avatarStyle">
      <img
        v-if="!imageFailed"
        class="group-avatar"
        :src="avatarUrl"
        :alt="`${name}的 QQ 群头像`"
        :loading="eager ? 'eager' : 'lazy'"
        draggable="false"
        @error="imageFailed = true"
      >
      <div v-else class="avatar-fallback" role="img" :aria-label="`${name}的 QQ 群头像不可用`">
        {{ initials }}
      </div>
    </div>
    <div class="identity-copy">
      <component :is="nameTag" class="group-name">{{ name }}</component>
      <div class="group-number">QQ群 {{ groupId }}</div>
    </div>
  </div>
</template>

<style scoped>
.group-identity { display: flex; align-items: center; gap: 14px; min-width: 0; }
.avatar-frame { flex: 0 0 auto; overflow: hidden; border-radius: 12px; background: color-mix(in srgb, currentColor 10%, transparent); }
.group-avatar { display: block; width: 100%; height: 100%; object-fit: cover; }
.avatar-fallback { display: grid; width: 100%; height: 100%; place-items: center; font-weight: 700; font-size: inherit; color: inherit; background: color-mix(in srgb, #2080f0 16%, transparent); user-select: none; }
.identity-copy { min-width: 0; }
.group-name { margin: 0; font-size: 1rem; font-weight: 650; line-height: 1.35; overflow-wrap: anywhere; word-break: break-word; }
h1.group-name { font-size: 1.5rem; font-weight: 700; line-height: 1.25; }
h2.group-name { font-size: 1.2rem; font-weight: 700; line-height: 1.3; }
.group-number { margin-top: 3px; opacity: .64; font-size: 0.86rem; line-height: 1.35; overflow-wrap: anywhere; }
</style>
