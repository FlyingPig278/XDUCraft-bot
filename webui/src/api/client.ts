import type { AssetCapability } from './schema'
import type { ErrorEnvelope, SessionInfo } from './types'

let csrfToken: string | null = null
export class ApiError extends Error {
  constructor(readonly status: number, readonly code: string, message: string, readonly fields: Record<string, unknown> = {}) {
    super(message)
    this.name = 'ApiError'
  }
}
function sameOriginPath(path: string): string {
  const url = new URL(path, window.location.origin)
  if (url.origin !== window.location.origin || !url.pathname.startsWith('/api/')) throw new Error('资源地址必须为同源管理 API')
  return url.pathname + url.search
}
async function parseError(response: Response): Promise<ApiError> {
  if (response.headers.get('content-type')?.toLowerCase().includes('application/json')) {
    try {
      const body = await response.json() as Partial<ErrorEnvelope>
      if (body.error) return new ApiError(response.status, body.error.code, body.error.message, body.error.fields ?? {})
    } catch { /* Never expose HTML, request bodies, or backend diagnostics. */ }
  }
  return new ApiError(response.status, `http_${response.status}`, `请求失败（HTTP ${response.status}）`)
}
async function responseFor(path: string, init: RequestInit = {}): Promise<Response> {
  const safePath = sameOriginPath(path)
  const method = (init.method ?? 'GET').toUpperCase()
  const headers = new Headers(init.headers)
  if (!headers.has('Accept')) headers.set('Accept', 'application/json')
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken) headers.set('X-CSRF-Token', csrfToken)
  // The browser supplies the real Origin for same-origin writes; do not forge it.
  const response = await fetch(safePath, { ...init, headers, credentials: 'same-origin', redirect: 'error', cache: 'no-store' })
  if (!response.ok) {
    if (response.status === 401 && safePath !== '/api/auth/login' && safePath !== '/api/auth/session') {
      csrfToken = null
      window.dispatchEvent(new CustomEvent('xducraft:unauthorized'))
    }
    throw await parseError(response)
  }
  return response
}
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await responseFor(path, init)
  return response.status === 204 ? undefined as T : await response.json() as T
}
export function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> { return request<T>(path, { signal }) }
export function apiWrite<T>(path: string, method: 'POST' | 'PUT', body?: unknown, revision?: string): Promise<T> {
  const headers = new Headers()
  if (body !== undefined) headers.set('Content-Type', 'application/json')
  if (revision) headers.set('If-Match', revision)
  return request<T>(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
}
export async function login(password: string): Promise<SessionInfo> {
  const session = await apiWrite<SessionInfo>('/api/auth/login', 'POST', { password })
  csrfToken = session.csrf_token
  return session
}
export async function restoreSession(): Promise<SessionInfo> {
  const session = await apiGet<SessionInfo>('/api/auth/session')
  csrfToken = session.csrf_token
  return session
}
export async function logout(): Promise<void> {
  try { await apiWrite<void>('/api/auth/logout', 'POST') } finally { csrfToken = null }
}
export function clearSessionToken(): void { csrfToken = null }
export function uploadAsset(capability: AssetCapability, file: Blob): Promise<{ name: string }> {
  if (file.size > capability.max_bytes) return Promise.reject(new Error(`文件不得超过 ${Math.floor(capability.max_bytes / 1024 / 1024)} MiB`))
  if (!capability.mime_types.includes(file.type)) return Promise.reject(new Error('该资源不支持此文件类型'))
  return request<{ name: string }>(capability.upload_url, { method: 'POST', headers: { 'Content-Type': file.type }, body: file })
}
export function assetUrl(capability: AssetCapability, name: string): string {
  return sameOriginPath(capability.read_url_prefix + encodeURIComponent(name))
}
