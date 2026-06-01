<script>
  import { onMount } from 'svelte'
  import { api } from './api.js'
  import WatchlistCard from './WatchlistCard.svelte'
  import WatchlistTableView from './WatchlistTableView.svelte'

  /** Passed down from App so toasts appear in the shared container */
  export let toastRef = null

  // ── State ──────────────────────────────────────────────────────────────────
  let data = null
  let loading = true
  let error = null

  /** Active column tab: 'watchlist_only' | 'in_seerr' | 'available' */
  let activeTab = 'watchlist_only'

  /** Set of tmdbIds (numbers) selected for bulk request */
  let selected = new Set()

  let requesting = false
  let searchQuery = ''
  let typeFilter = 'all' // 'all' | 'movie' | 'tv'
  let viewMode = 'grid'  // 'grid' | 'table'

  // ── Load ───────────────────────────────────────────────────────────────────
  async function load() {
    loading = true
    error = null
    try {
      data = await api.fetchWatchlistComparison()
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  }

  onMount(load)

  // ── Derived ────────────────────────────────────────────────────────────────
  $: rawColumn =
    data
      ? activeTab === 'watchlist_only'
        ? data.watchlistOnly
        : activeTab === 'in_seerr'
        ? data.alreadyRequested
        : data.available
      : []

  $: activeItems = rawColumn.filter((item) => {
    if (typeFilter !== 'all' && item.type !== typeFilter) return false
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      if (!item.title?.toLowerCase().includes(q)) return false
    }
    return true
  })

  $: selectedInView =
    activeTab === 'watchlist_only'
      ? new Set([...selected].filter((id) => activeItems.some((i) => i.tmdbId === id)))
      : new Set()

  // ── Selection helpers ──────────────────────────────────────────────────────
  function toggleSelect(tmdbId) {
    const next = new Set(selected)
    next.has(tmdbId) ? next.delete(tmdbId) : next.add(tmdbId)
    selected = next
  }

  function selectAll() {
    // Only selectable in watchlist_only; select all currently visible items
    selected = new Set(activeItems.map((i) => i.tmdbId))
  }

  function clearSelection() {
    selected = new Set()
  }

  function switchTab(tab) {
    activeTab = tab
    clearSelection()
  }

  // ── Bulk request ───────────────────────────────────────────────────────────
  async function requestSelected() {
    const toRequest = (data?.watchlistOnly ?? []).filter((i) => selectedInView.has(i.tmdbId))
    if (!toRequest.length) return

    const confirmed = confirm(
      `Request ${toRequest.length} item${toRequest.length === 1 ? '' : 's'} from your Plex watchlist?\n\nThis will submit a fresh Seerr request for each.`
    )
    if (!confirmed) return

    requesting = true
    const tid = toastRef?.addToast(`Requesting ${toRequest.length} items…`, 'loading', 0)
    try {
      const result = await api.requestWatchlistItems(
        toRequest.map((i) => ({ tmdbId: i.tmdbId, mediaType: i.type }))
      )
      toastRef?.removeToast(tid)
      const ok = result.results?.length ?? 0
      const fail = result.errors?.length ?? 0
      if (fail === 0) {
        toastRef?.addToast(`${ok} item${ok === 1 ? '' : 's'} requested successfully.`, 'success')
      } else {
        toastRef?.addToast(`${ok} succeeded, ${fail} failed. Check console for details.`, 'error')
        console.error('Watchlist request errors:', result.errors)
      }
      clearSelection()
      await load()
    } catch (e) {
      toastRef?.removeToast(tid)
      toastRef?.addToast(`Failed: ${e.message}`, 'error')
    } finally {
      requesting = false
    }
  }
</script>

<!-- ─────────────────────────────────────────────────────────────────────────
     Watchlist comparison view
     ───────────────────────────────────────────────────────────────────────── -->
