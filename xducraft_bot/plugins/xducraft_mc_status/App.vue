<script setup lang="ts">
// --- 1. 导入依赖 ---
import { ref, computed, nextTick, watch, onMounted, onBeforeUnmount, type Ref } from 'vue'
import draggable from 'vuedraggable'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
import {
  faSun,
  faMoon,
  faPlusCircle,
  faEdit,
  faTimes,
  faEyeSlash,
  faSave,
  faPlus,
  faTrash,
  faUpload,
  faClipboard,
  faSpinner
} from '@fortawesome/free-solid-svg-icons'
import { ColorPicker } from 'vue3-colorpicker'
import 'vue3-colorpicker/style.css'
import pako from 'pako'

// --- 数据压缩与编码 ---

// 定义服务器数据在紧凑数组表示中的索引常量，用于优化体积
const S_IP = 0;
const S_COMMENT = 1;
const S_TAG = 2;
const S_TAG_COLOR = 3;
const S_IGNORE = 4;
const S_CHILDREN = 5;

/**
 * 将服务器对象数组转换为更紧凑的数组格式以进行压缩。
 * @param {Server[]} servers - 服务器对象数组。
 * @returns {any[]} 转换后的紧凑数组。
 */
function jsonToCompactArray(servers: Server[]): any[] {
  if (!servers) return [];
  return servers.map(server => {
    const children = (server.children && server.children.length > 0)
      ? jsonToCompactArray(server.children)
      : 0;

    return [
      server.ip,
      server.comment || 0,
      server.tag || 0,
      server.tag_color || 0,
      server.ignore_in_list ? 1 : 0,
      children
    ];
  });
}

/**
 * 将紧凑数组格式的数据转换回标准服务器对象数组。
 * @param {any[]} compactData - 紧凑数组。
 * @returns {Server[]} 转换后的服务器对象数组。
 */
function compactArrayToJson(compactData: any[]): Server[] {
  return compactData.map(item => {
    const children = Array.isArray(item[S_CHILDREN])
      ? compactArrayToJson(item[S_CHILDREN])
      : [];

    const server: Server = {
      ip: item[S_IP],
      comment: item[S_COMMENT] || '',
      tag: item[S_TAG] || '',
      tag_color: item[S_TAG_COLOR] || 'FF9800',
      tag_color_with_hash: item[S_TAG_COLOR] ? `#${item[S_TAG_COLOR]}` : '#FF9800',
      ignore_in_list: item[S_IGNORE] === 1,
      children: children,
      // 以下是需要补全的默认/计算属性
      server_type: 'standalone', // 将在 buildTree 中被修正
      parent_ip: '', // 将在 buildTree 中被修正
      selectedPreset: ''
    };
    return server;
  });
}

/**
 * 将 Base64 字符串转换为 URL 安全的格式。
 * @param base64 - 标准 Base64 字符串。
 * @returns URL 安全的 Base64 字符串。
 */
function toUrlSafeBase64(base64: string): string {
  return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

/**
 * 将 URL 安全的 Base64 字符串转换回标准格式。
 * @param urlSafeBase64 - URL 安全的 Base64 字符串。
 * @returns 标准 Base64 字符串。
 */
function fromUrlSafeBase64(urlSafeBase64: string): string {
  let base64 = urlSafeBase64.replace(/-/g, '+').replace(/_/g, '/');
  while (base64.length % 4) {
    base64 += '=';
  }
  return base64;
}

/**
 * 压缩并编码配置对象为 URL 安全的字符串。
 * @param configObject - 完整的应用配置对象。
 * @returns 压缩和编码后的字符串。
 */
function compressConfig(configObject: AppConfig): string {
  try {
    const compactServers = jsonToCompactArray(configObject.servers);
    const compactStructure = [
      configObject.footer || 0,
      configObject.show_offline_by_default ? 1 : 0,
      compactServers
    ];
    const jsonString = JSON.stringify(compactStructure);
    const compressed = pako.deflate(jsonString, { level: 9 });
    const base64 = btoa(String.fromCharCode.apply(null, compressed as any));
    return toUrlSafeBase64(base64);
  } catch (e) {
    console.error("压缩失败:", e);
    return '';
  }
}

/**
 * 解码并解压字符串，还原为配置对象。
 * @param encodedString - 经过编码和压缩的字符串。
 * @returns 应用配置对象，如果失败则返回 null。
 */
function decompressConfig(encodedString: string): AppConfig | null {
  try {
    const base64 = fromUrlSafeBase64(encodedString);
    const binaryString = atob(base64);
    const charData = binaryString.split('').map(x => x.charCodeAt(0));
    const inflated = pako.inflate(new Uint8Array(charData), { to: 'string' });
    const compactStructure = JSON.parse(inflated);

    const servers = compactArrayToJson(compactStructure[2]);

    return {
      footer: compactStructure[0] === 0 ? '' : (compactStructure[0] || ''),
      show_offline_by_default: compactStructure[1] === 1,
      servers: servers
    };
  } catch (e) {
    console.error("解压失败:", e);
    return null;
  }
}

// --- (TS) 核心数据结构定义 ---
interface Server {
  ip: string;
  comment: string;
  tag: string;
  tag_color: string;
  tag_color_with_hash: string;
  server_type: 'standalone' | 'parent' | 'child';
  parent_ip: string;
  selectedPreset: string;
  ignore_in_list: boolean;
  priority?: number; // 用于拖拽排序，在拖拽结束后生成
  children: Server[]; // 存储子服务器，用于构建UI树形结构
}

interface AppConfig {
  footer: string;
  servers: Server[];
  show_offline_by_default: boolean;
}


// --- 2. 静态配置数据 ---

/**
 * @description 预设服务器标签，用于在弹窗中快速选择。
 */
const presets: Record<string, { tag: string; tag_color_with_hash: string }> = {
  "lobby": { tag: "大厅", tag_color_with_hash: "#3498DB" },
  "survival": { tag: "生存", tag_color_with_hash: "#2ECC71" },
  "creative": { tag: "创造", tag_color_with_hash: "#F1C40F" },
  "mod": { tag: "模组", tag_color_with_hash: "#E67E22" },
  "pvp": { tag: "PVP", tag_color_with_hash: "#E74C3C" },
  "recreation": { tag: "复原", tag_color_with_hash: "#9B59B6" }
}

/**
 * @description 服务器类型及其对应的显示文本。
 */
const serverTypeLabels: Record<string, string> = {
  standalone: '独立服务器',
  parent: '父服务器',
  child: '子服务器'
}

// --- 3. 核心响应式状态 ---

const config = ref<AppConfig>({
  footer: "",
  servers: [],
  show_offline_by_default: false
})

// UI上显示的服务器树形结构，由 `config.servers` 扁平列表计算而来。
const serverTree = ref<Server[]>([])

// 导入文本框的内容。
const jsonInput = ref(``)

// --- 主题切换 ---
const isDarkMode = ref(false);

function applyTheme(dark: boolean) {
  isDarkMode.value = dark;
  if (dark) {
    document.documentElement.classList.add('dark-mode');
    localStorage.setItem('theme', 'dark');
  } else {
    document.documentElement.classList.remove('dark-mode');
    localStorage.setItem('theme', 'light');
  }
}

function toggleTheme() {
  applyTheme(!isDarkMode.value);
}

// --- 4. 模态弹窗状态 ---

// --- (A) 通用 Alert/Confirm 弹窗 ---
const isModalVisible = ref(false)
const modalTitle = ref('')
const modalMessage = ref('')
const modalType = ref('alert')
const modalResolve = ref<((value: boolean | PromiseLike<boolean>) => void) | null>(null)

// --- (B) “添加/编辑”服务器弹窗状态 ---
const isServerModalVisible = ref(false)
const modalMode = ref<'add' | 'edit'>('add')
const currentServerData = ref<Partial<Server> | null>(null)
const editingServerIp = ref<string | null>(null)
const isSaving = ref(false) // 保存按钮的加载状态
const isDraggingChild = ref(false) // 是否正在拖拽子服务器

// --- (C) 弹窗及自定义下拉框的 DOM 引用和 A11y 状态 ---
const alertModalRef = ref<HTMLElement | null>(null)
const serverModalRef = ref<HTMLElement | null>(null)
const isParentSelectOpen = ref(false)
const activeParentIndex = ref(-1)
const parentSelectTriggerRef = ref<HTMLElement | null>(null)
const parentSelectOptionsRef = ref<HTMLElement | null>(null)
const isPresetSelectOpen = ref(false)
const presetSelectTriggerRef = ref<HTMLElement | null>(null)
const presetSelectOptionsRef = ref<HTMLElement | null>(null)
const activePresetIndex = ref(-1)
const isColorPickerOpen = ref(false)
const colorPickerTriggerRef = ref<HTMLElement | null>(null)
const colorPickerPanelRef = ref<HTMLElement | null>(null)
let cancelModalTimeout: number | null = null; // 统一的弹窗清理句柄

// --- (D) Toast 提示状态 ---
const isToastVisible = ref(false);
const toastMessage = ref('');
let toastTimeout: number | null = null;

// 使用常量替代魔法字符串，提高代码可维护性
const MODAL_MODE = Object.freeze({ ADD: 'add', EDIT: 'edit' });
const SERVER_TYPE = Object.freeze({ STANDALONE: 'standalone', PARENT: 'parent', CHILD: 'child' });

// 为弹窗内的元素定义 ID，用于 a11y 属性 (aria-labelledby, aria-describedby)
const modalIds = {
  alertTitle: 'alert-modal-title',
  alertMessage: 'alert-modal-message',
  serverTitle: 'server-modal-title',
  serverBody: 'server-modal-body'
}

// --- 5. A11y (无障碍) & 焦点管理 ---

const focusableSelectors = 'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex^="-"])'

/**
 * 在指定的容器内聚焦第一个可交互的元素。
 * 优先聚焦带有 `data-autofocus` 属性的元素。
 * @param containerRef - 容器的 Vue ref 或 HTMLElement。
 */
function focusFirstWithin(containerRef: Ref<HTMLElement | null> | HTMLElement) {
  nextTick(() => {
    const container = containerRef instanceof HTMLElement ? containerRef : containerRef?.value;
    if (!container) return
    const preferred = container.querySelector('[data-autofocus]') as HTMLElement | null
    const fallback = container.querySelector(focusableSelectors) as HTMLElement | null
    const target = preferred || fallback || container
    target.focus()
  })
}

// 监听各个弹窗的显示状态，自动聚焦
watch(isModalVisible, (visible) => {
  if (!visible) return
  focusFirstWithin(alertModalRef)
})

watch(isServerModalVisible, (visible) => {
  if (!visible) return
  focusFirstWithin(serverModalRef)
})

/**
 * 在弹窗内捕获 Tab 键，实现焦点循环。
 * @param event - 键盘事件。
 * @param containerRef - 弹窗容器的 Vue ref 或 HTMLElement。
 */
function trapFocus(event: KeyboardEvent, containerRef: Ref<HTMLElement | null> | HTMLElement) {
  const container = containerRef instanceof HTMLElement ? containerRef : containerRef?.value;
  if (!container) return
  const focusable = Array.from(container.querySelectorAll(focusableSelectors)) as HTMLElement[];
  if (focusable.length === 0) {
    event.preventDefault()
    container.focus()
    return
  }
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  const active = document.activeElement as HTMLElement | null;
  if (event.shiftKey) {
    if (active === first || active === container) {
      event.preventDefault()
      last?.focus()
    }
  } else if (active === last) {
    event.preventDefault()
    first?.focus()
  }
}

/**
 * 全局键盘事件处理器。
 * - Escape 键：按层级关闭最上层的 UI 元素（如弹窗、下拉框）。
 * - Tab 键：在弹窗内实现焦点循环。
 */
function handleGlobalKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    if (isModalVisible.value) {
      event.preventDefault()
      onModalCancel()
    }
    else if (isColorPickerOpen.value) {
      event.preventDefault()
      isColorPickerOpen.value = false;
      (colorPickerTriggerRef.value as HTMLElement | null)?.focus()
    }
    else if (isPresetSelectOpen.value) {
      event.preventDefault()
      isPresetSelectOpen.value = false;
      (presetSelectTriggerRef.value as HTMLElement | null)?.focus()
    }
    else if (isParentSelectOpen.value) {
      event.preventDefault()
      isParentSelectOpen.value = false;
      (parentSelectTriggerRef.value as HTMLElement | null)?.focus()
    }
    else if (isServerModalVisible.value) {
      event.preventDefault()
      closeServerModal()
    }
  } else if (event.key === 'Tab') {
    if (isColorPickerOpen.value) {
      isColorPickerOpen.value = false
      trapFocus(event, serverModalRef)
    }
    else if (isPresetSelectOpen.value) {
      isPresetSelectOpen.value = false
      trapFocus(event, serverModalRef)
    }
    else if (isParentSelectOpen.value) {
      isParentSelectOpen.value = false
      trapFocus(event, serverModalRef)
    }
    else if (isModalVisible.value) {
      trapFocus(event, alertModalRef)
    } else if (isServerModalVisible.value) {
      trapFocus(event, serverModalRef)
    }
  }
}

