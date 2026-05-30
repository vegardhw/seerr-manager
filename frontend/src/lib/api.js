// Token is stored in localStorage so the user only has to enter it once.
const TOKEN_KEY = 'seerr_manager_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

async function request(url, options = {}) {
  const hasBody = options.body !== undefined
  const token = getToken()
  const res = await fetch(url, {
    headers: {
      ...(hasBody ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      ...options.headers,
    },
    ...options,
  })
  if (res.status === 401) {
    // Token is wrong or missing — clear it so the UI can re-prompt.
    setToken('')
    throw new AuthError('Invalid or missing access token.')
  }
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json()
}

export class AuthError extends Error {}

export const api = {
  // ── Auth bootstrap ────────────────────────────────────────────────────────
  /** Returns {required: bool} — always unauthenticated. */
  fetchAuthRequired: () => fetch('/api/auth-required').then((r) => r.json()),

  // ── Requests view ─────────────────────────────────────────────────────────
  fetchRequests: () => request('/api/requests'),
  fetchStatus: () => request('/api/status'),

  rerequest: (id) => request(`/api/rerequest/${id}`, { method: 'POST' }),

  rerequestOrphan: (seerrMediaId, tmdbId, mediaType) =>
    request('/api/rerequest/orphan', {
      method: 'POST',
      body: JSON.stringify({ seerrMediaId, tmdbId, mediaType }),
    }),

  rerequestBatch: (ids, orphans) =>
    request('/api/rerequest/batch', {
      method: 'POST',
      body: JSON.stringify({ ids, orphans }),
    }),

  reset: (id) => request(`/api/reset/${id}`, { method: 'POST' }),

  resetOrphan: (seerrMediaId) =>
    request('/api/reset/orphan', {
      method: 'POST',
      body: JSON.stringify({ seerrMediaId }),
    }),

  resetBatch: (ids, orphanMediaIds) =>
    request('/api/reset/batch', {
      method: 'POST',
      body: JSON.stringify({ ids, orphanMediaIds }),
    }),

  // ── Watchlist comparison ───────────────────────────────────────────────────
  fetchWatchlistComparison: () => request('/api/watchlist/comparison'),

  /** items: Array<{ tmdbId: number, mediaType: 'movie' | 'tv' }> */
  requestWatchlistItems: (items) =>
    request('/api/watchlist/request', {
      method: 'POST',
      body: JSON.stringify({ items }),
    }),

  // ── Cache management ───────────────────────────────────────────────────────
  getCacheStatus: () => request('/api/cache/status'),
  clearCache: () => request('/api/cache', { method: 'DELETE' }),
}
