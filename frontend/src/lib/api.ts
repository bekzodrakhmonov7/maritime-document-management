const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export async function apiFetch<T = unknown>(path: string, options: RequestInit = {}): Promise<T> {
  const { supabase } = await import('./supabase')
  const { data } = await supabase.auth.getSession()
  const token = data.session?.access_token

  const headers = new Headers(options.headers)
  if (!(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  })

  if (!res.ok) {
    const err = await res.text()
    throw new Error(err || `HTTP ${res.status}`)
  }

  if (res.status === 204 || res.headers.get('content-length') === '0') {
    return undefined as T
  }

  return res.json() as Promise<T>
}