// --- 6. 计算属性 (Computed Properties) ---

/**
 * @description 计算出所有可以作为“父服务器”的服务器 (即 `standalone` 或 `parent` 类型)。
 */
const potentialParentServers = computed<Server[]>(() => {
  if (!config.value.servers) return []
  return config.value.servers.filter(s => s.server_type === SERVER_TYPE.PARENT || s.server_type === SERVER_TYPE.STANDALONE)
})

/**
 * @description 计算出最终用于“导出”的、经过清理的配置对象。
 * 该对象使用嵌套的 `servers` 树结构，以保留父子关系。
 */
const outputJson = computed<AppConfig>(() => {
  function cleanNode(node: Server): Server {
    const newNode: Server = {
      ip: node.ip,
      comment: node.comment,
      tag: node.tag,
      tag_color: node.tag_color,
      tag_color_with_hash: node.tag_color_with_hash,
      ignore_in_list: node.ignore_in_list,
      children: [],
      server_type: node.server_type || 'standalone',
      parent_ip: node.parent_ip || '',
      selectedPreset: node.selectedPreset || ''
    };
    if (node.children && node.children.length > 0) {
      newNode.children = node.children.map(cleanNode);
    }
    return newNode;
  }

  const cleanServers = serverTree.value.map(cleanNode);

  return {
    footer: config.value.footer,
    show_offline_by_default: config.value.show_offline_by_default,
    servers: cleanServers
  };
});

/**
 * @description 计算出用于 URL 分享的、经过压缩和编码的字符串。
 */
const compressedOutput = computed<string>(() => {
  return compressConfig(outputJson.value);
});

/**
 * @description 计算出用于QQ机器人的导入命令。
 */
const importCommand = computed<string>(() => {
  return `/mcs import ${compressedOutput.value}`;
});

/**
 * @description 计算当前在编辑弹窗中选中的“父服务器”对象，用于在下拉框中显示其名称。
 */
const selectedParent = computed<Server | undefined>(() => {
  if (!currentServerData.value || !currentServerData.value.parent_ip) {
    return undefined
  }
  return potentialParentServers.value.find(p => p.ip === currentServerData.value?.parent_ip)
})

/**
 * @description 计算当前在编辑弹窗中选中的“预设”对象，用于在下拉框中显示其内容。
 */
const selectedPresetObject = computed<{ tag: string; tag_color_with_hash: string; } | undefined>(() => {
  if (!currentServerData.value || !currentServerData.value.selectedPreset) {
    return undefined
  }
  return presets[currentServerData.value.selectedPreset]
})

const isAddMode = computed(() => modalMode.value === MODAL_MODE.ADD);

// --- 7. 方法 (Methods) ---

// --- (A) 通用 Alert/Confirm 弹窗方法 ---

function showAlert(message: string, title = '提示') {
  modalTitle.value = title
  modalMessage.value = message
  modalType.value = 'alert'
  isModalVisible.value = true
}

function showConfirm(message: string, title = '请确认'): Promise<boolean> {
  modalTitle.value = title
  modalMessage.value = message
  modalType.value = 'confirm'
  isModalVisible.value = true
  return new Promise((resolve) => {
    modalResolve.value = resolve
  })
}

function onModalConfirm() {
  isModalVisible.value = false
  if (modalResolve.value) {
    (modalResolve.value as (value: boolean) => void)(true)
  }
  modalResolve.value = null
}

function onModalCancel() {
  isModalVisible.value = false
  if (modalResolve.value) {
    modalResolve.value(false)
  }
  modalResolve.value = null
}

/**
 * @description 显示一个短暂的 Toast 提示消息。
 * @param {string} message - 要显示的消息。
 */
function showToast(message: string) {
  if (toastTimeout) {
    clearTimeout(toastTimeout);
  }
  toastMessage.value = message;
  isToastVisible.value = true;
  toastTimeout = window.setTimeout(() => {
    isToastVisible.value = false;
    toastTimeout = null;
  }, 3000);
}

// --- (B) “添加/编辑”服务器弹窗方法 ---

/**
 * @description 创建一个用于“添加”弹窗的空白服务器对象。
 * @param {Server | null} parentServer - 如果是添加子服务器，需传入其父服务器对象。
 * @returns {object} 一个新的服务器数据对象。
 */
function createBlankServer(parentServer: Server | null = null): Partial<Server> {
  return {
    ip: "",
    comment: "",
    tag: "",
    tag_color: "FF9800",
    tag_color_with_hash: "#FF9800",
    server_type: SERVER_TYPE.STANDALONE,
    parent_ip: parentServer ? parentServer.ip : "",
    selectedPreset: "",
    ignore_in_list: false,
    children: []
  }
}

/**
 * @description 打开服务器编辑弹窗，可用于“添加”或“编辑”模式。
 * @param {Server | null} [serverToEdit=null] - 要编辑的服务器对象。如果为 null，则为添加模式。
 * @param {Server | null} [parentServer=null] - (仅添加模式) 如果要添加子服务器，需传入其父服务器对象。
 */
async function openServerModal(serverToEdit: Server | null = null, parentServer: Server | null = null) {
  // 为防止快速连续点击导致状态错乱，先清除可能存在的关闭弹窗的计时器
  if (cancelModalTimeout) {
    clearTimeout(cancelModalTimeout)
    cancelModalTimeout = null
  }

  isSaving.value = false;

  // 先将数据设为 null，以确保 Vue 的 v-if 指令能够正确触发组件的重新渲染
  currentServerData.value = null
  await nextTick()

  if (serverToEdit) {
    modalMode.value = MODAL_MODE.EDIT
    editingServerIp.value = serverToEdit.ip
    currentServerData.value = JSON.parse(JSON.stringify(serverToEdit)) // 使用深拷贝以避免直接修改原始数据
  } else {
    modalMode.value = MODAL_MODE.ADD
    editingServerIp.value = null
    currentServerData.value = createBlankServer(parentServer)
  }

  isServerModalVisible.value = true
}

/**
 * @description 关闭服务器编辑弹窗，并延迟清理弹窗内的数据。
 */
function closeServerModal() {
  isServerModalVisible.value = false

  if (cancelModalTimeout) {
    clearTimeout(cancelModalTimeout)
  }

  // 延迟清理数据，以保证关闭动画的流畅性
  cancelModalTimeout = window.setTimeout(() => {
    currentServerData.value = null
    editingServerIp.value = null
    cancelModalTimeout = null
  }, 300)
}

/**
 * @description 保存“添加”或“编辑”的服务器。包含表单验证、数据更新和依赖处理。
 */
async function saveServer() {
  if (!currentServerData.value || isSaving.value) return;

  isSaving.value = true;
  const server = currentServerData.value as Server;
  const newIp = (server.ip || "").trim();

  // --- 1. 验证 ---
  if (newIp === '') {
    showAlert('服务器地址 (IP) 不能为空！', '保存失败');
    isSaving.value = false;
    return;
  }

  const isIpChanged = newIp !== editingServerIp.value;
  if (isIpChanged) {
    const isDuplicate = config.value.servers.some(s => s.ip === newIp);
    if (isDuplicate) {
      showAlert(`服务器地址 (IP) "${newIp}" 已存在！\n请使用唯一的 IP 地址。`, '保存失败');
      isSaving.value = false;
      return;
    }
  }

  if (server.parent_ip) {
    // 验证1: 父服务器不能成为子服务器
    if (modalMode.value === MODAL_MODE.EDIT && server.children && server.children.length > 0) {
      showAlert(
        `服务器 [${server.ip}] 本身是一个父服务器，因此不能被设置为其他服务器的子服务器。`,
        '保存失败'
      );
      isSaving.value = false;
      return;
    }
    // 验证2: 防止循环依赖
    if (checkForCircularDependency(editingServerIp.value || newIp, server.parent_ip)) {
      showAlert(
        `无法将服务器 [${server.parent_ip}] 设置为父服务器，因为这会创建一个循环依赖关系。`,
        '保存失败'
      );
      isSaving.value = false;
      return;
    }
  }

  // --- 2. 更新数据 ---
  server.ip = newIp;

  // 根据 parent_ip 自动设置 server_type
  if (server.parent_ip) {
    server.server_type = SERVER_TYPE.CHILD;
    // 自动将独立的父服转换为 'parent' 类型
    const parent = config.value.servers.find(s => s.ip === server.parent_ip);
    if (parent && parent.server_type === SERVER_TYPE.STANDALONE) {
      parent.server_type = SERVER_TYPE.PARENT;
    }
  } else {
    // 如果它有子节点，将在 flattenTreeAndSync 中被更正为 'parent'
    server.server_type = SERVER_TYPE.STANDALONE;
  }

  // --- 3. 应用更改到扁平列表 ---
  if (modalMode.value === MODAL_MODE.EDIT) {
    // 如果 IP 地址被修改，需要更新所有子服务器的 parent_ip
    if (isIpChanged && editingServerIp.value) {
      config.value.servers.forEach(s => {
        if (s.parent_ip === editingServerIp.value) {
          s.parent_ip = newIp;
        }
      });
    }

    // 找到并更新原始服务器对象
    const originalServer = config.value.servers.find(s => s.ip === editingServerIp.value);
    if (originalServer) {
      Object.assign(originalServer, server);
    }
  } else {
    // 添加新服务器
    config.value.servers.push(server as Server);
  }

  // --- 4. 收尾 ---
  isSaving.value = false;
  closeServerModal();
  showToast(modalMode.value === MODAL_MODE.ADD ? '服务器已成功添加！' : '服务器已成功更新！');
}

