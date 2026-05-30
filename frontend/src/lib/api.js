async function request(url, options = {}) {
  const hasBody = options.body !== undefined
  const res = await fetch(url, {
    headers: {
      ...(hasBody ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
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
