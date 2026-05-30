<script>
  import { createEventDispatcher } from 'svelte'

  export let item
  export let selected = false
  /** Only show checkbox in the "Watchlist Only" column */
  export let selectable = false

  const dispatch = createEventDispatcher()

  const REQUEST_STATUS_COLOR = {
    PENDING:             '#f59e0b',
    APPROVED:            '#6366f1',
    DECLINED:            '#ef4444',
    AVAILABLE:           '#22c55e',
    PARTIALLY_AVAILABLE: '#3b82f6',
  }

  const MEDIA_STATUS_COLOR = {
    UNKNOWN:             '#64748b',
    PENDING:             '#f59e0b',
    PROCESSING:          '#3b82f6',
    PARTIALLY_AVAILABLE: '#8b5cf6',
    AVAILABLE:           '#22c55e',
    DELETED:             '#ef4444',
  }

  // Media status reflects what's actually in the library and is more
  // authoritative than request status.  Prefer it unless it's absent or
  // UNKNOWN, in which case fall back to request status.
  $: _effectiveMediaStatus = (item.mediaStatus && item.mediaStatus !== 'UNKNOWN')
    ? item.mediaStatus : null
  $: statusLabel = _effectiveMediaStatus || item.requestStatus || null
  $: statusColor = _effectiveMediaStatus
    ? (MEDIA_STATUS_COLOR[_effectiveMediaStatus] ?? '#64748b')
    : (REQUEST_STATUS_COLOR[item.requestStatus]  ?? '#64748b')

  $: isTV = item.type === 'tv'

  function handleCheck(e) {
    e.stopPropagation()
    e.preventDefault()
    dispatch('toggleSelect', item.tmdbId)
  }
</script>

<article
  class="wcard"
  class:wcard--selected={selected}
  class:wcard--selectable={selectable}
  aria-label={item.title}
>
  <div class="wcard__poster">
    {#if item.posterUrl}
      <img src={item.posterUrl} alt={item.title} loading="lazy" />
    {:else}
      <div class="wcard__no-poster">
        {isTV ? '📺' : '🎬'}
      </div>
    {/if}

    {#if selectable}
      <div
        class="wcard__check"
        role="checkbox"
        aria-checked={selected}
        tabindex="0"
        on:click={handleCheck}
        on:keydown={(e) => { if (e.key === ' ') { e.preventDefault(); handleCheck(e) } }}
      >
        <span class="wcard__checkmark" class:wcard__checkmark--checked={selected}></span>
      </div>
    {/if}

    <span class="wcard__type" class:wcard__type--tv={isTV}>
      {isTV ? 'TV' : 'MOVIE'}
    </span>
  </div>

  <div class="wcard__body">
    <p class="wcard__title" title={item.title}>{item.title}</p>
    {#if item.year}
      <p class="wcard__year">{item.year}</p>
    {/if}

    {#if statusLabel}
      <div class="wcard__badges">
        <span
          class="badge"
          style="color:{statusColor};border-color:{statusColor}25;background:{statusColor}18"
        >
          {statusLabel}
        </span>
      </div>
    {/if}

    <div class="wcard__id">
      <span class="id-tag" title="TMDB ID">TMDB {item.tmdbId}</span>
    </div>
  </div>
</article>

<style>
  .wcard {
    background: #131720;
    border: 1.5px solid #1e293b;
    border-radius: 0.625rem;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    transition: border-color 0.15s, box-shadow 0.15s;
    user-select: none;
  }
  .wcard--selectable { cursor: pointer; }
  .wcard--selectable:hover { border-color: #334155; box-shadow: 0 4px 16px rgba(0,0,0,0.3); }
  .wcard--selected { border-color: #6366f1; box-shadow: 0 0 0 1px #6366f1; }

  /* ── Poster ── */
  .wcard__poster {
    position: relative;
    aspect-ratio: 2/3;
    background: #0d1117;
    overflow: hidden;
  }
  .wcard__poster img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  .wcard__no-poster {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 2.5rem;
    color: #334155;
  }

  /* ── Checkbox ── */
  .wcard__check {
    position: absolute;
    top: 0.4rem;
    left: 0.4rem;
    cursor: pointer;
  }
  .wcard__checkmark {
    display: block;
    width: 1.1rem;
    height: 1.1rem;
    border-radius: 0.25rem;
    border: 2px solid rgba(255,255,255,0.45);
    background: rgba(0,0,0,0.5);
    transition: all 0.15s;
  }
  .wcard__checkmark--checked {
    background: #6366f1;
    border-color: #6366f1;
  }
  .wcard__checkmark--checked::after {
    content: '✓';
    display: block;
    color: #fff;
    font-size: 0.7rem;
    text-align: center;
    line-height: 1.1rem;
  }

  /* ── Type badge ── */
  .wcard__type {
    position: absolute;
    bottom: 0.35rem;
    right: 0.35rem;
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    padding: 0.15rem 0.35rem;
    border-radius: 0.25rem;
    background: rgba(59,130,246,0.85);
    color: #fff;
  }
  .wcard__type--tv { background: rgba(139,92,246,0.85); }

  /* ── Body ── */
  .wcard__body {
    padding: 0.5rem 0.5rem 0.6rem;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    flex: 1;
  }

  .wcard__title {
    font-size: 0.75rem;
    font-weight: 600;
    color: #e2e8f0;
    margin: 0;
    line-height: 1.3;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .wcard__year {
    font-size: 0.65rem;
    color: #64748b;
    margin: 0;
  }

  .wcard__badges { display: flex; flex-wrap: wrap; gap: 0.25rem; }

  .badge {
    font-size: 0.55rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    padding: 0.1rem 0.3rem;
    border-radius: 0.25rem;
    border: 1px solid;
    white-space: nowrap;
  }

  .wcard__id {
    display: flex;
    flex-wrap: wrap;
    gap: 0.2rem;
    margin-top: auto;
    padding-top: 0.25rem;
  }

  .id-tag {
    font-size: 0.55rem;
    font-weight: 600;
    padding: 0.1rem 0.3rem;
    border-radius: 0.2rem;
    background: #1e3a5f;
    color: #60a5fa;
    white-space: nowrap;
  }
</style>
