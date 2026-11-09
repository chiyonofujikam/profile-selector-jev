import { modelText } from './messages'

const base = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${base}${path}`, { ...options, headers: { 'Content-Type': 'application/json', ...options?.headers } })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new Error('The service is unavailable. Check that the API is running, then retry.')
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = body.error?.message || body.detail?.message || body.detail || body.message
    throw new Error(typeof detail === 'string' ? modelText(detail) : `The request could not be completed (${response.status}).`)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
export function post<T>(path: string, data: unknown, signal?: AbortSignal) {
  return api<T>(path, {
    method: 'POST',
    body: JSON.stringify(data),
    signal,
  })
}
