<script>
  import { onMount } from 'svelte'
  import { api } from './lib/api.js'
  import FilterBar from './lib/FilterBar.svelte'
  import CardGrid from './lib/CardGrid.svelte'
  import DetailDrawer from './lib/DetailDrawer.svelte'
  import WatchlistView from './lib/WatchlistView.svelte'
  import Toast from './lib/Toast.svelte'

  // ── Global view ─────────────────────────────────────────────────────────
  let view = 'requests'   // 'requests' | 'watchlist'

  // ── Requests state ──────────────────────────────────────────────────────
  let requests = []
  let loading = true
  let error = null

  let filter = 'all'
  let flaggedOnly = false
  let mediaStatusFilter = 'all'
  let searchQuery = ''
  let selected = new Set()
  let activeItem = null

  let rerequestingKeys = new Set()
  let rerequestingBatch = false

  // ── Cache info ───────────────────────────────────────────────────────────
  let cacheInfo = null

  /** @type {Toast} */
  let toastRef

  // ── Helpers ─────────────────────────────────────────────────────────────
  function itemKey(item) {
    return item.orphan ? `o-${item.media.id}` : String(item.id)
  }

  function addKeys(items) {
    return items.map((r) => ({ ...r, _key: itemKey(r) }))
  }

  const STATUS_ORDER = ['DELETED', 'PROCESSING', 'PENDING', 'PARTIALLY_AVAILABLE', 'AVAILABLE', 'UNKNOWN']
  $: availableMediaStatuses = STATUS_ORDER.filter(
    (s) => requests.some((r) => r.mediaStatusLabel === s)
  )

  $: filtered = requests.filter((r) => {
    if (filter !== 'all' && r.type !== filter) return false
    if (flaggedOnly && !r.flagged) return false
    if (mediaStatusFilter !== 'all' && r.mediaStatusLabel !== mediaStatusFilter) return false
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      if (!r.title?.toLowerCase().includes(q)) return false
    }
    return true
  })

  $: selectedInView = new Set([...selected].filter((k) => filtered.some((r) => r._key === k)))

  // ── Load requests ────────────────────────────────────────────────────────
  async function load() {
    loading = true
    error = null
    try {
      requests = addKeys(await api.fetchRequests())
      // Refresh cache indicator in background
      api.getCacheStatus().then((s) => { cacheInfo = s }).catch(() => {})
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  }

  // Handle refresh button — clears server cache then reloads
  async function handleRefresh() {
    if (view === 'watchlist') {
      // WatchlistView manages its own reload; we just clear the server cache
      await api.clearCache().catch(() => {})
      cacheInfo = null
      // Trigger WatchlistView reload by re-mounting via key (done via event)
      watchlistReloadKey++
      return
    }
    await api.clearCache().catch(() => {})
    cacheInfo = null
    await load()
  }

  let watchlistReloadKey = 0  // bump to force WatchlistView remount on manual refresh

  onMount(load)

  // ── Selection ────────────────────────────────────────────────────────────
  function toggleSelect(key) {
    const next = new Set(selected)
    next.has(key) ? next.delete(key) : next.add(key)
    selected = next
  }

  function selectAll() {
    selected = new Set(filtered.map((r) => r._key))
  }

  function clearSelection() {
    selected = new Set()
  }

  // ── Re-request single ─────────────────────────────────────────────────────
  async function doRerequest(item) {
    const key = item._key
    rerequestingKeys = new Set([...rerequestingKeys, key])
    const tid = toastRef.addToast('Re-requesting…', 'loading', 0)
    try {
      if (item.orphan) {
        await api.rerequestOrphan(item.media.id, item.media.tmdbId, item.type)
      } else {
        await api.rerequest(item.id)
      }
      toastRef.removeToast(tid)
      toastRef.addToast('Request submitted successfully.', 'success')
      const next = new Set(selected)
      next.delete(key)
      selected = next
      if (activeItem?._key === key) activeItem = null
      await load()
    } catch (e) {
      toastRef.removeToast(tid)
      toastRef.addToast(`Failed: ${e.message}`, 'error')
    } finally {
      const next = new Set(rerequestingKeys)
      next.delete(key)
      rerequestingKeys = next
    }
  }

  // ── Re-request batch ──────────────────────────────────────────────────────
  async function doRerequestBatch() {
    const keys = [...selectedInView]
    if (!keys.length) return

    const selectedItems = filtered.filter((r) => keys.includes(r._key))
    const regularItems = selectedItems.filter((r) => !r.orphan)
    const orphanItems = selectedItems.filter((r) => r.orphan)

    const total = selectedItems.length
    const confirmed = confirm(
      `Re-request ${total} selected item${total === 1 ? '' : 's'}?\n\nThis will clear and re-submit each request.`
    )
    if (!confirmed) return

    rerequestingBatch = true
    const tid = toastRef.addToast(`Re-requesting ${total} items…`, 'loading', 0)
    try {
      const result = await api.rerequestBatch(
        regularItems.map((r) => r.id),
        orphanItems.map((r) => ({
          seerrMediaId: r.media.id,
          tmdbId: r.media.tmdbId,
          mediaType: r.type,
        }))
      )
      toastRef.removeToast(tid)
      const ok = result.results?.length ?? 0
      const fail = result.errors?.length ?? 0
      if (fail === 0) {
        toastRef.addToast(`${ok} item${ok === 1 ? '' : 's'} re-requested successfully.`, 'success')
      } else {
        toastRef.addToast(`${ok} succeeded, ${fail} failed. Check console for details.`, 'error')
        console.error('Batch re-request errors:', result.errors)
      }
      clearSelection()
      await load()
    } catch (e) {
      toastRef.removeToast(tid)
      toastRef.addToast(`Batch failed: ${e.message}`, 'error')
    } finally {
      rerequestingBatch = false
    }
  }

  // ── View switching ────────────────────────────────────────────────────────
  function handleViewChange(e) {
    view = e.detail
    clearSelection()
  }
</script>

<div class="app">
  <FilterBar
    {view}
    {filter}
    {flaggedOnly}
    {mediaStatusFilter}
    {searchQuery}
    {availableMediaStatuses}
    {cacheInfo}
    totalCount={requests.length}
    filteredCount={filtered.length}
    selectedCount={selectedInView.size}
    rerequesting={rerequestingBatch}
    refreshing={loading}
    on:viewChange={handleViewChange}
    on:filterChange={(e) => { filter = e.detail; selected = new Set() }}
    on:toggleFlagged={() => { flaggedOnly = !flaggedOnly; selected = new Set() }}
    on:mediaStatusChange={(e) => { mediaStatusFilter = e.detail; selected = new Set() }}
    on:searchChange={(e) => { searchQuery = e.detail; selected = new Set() }}
    on:selectAll={selectAll}
    on:clearSelection={clearSelection}
    on:rerequestSelected={doRerequestBatch}
    on:refresh={handleRefresh}
  />

  <main class="main">
    {#if view === 'requests'}
      {#if loading}
        <div class="state-center">
          <div class="spinner"></div>
          <p>Loading requests…</p>
        </div>
      {:else if error}
        <div class="state-center state-center--error">
          <span style="font-size:2rem">⚠</span>
          <p>{error}</p>
          <button class="retry-btn" on:click={load}>Retry</button>
        </div>
      {:else}
        <CardGrid
          items={filtered}
          {selected}
          on:cardClick={(e) => (activeItem = e.detail)}
          on:toggleSelect={(e) => toggleSelect(e.detail)}
        />
      {/if}
    {:else}
      <!-- key forces a fresh load when the user manually hits refresh on watchlist tab -->
      {#key watchlistReloadKey}
        <WatchlistView {toastRef} />
      {/key}
    {/if}
  </main>

  <DetailDrawer
    item={activeItem}
    rerequesting={activeItem ? rerequestingKeys.has(activeItem._key) : false}
    on:close={() => (activeItem = null)}
    on:rerequest={(e) => doRerequest(e.detail)}
  />

  <Toast bind:this={toastRef} />
</div>

<style>
  :global(*) {
    box-sizing: border-box;
    -webkit-tap-highlight-color: transparent;
  }
  :global(body) {
    margin: 0;
    background: #0d1117;
    color: #e2e8f0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    min-height: 100dvh;
  }
  :global(#app) { min-height: 100dvh; }

  .app {
    min-height: 100dvh;
    display: flex;
    flex-direction: column;
  }

  .main { flex: 1; display: flex; flex-direction: column; }

  .state-center {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 1rem;
    padding: 5rem 1rem;
    color: #64748b;
    font-size: 0.9rem;
    flex: 1;
  }
  .state-center--error { color: #f87171; }

  .spinner {
    width: 2.5rem;
    height: 2.5rem;
    border: 3px solid #1e293b;
    border-top-color: #6366f1;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .retry-btn {
    background: #1e293b;
    border: none;
    border-radius: 0.5rem;
    color: #94a3b8;
    cursor: pointer;
    font-size: 0.875rem;
    padding: 0.5rem 1.25rem;
  }
  .retry-btn:hover { background: #2d3748; color: #f1f5f9; }
</style>
