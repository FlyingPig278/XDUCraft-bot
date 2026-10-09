import type { ErrorEnvelope, SessionInfo } from './types'

let csrfToken: string | null = null

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly fields: Record<string, string | string[]>
  constructor(status: number, code: string, message: string, fields: Record<string, string | string[]> = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.fields = fields
  }
}

function isJson(response: Response): boolean {
  return response.headers.get('content-type')?.toLowerCase().includes('application/json') ?? false
}

async function parseError(response: Response): Promise<ApiError> {
  if (isJson(response)) {
    try {
      const body = await response.json() as Partial<ErrorEnvelope>
      if (body.error) return new ApiError(response.status, body.error.code, body.error.message, body.error.fields)
    } catch { /* use generic safe error below */ }
  }
  return new ApiError(response.status, `http_${response.status}`, `请求失败（HTTP ${response.status}）`)
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken) headers.set('X-CSRF-Token', csrfToken)
  const response = await fetch(path, { ...init, headers, credentials: 'same-origin' })
  if (!response.ok) {
    if (response.status === 401 && path !== '/api/auth/login' && path !== '/api/auth/session') {
      csrfToken = null
      window.dispatchEvent(new CustomEvent('xducraft:unauthorized'))
    }
    throw await parseError(response)
  }
  if (response.status === 204) return undefined as T
  return await response.json() as T
}

export async function apiGet<T>(path: string): Promise<T> { return request<T>(path) }

export async function apiWrite<T>(path: string, method: 'POST' | 'PUT' | 'DELETE', body?: unknown, revision?: string): Promise<T> {
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

export async function uploadKeywordImage(file: File): Promise<{ name: string }> {
  const headers = new Headers({ 'Content-Type': file.type || 'application/octet-stream', 'Accept': 'application/json' })
  if (csrfToken) headers.set('X-CSRF-Token', csrfToken)
  return request<{ name: string }>('/api/keyword/media', { method: 'POST', headers, body: file })
}

export function keywordMediaUrl(name: string): string {
  return `/api/keyword/media/${encodeURIComponent(name)}`
}