// --- (C) 服务器增删改查及列表操作 ---

/**
 * @description “添加服务器”按钮的快捷方式，打开服务器编辑弹窗。
 */
const addServer = () => openServerModal(null, null)

/**
 * @description “添加子服务器”按钮的快捷方式。
 * @param {Server} parent - 该子服务器的父服务器对象。
 */
const addChildServer = (parent: Server) => openServerModal(null, parent)

/**
 * @description 删除一个服务器（及其所有子服务器）。
 */
async function removeServer(server: Server) {
  const serverToRemove = server

  let confirmed = false
  if (serverToRemove.server_type === 'parent' || serverToRemove.server_type === 'standalone') {
    const childCount = config.value.servers.filter(s => s.parent_ip === serverToRemove.ip).length
    const message = `确定要删除服务器 ${serverToRemove.ip} 吗？${childCount > 0 ? `\n(其 ${childCount} 个子服务器将一并删除)` : ''}`
    confirmed = await showConfirm(message, '删除确认');
  } else {
    confirmed = await showConfirm(`确定要删除服务器 ${serverToRemove.ip} 吗？`, '删除确认');
  }

  if (confirmed) {
    if (serverToRemove.server_type === 'parent' || serverToRemove.server_type === 'standalone') {
      // 删除父服及其所有子服
      const parentIp = serverToRemove.ip
      config.value.servers = config.value.servers.filter(s => {
        return s.ip !== serverToRemove.ip && s.parent_ip !== parentIp
      })
    } else {
      // 只删除一个子服
      const index = config.value.servers.findIndex(s => s.ip === serverToRemove.ip);
      if (index > -1) {
        config.value.servers.splice(index, 1)
      }
    }
  }
}

/**
 * @description 删除所有服务器，操作前会弹出确认框。
 */
async function removeAllServers() {
  const confirmed = await showConfirm(
    `您确定要删除所有 ${config.value.servers.length} 个服务器吗？\n此操作不可撤销。`,
    '删除全部确认'
  );
  if (confirmed) {
    config.value.servers = [];
  }
}

/**
 * @description vuedraggable 的 :move 钩子，用于定义拖拽规则。
 * 主要规则：禁止将一个父服务器（即包含子服务器的服务器）拖拽进另一个服务器的子列表中。
 * @param {any} moveEvent - vuedraggable 提供的移动事件对象。
 * @returns {boolean} - 如果允许移动则返回 true，否则返回 false。
 */
function checkMove(moveEvent: any): boolean {
  const draggedEl = moveEvent.draggedContext.element as Server
  const toEl = moveEvent.to as HTMLElement

  // --- 1. 拖拽子服务器时，设置标志位 ---
  if (moveEvent.dragged.parentElement.classList.contains('child-list')) {
    isDraggingChild.value = true;
  } else {
    isDraggingChild.value = false;
  }

  // --- 2. 禁止将父服务器拖拽进子列表 ---
  if (
    draggedEl &&
    draggedEl.children &&
    draggedEl.children.length > 0
  ) {
    if (toEl && toEl.classList && toEl.classList.contains('child-list')) {
      return false
    }
  }

  // --- 3. 处理子服务器“向左拖出”取消嵌套的逻辑 ---
  if (isDraggingChild.value) {
    const rootList = document.querySelector('.server-list-anim-root');
    if (toEl === rootList) {
      // 当子服务器被拖到根列表时，允许移动
      return true;
    }
  }

  return true
}

// --- (D) 弹窗内的表单交互逻辑 ---

function updateColorFromPicker(server: Server) {
  server.tag_color = server.tag_color_with_hash.substring(1).toUpperCase()
}

function applyPreset(server: Server) {
  const presetKey = server.selectedPreset
  if (!presetKey || !presets[presetKey]) return

  const preset = presets[presetKey]
  if (preset) {
    server.tag = preset.tag
    server.tag_color_with_hash = preset.tag_color_with_hash
    updateColorFromPicker(server)
  }
}

function checkIfCustom(server: Server) {
  if (!server.selectedPreset || !presets[server.selectedPreset]) return
  const preset = presets[server.selectedPreset]

  if (preset && (server.tag !== preset.tag || server.tag_color_with_hash !== preset.tag_color_with_hash)) {
    server.selectedPreset = ""
  }
}

function onColorInput(server: Server) {
  updateColorFromPicker(server)
  checkIfCustom(server)
}

/**
 * @description 切换父服务器下拉框的显示。
 */
function toggleParentSelect() {
  isParentSelectOpen.value = !isParentSelectOpen.value
  if (isParentSelectOpen.value) {
    const currentIndex = potentialParentServers.value.findIndex(p => p.ip === currentServerData.value?.parent_ip);
    activeParentIndex.value = currentIndex > -1 ? currentIndex + 1 : 0; // +1 因为第一个是“无”
  } else {
    activeParentIndex.value = -1;
  }
}

/**
 * @description 处理父服务器下拉框的键盘导航（上下箭头选择，Enter键确认）。
 */
function handleParentSelectKeydown(event: KeyboardEvent) {
  if (!isParentSelectOpen.value) return;

  const optionsCount = potentialParentServers.value.length + 1;
  if (event.key === 'ArrowDown') {
    event.preventDefault();
    activeParentIndex.value = (activeParentIndex.value + 1) % optionsCount;
  } else if (event.key === 'ArrowUp') {
    event.preventDefault();
    activeParentIndex.value = (activeParentIndex.value - 1 + optionsCount) % optionsCount;
  } else if (event.key === 'Enter') {
    event.preventDefault();
    if (activeParentIndex.value >= 0) {
      const selectedIp = activeParentIndex.value === 0
        ? ''
        : (potentialParentServers.value[activeParentIndex.value - 1]?.ip ?? '');
      if (selectedIp !== editingServerIp.value) {
        selectParent(selectedIp);
      }
    }
  }
  nextTick(() => {
    const highlightedElement = parentSelectOptionsRef.value?.querySelector('.is-active');
    highlightedElement?.scrollIntoView({ block: 'nearest' });
  });
}

/**
 * @description 在下拉框中选择一个新的父服务器。
 */
function selectParent(parentIp: string) {
  if (currentServerData.value) {
    currentServerData.value.parent_ip = parentIp
  }
  isParentSelectOpen.value = false
    ; (parentSelectTriggerRef.value as HTMLElement | null)?.focus()
}

/**
 * @description 处理点击外部区域以关闭父服务器下拉框的逻辑。
 */
function handleClickOutsideParentSelect(event: MouseEvent) {
  if (
    isParentSelectOpen.value &&
    parentSelectTriggerRef.value && !(parentSelectTriggerRef.value as HTMLElement).contains(event.target as Node) &&
    parentSelectOptionsRef.value && !(parentSelectOptionsRef.value as HTMLElement).contains(event.target as Node)
  ) {
    isParentSelectOpen.value = false
  }
}

/**
 * @description 切换快捷预设下拉框的显示。
 */
function togglePresetSelect() {
  isPresetSelectOpen.value = !isPresetSelectOpen.value;
  if (isPresetSelectOpen.value) {
    const presetKeys = Object.keys(presets);
    const currentIndex = presetKeys.indexOf(currentServerData.value?.selectedPreset || '');
    activePresetIndex.value = currentIndex > -1 ? currentIndex + 1 : 0;
  } else {
    activePresetIndex.value = -1;
  }
}

/**
 * @description 处理预设下拉框的键盘导航（上下箭头选择，Enter键确认）。
 */
function handlePresetSelectKeydown(event: KeyboardEvent) {
  if (!isPresetSelectOpen.value) return;

  const optionsCount = Object.keys(presets).length + 1;
  if (event.key === 'ArrowDown') {
    event.preventDefault();
    activePresetIndex.value = (activePresetIndex.value + 1) % optionsCount;
  } else if (event.key === 'ArrowUp') {
    event.preventDefault();
    activePresetIndex.value = (activePresetIndex.value - 1 + optionsCount) % optionsCount;
  } else if (event.key === 'Enter') {
    event.preventDefault();
    if (activePresetIndex.value >= 0) {
      const presetKeys = Object.keys(presets);
      const selectedKey = activePresetIndex.value === 0 ? '' : presetKeys[activePresetIndex.value - 1];
      selectPreset(selectedKey as string);
    }
  }
  nextTick(() => {
    const highlightedElement = (presetSelectOptionsRef.value as HTMLElement | null)?.querySelector('.is-active');
    (highlightedElement as HTMLElement | null)?.scrollIntoView({ block: 'nearest' });
  });
}

/**
 * @description 在下拉框中选择一个新的预设。
 */
function selectPreset(presetKey: string) {
  if (currentServerData.value) {
    currentServerData.value.selectedPreset = presetKey
    applyPreset(currentServerData.value as Server);
  }
  isPresetSelectOpen.value = false
  activePresetIndex.value = -1;
  ; (presetSelectTriggerRef.value as HTMLElement | null)?.focus()
}

/**
 * @description 处理点击外部区域以关闭预设下拉框的逻辑。
 */
function handleClickOutsidePresetSelect(event: MouseEvent) {
  if (
    isPresetSelectOpen.value &&
    presetSelectTriggerRef.value && !(presetSelectTriggerRef.value as HTMLElement).contains(event.target as Node) &&
    presetSelectOptionsRef.value && !(presetSelectOptionsRef.value as HTMLElement).contains(event.target as Node)
  ) {
    isPresetSelectOpen.value = false
  }
}

/**
 * @description 切换颜色选择器的显示状态。
 */
function toggleColorPicker() {
  isColorPickerOpen.value = !isColorPickerOpen.value
}

/**
 * @description 关闭颜色选择器并使焦点返回到触发器按钮。
 */
function closeColorPicker() {
  isColorPickerOpen.value = false
    ; (colorPickerTriggerRef.value as HTMLElement | null)?.focus()
}

// --- (E) 导入/导出 (IO) 操作 ---

/**
 * @description 复制QQ机器人导入命令到剪贴板。
 */
function copyImportCommand() {
  navigator.clipboard.writeText(importCommand.value).then(() => {
    showToast('导入命令已复制！请直接将其发送到QQ群中。');
  }, () => {
    showAlert('复制失败！请检查浏览器权限。', '复制失败');
  });
}

/**
 * @description 将当前配置下载为 JSON 文件。
 */
