<script>
  import { createEventDispatcher } from 'svelte'

  export let view = 'requests'          // 'requests' | 'watchlist'
  export let filter = 'all'
  export let flaggedOnly = false
  export let mediaStatusFilter = 'all'
  export let searchQuery = ''
  export let totalCount = 0
  export let filteredCount = 0
  export let selectedCount = 0
  export let rerequesting = false
  export let refreshing = false
  export let availableMediaStatuses = []
  export let cacheInfo = null            // { ttl_seconds, entries } | null

  const dispatch = createEventDispatcher()

  const MEDIA_STATUS_LABELS = {
    all: 'All statuses',
    DELETED: 'Deleted',
    PROCESSING: 'Processing',
    PARTIALLY_AVAILABLE: 'Partial',
    AVAILABLE: 'Available',
    PENDING: 'Pending',
    UNKNOWN: 'Unknown',
  }

  $: cacheEntries = cacheInfo?.entries ?? {}
  $: cachedKeys = Object.keys(cacheEntries)
  $: anyFresh = cachedKeys.some((k) => (cacheEntries[k]?.expires_in_seconds ?? 0) > 0)
</script>

<header class="filter-bar">
  <!-- ── App title + global nav ── -->
  <div class="filter-bar__top">
    <h1 class="filter-bar__title">
      <span class="filter-bar__icon">📺</span>
      Seerr Manager
    </h1>

    <nav class="nav-tabs" aria-label="Main navigation">
      <button
        class="ntab"
        class:ntab--active={view === 'requests'}
        on:click={() => dispatch('viewChange', 'requests')}
      >
        Requests
      </button>
      <button
        class="ntab"
        class:ntab--active={view === 'watchlist'}
        on:click={() => dispatch('viewChange', 'watchlist')}
      >
        Watchlist
      </button>
    </nav>

    <div class="filter-bar__right">
      {#if view === 'requests'}
        <span class="filter-bar__count">{filteredCount} / {totalCount}</span>
      {/if}
      {#if anyFresh}
        <span
          class="cache-badge"
          title="Data served from cache. Refresh or wait for TTL to re-fetch."
        >⚡ cached</span>
      {/if}
      <button
        class="btn-refresh"
        class:btn-refresh--spinning={refreshing}
        disabled={refreshing}
        title="Refresh"
        on:click={() => dispatch('refresh')}
      >↻</button>
    </div>
  </div>

  <!-- ── Requests-only controls ── -->
  {#if view === 'requests'}
    <input
      class="search"
      type="search"
      placeholder="Search titles…"
      value={searchQuery}
      on:input={(e) => dispatch('searchChange', e.target.value)}
      spellcheck="false"
    />

    <div class="filter-bar__controls">
      <div class="pill-group" role="group" aria-label="Media type filter">
        {#each ['all', 'movie', 'tv'] as type}
          <button
            class="pill"
            class:pill--active={filter === type}
            on:click={() => dispatch('filterChange', type)}
          >
            {type === 'all' ? 'All' : type === 'movie' ? 'Movies' : 'TV'}
          </button>
        {/each}
      </div>

      <button
        class="pill"
        class:pill--active={flaggedOnly}
        class:pill--warn={flaggedOnly}
        on:click={() => dispatch('toggleFlagged')}
      >
        ⚑ Flagged
      </button>

      {#if availableMediaStatuses.length > 1}
        <div class="pill-group" role="group" aria-label="Media status filter">
          <button
            class="pill"
            class:pill--active={mediaStatusFilter === 'all'}
            on:click={() => dispatch('mediaStatusChange', 'all')}
          >
            Status: all
          </button>
          {#each availableMediaStatuses as status}
            <button
              class="pill pill--status pill--status-{status}"
              class:pill--active={mediaStatusFilter === status}
              on:click={() => dispatch('mediaStatusChange', status)}
            >
              {MEDIA_STATUS_LABELS[status] ?? status}
            </button>
          {/each}
        </div>
      {/if}
    </div>

    {#if selectedCount > 0}
      <div class="filter-bar__actions">
        <button class="btn btn--ghost" on:click={() => dispatch('clearSelection')}>
          Clear ({selectedCount})
        </button>
        <button class="btn btn--ghost" on:click={() => dispatch('selectAll')}>
          Select all visible
        </button>
        <button
          class="btn btn--primary"
          disabled={rerequesting}
          on:click={() => dispatch('rerequestSelected')}
        >
          {rerequesting ? '⟳ Working…' : `Re-request ${selectedCount}`}
        </button>
      </div>
    {:else}
      <div class="filter-bar__actions">
        <button class="btn btn--ghost" on:click={() => dispatch('selectAll')}>
          Select all visible
        </button>
      </div>
    {/if}
  {/if}
</header>

<style>
  .filter-bar {
    position: sticky;
    top: 0;
    z-index: 100;
    background: #0d1117;
    border-bottom: 1px solid #1e293b;
    padding: 0.75rem 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.625rem;
  }

  .filter-bar__top {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .filter-bar__title {
    font-size: 1.05rem;
    font-weight: 700;
    color: #f1f5f9;
    margin: 0;
    display: flex;
    align-items: center;
    gap: 0.4rem;
    flex-shrink: 0;
  }

  .filter-bar__icon { font-size: 1.15rem; }

  /* ── Global nav tabs ── */
  .nav-tabs {
    display: flex;
    gap: 2px;
    background: #1e293b;
    border-radius: 0.375rem;
    padding: 2px;
  }

  .ntab {
    background: transparent;
    border: none;
    border-radius: 0.25rem;
    color: #64748b;
    cursor: pointer;
    font-size: 0.78rem;
    font-weight: 600;
    padding: 0.25rem 0.7rem;
    transition: all 0.15s;
    white-space: nowrap;
  }
  .ntab:hover { color: #f1f5f9; background: #2d3748; }
  .ntab--active { background: #334155; color: #f1f5f9; }

  /* ── Right side ── */
  .filter-bar__right {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    margin-left: auto;
    flex-shrink: 0;
  }

  .filter-bar__count {
    font-size: 0.75rem;
    color: #64748b;
    font-variant-numeric: tabular-nums;
  }

  .cache-badge {
    font-size: 0.65rem;
    font-weight: 600;
    color: #6366f1;
    background: rgba(99,102,241,0.12);
    border: 1px solid rgba(99,102,241,0.25);
    border-radius: 0.25rem;
    padding: 0.1rem 0.35rem;
    white-space: nowrap;
  }

  .btn-refresh {
    background: none;
    border: 1px solid #1e293b;
    border-radius: 0.375rem;
    color: #64748b;
    cursor: pointer;
    font-size: 1rem;
    line-height: 1;
    padding: 0.15rem 0.4rem;
    transition: all 0.15s;
  }
  .btn-refresh:hover:not(:disabled) { color: #f1f5f9; border-color: #334155; }
  .btn-refresh:disabled { cursor: not-allowed; opacity: 0.4; }
  .btn-refresh--spinning { animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* ── Search ── */
  .search {
    width: 100%;
    background: #1e293b;
    border: 1px solid #2d3748;
    border-radius: 0.375rem;
    color: #e2e8f0;
    font-size: 0.875rem;
    padding: 0.4rem 0.75rem;
    outline: none;
    transition: border-color 0.15s;
  }
  .search::placeholder { color: #475569; }
  .search:focus { border-color: #6366f1; }
  .search::-webkit-search-cancel-button { cursor: pointer; }

  /* ── Controls row ── */
  .filter-bar__controls {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .filter-bar__actions {
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  /* ── Pill groups ── */
  .pill-group {
    display: flex;
    background: #1e293b;
    border-radius: 0.375rem;
    padding: 2px;
    gap: 2px;
    flex-wrap: wrap;
  }

  .pill {
    background: transparent;
    border: none;
    border-radius: 0.25rem;
    color: #94a3b8;
    cursor: pointer;
    font-size: 0.8rem;
    font-weight: 500;
    padding: 0.25rem 0.625rem;
    transition: all 0.15s;
    white-space: nowrap;
  }
  .pill:hover { color: #f1f5f9; background: #2d3748; }
  .pill--active { background: #334155; color: #f1f5f9; }
  .pill--warn.pill--active { background: #78350f; color: #fbbf24; }

  .pill--status-DELETED.pill--active            { background: #3b0f0f; color: #f87171; }
  .pill--status-PROCESSING.pill--active         { background: #0f2a4a; color: #60a5fa; }
  .pill--status-PARTIALLY_AVAILABLE.pill--active { background: #2d1a4a; color: #a78bfa; }
  .pill--status-AVAILABLE.pill--active          { background: #0f2d1a; color: #4ade80; }
  .pill--status-PENDING.pill--active            { background: #3b2800; color: #fbbf24; }

  /* ── Action buttons ── */
  .btn {
    border: none;
    border-radius: 0.375rem;
    cursor: pointer;
    font-size: 0.8rem;
    font-weight: 600;
    padding: 0.375rem 0.75rem;
    transition: all 0.15s;
    white-space: nowrap;
  }
  .btn--ghost { background: #1e293b; color: #94a3b8; }
  .btn--ghost:hover { background: #2d3748; color: #f1f5f9; }
  .btn--primary { background: #6366f1; color: #fff; }
  .btn--primary:hover:not(:disabled) { background: #4f46e5; }
  .btn--primary:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
