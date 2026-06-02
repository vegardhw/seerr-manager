<script>
  import { onMount } from 'svelte'
  import { api } from './api.js'
  import LibraryCard from './LibraryCard.svelte'
  import LibraryTableView from './LibraryTableView.svelte'

  /** Shared toast container passed down from App.svelte */
  export let toastRef = null

  // ── State ──────────────────────────────────────────────────────────────────
  let data = null
  let loading = true
  let error = null

  /** Active sub-tab: 'untracked' | 'watchlisted' | 'in_seerr' */
  let activeTab = 'untracked'

  /** Selected TMDB IDs (Set<number>) — only active in requestable tabs */
  let selected = new Set()

  let requesting = false
  let searchQuery = ''
  let typeFilter  = 'all'      // 'all' | 'movie' | 'tv'
  let hasFileOnly = true        // hide items with no file on disk by default
  let viewMode    = 'grid'      // 'grid' | 'table'

  // ── Load ───────────────────────────────────────────────────────────────────
  async function load() {
    loading = true
    error = null
    try {
      data = await api.fetchLibraryUntracked()
      // Default to 'in_seerr' if untracked is empty but inSeerr has content
      if (data.stats.untracked === 0 && data.stats.inSeerr > 0) {
        activeTab = 'in_seerr'
      }
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
      ? activeTab === 'untracked'
        ? data.untracked
        : activeTab === 'watchlisted'
        ? data.watchlistedNotInSeerr
        : data.inSeerr
      : []

  $: activeItems = rawColumn.filter((item) => {
    if (hasFileOnly && !item.hasFile) return false
    if (typeFilter !== 'all' && item.type !== typeFilter) return false
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      if (!item.title?.toLowerCase().includes(q)) return false
    }
    return true
  })

  /** Selection only applies to requestable tabs */
  $: isSelectable = activeTab === 'untracked' || activeTab === 'watchlisted'
  $: selectedInView = isSelectable
    ? new Set([...selected].filter((id) => activeItems.some((i) => i.tmdbId === id)))
    : new Set()

  // ── Helpers ────────────────────────────────────────────────────────────────
  function toggleSelect(tmdbId) {
    const next = new Set(selected)
    next.has(tmdbId) ? next.delete(tmdbId) : next.add(tmdbId)
    selected = next
  }

  function selectAll() {
    selected = new Set(activeItems.map((i) => i.tmdbId))
  }

  function clearSelection() {
    selected = new Set()
  }

  function switchTab(tab) {
    activeTab = tab
    clearSelection()
  }

  // ── Request in Seerr ───────────────────────────────────────────────────────
  async function requestSelected() {
    const toRequest = rawColumn.filter((i) => selectedInView.has(i.tmdbId))
    if (!toRequest.length) return

    const count = toRequest.length
    const confirmed = confirm(
      `Request ${count} item${count === 1 ? '' : 's'} in Seerr?\n\nThis will submit a fresh request for each selected title.`
    )
    if (!confirmed) return

    requesting = true
    const tid = toastRef?.addToast(`Requesting ${count} items…`, 'loading', 0)
    try {
      const result = await api.requestWatchlistItems(
        toRequest.map((i) => ({ tmdbId: i.tmdbId, mediaType: i.type }))
      )
      toastRef?.removeToast(tid)
      const ok   = result.results?.length ?? 0
      const fail = result.errors?.length  ?? 0
      if (fail === 0) {
        toastRef?.addToast(`${ok} item${ok === 1 ? '' : 's'} requested successfully.`, 'success')
      } else {
        toastRef?.addToast(`${ok} succeeded, ${fail} failed. Check console for details.`, 'error')
        console.error('Library request errors:', result.errors)
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
     Library view — Radarr + Sonarr cross-reference
     ───────────────────────────────────────────────────────────────────────── -->
<div class="lv">

  {#if loading}
    <div class="state-center">
      <div class="spinner"></div>
      <p>Loading library…</p>
    </div>

  {:else if error}
    <div class="state-center state-center--error">
      <span style="font-size:2rem">⚠</span>
      <p>{error}</p>
      <button class="btn btn--ghost" on:click={load}>Retry</button>
    </div>

  {:else if data && !data.configured.radarr && !data.configured.sonarr}
    <!-- ── Not configured ── -->
    <div class="not-configured">
      <div class="nc-card">
        <div class="nc-icon">🔌</div>
        <h2 class="nc-title">Configure Radarr &amp; Sonarr</h2>
        <p class="nc-desc">
          Set the following environment variables and restart the container to enable the Library view.
          You can configure either or both services independently.
        </p>
        <div class="nc-vars">
          <div class="nc-var-group">
            <span class="nc-svc nc-svc--radarr">RADARR</span>
            <code>RADARR_URL</code>
            <code>RADARR_API_KEY</code>
          </div>
          <div class="nc-var-group">
            <span class="nc-svc nc-svc--sonarr">SONARR</span>
            <code>SONARR_URL</code>
            <code>SONARR_API_KEY</code>
          </div>
        </div>
        <p class="nc-hint">
          Find your API key in <strong>Settings → General → Security</strong> in Radarr or Sonarr.
        </p>
      </div>
    </div>

  {:else if data}

    <!-- ── Stats bar ── -->
    <div class="stats-bar">
      {#if data.configured.radarr}
        <div class="stat stat--radarr">
          <span class="stat__value">{data.stats.radarrTotal}</span>
          <span class="stat__label">Radarr movies</span>
        </div>
      {/if}
      {#if data.configured.sonarr}
        <div class="stat stat--sonarr">
          <span class="stat__value">{data.stats.sonarrTotal}</span>
          <span class="stat__label">Sonarr series</span>
        </div>
      {/if}
      <div class="stat stat--warn">
        <span class="stat__value">{data.stats.untracked}</span>
        <span class="stat__label">Untracked</span>
      </div>
      <div class="stat stat--amber">
        <span class="stat__value">{data.stats.watchlistedNotInSeerr}</span>
        <span class="stat__label">On watchlist</span>
      </div>
      <div class="stat stat--green">
        <span class="stat__value">{data.stats.inSeerr}</span>
        <span class="stat__label">In Seerr</span>
      </div>
      {#if data.stats.noTmdbId > 0}
        <div class="stat stat--muted" title="Items skipped because no TMDB ID could be resolved">
          <span class="stat__value">{data.stats.noTmdbId}</span>
          <span class="stat__label">No TMDB ID</span>
        </div>
      {/if}

      <!-- Service status indicators -->
      <div class="stat-services">
        <span
          class="svc-badge"
          class:svc-badge--on={data.configured.radarr}
          class:svc-badge--off={!data.configured.radarr}
          title={data.configured.radarr ? 'Radarr connected' : 'Radarr not configured'}
        >
          RADARR {data.configured.radarr ? '●' : '○'}
        </span>
        <span
          class="svc-badge"
          class:svc-badge--sonarr={data.configured.sonarr}
          class:svc-badge--off={!data.configured.sonarr}
          title={data.configured.sonarr ? 'Sonarr connected' : 'Sonarr not configured'}
        >
          SONARR {data.configured.sonarr ? '●' : '○'}
        </span>
      </div>
    </div>

    <!-- ── Sub-tabs ── -->
    <div class="tab-row">
      <button
        class="ctab"
        class:ctab--active={activeTab === 'untracked'}
        on:click={() => switchTab('untracked')}
      >
        <span class="ctab__dot ctab__dot--warn"></span>
        Untracked
        <span class="ctab__count">{data.stats.untracked}</span>
      </button>
      <button
        class="ctab"
        class:ctab--active={activeTab === 'watchlisted'}
        on:click={() => switchTab('watchlisted')}
      >
        <span class="ctab__dot ctab__dot--amber"></span>
        On Watchlist
        <span class="ctab__count">{data.stats.watchlistedNotInSeerr}</span>
      </button>
      <button
        class="ctab"
        class:ctab--active={activeTab === 'in_seerr'}
        on:click={() => switchTab('in_seerr')}
      >
        <span class="ctab__dot ctab__dot--green"></span>
        In Seerr
        <span class="ctab__count">{data.stats.inSeerr}</span>
      </button>
    </div>

    <!-- ── Tab description ── -->
    <div class="col-desc">
      {#if activeTab === 'untracked'}
        <p>
          In your library but <strong>absent from both Seerr and your watchlist</strong> — Seerr has no record
          of these titles. Select any to request them in Seerr.
        </p>
      {:else if activeTab === 'watchlisted'}
        <p>
          In your library and <strong>on your Plex watchlist</strong>, but not yet in Seerr.
          These will likely be auto-requested by Seerr's watchlist sync, or you can trigger them manually.
        </p>
      {:else}
        <p>
          In your library and <strong>already tracked by Seerr</strong>. Status badges reflect
          the current Seerr media record.
        </p>
      {/if}
    </div>

    <!-- ── Toolbar ── -->
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

      <button
        class="pill"
        class:pill--active={hasFileOnly}
        title="Only show items with a file present on disk"
        on:click={() => { hasFileOnly = !hasFileOnly; clearSelection() }}
      >
        ● Has file
      </button>

      {#if isSelectable}
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
              {requesting ? '⟳ Working…' : `Request ${selectedInView.size} in Seerr`}
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
            <rect x="1" y="2"  width="12" height="2" rx="0.5" fill="currentColor"/>
            <rect x="1" y="6"  width="12" height="2" rx="0.5" fill="currentColor"/>
            <rect x="1" y="10" width="12" height="2" rx="0.5" fill="currentColor"/>
          </svg>
        </button>
      </div>

      <button class="btn btn--ghost btn--icon" title="Refresh" on:click={load}>↻</button>
    </div>

    <!-- ── Content ── -->
    {#if activeItems.length === 0}
      <div class="empty">
        <span class="empty__icon">
          {#if activeTab === 'untracked'}🎉{:else if activeTab === 'watchlisted'}📋{:else}✅{/if}
        </span>
        <p>
          {#if searchQuery || typeFilter !== 'all' || hasFileOnly}
            No items match your filters.
          {:else if activeTab === 'untracked'}
            Everything in your library is tracked by Seerr or on your watchlist — great!
          {:else if activeTab === 'watchlisted'}
            No library items are on the watchlist but outside Seerr.
          {:else}
            No library items are currently tracked in Seerr.
          {/if}
        </p>
        {#if hasFileOnly && rawColumn.some((i) => !i.hasFile)}
          <button class="btn btn--ghost" on:click={() => (hasFileOnly = false)}>
            Show items without a file too
          </button>
        {/if}
      </div>
    {:else if viewMode === 'table'}
      <LibraryTableView
        items={activeItems}
        {selected}
        selectable={isSelectable}
        on:toggleSelect={(e) => toggleSelect(e.detail)}
      />
    {:else}
      <div class="lgrid">
        {#each activeItems as item (item.tmdbId ?? item.libraryId)}
          <LibraryCard
            {item}
            selected={selected.has(item.tmdbId)}
            selectable={isSelectable}
            on:toggleSelect={(e) => toggleSelect(e.detail)}
          />
        {/each}
      </div>
    {/if}

  {/if}
</div>

<style>
  .lv {
    flex: 1;
    display: flex;
    flex-direction: column;
  }

  /* ── Loading / error ── */
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
    width: 2.5rem; height: 2.5rem;
    border: 3px solid #1e293b;
    border-top-color: #6366f1;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Not configured ── */
  .not-configured {
    display: flex;
    align-items: center;
    justify-content: center;
    flex: 1;
    padding: 2rem 1rem;
  }
  .nc-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 0.75rem;
    padding: 2rem;
    max-width: 32rem;
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 1rem;
    text-align: center;
  }
  .nc-icon { font-size: 3rem; }
  .nc-title { margin: 0; font-size: 1.15rem; color: #f1f5f9; }
  .nc-desc  { margin: 0; font-size: 0.85rem; color: #94a3b8; line-height: 1.6; }
  .nc-vars {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    background: #0d1117;
    border-radius: 0.5rem;
    padding: 1rem;
  }
  .nc-var-group {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
    justify-content: center;
  }
  .nc-svc {
    font-size: 0.65rem;
    font-weight: 800;
    letter-spacing: 0.06em;
    padding: 0.15rem 0.4rem;
    border-radius: 0.25rem;
  }
  .nc-svc--radarr { background: rgba(245,158,11,0.15); color: #f59e0b; }
  .nc-svc--sonarr { background: rgba(16,185,129,0.15); color: #10b981; }
  .nc-var-group code {
    background: #1e293b;
    color: #a5b4fc;
    font-size: 0.78rem;
    padding: 0.15rem 0.45rem;
    border-radius: 0.25rem;
    font-family: 'SFMono-Regular', Consolas, monospace;
  }
  .nc-hint { margin: 0; font-size: 0.75rem; color: #64748b; }

  /* ── Stats bar ── */
  .stats-bar {
    display: flex;
    align-items: stretch;
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
  .stat__value {
    font-size: 1.5rem; font-weight: 800; color: #f1f5f9;
    font-variant-numeric: tabular-nums; line-height: 1;
  }
  .stat__label {
    font-size: 0.65rem; font-weight: 600; color: #64748b;
    letter-spacing: 0.04em; white-space: nowrap; text-transform: uppercase;
  }
  .stat--radarr .stat__value { color: #f59e0b; }
  .stat--sonarr .stat__value { color: #10b981; }
  .stat--warn   .stat__value { color: #ef4444; }
  .stat--amber  .stat__value { color: #f59e0b; }
  .stat--green  .stat__value { color: #4ade80; }
  .stat--muted  .stat__value { color: #94a3b8; }

  /* ── Service status badges ── */
  .stat-services {
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 0.3rem;
    padding: 0.5rem 0.875rem;
    margin-left: auto;
    flex-shrink: 0;
  }
  .svc-badge {
    font-size: 0.6rem;
    font-weight: 800;
    letter-spacing: 0.06em;
    padding: 0.15rem 0.4rem;
    border-radius: 0.25rem;
    white-space: nowrap;
  }
  .svc-badge--on     { background: rgba(245,158,11,0.15); color: #f59e0b; }
  .svc-badge--sonarr { background: rgba(16,185,129,0.15); color: #10b981; }
  .svc-badge--off    { background: #1e293b; color: #475569; }

  /* ── Sub-tabs ── */
  .tab-row {
    display: flex;
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
    width: 0.5rem; height: 0.5rem;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .ctab__dot--warn  { background: #ef4444; }
  .ctab__dot--amber { background: #f59e0b; }
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
  .col-desc strong { color: #94a3b8; }

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
  }
  .vtoggle:hover { color: #f1f5f9; background: #2d3748; }
  .vtoggle--active { background: #334155; color: #f1f5f9; }

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
  .btn--ghost   { background: #1e293b; color: #b0bec5; }
  .btn--ghost:hover { background: #2d3748; color: #f1f5f9; }
  .btn--primary { background: #6366f1; color: #fff; }
  .btn--primary:hover:not(:disabled) { background: #4f46e5; }
  .btn--primary:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn--icon { padding: 0.35rem 0.55rem; font-size: 1rem; line-height: 1; }

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
  .lgrid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.5rem;
    padding: 0.625rem;
  }
  @media (min-width: 540px)  { .lgrid { grid-template-columns: repeat(4, 1fr); } }
  @media (min-width: 768px)  { .lgrid { grid-template-columns: repeat(5, 1fr); gap: 0.75rem; padding: 0.875rem; } }
  @media (min-width: 1200px) { .lgrid { grid-template-columns: repeat(6, 1fr); } }
  @media (min-width: 1600px) { .lgrid { grid-template-columns: repeat(7, 1fr); } }
</style>