function downloadJson() {
  const jsonString = JSON.stringify(outputJson.value, null, 2);
  const blob = new Blob([jsonString], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'mcs-config.json';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * @description “加载配置”按钮的点击事件处理器。
 * 支持从 URL、JSON 文本、/mcs import 命令或裸压缩字符串加载。
 */
async function loadConfig() {
  if (config.value.servers.length > 0) {
    const confirmed = await showConfirm(
      '您确定要加载新的配置吗？\n当前编辑器中的所有服务器都将被替换。',
      '覆盖确认'
    );
    if (!confirmed) {
      return;
    }
  }

  let input = jsonInput.value.trim();
  if (!input) {
    showAlert('输入框不能为空。', '提示');
    return;
  }

  // 1. 标准化输入：处理 /mcs import 前缀
  if (input.startsWith('/mcs import ')) {
    input = input.substring('/mcs import '.length).trim();
  }

  let newConfig: AppConfig | null = null;

  // 2. 尝试按优先级顺序解析输入
  // 优先级 1: URL with ?data= param
  if (input.startsWith('http') && input.includes('?data=')) {
    try {
      const url = new URL(input);
      const dataFromUrl = url.searchParams.get('data');
      if (dataFromUrl) {
        newConfig = decompressConfig(dataFromUrl);
        if (!newConfig) {
          showAlert('无法解压来自链接的数据，链接可能不完整或已损坏。', '导入失败');
          return;
        }
      } else {
        showAlert('链接中未找到有效的“data”参数。', '导入失败');
        return;
      }
    } catch (e) {
      showAlert('输入的分享链接无效。', '导入失败');
      return;
    }
  } else {
    // 优先级 2: 裸压缩字符串
    newConfig = decompressConfig(input);

    // 优先级 3: JSON 文本 (如果解压失败)
    if (!newConfig) {
      try {
        // `parseAndSetConfig` 期望一个字符串或对象，这里我们直接给它字符串
        const success = parseAndSetConfig(input);
        if (success) {
          showToast(`配置已成功加载！共导入 ${config.value.servers.length} 个服务器。`);
          jsonInput.value = '';
        }
        // parseAndSetConfig 会处理自己的错误提示，所以这里直接返回
        return;
      } catch (e) {
        // 如果 `parseAndSetConfig` 内部的 JSON.parse 失败，它会抛出异常并显示 alert。
        // 如果我们到了这里，说明所有尝试都失败了。
        showAlert('输入的内容无法被识别为有效链接、JSON或压缩数据。请检查输入是否正确。', '导入失败');
        return;
      }
    }
  }

  // 3. 如果通过 URL 或解压获得了配置对象，则加载它
  if (newConfig) {
    const success = parseAndSetConfig(newConfig);
    if (success) {
      showToast(`配置已成功加载！共导入 ${config.value.servers.length} 个服务器。`);
      jsonInput.value = '';
    }
  }
}

/**
 * @description 解析 JSON 字符串或已解压的对象，并将其加载到应用的状态中。
 * @param {string | AppConfig} input - JSON 字符串或配置对象。
 * @returns {boolean} - 解析和加载是否成功。
 */
function parseAndSetConfig(input: string | AppConfig): boolean {
  function flattenImportedServers(servers: any[], parentIp = ""): any[] {
    if (!Array.isArray(servers)) return [];
    const flatList: any[] = [];
    servers.forEach(s => {
      s.parent_ip = s.parent_ip || parentIp;
      const children = s.children;
      delete s.children;
      flatList.push(s);
      if (children) {
        flatList.push(...flattenImportedServers(children, s.ip));
      }
    });
    return flatList;
  }

  function processAndValidate(flatList: any[]): Server[] {
    const ipSet = new Set<string>();
    const duplicates: string[] = [];
    const validatedServers: Server[] = [];

    flatList.forEach(s => {
      if (!s.ip) {
        throw new Error('导入失败：存在没有 IP 地址的服务器条目。');
      }
      if (ipSet.has(s.ip)) {
        duplicates.push(s.ip);
      }
      ipSet.add(s.ip);

      // 补全 UI 辅助属性和默认值
      const server: Partial<Server> = {
        ...s,
        tag_color_with_hash: (s.tag_color && s.tag_color.length > 0) ? '#' + s.tag_color : '#FF9800',
        selectedPreset: "",
        ignore_in_list: s.ignore_in_list || false,
        comment: s.comment || "",
        children: []
      };
      validatedServers.push(server as Server);
    });

    if (duplicates.length > 0) {
      throw new Error(`导入失败：JSON 数据中包含重复的 IP 地址。\n重复项: ${[...new Set(duplicates)].join(', ')}`);
    }

    return validatedServers.sort((a, b) => (a.priority || 0) - (b.priority || 0));
  }

  let importedConfig: any;
  try {
    if (typeof input === 'string') {
      importedConfig = JSON.parse(input);
    } else {
      importedConfig = input;
    }

    const flatServers = flattenImportedServers(importedConfig.servers || []);
    const validatedServers = processAndValidate(flatServers);

    let footerContent = importedConfig.footer;
    if (typeof footerContent === 'object' && footerContent !== null && 'text' in footerContent) {
      footerContent = (footerContent as { text: string }).text;
    }

    config.value.servers = validatedServers;
    config.value.footer = footerContent || "";
    config.value.show_offline_by_default = importedConfig.show_offline_by_default || false;

    return true;
  } catch (e) {
    showAlert(e instanceof Error ? e.message : String(e), '导入失败');
    return false;
  }
}

// --- (F) 辅助函数 (Helpers) ---

/**
 * @description 检查设置父服务器时是否会造成循环依赖。
 * @param {string} serverIp - 当前服务器的 IP。
 * @param {string} newParentIp - 计划设置的父服务器 IP。
 * @returns {boolean} - 如果会造成循环则返回 true。
 */
function checkForCircularDependency(serverIp: string, newParentIp: string): boolean {
  if (!newParentIp || serverIp === newParentIp) {
    return false;
  }

  let currentIp: string | undefined = newParentIp;
  const visited = new Set<string>([serverIp]);

  while (currentIp) {
    if (visited.has(currentIp)) {
      return true; // 发现循环
    }
    visited.add(currentIp);

    const parentServer = config.value.servers.find(s => s.ip === currentIp);
    currentIp = parentServer ? parentServer.parent_ip : undefined;
  }

  return false;
}

/**
 * @description 根据给定的十六进制颜色代码，计算出对比度最高的文本颜色（黑色或白色）。
 */
function getContrastColor(hexColor: string): string {
  if (!hexColor || hexColor.length < 7) return '#000000';
  const r = parseInt(hexColor.substr(1, 2), 16);
  const g = parseInt(hexColor.substr(3, 2), 16);
  const b = parseInt(hexColor.substr(5, 2), 16);
  const yiq = ((r * 299) + (g * 587) + (b * 114)) / 1000;
  return (yiq >= 128) ? '#000000' : '#FFFFFF';
}

/**
 * @description 清理 IP 地址字符串，使其可用作 HTML 元素的 ID。
 */
function sanitizeIpForId(ip: string | undefined): string {
  if (!ip) return 'new-server';
  return ip.replace(/[^a-zA-Z0-9_-]/g, '_');
}

// --- 8. 核心数据同步 ---

/**
 * @description 将扁平的服务器列表（`config.servers`）转换为嵌套的树形结构，用于 UI 渲染。
 * @param {Server[]} flatList - 扁平的服务器数组。
 * @returns {Server[]} - 嵌套的树形结构数组。
 */
function buildTree(flatList: Server[]): Server[] {
  const map: Record<string, Server> = {}
  const serversWithChildren: Server[] = flatList
    .map(server => {
      const serverCopy = { ...server, children: [] }
      map[serverCopy.ip] = serverCopy
      return serverCopy
    })

  const tree: Server[] = []

  serversWithChildren.forEach(server => {
    if (server.parent_ip) {
      const parent = map[server.parent_ip]
      if (parent) {
        server.server_type = 'child'
        parent.children.push(server)
      } else {
        // 孤儿节点：父节点不存在，将其视为根节点
        server.parent_ip = ''
        server.server_type = 'standalone'
        tree.push(server)
      }
    } else {
      // 根节点
      tree.push(server)
    }
  })

  return tree
}

/**
 * @description 拖拽操作结束后，将 UI 的树形结构 (`serverTree`) 扁平化，并同步回核心数据 `config.value.servers`。
 * 同时，重新计算所有服务器的 `server_type` 和 `priority`。
 */
function flattenTreeAndSync() {
  isDraggingChild.value = false; // 重置标志位
  const newFlatList: Server[] = []
  let priorityCounter = 0

  function traverse(nodes: Server[], parentIp = "") {
    if (!nodes) return

    nodes.forEach((server) => {
      server.parent_ip = parentIp

      if (parentIp) {
        server.server_type = 'child'
      }
      else if (server.children && server.children.length > 0) {
        server.server_type = 'parent'
      } else {
        server.server_type = 'standalone'
      }

      server.priority = (priorityCounter + 1) * 10
      priorityCounter++

      const { children, ...flatServer } = server
      newFlatList.push(flatServer as Server)

      if (children) {
        traverse(children, server.ip)
      }
    })
  }

  traverse(serverTree.value, "")

  // 为避免触发不必要的 watch 更新循环，先临时停止监听，更新数据后再重新启动。
  stopWatch()
  config.value.servers = newFlatList
  nextTick(() => {
    startWatch()
  })
}

// 监听 `config.servers` 的变化，并自动更新 `serverTree`
const stopWatch = watch(
  () => config.value.servers,
  (newFlatList) => {
    serverTree.value = buildTree(newFlatList)
  },
  {
    deep: true,
    immediate: true
  }
)

const startWatch = () => {
  stopWatch() // 确保旧的已停止
  watch(
    () => config.value.servers,
    (newFlatList) => {
      serverTree.value = buildTree(newFlatList)
    },
    { deep: true, immediate: true }
  )
}

// --- 9. 初始化与生命周期 ---

onMounted(async () => {
  // 优先检查 URL search params 中是否有名为 'data' 的参数
  const urlParams = new URLSearchParams(window.location.search);
  const dataFromUrl = urlParams.get('data');

  if (dataFromUrl) {
    const decompressedConfig = decompressConfig(dataFromUrl);
    if (decompressedConfig) {
      const success = parseAndSetConfig(decompressedConfig);
      if (success) {
        showToast('已从 URL 成功导入配置！');
        // 清理 URL，避免刷新时重复导入
        window.history.replaceState({}, document.title, window.location.pathname);
      } else {
        showAlert('从 URL 导入配置失败，数据可能已损坏。', '导入失败');
      }
    } else {
      showAlert('无法解压来自 URL 的数据，链接可能不完整或已损坏。', '导入失败');
    }
    return; // 处理完 URL 后即返回，不再处理剪贴板
  }

  // 如果 URL 中没有数据，再尝试从剪贴板自动导入
  try {
    const text = await navigator.clipboard.readText();
    if (!text) return;

    const data = JSON.parse(text);

    if (data && (Array.isArray(data.servers) || data.hasOwnProperty('footer'))) {
      jsonInput.value = text;
      parseAndSetConfig(text);
      showToast('已从剪贴板自动导入配置。');
    }
  } catch (e: any) {
    console.warn('从剪贴板自动导入失败:', e.message);
  }

  // 初始化时加载一个空配置
  if (config.value.servers.length === 0 && !config.value.footer) {
    parseAndSetConfig(`{}`);
  }

  // 初始化主题
  const savedTheme = localStorage.getItem('theme')
  if (savedTheme) {
    applyTheme(savedTheme === 'dark')
  } else {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    applyTheme(prefersDark)
  }

  // 添加全局事件监听
  document.addEventListener('keydown', handleGlobalKeydown);
});

onBeforeUnmount(() => {
  // 移除全局事件监听，防止内存泄漏
  document.removeEventListener('keydown', handleGlobalKeydown);
  document.removeEventListener('mousedown', handleClickOutsideParentSelect);
  document.removeEventListener('mousedown', handleClickOutsidePresetSelect);
});

</script>

<template>
  <div class="layout-container">

    <div class="panel editor-panel">
      <header class="panel-header">

        <button @click="toggleTheme" class="theme-toggle-btn" :title="isDarkMode ? '切换到日间模式' : '切换到夜间模式'">
          <font-awesome-icon v-if="isDarkMode" :icon="faSun" />
          <font-awesome-icon v-else :icon="faMoon" />
        </button>
        <h1>服务器配置编辑器</h1>
        <div class="subtitle">拖拽服务器卡片调整优先级</div>
      </header>

      <div class="panel-body">

        <div class="form-section">
          <h3>全局设置</h3>
          <div class="form-group">
            <label for="global-footer"
              style="font-weight: normal; font-size: 0.95rem; color: var(--color-text-primary);">
              页脚文本 (Footer)
            </label>
            <input id="global-footer" type="text" v-model="config.footer" placeholder="输入页脚文本" />
          </div>

          <div class="form-group-toggle">
            <label for="global_show_offline" class="toggle-switch-label">
              默认显示离线服务器
            </label>
            <label class="toggle-switch">
              <input type="checkbox" v-model="config.show_offline_by_default" id="global_show_offline"
                class="toggle-switch-input" />
              <span class="toggle-switch-slider"></span>
            </label>
            <p class="form-help-text" style="margin-left: 10px; margin-top: 0; margin-bottom: 0;">
              (勾选后, /mcs 命令将默认显示所有服务器, 相当于 /mcs all)
            </p>
          </div>
        </div>

        <div class="form-section server-list-section">
          <div class="server-list-header">
            <h3>服务器列表</h3>
            <div class="header-actions">
              <button @click="removeAllServers" class="btn btn-danger" v-if="config.servers.length > 0">
                <font-awesome-icon :icon="faTrash" /> 全部删除
              </button>
              <button @click="addServer" class="btn btn-add">
                + 添加服务器
              </button>
            </div>
          </div>

          <draggable v-if="serverTree && serverTree.length > 0" v-model="serverTree"
            :item-key="(server: Server) => server.ip" handle=".drag-handle"
            :group="{ name: 'servers', pull: true, put: true }" :move="checkMove" @end="flattenTreeAndSync"
            :swap-threshold="0.2" class="server-list" :name="'server-list-anim-root'">
            <template #item="{ element: server }">
              <div :key="server.ip" class="server-item-container" :class="{
                'is-parent-container': server.children.length > 0
              }">
                <div class="server-item-simple" :class="{
                  'is-parent': server.children.length > 0,
                  'is-standalone': server.children.length === 0,
                  'is-ignored': server.ignore_in_list
                }">
                  <div class="drag-handle">⠿</div>
                  <div class="simple-info">
                    <div class="simple-info-line">
                      <span v-if="server.tag" class="simple-tag" :style="{
                        backgroundColor: server.tag_color_with_hash,
                        color: getContrastColor(server.tag_color_with_hash)
                      }">
                        {{ server.tag }}
                      </span>
                      <span class="simple-comment" v-if="server.comment">{{ server.comment }}</span>
                    </div>
                    <div class="simple-info-line">
                      <span class="simple-ip" :class="{ 'with-comment': server.comment }">
                        {{ server.comment ? '(' + server.ip + ')' : server.ip }}
                      </span>
                      <span v-if="server.ignore_in_list" class="simple-ignored-badge">(已隐藏)</span>
                    </div>
                  </div>
                  <div class="simple-actions">
                    <button @click="addChildServer(server)" class="btn btn-add-child-simple btn-icon-simple"
                      title="添加子服务器">
                      <font-awesome-icon :icon="faPlus" />
                    </button>
                    <button @click="openServerModal(server)" class="btn btn-edit-simple btn-icon-simple" title="编辑服务器">
                      <font-awesome-icon :icon="faEdit" />
                    </button>
                    <button @click="removeServer(server)" class="btn btn-danger btn-remove-simple btn-icon-simple"
                      title="删除服务器">
                      <font-awesome-icon :icon="faTrash" />
                    </button>
                  </div>
                </div>

                <draggable v-model="server.children" :item-key="(child: Server) => child.ip" handle=".drag-handle"
                  :group="{ name: 'servers', pull: true, put: true }" @end="flattenTreeAndSync" :swap-threshold="0.2"
                  class="server-list child-list" :name="'server-list-anim-child'">
                  <template #item="{ element: childServer }">
                    <div :key="childServer.ip" class="server-item-simple is-child" :class="{
                      'is-ignored': childServer.ignore_in_list
                    }">
                      <div class="drag-handle">⠿</div>
                      <div class="simple-info">
                        <div class="simple-info-line">
                          <span v-if="childServer.tag" class="simple-tag" :style="{
                            backgroundColor: childServer.tag_color_with_hash,
                            color: getContrastColor(childServer.tag_color_with_hash)
                          }">
                            {{ childServer.tag }}
                          </span>
                          <span class="simple-comment" v-if="childServer.comment">{{ childServer.comment }}</span>
                        </div>
                        <div class="simple-info-line">
                          <span class="simple-ip" :class="{ 'with-comment': childServer.comment }">
                            {{ childServer.comment ? '(' + childServer.ip + ')' : childServer.ip }}
                          </span>
                          <span v-if="childServer.ignore_in_list" class="simple-ignored-badge">(已隐藏)</span>
                        </div>
                      </div>
                      <div class="simple-actions">
                        <button @click="openServerModal(childServer)" class="btn btn-edit-simple btn-icon-simple"
                          title="编辑服务器">
                          <font-awesome-icon :icon="faEdit" />
                        </button>
                        <button @click="removeServer(childServer)"
                          class="btn btn-danger btn-remove-simple btn-icon-simple" title="删除服务器">
                          <font-awesome-icon :icon="faTrash" />
                        </button>
                      </div>
                    </div>
                  </template>
                </draggable>
              </div>
            </template>
          </draggable>

          <div v-else class="empty-state">
            <h3>尚未添加服务器</h3>
            <p>点击上方"添加"按钮开始配置，或使用导入功能粘贴数据</p>
          </div>
        </div>
      </div>
    </div>

    <div class="panel io-panel">
      <div class="panel-body">
        <div class="form-section">
          <h3 class="io-header">1. 导入 (Import)</h3>
          <p>粘贴分享链接，或机器人导出的数据（如/mcs import命令、JSON等）：</p>
          <div class="form-group">
            <textarea v-model="jsonInput" rows="8" placeholder="在此粘贴分享链接或机器人导出的数据..."></textarea>
          </div>
          <button @click="loadConfig" class="btn btn-primary">
            <font-awesome-icon :icon="faUpload" /> 加载配置
          </button>
        </div>

        <div class="form-section">
          <h3 class="io-header">2. 导出 (Export)</h3>
          <p>复制生成的命令，并将其发送到QQ群聊中：</p>
          <div class="form-group">
            <textarea :value="importCommand" rows="8" readonly></textarea>
          </div>
          <button @click="copyImportCommand" class="btn btn-secondary">
            <font-awesome-icon :icon="faClipboard" /> 复制导入命令
          </button>
          <button @click="downloadJson" class="btn btn-primary" style="margin-left: 10px;">
            <font-awesome-icon :icon="faSave" /> 导出JSON
          </button>
        </div>
      </div>
    </div>

    <transition name="modal-fade">
      <div v-if="isModalVisible" class="modal-overlay" role="presentation" @click.self="onModalCancel">
        <div class="modal-box" ref="alertModalRef" role="dialog" aria-modal="true"
          :aria-labelledby="modalIds.alertTitle" :aria-describedby="modalIds.alertMessage" tabindex="-1">
          <div class="modal-header">
            <h3 :id="modalIds.alertTitle">{{ modalTitle }}</h3>
          </div>
          <div class="modal-body">
            <pre :id="modalIds.alertMessage">{{ modalMessage }}</pre>
          </div>
          <div class="modal-footer">
            <button v-if="modalType === 'confirm'" @click="onModalCancel" class="btn btn-modal-cancel"
              type="button">取消</button>
            <button @click="onModalConfirm" class="btn btn-modal-confirm" type="button">确认</button>
          </div>
        </div>
      </div>
    </transition>


    <transition name="modal-fade">
      <div v-if="isServerModalVisible" class="modal-overlay edit-modal" role="presentation"
        @click.self="closeServerModal">
        <div class="modal-box edit-modal-box" ref="serverModalRef" role="dialog" aria-modal="true"
          :aria-labelledby="modalIds.serverTitle" :aria-describedby="modalIds.serverBody" tabindex="-1">

          <div class="modal-header">
            <h3 v-if="modalMode === 'add'" :id="modalIds.serverTitle">
              <font-awesome-icon :icon="faPlusCircle" /> 添加新服务器
            </h3>
            <h3 v-else :id="modalIds.serverTitle">
              <font-awesome-icon :icon="faEdit" /> 编辑服务器 {{ editingServerIp }}
            </h3>
            <button @click="closeServerModal" class="btn-close-modal" type="button">
              <font-awesome-icon :icon="faTimes" />
            </button>
          </div>

          <div class="modal-body" v-if="currentServerData" :id="modalIds.serverBody">
            <div class="server-form">

              <div class="form-row">
                <div class="form-group grow">
                  <label>服务器地址 (IP) <span class="required">*</span></label>
                  <input type="text" v-model="currentServerData.ip" placeholder="例如: play.example.com" data-autofocus />
                </div>
              </div>

              <div class="form-row">
                <div class="form-group grow">
                  <label>注释 (Comment) (可选)</label>
                  <input type="text" v-model="currentServerData.comment" placeholder="例如: 生存一区 (S1)" />
                </div>
              </div>

              <div class="form-row">

                <div class="form-group" style="flex-grow: 1;"> <label>标签 / 颜色</label>
                  <div class="form-compound-input">
                    <input type="text" v-model="currentServerData.tag"
                      @input="checkIfCustom(currentServerData as Server)" placeholder="留空则不显示"
                      class="form-compound-input-text" />

                    <div class="color-picker-wrapper">
                      <button type="button" class="custom-color-trigger" ref="colorPickerTriggerRef"
                        :style="{ backgroundColor: currentServerData.tag_color_with_hash }"
                        @click.stop="toggleColorPicker">
                      </button>

                      <transition name="modal-fade">
                        <div v-if="isColorPickerOpen" class="color-picker-modal-overlay" @click.self="closeColorPicker"
                          role="presentation">
                          <div class="color-picker-modal-box" ref="colorPickerPanelRef" role="dialog" aria-modal="true">
                            <ColorPicker is-widget format="hex" :disable-alpha="true"
                              v-model:pureColor="currentServerData.tag_color_with_hash"
                              @pureColorChange="onColorInput(currentServerData as Server)" />
                            <button type="button" class="btn btn-modal-confirm btn-color-picker-done"
                              @click="closeColorPicker">
                              完成
                            </button>
                          </div>
                        </div>
                      </transition>
                    </div>
                  </div>
                </div>

                <div class="form-group" style="flex-grow: 1;">
                  <label>快捷预设</label>
                  <div class="custom-select-container">

                    <button type="button" class="custom-select-trigger" ref="presetSelectTriggerRef"
                      @click="togglePresetSelect" @keydown="handlePresetSelectKeydown" aria-haspopup="listbox"
                      :aria-expanded="isPresetSelectOpen"
                      :aria-activedescendant="(isPresetSelectOpen && activePresetIndex > -1 ? `preset-option-${activePresetIndex}` : undefined)">

                      <span v-if="selectedPresetObject" class="selected-option-content">
                        <span class="simple-tag-small" :style="{
                          backgroundColor: selectedPresetObject.tag_color_with_hash,
                          color: getContrastColor(selectedPresetObject.tag_color_with_hash)
                        }">{{ selectedPresetObject.tag }}</span>
                        <span class="option-text">{{ selectedPresetObject.tag }}</span>
                      </span>
                      <span v-else class="option-placeholder">-- 自定义 --</span>

                      <span class="custom-select-arrow" :class="{ 'is-open': isPresetSelectOpen }">▼</span>
                    </button>

                    <transition name="modal-fade">
                      <ul v-if="isPresetSelectOpen" class="custom-select-options" ref="presetSelectOptionsRef"
                        role="listbox">

                        <li :id="`preset-option-0`" class="custom-select-option"
                          :class="{ 'is-selected': !currentServerData.selectedPreset, 'is-active': activePresetIndex === 0 }"
                          @click="selectPreset('')" role="option" :aria-selected="!currentServerData.selectedPreset">
                          <span class="option-placeholder">-- 自定义 --</span>
                        </li>

                        <li v-for="(preset, key, index) in presets" :key="key" :id="`preset-option-${index + 1}`"
                          class="custom-select-option" :class="{
                            'is-selected': currentServerData.selectedPreset === key,
                            'is-active': activePresetIndex === index + 1
                          }" @click="selectPreset(key)" role="option"
                          :aria-selected="currentServerData.selectedPreset === key">

                          <span class="simple-tag-small" :style="{
                            backgroundColor: preset.tag_color_with_hash,
                            color: getContrastColor(preset.tag_color_with_hash)
                          }">{{ preset.tag }}</span>

                          <span class="option-text">{{ preset.tag }}</span>
                        </li>
                      </ul>
                    </transition>
                  </div>
                </div>

              </div>
              <p class="form-help-text" style="margin-top: -10px; margin-bottom: 18px;text-align: right;">
                💡 选择预设可自动填充标签和颜色。
              </p>


              <div class="form-row">
                <div class="form-group grow">
                  <label>父服务器 (Parent IP)</label>
                  <div class="custom-select-container">

                    <button type="button" class="custom-select-trigger" ref="parentSelectTriggerRef"
                      @click="toggleParentSelect" @keydown="handleParentSelectKeydown" :disabled="(modalMode === MODAL_MODE.EDIT && currentServerData.children && currentServerData.children.length > 0) ||
                        (potentialParentServers.length === 0)
                        " aria-haspopup="listbox" :aria-expanded="isParentSelectOpen"
                      :aria-activedescendant="(isParentSelectOpen && activeParentIndex > -1 ? `parent-option-${activeParentIndex}` : undefined)">

                      <span v-if="selectedParent" class="selected-option-content">
                        <span v-if="selectedParent.tag" class="simple-tag-small" :style="{
                          backgroundColor: selectedParent.tag_color_with_hash,
                          color: getContrastColor(selectedParent.tag_color_with_hash)
                        }">{{ selectedParent.tag }}</span>
                        <span class="option-text">
                          <template v-if="selectedParent.comment">{{ selectedParent.comment }} ({{ selectedParent.ip
                          }})
                          </template>
                          <template v-else>{{ selectedParent.ip }}</template>
                        </span>
                      </span>
                      <span v-else class="option-placeholder">-- 默认为根服务器 --</span>

                      <span class="custom-select-arrow" :class="{ 'is-open': isParentSelectOpen }">▼</span>
                    </button>

                    <transition name="modal-fade">
                      <ul v-if="isParentSelectOpen" class="custom-select-options is-parent-select"
                        ref="parentSelectOptionsRef" role="listbox">

                        <li :id="`parent-option-0`" class="custom-select-option"
                          :class="{ 'is-selected': !currentServerData.parent_ip, 'is-active': activeParentIndex === 0 }"
                          @click="selectParent('')" role="option" :aria-selected="!currentServerData.parent_ip">
                          <span class="option-placeholder">-- 默认为根服务器 --</span>
                        </li>

                        <li v-for="(parent, index) in potentialParentServers" :key="parent.ip"
                          :id="`parent-option-${index + 1}`" class="custom-select-option" :class="{
                            'is-selected': currentServerData.parent_ip === parent.ip,
                            'is-disabled': parent.ip === editingServerIp,
                            'is-active': activeParentIndex === index + 1
                          }" @click="parent.ip === editingServerIp ? null : selectParent(parent.ip)" role="option"
                          :aria-selected="currentServerData.parent_ip === parent.ip"
                          :aria-disabled="parent.ip === editingServerIp">

                          <span v-if="parent.tag" class="simple-tag-small" :style="{
                            backgroundColor: parent.tag_color_with_hash,
                            color: getContrastColor(parent.tag_color_with_hash)
                          }">{{ parent.tag }}</span>

                          <span class="option-text">
                            <template v-if="parent.comment">{{ parent.comment }} ({{ parent.ip }})</template>
                            <template v-else>{{ parent.ip }}</template>
                          </span>
                        </li>
                      </ul>
                    </transition>

                  </div>
                  <p v-if="potentialParentServers.length === 0 && modalMode === 'add'" class="form-help-text">
                    当前没有可用的父服务器，将作为根服务器添加。
                  </p>
                </div>
              </div>

              <div class="form-row">
                <div style="padding-top: 10px;">
                  <div class="form-group-toggle" style="margin-top: 0;">
                    <label class="toggle-switch">
                      <input type="checkbox" v-model="currentServerData.ignore_in_list"
                        :id="'ignore_mod_' + sanitizeIpForId(currentServerData.ip)" class="toggle-switch-input" />
                      <span class="toggle-switch-slider"></span>
                    </label>
                    <label :for="'ignore_mod_' + sanitizeIpForId(currentServerData.ip || 'new')"
                      class="toggle-switch-label">
                      <font-awesome-icon :icon="faEyeSlash" /> 在列表中隐藏
                    </label>
                  </div>
                  <p class="form-help-text" style="margin-top: 8px; margin-bottom: 0; padding-left: 5px;">
                    (勾选后, 该服务器将不会显示在 /mcs 的列表图片中)
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div class="modal-footer">
            <button @click="closeServerModal" class="btn-modal-cancel" type="button">
              <font-awesome-icon :icon="faTimes" /> 取消
            </button>
            <button @click="saveServer" class="btn-modal-confirm" type="button" :disabled="isSaving">
              <font-awesome-icon :icon="isSaving ? faSpinner : faSave" :spin="isSaving" />
              <span v-if="isSaving">正在保存...</span>
              <span v-else>{{ modalMode === MODAL_MODE.ADD ? '确认添加' : '保存更改' }}</span>
            </button>
          </div>

        </div>
      </div>
    </transition>

    <!-- Toast 小提示 -->
    <transition name="toast-fade">
      <div v-if="isToastVisible" class="toast-notification">
        {{ toastMessage }}
      </div>
    </transition>

  </div>
