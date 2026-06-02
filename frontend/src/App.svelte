<script>
  import { onMount } from 'svelte'
  import { api, AuthError, getToken, setToken } from './lib/api.js'
  import FilterBar from './lib/FilterBar.svelte'
  import CardGrid from './lib/CardGrid.svelte'
  import RequestsTableView from './lib/RequestsTableView.svelte'
  import DetailDrawer from './lib/DetailDrawer.svelte'
  import WatchlistView from './lib/WatchlistView.svelte'
  import LibraryView from './lib/LibraryView.svelte'
  import Toast from './lib/Toast.svelte'

  // ── Auth state ───────────────────────────────────────────────────────────
  let authRequired = false
  let authChecked = false
  let tokenInput = getToken()
  let authError = ''

  async function checkAuth() {
    try {
      const res = await api.fetchAuthRequired()
      authRequired = res.required
    } catch (_) {
      authRequired = false
    }
    authChecked = true
    if (!authRequired || getToken()) {
      load()
    }
  }

  async function submitToken() {
    authError = ''
    setToken(tokenInput.trim())
    try {
      await api.fetchStatus()
      load()
    } catch (e) {
      if (e instanceof AuthError) {
        authError = 'Incorrect token — please try again.'
      } else {
        // Status endpoint errored for another reason (e.g. Seerr not configured)
        // but auth passed — proceed.
        load()
      }
    }
  }

  // ── Global view ─────────────────────────────────────────────────────────
  let view = 'requests'   // 'requests' | 'watchlist' | 'library'
  let viewMode = 'grid'   // 'grid' | 'table'  — persisted per-view below

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
  let resettingKeys = new Set()
  let resettingBatch = false

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
      if (e instanceof AuthError) {
        authChecked = true
        authRequired = true
        tokenInput = ''
        return
      }
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
    if (view === 'library') {
      await api.clearCache().catch(() => {})
      cacheInfo = null
      libraryReloadKey++
      return
    }
    await api.clearCache().catch(() => {})
    cacheInfo = null
    await load()
  }

  let watchlistReloadKey = 0  // bump to force WatchlistView remount on manual refresh
  let libraryReloadKey = 0    // bump to force LibraryView remount on manual refresh

  onMount(checkAuth)

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

  // ── Reset single ──────────────────────────────────────────────────────────
  async function doReset(item) {
    const key = item._key
    resettingKeys = new Set([...resettingKeys, key])
    const tid = toastRef.addToast('Resetting…', 'loading', 0)
    try {
      if (item.orphan) {
        await api.resetOrphan(item.media.id)
      } else {
        await api.reset(item.id)
      }
      toastRef.removeToast(tid)
      toastRef.addToast('Item reset — request and media record removed.', 'success')
      const next = new Set(selected)
      next.delete(key)
      selected = next
      if (activeItem?._key === key) activeItem = null
      await load()
    } catch (e) {
      toastRef.removeToast(tid)
      toastRef.addToast(`Reset failed: ${e.message}`, 'error')
    } finally {
      const next = new Set(resettingKeys)
      next.delete(key)
      resettingKeys = next
    }
  }

  // ── Reset batch ────────────────────────────────────────────────────────────
  async function doResetBatch() {
    const keys = [...selectedInView]
    if (!keys.length) return

    const selectedItems = filtered.filter((r) => keys.includes(r._key))
    const regularItems = selectedItems.filter((r) => !r.orphan)
    const orphanItems = selectedItems.filter((r) => r.orphan)

    const total = selectedItems.length
    const confirmed = confirm(
      `Reset ${total} selected item${total === 1 ? '' : 's'}?\n\nThis will permanently delete the request and media record from Seerr. No new request will be created.`
    )
    if (!confirmed) return

    resettingBatch = true
    const tid = toastRef.addToast(`Resetting ${total} items…`, 'loading', 0)
    try {
      const result = await api.resetBatch(
        regularItems.map((r) => r.id),
        orphanItems.map((r) => r.media.id)
      )
      toastRef.removeToast(tid)
      const ok = result.results?.length ?? 0
      const fail = result.errors?.length ?? 0
      if (fail === 0) {
        toastRef.addToast(`${ok} item${ok === 1 ? '' : 's'} reset successfully.`, 'success')
      } else {
        toastRef.addToast(`${ok} succeeded, ${fail} failed. Check console for details.`, 'error')
        console.error('Batch reset errors:', result.errors)
      }
      clearSelection()
      await load()
    } catch (e) {
      toastRef.removeToast(tid)
      toastRef.addToast(`Batch reset failed: ${e.message}`, 'error')
    } finally {
      resettingBatch = false
    }
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

  function handleViewModeChange(e) {
    viewMode = e.detail
  }
</script>

<div class="app">
  <!-- Login overlay shown when APP_SECRET is set and no valid token is stored -->
  {#if authRequired && (!getToken() || authError)}
    <div class="login-overlay">
      <div class="login-card">
        <h1 class="login-title">Seerr Manager</h1>
        <p class="login-subtitle">Enter your access token to continue.</p>
        <form class="login-form" on:submit|preventDefault={submitToken}>
          <input
            class="login-input"
            type="password"
            placeholder="Access token"
            bind:value={tokenInput}
            autocomplete="current-password"
          />
          {#if authError}<p class="login-error">{authError}</p>{/if}
          <button class="login-btn" type="submit">Unlock</button>
        </form>
      </div>
    </div>
  {/if}
  <FilterBar
    {view}
    {filter}
    {flaggedOnly}
    {mediaStatusFilter}
    {searchQuery}
    {availableMediaStatuses}
    {cacheInfo}
    {viewMode}
    totalCount={requests.length}
    filteredCount={filtered.length}
    selectedCount={selectedInView.size}
    rerequesting={rerequestingBatch}
    resetting={resettingBatch}
    refreshing={loading}
    on:viewChange={handleViewChange}
    on:filterChange={(e) => { filter = e.detail; selected = new Set() }}
    on:toggleFlagged={() => { flaggedOnly = !flaggedOnly; selected = new Set() }}
    on:mediaStatusChange={(e) => { mediaStatusFilter = e.detail; selected = new Set() }}
    on:searchChange={(e) => { searchQuery = e.detail; selected = new Set() }}
    on:selectAll={selectAll}
    on:clearSelection={clearSelection}
    on:rerequestSelected={doRerequestBatch}
    on:resetSelected={doResetBatch}
    on:refresh={handleRefresh}
    on:viewModeChange={handleViewModeChange}
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
        {#if viewMode === 'table'}
          <RequestsTableView
            items={filtered}
            {selected}
            on:cardClick={(e) => (activeItem = e.detail)}
            on:toggleSelect={(e) => toggleSelect(e.detail)}
          />
        {:else}
          <CardGrid
            items={filtered}
            {selected}
            on:cardClick={(e) => (activeItem = e.detail)}
            on:toggleSelect={(e) => toggleSelect(e.detail)}
          />
        {/if}
      {/if}
    {:else if view === 'watchlist'}
      <!-- key forces a fresh load when the user manually hits refresh on watchlist tab -->
      {#key watchlistReloadKey}
        <WatchlistView {toastRef} />
      {/key}
    {:else if view === 'library'}
      <!-- key forces a fresh load when the user manually hits refresh on library tab -->
      {#key libraryReloadKey}
        <LibraryView {toastRef} />
      {/key}
    {/if}
  </main>

  <DetailDrawer
    item={activeItem}
    rerequesting={activeItem ? rerequestingKeys.has(activeItem._key) : false}
    resetting={activeItem ? resettingKeys.has(activeItem._key) : false}
    on:close={() => (activeItem = null)}
    on:rerequest={(e) => doRerequest(e.detail)}
    on:reset={(e) => doReset(e.detail)}
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
    color: #94a3b8;
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
    color: #b0bec5;
    cursor: pointer;
    font-size: 0.875rem;
    padding: 0.5rem 1.25rem;
  }
  .retry-btn:hover { background: #2d3748; color: #f1f5f9; }

  /* Login overlay */
  .login-overlay {
    position: fixed;
    inset: 0;
    background: #0d1117;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }
  .login-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 0.75rem;
    padding: 2rem;
    width: 100%;
    max-width: 24rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }
  .login-title {
    margin: 0;
    font-size: 1.25rem;
    color: #f1f5f9;
    text-align: center;
  }
  .login-subtitle {
    margin: 0;
    font-size: 0.85rem;
    color: #94a3b8;
    text-align: center;
  }
  .login-form {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  .login-input {
    background: #0d1117;
    border: 1px solid #30363d;
    border-radius: 0.5rem;
    color: #f1f5f9;
    font-size: 0.9rem;
    padding: 0.6rem 0.75rem;
    width: 100%;
    outline: none;
  }
  .login-input:focus { border-color: #6366f1; }
  .login-error {
    margin: 0;
    color: #f87171;
    font-size: 0.8rem;
    text-align: center;
  }
  .login-btn {
    background: #6366f1;
    border: none;
    border-radius: 0.5rem;
    color: #fff;
    cursor: pointer;
    font-size: 0.9rem;
    font-weight: 600;
    padding: 0.6rem;
    width: 100%;
  }
  .login-btn:hover { background: #4f46e5; }
</style>
