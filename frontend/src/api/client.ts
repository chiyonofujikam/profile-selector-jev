const base = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
export class ApiError extends Error {
  constructor(message: string, public status: number, public requestId?: string) { super(message) }
}
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${base}${path}`, { ...options, headers: { 'Content-Type': 'application/json', ...options?.headers } })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError('The service is unavailable. Check that the API is running, then retry.', 0)
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = body.error?.message || body.detail?.message || body.detail || body.message
    throw new ApiError(typeof detail === 'string' ? detail : `The request could not be completed (${response.status}).`, response.status, response.headers.get('x-request-id') || undefined)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
export const post = <T>(path: string, data: unknown, signal?: AbortSignal) => api<T>(path, { method: 'POST', body: JSON.stringify(data), signal })