</template>

<style>
/* --- 1. 主题与颜色变量 --- */

:root {
  --color-body-gradient-start: #eef2ff;
  --color-body-gradient-end: #f9fafb;
  --color-panel-gradient-start: #6366f1;
  --color-panel-gradient-end: #7c3aed;
  --color-surface: #ffffff;
  --color-surface-muted: #f5f7fb;
  --color-text-primary: #1f2933;
  --color-text-secondary: #4b5563;
  --color-border: #dbe2ef;
  --color-primary: #4f46e5;
  --color-primary-hover: #4338ca;
  --color-secondary: #2563eb;
  --color-secondary-hover: #1d4ed8;
  --color-success: #10b981;
  --color-success-hover: #059669;
  --color-danger: #ef4444;
  --color-danger-hover: #dc2626;
  --color-focus-outline: rgba(99, 102, 241, 0.45);
  --shadow-soft: 0 10px 30px rgba(15, 23, 42, 0.08);
  --shadow-hover: 0 16px 40px rgba(79, 70, 229, 0.16);
}

/* --- 夜间模式 --- */
html.dark-mode {
  --color-body-gradient-start: #111827;
  --color-body-gradient-end: #1f2937;
  --color-panel-gradient-start: #4f46e5;
  --color-panel-gradient-end: #7c3aed;
  --color-surface: #1f2937;
  --color-surface-muted: #374151;
  --color-text-primary: #f3f4f6;
  --color-text-secondary: #9ca3af;
  --color-border: #4b5563;
  --color-primary: #818cf8;
  --color-primary-hover: #6366f1;
  --color-secondary: #60a5fa;
  --color-secondary-hover: #3b82f6;
  --color-focus-outline: rgba(129, 140, 248, 0.55);
  --shadow-soft: 0 10px 20px rgba(0, 0, 0, 0.2);
  --shadow-hover: 0 16px 40px rgba(0, 0, 0, 0.25);
}

