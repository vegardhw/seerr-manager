<script>
  import { createEventDispatcher } from 'svelte'

  export let item
  export let selected = false
  export let selectable = false

  const dispatch = createEventDispatcher()

  const SOURCE = {
    radarr: { label: 'RADARR', color: '#f59e0b', bg: 'rgba(245,158,11,0.15)' },
    sonarr: { label: 'SONARR', color: '#10b981', bg: 'rgba(16,185,129,0.15)' },
  }

  const SEERR_STATUS_COLOR = {
    UNKNOWN:             '#64748b',
    PENDING:             '#f59e0b',
    PROCESSING:          '#3b82f6',
    PARTIALLY_AVAILABLE: '#8b5cf6',
    AVAILABLE:           '#22c55e',
    DELETED:             '#ef4444',
  }

  $: src = SOURCE[item.source] ?? SOURCE.radarr
  $: isTV = item.type === 'tv'
  $: seerrStatus = item.seerrMediaStatus ?? null

  function formatSize(bytes) {
    if (!bytes) return null
    if (bytes >= 1099511627776) return (bytes / 1099511627776).toFixed(1) + ' TB'
    if (bytes >= 1073741824)    return (bytes / 1073741824).toFixed(1) + ' GB'
    if (bytes >= 1048576)       return (bytes / 1048576).toFixed(0) + ' MB'
    return bytes + ' B'
  }

  function handleCheck(e) {
    e.stopPropagation()
    e.preventDefault()
    dispatch('toggleSelect', item.tmdbId)
  }
</script>

<article
  class="lcard"
  class:lcard--selected={selected}
  class:lcard--selectable={selectable}
  aria-label={item.title}
>
  <div class="lcard__poster">
    {#if item.posterUrl}
      <img src={item.posterUrl} alt={item.title} loading="lazy" />
    {:else}
      <div class="lcard__no-poster">{isTV ? '📺' : '🎬'}</div>
    {/if}

    {#if selectable}
      <div
        class="lcard__check"
        role="checkbox"
        aria-checked={selected}
        tabindex="0"
        on:click={handleCheck}
        on:keydown={(e) => { if (e.key === ' ') { e.preventDefault(); handleCheck(e) } }}
      >
        <span class="lcard__checkmark" class:lcard__checkmark--checked={selected}></span>
      </div>
    {/if}

    <!-- Source badge -->
    <span
      class="lcard__source"
      style="background:{src.bg};color:{src.color}"
    >{src.label}</span>

    <!-- Type badge -->
    <span class="lcard__type" class:lcard__type--tv={isTV}>
      {isTV ? 'TV' : 'MOVIE'}
    </span>

    <!-- File-present dot -->
    {#if item.hasFile}
      <span class="lcard__file-dot" title="File present on disk">●</span>
    {/if}
  </div>

  <div class="lcard__body">
    <p class="lcard__title" title={item.title}>{item.title}</p>
    {#if item.year}
      <p class="lcard__year">{item.year}</p>
    {/if}

    <div class="lcard__badges">
      <!-- Seerr media status (inSeerr bucket only) -->
      {#if seerrStatus}
        {@const sc = SEERR_STATUS_COLOR[seerrStatus] ?? '#64748b'}
        <span
          class="badge"
          style="color:{sc};border-color:{sc}25;background:{sc}18"
        >{seerrStatus}</span>
      {/if}

      <!-- File size -->
      {#if item.sizeOnDisk}
        <span class="badge badge--size">{formatSize(item.sizeOnDisk)}</span>
      {/if}
    </div>

    <!-- Episode count for TV -->
    {#if isTV && item.totalEpisodeCount}
      <p class="lcard__eps">
        {item.episodeFileCount} / {item.totalEpisodeCount} eps
      </p>
    {/if}

    <div class="lcard__ids">
      {#if item.tmdbId}
        <span class="id-tag">TMDB {item.tmdbId}</span>
      {/if}
      {#if isTV && item.tvdbId}
        <span class="id-tag id-tag--tvdb">TVDB {item.tvdbId}</span>
      {/if}
    </div>
  </div>
</article>

<style>
  .lcard {
    background: #131720;
    border: 1.5px solid #1e293b;
    border-radius: 0.625rem;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    transition: border-color 0.15s, box-shadow 0.15s;
    user-select: none;
  }
  .lcard--selectable { cursor: pointer; }
  .lcard--selectable:hover { border-color: #334155; box-shadow: 0 4px 16px rgba(0,0,0,0.3); }
  .lcard--selected  { border-color: #6366f1; box-shadow: 0 0 0 1px #6366f1; }

  /* ── Poster ── */
  .lcard__poster {
    position: relative;
    aspect-ratio: 2/3;
    background: #0d1117;
    overflow: hidden;
  }
  .lcard__poster img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  .lcard__no-poster {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 2.5rem;
    color: #334155;
  }

  /* ── Checkbox ── */
  .lcard__check {
    position: absolute;
    top: 0.4rem;
    left: 0.4rem;
    cursor: pointer;
  }
  .lcard__checkmark {
    display: block;
    width: 1.1rem;
    height: 1.1rem;
    border-radius: 0.25rem;
    border: 2px solid rgba(255,255,255,0.45);
    background: rgba(0,0,0,0.5);
    transition: all 0.15s;
  }
  .lcard__checkmark--checked { background: #6366f1; border-color: #6366f1; }
  .lcard__checkmark--checked::after {
    content: '✓';
    display: block;
    color: #fff;
    font-size: 0.7rem;
    text-align: center;
    line-height: 1.1rem;
  }

  /* ── Source badge (top-right) ── */
  .lcard__source {
    position: absolute;
    top: 0.35rem;
    right: 0.35rem;
    font-size: 0.55rem;
    font-weight: 800;
    letter-spacing: 0.06em;
    padding: 0.15rem 0.35rem;
    border-radius: 0.25rem;
  }

  /* ── Type badge (bottom-right) ── */
  .lcard__type {
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
  .lcard__type--tv { background: rgba(139,92,246,0.85); }

  /* ── File dot (bottom-left) ── */
  .lcard__file-dot {
    position: absolute;
    bottom: 0.4rem;
    left: 0.45rem;
    font-size: 0.55rem;
    color: #22c55e;
    line-height: 1;
  }

  /* ── Body ── */
  .lcard__body {
    padding: 0.5rem 0.5rem 0.6rem;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    flex: 1;
  }

  .lcard__title {
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
  .lcard__year {
    font-size: 0.65rem;
    color: #94a3b8;
    margin: 0;
  }

  .lcard__badges { display: flex; flex-wrap: wrap; gap: 0.25rem; }

  .badge {
    font-size: 0.55rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    padding: 0.1rem 0.3rem;
    border-radius: 0.25rem;
    border: 1px solid;
    white-space: nowrap;
  }
  .badge--size {
    background: #1e293b;
    color: #94a3b8;
    border-color: #334155;
  }

  .lcard__eps {
    font-size: 0.62rem;
    color: #94a3b8;
    margin: 0;
  }

  .lcard__ids {
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
  .id-tag--tvdb { background: #2d1a4a; color: #a78bfa; }
</style>
