<script>
  import { createEventDispatcher } from 'svelte'

  export let item = null
  export let rerequesting = false
  export let resetting = false

  const dispatch = createEventDispatcher()

  const MEDIA_STATUS_COLOR = {
    UNKNOWN: '#64748b',
    PENDING: '#f59e0b',
    PROCESSING: '#3b82f6',
    PARTIALLY_AVAILABLE: '#8b5cf6',
    AVAILABLE: '#22c55e',
    DELETED: '#ef4444',
  }

  $: mediaStatusColor = item ? (MEDIA_STATUS_COLOR[item.mediaStatusLabel] ?? '#64748b') : '#64748b'

  function handleBackdrop(e) {
    if (e.target === e.currentTarget) dispatch('close')
  }

  function formatDate(dateStr) {
    if (!dateStr) return '—'
    return new Date(dateStr).toLocaleDateString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
    })
  }
</script>

{#if item}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <div class="backdrop" on:click={handleBackdrop} role="presentation">
    <div class="drawer" role="dialog" aria-modal="true" aria-label={item.title}>
      <div class="drawer__handle"></div>

      <div class="drawer__header">
        {#if item.posterUrl}
          <img class="drawer__poster" src={item.posterUrl} alt={item.title} />
        {:else}
          <div class="drawer__poster drawer__poster--empty">
            {item.type === 'tv' ? '📺' : '🎬'}
          </div>
        {/if}

        <div class="drawer__meta">
          <div class="drawer__type-row">
            <span class="type-pill" class:type-pill--tv={item.type === 'tv'}>
              {item.type === 'tv' ? 'TV Series' : 'Movie'}
            </span>
            {#if item.flagged}
              <span class="flag-badge">⚑ Flagged</span>
            {/if}
          </div>

          <h2 class="drawer__title">{item.title}</h2>
          {#if item.year}<p class="drawer__year">{item.year}</p>{/if}

          <div class="drawer__statuses">
            <span class="status-chip" style="color:{mediaStatusColor};border-color:{mediaStatusColor}30;background:{mediaStatusColor}12">
              {item.mediaStatusLabel}
            </span>
          </div>
        </div>
      </div>

      {#if item.orphan}
        <div class="drawer__orphan-note">
          No active request — this item was in your library but has no request record.
          Use "New request" to re-add it.
        </div>
      {/if}

      {#if item.flagged && item.flagReasons?.length}
        <div class="drawer__warn">
          <strong>⚑ Flagged:</strong>
          <ul>
            {#each item.flagReasons as reason}
              <li>{reason}</li>
            {/each}
          </ul>
        </div>
      {/if}

      {#if item.overview}
        <p class="drawer__overview">{item.overview}</p>
      {/if}

      <div class="drawer__section">
        <h3 class="drawer__section-title">IDs</h3>
        <div class="id-grid">
          <div class="id-row">
            <span class="id-label">TMDB</span>
            <span class="id-value" class:id-value--missing={!item.media?.tmdbId}>
              {item.media?.tmdbId ?? 'Missing'}
            </span>
          </div>
          <div class="id-row">
            <span class="id-label">TVDB</span>
            <span class="id-value" class:id-value--missing={!item.media?.tvdbId}>
              {item.media?.tvdbId ?? 'None'}
            </span>
          </div>
          <div class="id-row">
            <span class="id-label">IMDB</span>
            <span class="id-value" class:id-value--missing={!item.media?.imdbId}>
              {item.media?.imdbId ?? 'None'}
            </span>
          </div>
          {#if item.resolvedTmdbId && item.resolvedTmdbId !== item.media?.tmdbId}
            <div class="id-row">
              <span class="id-label">Resolved TMDB</span>
              <span class="id-value id-value--resolved">{item.resolvedTmdbId}</span>
            </div>
          {/if}
        </div>
      </div>

      <div class="drawer__section">
        <h3 class="drawer__section-title">Request Details</h3>
        <div class="id-grid">
          {#if !item.orphan}
          <div class="id-row">
            <span class="id-label">Request ID</span>
            <span class="id-value">{item.id}</span>
          </div>
          {/if}
          <div class="id-row">
            <span class="id-label">Requested by</span>
            <span class="id-value">{item.requestedBy?.displayName ?? '—'}</span>
          </div>
          <div class="id-row">
            <span class="id-label">Created</span>
            <span class="id-value">{formatDate(item.createdAt)}</span>
          </div>
          <div class="id-row">
            <span class="id-label">Updated</span>
            <span class="id-value">{formatDate(item.updatedAt)}</span>
          </div>
          {#if item.type === 'tv' && item.seasons?.length}
            <div class="id-row">
              <span class="id-label">Seasons</span>
              <span class="id-value">
                {item.seasons.map((s) => `S${String(s.seasonNumber).padStart(2,'0')}`).join(', ')}
              </span>
            </div>
          {/if}
        </div>
      </div>

      <div class="drawer__actions">
        <button class="btn btn--ghost" on:click={() => dispatch('close')}>
          Close
        </button>
        {#if item.mediaStatusLabel === 'DELETED'}
          <button
            class="btn btn--danger"
            disabled={resetting || rerequesting}
            title="Remove the request and media record from Seerr without re-requesting"
            on:click={() => dispatch('reset', item)}
          >
            {resetting ? '⟳ Working…' : '🗑 Reset'}
          </button>
        {/if}
        <button
          class="btn btn--primary"
          disabled={rerequesting || resetting || !item.media?.tmdbId}
          title={!item.media?.tmdbId ? 'No TMDB ID available' : ''}
          on:click={() => dispatch('rerequest', item)}
        >
          {rerequesting ? '⟳ Working…' : item.orphan ? '＋ New request' : '↺ Re-request'}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    z-index: 500;
    display: flex;
    align-items: flex-end;
    backdrop-filter: blur(2px);
  }

  @media (min-width: 640px) {
    .backdrop { align-items: center; justify-content: center; }
  }

  .drawer {
    background: #131720;
    border: 1px solid #1e293b;
    border-radius: 1rem 1rem 0 0;
    max-height: 90vh;
    overflow-y: auto;
    padding: 1rem;
    width: 100%;
    animation: slide-up 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
  }

  @media (min-width: 640px) {
    .drawer {
      border-radius: 1rem;
      max-width: 36rem;
      max-height: 85vh;
      animation: fade-in 0.2s ease;
    }
  }

  @keyframes slide-up {
    from { transform: translateY(100%); }
    to   { transform: translateY(0); }
  }
  @keyframes fade-in {
    from { opacity: 0; transform: scale(0.97); }
    to   { opacity: 1; transform: scale(1); }
  }

  .drawer__handle {
    width: 2.5rem;
    height: 4px;
    background: #334155;
    border-radius: 9999px;
    margin: 0 auto 1rem;
  }
  @media (min-width: 640px) { .drawer__handle { display: none; } }

  .drawer__header {
    display: flex;
    gap: 0.875rem;
    margin-bottom: 1rem;
  }

  .drawer__poster {
    width: 5.5rem;
    flex-shrink: 0;
    border-radius: 0.5rem;
    object-fit: cover;
    aspect-ratio: 2/3;
    background: #1e293b;
  }
  .drawer__poster--empty {
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 2rem;
    color: #334155;
  }

  .drawer__meta { flex: 1; min-width: 0; }

  .drawer__type-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.375rem;
    flex-wrap: wrap;
  }

  .type-pill {
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    padding: 0.15rem 0.5rem;
    border-radius: 9999px;
    background: rgba(59,130,246,0.2);
    color: #60a5fa;
  }
  .type-pill--tv { background: rgba(139,92,246,0.2); color: #a78bfa; }

  .flag-badge {
    font-size: 0.65rem;
    font-weight: 700;
    padding: 0.15rem 0.5rem;
    border-radius: 9999px;
    background: rgba(245,158,11,0.15);
    color: #fbbf24;
  }

  .drawer__title {
    font-size: 1.05rem;
    font-weight: 700;
    color: #f1f5f9;
    margin: 0 0 0.25rem;
    line-height: 1.3;
  }
  .drawer__year { font-size: 0.8rem; color: #64748b; margin: 0 0 0.5rem; }

  .drawer__statuses { display: flex; flex-wrap: wrap; gap: 0.375rem; }

  .status-chip {
    font-size: 0.65rem;
    font-weight: 600;
    padding: 0.2rem 0.5rem;
    border-radius: 0.25rem;
    border: 1px solid;
    white-space: nowrap;
  }

  .drawer__orphan-note {
    background: rgba(99,102,241,0.08);
    border: 1px solid rgba(99,102,241,0.25);
    border-radius: 0.5rem;
    color: #a5b4fc;
    font-size: 0.8rem;
    line-height: 1.5;
    margin-bottom: 0.875rem;
    padding: 0.625rem 0.875rem;
  }

  .drawer__warn {
    background: rgba(245,158,11,0.08);
    border: 1px solid rgba(245,158,11,0.25);
    border-radius: 0.5rem;
    color: #fbbf24;
    font-size: 0.8rem;
    margin-bottom: 0.875rem;
    padding: 0.625rem 0.875rem;
  }
  .drawer__warn strong { display: block; margin-bottom: 0.25rem; }
  .drawer__warn ul { margin: 0; padding-left: 1.25rem; }
  .drawer__warn li { margin-bottom: 0.2rem; }

  .drawer__overview {
    font-size: 0.825rem;
    color: #94a3b8;
    line-height: 1.6;
    margin: 0 0 1rem;
  }

  .drawer__section { margin-bottom: 1rem; }
  .drawer__section-title {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: #475569;
    text-transform: uppercase;
    margin: 0 0 0.5rem;
  }

  .id-grid { display: flex; flex-direction: column; gap: 0.3rem; }
  .id-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    font-size: 0.8rem;
  }
  .id-label { color: #64748b; flex-shrink: 0; }
  .id-value { color: #e2e8f0; font-variant-numeric: tabular-nums; font-weight: 500; }
  .id-value--missing { color: #f87171; }
  .id-value--resolved { color: #34d399; }

  .drawer__actions {
    display: flex;
    gap: 0.625rem;
    padding-top: 0.5rem;
    border-top: 1px solid #1e293b;
    margin-top: 0.5rem;
  }

  .btn {
    border: none;
    border-radius: 0.5rem;
    cursor: pointer;
    font-size: 0.875rem;
    font-weight: 600;
    padding: 0.625rem 1rem;
    transition: all 0.15s;
    flex: 1;
  }
  .btn--ghost { background: #1e293b; color: #94a3b8; }
  .btn--ghost:hover { background: #2d3748; color: #f1f5f9; }
  .btn--primary { background: #6366f1; color: #fff; }
  .btn--primary:hover:not(:disabled) { background: #4f46e5; }
  .btn--primary:disabled { opacity: 0.4; cursor: not-allowed; }
  .btn--danger { background: #7f1d1d; color: #fca5a5; border: 1px solid #991b1b; }
  .btn--danger:hover:not(:disabled) { background: #991b1b; color: #fecaca; }
  .btn--danger:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
