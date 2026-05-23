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
}