/* 为颜色变化添加过渡动画 */
body {
  transition: background 0.3s ease;
}

.panel,
.modal-box,
.btn,
input,
select,
textarea,
.server-item-simple,
.btn-modal-cancel,
.btn-modal-confirm,
.form-compound-input,
.custom-select-trigger {
  transition: background 0.3s ease, color 0.3s ease, border-color 0.3s ease;
}

/* --- 2. 全局与布局 --- */
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
  font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

body {
  background: linear-gradient(135deg, var(--color-body-gradient-start), var(--color-body-gradient-end));
  min-height: 100vh;
  padding: 20px;
  color: var(--color-text-primary);
  line-height: 1.5;
}

.layout-container {
  display: grid;
  grid-template-columns: minmax(600px, 2fr) minmax(350px, 1fr);
  align-items: flex-start;
  gap: 20px;
  max-width: 1280px;
  width: 100%;
  margin: 0 auto;
}

.panel {
  background: var(--color-surface);
  border-radius: 16px;
  box-shadow: var(--shadow-soft);
  overflow: hidden;
  min-width: 0;
  border: 1px solid var(--color-border);
}

.io-panel {
  position: sticky;
  top: 20px;
  align-self: flex-start;
}

.panel-header {
  position: relative;
  background: linear-gradient(135deg, var(--color-panel-gradient-start), var(--color-panel-gradient-end));
  color: #fff;
  padding: 24px 20px;
  text-align: center;
}

.panel-header h1 {
  font-size: 28px;
  margin-bottom: 10px;
}

.panel-header .subtitle {
  font-size: 16px;
  opacity: 0.9;
}

.panel-body {
  padding: 20px;
}