<div class="wv">

  {#if loading}
    <div class="state-center">
      <div class="spinner"></div>
      <p>Loading watchlist comparison…</p>
    </div>

  {:else if error}
    <div class="state-center state-center--error">
      <span style="font-size:2rem">⚠</span>
      <p>{error}</p>
      <button class="btn btn--ghost" on:click={load}>Retry</button>
    </div>

  {:else if data}

    <!-- ── Stats bar ── -->
    <div class="stats-bar">
      <div class="stat">
        <span class="stat__value">{data.stats.watchlistTotal}</span>
        <span class="stat__label">Watchlist total</span>
      </div>
      <div class="stat stat--warn">
        <span class="stat__value">{data.stats.watchlistOnly}</span>
        <span class="stat__label">Not in Seerr</span>
      </div>
      <div class="stat stat--blue">
        <span class="stat__value">{data.stats.alreadyRequested}</span>
        <span class="stat__label">In Seerr</span>
      </div>
      <div class="stat stat--green">
        <span class="stat__value">{data.stats.available}</span>
        <span class="stat__label">Available</span>
      </div>
      <div class="stat stat--muted">
        <span class="stat__value">{data.stats.notOnWatchlist}</span>
        <span class="stat__label">Requested elsewhere</span>
      </div>
    </div>

    {#if data.stats.notOnWatchlist > 0}
      <div class="info-banner">
        <span class="info-banner__icon">ℹ</span>
        <span>
          <strong>{data.stats.notOnWatchlist}</strong> Seerr request{data.stats.notOnWatchlist === 1 ? '' : 's'} found that
          {data.stats.notOnWatchlist === 1 ? 'is' : 'are'} not on your Plex watchlist — requested from another source
          or added manually. You can manage those in the <strong>Requests</strong> tab.
        </span>
      </div>
    {/if}

    <!-- ── Column tabs ── -->
    <div class="tab-row">
      <button
        class="ctab"
        class:ctab--active={activeTab === 'watchlist_only'}
        on:click={() => switchTab('watchlist_only')}
      >
        <span class="ctab__dot ctab__dot--warn"></span>
        Watchlist Only
        <span class="ctab__count">{data.stats.watchlistOnly}</span>
      </button>
      <button
        class="ctab"
        class:ctab--active={activeTab === 'in_seerr'}
        on:click={() => switchTab('in_seerr')}
      >
        <span class="ctab__dot ctab__dot--blue"></span>
        In Seerr
        <span class="ctab__count">{data.stats.alreadyRequested}</span>
      </button>
      <button
        class="ctab"
        class:ctab--active={activeTab === 'available'}
        on:click={() => switchTab('available')}
      >
        <span class="ctab__dot ctab__dot--green"></span>
        Available
        <span class="ctab__count">{data.stats.available}</span>
      </button>
    </div>

    <!-- ── Column description ── -->
    <div class="col-desc">
      {#if activeTab === 'watchlist_only'}
        <p>Items on your Plex watchlist with no Seerr request yet — select any to bulk-request them.</p>
      {:else if activeTab === 'in_seerr'}
        <p>Items on your watchlist that have an active Seerr request. Status badges reflect the current Seerr state.</p>
      {:else}
        <p>Items on your watchlist that are already available in your library. These can safely be removed from your Plex watchlist.</p>
      {/if}
    </div>

    <!-- ── Search + type filter + actions ── -->
    <div class="toolbar">
      <input
        class="search"
        type="search"
        placeholder="Search titles…"
        bind:value={searchQuery}
        spellcheck="false"
      />

      <div class="pill-group" role="group" aria-label="Media type filter">
        {#each ['all', 'movie', 'tv'] as t}
          <button
            class="pill"
            class:pill--active={typeFilter === t}
            on:click={() => { typeFilter = t; clearSelection() }}
          >
            {t === 'all' ? 'All' : t === 'movie' ? 'Movies' : 'TV'}
          </button>
        {/each}
      </div>

      {#if activeTab === 'watchlist_only'}
        <div class="toolbar__actions">
          {#if selectedInView.size > 0}
            <button class="btn btn--ghost" on:click={clearSelection}>
              Clear ({selectedInView.size})
            </button>
            <button
              class="btn btn--primary"
              disabled={requesting}
              on:click={requestSelected}
            >
              {requesting ? '⟳ Working…' : `Request ${selectedInView.size} selected`}
            </button>
          {/if}
          <button class="btn btn--ghost" on:click={selectAll}>
            Select all visible ({activeItems.length})
          </button>
        </div>
      {/if}

      <div class="toolbar__count">
        {activeItems.length} item{activeItems.length === 1 ? '' : 's'}
      </div>

      <!-- View mode toggle -->
      <div class="view-toggle" role="group" aria-label="View mode">
        <button
          class="vtoggle"
          class:vtoggle--active={viewMode === 'grid'}
          title="Grid view"
          on:click={() => (viewMode = 'grid')}
          aria-pressed={viewMode === 'grid'}
        >
          <svg width="13" height="13" viewBox="0 0 14 14" fill="none" aria-hidden="true">
            <rect x="1"   y="1"   width="4.5" height="4.5" rx="0.75" fill="currentColor"/>
            <rect x="8.5" y="1"   width="4.5" height="4.5" rx="0.75" fill="currentColor"/>
            <rect x="1"   y="8.5" width="4.5" height="4.5" rx="0.75" fill="currentColor"/>
            <rect x="8.5" y="8.5" width="4.5" height="4.5" rx="0.75" fill="currentColor"/>
          </svg>
        </button>
        <button
          class="vtoggle"
          class:vtoggle--active={viewMode === 'table'}
          title="Table view"
          on:click={() => (viewMode = 'table')}
          aria-pressed={viewMode === 'table'}
        >
          <svg width="13" height="13" viewBox="0 0 14 14" fill="none" aria-hidden="true">
            <rect x="1" y="2"   width="12" height="2" rx="0.5" fill="currentColor"/>
            <rect x="1" y="6"   width="12" height="2" rx="0.5" fill="currentColor"/>
            <rect x="1" y="10" width="12" height="2" rx="0.5" fill="currentColor"/>
          </svg>
        </button>
      </div>

      <button
        class="btn btn--ghost btn--icon"
        title="Refresh watchlist comparison"
        on:click={load}
      >↻</button>
    </div>

    <!-- ── Card grid / table ── -->
    {#if activeItems.length === 0}
      <div class="empty">
        <span class="empty__icon">📭</span>
        <p>
          {#if searchQuery || typeFilter !== 'all'}
            No items match your filters.
          {:else if activeTab === 'watchlist_only'}
            All watchlist items have already been requested — great!
          {:else if activeTab === 'in_seerr'}
            No watchlist items are currently tracked in Seerr.
          {:else}
            No watchlist items are available in the library yet.
          {/if}
        </p>
      </div>
    {:else if viewMode === 'table'}
      <WatchlistTableView
        items={activeItems}
        {selected}
        selectable={activeTab === 'watchlist_only'}
        on:toggleSelect={(e) => toggleSelect(e.detail)}
      />
    {:else}
      <div class="wgrid">
        {#each activeItems as item (item.tmdbId)}
          <WatchlistCard
            {item}
            selected={selected.has(item.tmdbId)}
            selectable={activeTab === 'watchlist_only'}
            on:toggleSelect={(e) => toggleSelect(e.detail)}
          />
        {/each}
      </div>
    {/if}

  {/if}
</div>

<style>
  .wv {
    flex: 1;
    display: flex;
    flex-direction: column;
  }

  /* ── Loading / error states ── */
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

  /* ── Stats bar ── */
  .stats-bar {
    display: flex;
    gap: 0;
    border-bottom: 1px solid #1e293b;
    overflow-x: auto;
    scrollbar-width: none;
  }
  .stats-bar::-webkit-scrollbar { display: none; }

  .stat {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 0.75rem 1.25rem;
    gap: 0.15rem;
    border-right: 1px solid #1e293b;
    flex-shrink: 0;
  }
  .stat:last-child { border-right: none; }

  .stat__value {
    font-size: 1.5rem;
    font-weight: 800;
    color: #f1f5f9;
    font-variant-numeric: tabular-nums;
    line-height: 1;
  }
  .stat__label {
    font-size: 0.65rem;
    font-weight: 600;
    color: #64748b;
    letter-spacing: 0.04em;
    white-space: nowrap;
    text-transform: uppercase;
  }
  .stat--warn  .stat__value { color: #fbbf24; }
  .stat--blue  .stat__value { color: #60a5fa; }
  .stat--green .stat__value { color: #4ade80; }
  .stat--muted .stat__value { color: #94a3b8; }

  /* ── Info banner ── */
  .info-banner {
    display: flex;
    align-items: flex-start;
    gap: 0.625rem;
    background: rgba(99,102,241,0.07);
    border-bottom: 1px solid rgba(99,102,241,0.18);
    color: #a5b4fc;
    font-size: 0.8rem;
    line-height: 1.5;
    padding: 0.625rem 1rem;
  }
  .info-banner__icon {
    font-size: 1rem;
    flex-shrink: 0;
    margin-top: 0.05rem;
  }

  /* ── Column tabs ── */
  .tab-row {
    display: flex;
    gap: 0;
    border-bottom: 1px solid #1e293b;
    overflow-x: auto;
    scrollbar-width: none;
  }
  .tab-row::-webkit-scrollbar { display: none; }

  .ctab {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: #94a3b8;
    cursor: pointer;
    font-size: 0.8rem;
    font-weight: 600;
    padding: 0.75rem 1.125rem;
    transition: all 0.15s;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .ctab:hover { color: #cbd5e1; }
  .ctab--active { color: #f1f5f9; border-bottom-color: #6366f1; }

  .ctab__dot {
    display: inline-block;
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .ctab__dot--warn  { background: #f59e0b; }
  .ctab__dot--blue  { background: #3b82f6; }
  .ctab__dot--green { background: #22c55e; }

  .ctab__count {
    background: #1e293b;
    border-radius: 9999px;
    font-size: 0.65rem;
    font-weight: 700;
    padding: 0.1rem 0.45rem;
    color: #94a3b8;
  }
  .ctab--active .ctab__count { background: rgba(99,102,241,0.2); color: #a5b4fc; }

  /* ── Column description ── */
  .col-desc {
    padding: 0.5rem 1rem 0;
  }
  .col-desc p {
    margin: 0;
    font-size: 0.78rem;
    color: #64748b;
    line-height: 1.5;
  }

  /* ── Toolbar ── */
  .toolbar {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
    padding: 0.625rem 1rem;
    border-bottom: 1px solid #1e293b;
  }

  .search {
    flex: 1;
    min-width: 10rem;
    background: #1e293b;
    border: 1px solid #2d3748;
    border-radius: 0.375rem;
    color: #e2e8f0;
    font-size: 0.8rem;
    padding: 0.375rem 0.75rem;
    outline: none;
    transition: border-color 0.15s;
  }
  .search::placeholder { color: #64748b; }
  .search:focus { border-color: #6366f1; }
  .search::-webkit-search-cancel-button { cursor: pointer; }

  .pill-group {
    display: flex;
    background: #1e293b;
    border-radius: 0.375rem;
    padding: 2px;
    gap: 2px;
    flex-shrink: 0;
  }

  .pill {
    background: transparent;
    border: none;
    border-radius: 0.25rem;
    color: #b0bec5;
    cursor: pointer;
    font-size: 0.75rem;
    font-weight: 500;
    padding: 0.2rem 0.55rem;
    transition: all 0.15s;
    white-space: nowrap;
  }
  .pill:hover { color: #f1f5f9; background: #2d3748; }
  .pill--active { background: #334155; color: #f1f5f9; }

  .toolbar__actions {
    display: flex;
    gap: 0.375rem;
    flex-wrap: wrap;
  }

  .toolbar__count {
    font-size: 0.72rem;
    color: #64748b;
    margin-left: auto;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  /* ── View mode toggle ── */
  .view-toggle {
    display: flex;
    background: #1e293b;
    border-radius: 0.375rem;
    padding: 2px;
    gap: 2px;
    flex-shrink: 0;
  }
  .vtoggle {
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: none;
    border-radius: 0.25rem;
    color: #94a3b8;
    cursor: pointer;
    padding: 0.25rem 0.45rem;
    transition: all 0.15s;
    line-height: 1;
  }
  .vtoggle:hover { color: #f1f5f9; background: #2d3748; }
  .vtoggle--active { background: #334155; color: #f1f5f9; }

  /* ── Buttons ── */
  .btn {
    border: none;
    border-radius: 0.375rem;
    cursor: pointer;
    font-size: 0.78rem;
    font-weight: 600;
    padding: 0.35rem 0.75rem;
    transition: all 0.15s;
    white-space: nowrap;
  }
  .btn--ghost {
    background: #1e293b;
    color: #b0bec5;
  }
  .btn--ghost:hover { background: #2d3748; color: #f1f5f9; }
  .btn--primary {
    background: #6366f1;
    color: #fff;
  }
  .btn--primary:hover:not(:disabled) { background: #4f46e5; }
  .btn--primary:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn--icon {
    padding: 0.35rem 0.55rem;
    font-size: 1rem;
    line-height: 1;
  }

  /* ── Empty state ── */
  .empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    padding: 4rem 1rem;
    color: #64748b;
    flex: 1;
  }
  .empty__icon { font-size: 3rem; }
  .empty p { font-size: 0.9rem; margin: 0; text-align: center; }

  /* ── Card grid ── */
  .wgrid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.5rem;
    padding: 0.625rem;
  }

  @media (min-width: 540px) {
    .wgrid { grid-template-columns: repeat(4, 1fr); }
  }
  @media (min-width: 768px) {
    .wgrid { grid-template-columns: repeat(5, 1fr); gap: 0.75rem; padding: 0.875rem; }
  }
  @media (min-width: 1200px) {
    .wgrid { grid-template-columns: repeat(6, 1fr); }
  }
  @media (min-width: 1600px) {
    .wgrid { grid-template-columns: repeat(7, 1fr); }
  }
</style>