.theme-toggle-btn {
  position: absolute;
  top: 20px;
  right: 20px;
  background: rgba(255, 255, 255, 0.2);
  border: none;
  color: #fff;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  font-size: 1.2rem;
  cursor: pointer;
  transition: all 0.3s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
}

.theme-toggle-btn:hover {
  background: rgba(255, 255, 255, 0.3);
  transform: scale(1.1);
}

html.dark-mode .theme-toggle-btn {
  background: rgba(0, 0, 0, 0.2);
  color: #f3f4f6;
}

html.dark-mode .theme-toggle-btn:hover {
  background: rgba(0, 0, 0, 0.3);
}

/* --- 3. 表单通用样式 --- */
.form-section {
  margin-bottom: 20px;
}

.form-section h3 {
  font-size: 1.4rem;
  color: var(--color-text-primary);
  margin-bottom: 15px;
  padding-bottom: 5px;
  border-bottom: 2px solid var(--color-border);
}

.io-panel .form-section h3 {
  font-size: 1.2rem;
  border-bottom: none;
  color: var(--color-primary);
}

.form-section p {
  margin-bottom: 10px;
  color: var(--color-text-secondary);
  font-size: 0.9rem;
}

.form-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 10px;
}

.form-group {
  margin-bottom: 0px;
  flex: 1;
  min-width: 100px;
  min-width: 0;
}

.form-group.grow {
  flex: 2;
}

label {
  display: block;
  margin-bottom: 3px;
  font-weight: 500;
  color: var(--color-text-primary);
  font-size: 0.85rem;
}

label .required {
  color: var(--color-danger);
  font-weight: bold;
  margin-left: 2px;
}

input[type="text"],
textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  font-size: 0.95rem;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
  max-width: 100%;
  background-color: var(--color-surface);
  color: var(--color-text-primary);
}

input[type="text"]::placeholder,
textarea::placeholder {
  color: var(--color-text-secondary);
  opacity: 0.6;
}

input[type="text"]:focus,
textarea:focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-focus-outline);
  outline: none;
}

button:focus-visible,
.btn:focus-visible,
.btn-close-modal:focus-visible {
  outline: 3px solid var(--color-focus-outline);
  outline-offset: 2px;
}

textarea {
  font-family: "JetBrains Mono", "Fira Code", "Consolas", "Courier New", monospace;
  font-size: 14px;
  line-height: 1.5;
}

.form-help-text {
  font-size: 0.8rem;
  color: var(--color-text-secondary);
  margin-top: 5px;
  margin-bottom: 0;
}

/* --- 4. 按钮通用样式 --- */
.btn {
  border: 1px solid transparent;
  border-radius: 10px;
  padding: 10px 16px;
  cursor: pointer;
  font-weight: 600;
  font-size: 0.95rem;
  font-family: inherit;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  white-space: nowrap;
  transition: background 0.2s ease, color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease, border-color 0.2s ease;
}

.btn:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-hover);
}

.btn-primary {
  background: var(--color-success);
  color: #fff;
}

.btn-primary:hover {
  background: var(--color-success-hover);
}

.btn-secondary {
  background: var(--color-secondary);
  color: #fff;
}

.btn-secondary:hover {
  background: var(--color-secondary-hover);
}

.btn-danger {
  background: var(--color-danger);
  color: #fff;
}

.btn-danger:hover {
  background: var(--color-danger-hover);
}

.btn-add {
  background: var(--color-primary);
  color: #fff;
}

.btn-add:hover {
  background: var(--color-primary-hover);
}

/* --- 5. 服务器列表 --- */
.server-list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.server-list {
  min-height: 50px;
  margin-top: 15px;
}

.server-item-simple {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 12px 14px;
  display: flex;
  align-items: center;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
  user-select: none;
}

.server-item-simple:hover {
  border-color: var(--color-primary);
  box-shadow: 0 10px 16px rgba(79, 70, 229, 0.15);
}

.server-item-container:has(.child-list .sortable-ghost)>.server-item-simple {
  border-color: var(--color-success);
  box-shadow: 0 0 0 3px var(--color-success);
}

.server-item-simple.is-child {
  background: var(--color-surface-muted);
  border-left: 4px solid var(--color-panel-gradient-end);
  margin-bottom: 6px;
}

.server-item-simple.is-parent {
  border-left: 4px solid var(--color-panel-gradient-start);
}

/* “在列表中隐藏”的删除线样式 */
.server-item-simple.is-ignored .simple-info {
  text-decoration: none;
}

.server-item-simple.is-ignored .simple-tag,
.server-item-simple.is-ignored .simple-comment,
.server-item-simple.is-ignored .simple-ip {
  text-decoration: line-through;
  opacity: 0.7;
}

.server-item-simple.is-ignored .simple-ignored-badge {
  text-decoration: none;
  opacity: 1;
}

.simple-info {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  overflow: hidden;
  white-space: nowrap;
  min-width: 0;
}

/* 在桌面端，此包装器在布局上“消失”，使其子元素表现得像直接的 flex 子项 */
.simple-info-line {
  display: contents;
}

.simple-tag {
  font-size: 0.85rem;
  font-weight: 500;
  padding: 3px 8px;
  border-radius: 4px;
  flex-shrink: 0;
}

.simple-comment {
  font-weight: 500;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex-shrink: 1;
}

.simple-ip {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex-shrink: 1;
  min-width: 0;
}

.simple-ip.with-comment {
  color: var(--color-text-secondary);
  font-size: 0.85rem;
  margin-left: -5px;
}

.simple-ignored-badge {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--color-text-secondary);
  flex-shrink: 0;
}

.simple-actions {
  display: flex;
  gap: 8px;
  margin-left: 10px;
}

.btn-add-child-simple,
.btn-edit-simple {
  background: var(--color-surface-muted);
  color: var(--color-primary);
  border: 1px solid var(--color-border);
  transition: background 0.2s ease, color 0.2s ease, border-color 0.2s ease;
}

.btn-add-child-simple:hover,
.btn-add-child-simple:focus-visible,
.btn-edit-simple:hover,
.btn-edit-simple:focus-visible {
  background: var(--color-body-gradient-start);
  border-color: var(--color-primary);
}

.drag-handle {
  width: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 12px;
  cursor: grab;
  color: var(--color-text-secondary);
  font-size: 1.5rem;
  padding-top: 0;
  user-select: none;
}

.drag-handle:active {
  cursor: grabbing;
}

.empty-state {
  text-align: center;
  padding: 20px;
  color: var(--color-text-secondary);
  background: var(--color-surface-muted);
  border-radius: 8px;
  margin-top: 15px;
}

/* --- 6. 拖拽与列表结构 --- */
.server-item-container {
  margin-bottom: 6px;
  position: relative;
}

.child-list {
  margin-left: 40px;
}

.server-item-container.is-parent-container .child-list {
  margin-top: 6px;
  min-height: 40px;
}

.server-item-container:not(.is-parent-container) .child-list {
  margin-top: 0;
  min-height: 0;
}

.server-item-simple.sortable-drag {
  opacity: 0.9;
  background: #f5f3ff;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
  transform: scale(1.02);
}

.sortable-ghost {
  background: var(--color-body-gradient-start);
  border: 2px dashed var(--color-primary);
  opacity: 0.7;
  border-radius: 8px;
}

.sortable-ghost>* {
  visibility: hidden;
}

/* 减小子列表占位符的高度，增加拖拽到根列表的容错率 */
.child-list.sortable-ghost {
  min-height: 30px;
}

.server-list-anim-root-enter-from,
.server-list-anim-root-leave-to {
  opacity: 0;
  transform: scale(0.9);
}

.server-list-anim-root-enter-active,
.server-list-anim-root-leave-active {
  transition: all 0.3s ease;
}

.server-list-anim-root-move {
  transition: transform 0.3s cubic-bezier(0.55, 0, 0.1, 1);
}

.server-item-container.sortable-ghost {
  background: var(--color-body-gradient-start);
  border: 2px dashed var(--color-primary);
  opacity: 0.7;
  border-radius: 8px;
  min-height: 50px;
}

.server-item-container.sortable-ghost>* {
  visibility: hidden;
}

.server-list-anim-child-enter-active,
.server-list-anim-child-leave-active {
  transition: all 0.3s ease;
}

.server-list-anim-child-enter-from,
.server-list-anim-child-leave-to {
  opacity: 0;
  transform: translateX(30px);
}

.server-list-anim-child-move {
  transition: transform 0.3s ease;
}

/* --- 7. 通用弹窗 (Alert/Confirm) --- */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.55);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  z-index: 2000;
}

.modal-box {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 16px;
  box-shadow: var(--shadow-hover);
  width: min(90%, 520px);
  overflow: hidden;
  animation: modal-pop-in 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}

.modal-header {
  padding: 15px 20px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface-muted);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.modal-header h3 {
  font-size: 1.25rem;
  color: var(--color-text-primary);
}

.modal-body {
  padding: 28px 24px;
  font-size: 1rem;
  line-height: 1.6;
  color: var(--color-text-primary);
}

.modal-body pre {
  white-space: pre-wrap;
  word-wrap: break-word;
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
  color: var(--color-text-secondary);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px;
  background: var(--color-surface-muted);
  border-top: 1px solid var(--color-border);
}

.btn-modal-cancel {
  background: var(--color-surface-muted);
  color: var(--color-text-primary);
  border: 1px solid var(--color-border);
  padding: 10px 22px;
  border-radius: 12px;
  font-weight: 600;
  font-size: 0.95rem;
  transition: background 0.2s ease, border-color 0.2s ease, color 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease;
}

.btn-modal-cancel:hover,
.btn-modal-cancel:focus-visible {
  background: var(--color-body-gradient-start);
  border-color: var(--color-primary);
  color: var(--color-primary);
  transform: translateY(-1px);
  box-shadow: var(--shadow-hover);
}

.btn-modal-confirm {
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-secondary) 100%);
  color: #fff;
  border: none;
  padding: 10px 26px;
  border-radius: 12px;
  font-weight: 600;
  font-size: 0.95rem;
  cursor: pointer;
  transition: background 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease;
  box-shadow: 0 6px 16px rgba(79, 70, 229, 0.25);
}

.btn-modal-confirm:hover,
.btn-modal-confirm:focus-visible {
  transform: translateY(-1px);
  box-shadow: 0 10px 20px rgba(79, 70, 229, 0.3);
  background: linear-gradient(135deg, var(--color-primary-hover) 0%, var(--color-secondary-hover) 100%);
}

@keyframes modal-pop-in {
  from {
    opacity: 0;
    transform: scale(0.8);
  }

  to {
    opacity: 1;
    transform: scale(1);
  }
}

.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.3s ease;
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}

/* --- 8. “添加/编辑”服务器弹窗 --- */
.modal-overlay.edit-modal {
  z-index: 1500;
}

.modal-box.edit-modal-box {
  max-width: 760px;
  display: flex;
  flex-direction: column;
  /* 适应手机端，允许内容滚动 */
  max-height: 90vh;
  max-height: 90dvh;
}

.edit-modal-box .modal-header {
  background: linear-gradient(135deg, var(--color-panel-gradient-start), var(--color-panel-gradient-end));
  color: #fff;
  padding: 24px 28px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.18);
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-shrink: 0;
}

.edit-modal-box .modal-header h3 {
  font-size: 1.4rem;
  font-weight: 600;
  margin: 0;
}

.btn-close-modal {
  background: transparent;
  border: none;
  font-size: 1.5rem;
  line-height: 1;
  color: rgba(255, 255, 255, 0.85);
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 50%;
  transition: background 0.2s ease, color 0.2s ease, transform 0.2s ease;
}

.btn-close-modal:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.18);
  transform: scale(1.08);
}

.edit-modal-box .modal-body {
  padding: 28px;
  overflow-y: auto;
  background: var(--color-surface);
  scrollbar-gutter: stable;
  flex-grow: 1;
  min-height: 0;
}

.server-form {
  padding: 4px 0;
}

.server-form .form-row {
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
  margin-bottom: 18px;
}

.server-form .form-group {
  flex: 1;
  min-width: 160px;
  position: relative;
}

.server-form label {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
  font-weight: 600;
  color: var(--color-text-primary);
  font-size: 0.95rem;
}

.server-form .required {
  color: var(--color-danger);
  margin-left: 4px;
}

.server-form input[type="text"] {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--color-surface);
  box-shadow: 0 2px 6px rgba(15, 23, 42, 0.06);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
  padding-left: 26px;
  color: var(--color-text-primary);
  position: relative;
  z-index: 1;
}

.server-form input[type="text"]:focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-focus-outline);
  outline: none;
}

.server-form .form-help-text {
  font-size: 0.85rem;
  color: var(--color-text-secondary);
  margin-top: 8px;
  margin-bottom: 0;
  line-height: 1.4;
}

.edit-modal-box .modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 15px;
  padding: 18px 28px;
  background: var(--color-surface-muted);
  border-top: 1px solid var(--color-border);
  flex-shrink: 0;
}

.server-form .form-group::before {
  content: '';
  position: absolute;
  top: 42px;
  left: 12px;
  width: 4px;
  height: 20px;
  background: linear-gradient(to bottom, var(--color-panel-gradient-start), var(--color-panel-gradient-end));
  border-radius: 2px;
  opacity: 0.6;
  z-index: 2;
}

.server-form .form-group:has(> .color-picker)::before,
.server-form .form-group-checkbox::before {
  display: none;
}

.server-form .form-group:has(.color-picker) input {
  padding-left: 4px;
}

/* --- 9. 复合输入框 (标签+颜色) --- */
.form-compound-input {
  display: flex;
  align-items: center;
  position: relative;
  width: 100%;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--color-surface);
  box-shadow: 0 2px 6px rgba(15, 23, 42, 0.06);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.form-compound-input:focus-within {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-focus-outline);
}

.form-compound-input-text {
  flex: 1 1 auto;
  border: none !important;
  outline: none !important;
  box-shadow: none !important;
  background: transparent;
  padding-left: 26px !important;
  min-width: 0;
}

/* --- 10. 自定义下拉框 (预设/父服务器) --- */
.custom-select-container {
  position: relative;
  width: 100%;
}

.custom-select-trigger {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--color-surface);
  box-shadow: 0 2px 6px rgba(15, 23, 42, 0.06);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: space-between;
  text-align: left;
  cursor: pointer;
  font-size: 0.95rem;
  color: var(--color-text-primary);
  outline: none;
  padding-left: 26px;
  position: relative;
  z-index: 1;
}

.custom-select-trigger:focus-visible {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px var(--color-focus-outline);
}

.custom-select-trigger:disabled {
  background-color: var(--color-surface-muted);
  color: var(--color-text-secondary);
  cursor: not-allowed;
  opacity: 0.7;
}

.selected-option-content {
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
}

.option-text {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.option-placeholder {
  color: var(--color-text-secondary);
  opacity: 0.8;
}

.custom-select-arrow {
  font-size: 12px;
  color: var(--color-text-secondary);
  transition: transform 0.2s ease;
  transform-origin: center;
  margin-left: 8px;
  flex-shrink: 0;
}

.custom-select-arrow.is-open {
  transform: rotate(180deg);
}

.custom-select-options {
  position: absolute;
  top: 105%;
  left: 0;
  right: 0;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  box-shadow: var(--shadow-soft);
  z-index: 1600;
  max-height: 200px;
  overflow-y: auto;
  list-style: none;
  padding: 5px;
  margin: 0;
  overscroll-behavior-y: contain;
}

.custom-select-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s ease;
  color: var(--color-text-primary);
  overflow: hidden;
}

.custom-select-option:hover,
.custom-select-option.is-active {
  background-color: var(--color-body-gradient-start);
}

.custom-select-option.is-selected {
  background: var(--color-body-gradient-start);
  color: var(--color-primary);
  font-weight: 600;
}

.custom-select-option.is-disabled {
  color: var(--color-text-secondary);
  opacity: 0.6;
  cursor: not-allowed;
  background: transparent;
}

.custom-select-option.is-disabled:hover {
  background: transparent;
}

.simple-tag-small {
  font-size: 0.8rem;
  font-weight: 500;
  padding: 2px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}

.custom-select-options.is-parent-select {
  top: auto;
  bottom: 105%;
  box-shadow: var(--shadow-soft);
}

/* --- 11. 自定义颜色选择器 --- */
.color-picker-wrapper {
  flex: 0 0 auto;
  position: relative;
  width: 44px;
  height: 44px;
  margin: 2px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.custom-color-trigger {
  width: 36px;
  height: 36px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  cursor: pointer;
  padding: 0;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.custom-color-trigger:hover {
  transform: scale(1.1);
}

.custom-color-trigger:focus-visible {
  outline: 3px solid var(--color-focus-outline);
  outline-offset: 2px;
}

.color-picker-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.55);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  z-index: 1800;
}

.color-picker-modal-box {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 16px;
  box-shadow: var(--shadow-hover);
  padding: 12px;
  animation: modal-pop-in 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
  overscroll-behavior-y: contain;
}

/* 覆盖 vue3-colorpicker 的默认样式 */
.color-picker-modal-box .vc-color-wrap {
  border: none !important;
  box-shadow: none !important;
  background: transparent !important;
  width: 280px;
}

.color-picker-modal-box .vc-color-wrap.is-widget {
  padding: 0 !important;
}

.btn-color-picker-done {
  width: 100%;
  margin-top: 10px;
  font-size: 1rem;
  padding-top: 12px;
  padding-bottom: 12px;
}

/* --- 12. Toast 提示 --- */
.toast-notification {
  position: fixed;
  top: 80px;
  left: 50%;
  transform: translateX(-50%);
  background-color: var(--color-success);
  color: #fff;
  padding: 10px 20px;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 2000;
  font-weight: 500;
}

.toast-fade-enter-active,
.toast-fade-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}

.toast-fade-enter-from,
.toast-fade-leave-to {
  opacity: 0;
  transform: translate(-50%, -20px);
}

/* --- 13. 自定义滚动条 (夜间模式) --- */
html.dark-mode {
  scrollbar-color: #6b7280 #374151;
  scrollbar-width: thin;
}

html.dark-mode ::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

html.dark-mode ::-webkit-scrollbar-track {
  background: var(--color-surface-muted);
  border-radius: 4px;
}

html.dark-mode ::-webkit-scrollbar-thumb {
  background-color: #6b7280;
  border-radius: 4px;
  border: 2px solid var(--color-surface-muted);
}

html.dark-mode ::-webkit-scrollbar-thumb:hover {
  background-color: var(--color-text-secondary);
}

/* --- 14. 图标对齐修正 --- */
.btn svg,
.btn-modal-cancel svg,
.btn-modal-confirm svg,
.toggle-switch-label svg,
.modal-header h3 svg {
  vertical-align: -0.125em;
}

.theme-toggle-btn svg,
.btn-close-modal svg {
  vertical-align: middle;
}

/* --- 15. 统一列表项中的图标按钮样式 --- */
.btn-icon-simple {
  width: 32px;
  height: 32px;
  padding: 0;
  font-size: 0.9rem;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.btn-icon-simple:hover,
.btn-icon-simple:focus-visible {
  transform: none;
  box-shadow: none;
}

.btn-remove-simple {
  background: var(--color-surface-muted);
  border: 1px solid var(--color-border);
  color: var(--color-danger);
}

.btn-remove-simple:hover,
.btn-remove-simple:focus-visible {
  background: var(--color-danger);
  border-color: var(--color-danger-hover);
  color: #fff;
}

/* --- 16. 切换开关(Toggle Switch)样式 --- */
.form-group-toggle {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 15px;
  padding-left: 5px;
}

.toggle-switch-label {
  color: var(--color-text-primary);
  font-weight: 500;
  cursor: pointer;
  user-select: none;
  font-size: 0.95rem;
}

.toggle-switch {
  position: relative;
  display: inline-block;
  width: 50px;
  height: 28px;
  flex-shrink: 0;
}

.toggle-switch-input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-switch-slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: var(--color-border);
  transition: .3s;
  border-radius: 28px;
}

.toggle-switch-slider:before {
  position: absolute;
  content: "";
  height: 20px;
  width: 20px;
  left: 4px;
  bottom: 4px;
  background-color: white;
  transition: .3s;
  border-radius: 50%;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
}

.toggle-switch-input:checked+.toggle-switch-slider {
  background-color: var(--color-primary);
}

.toggle-switch-input:checked+.toggle-switch-slider:before {
  transform: translateX(22px);
}

.toggle-switch-input:focus-visible+.toggle-switch-slider {
  box-shadow: 0 0 0 3px var(--color-focus-outline);
}

/* --- 17. 移动端适配 (max-width: 600px) --- */
@media (max-width: 1100px) {
  .layout-container {
    grid-template-columns: 1fr;
  }

  .io-panel {
    position: static;
    top: auto;
  }
}

@media (max-width: 600px) {
  .server-item-simple {
    padding: 10px 10px 12px 10px;
    align-items: flex-start;
  }

  .simple-info {
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
    white-space: normal;
  }

  .simple-info-line {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
  }

  .simple-tag {
    white-space: nowrap;
    flex-shrink: 0;
  }

  .simple-comment {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex-shrink: 1;
    min-width: 0;
    flex: 1;
  }

  .simple-ip {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex-shrink: 1;
    min-width: 0;
  }

  .simple-ignored-badge {
    white-space: nowrap;
    flex-shrink: 0;
  }

  .simple-ip.with-comment {
    margin-left: 0;
    font-size: 0.85rem;
  }

  .drag-handle {
    margin-top: 1px;
  }

  .simple-actions {
    gap: 5px;
    margin-left: 8px;
    padding-top: 0;
  }

  .server-list-header {
    flex-wrap: wrap;
    gap: 10px 15px;
  }

  .server-list-header h3 {
    white-space: nowrap;
    font-size: 1.3rem;
    margin-bottom: 0;
  }

  .header-actions {
    flex-grow: 1;
    justify-content: flex-end;
  }
}

@media (max-width: 440px) {
  .server-form .form-row {
    flex-direction: column;
    gap: 15px;
  }

  .edit-modal-box {
    width: 95%;
  }
}
</style>