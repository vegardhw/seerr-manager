<script>
  import { createEventDispatcher } from 'svelte'

  export let item
  export let selected = false

  const dispatch = createEventDispatcher()

  const STATUS_COLOR = {
    PENDING: '#f59e0b',
    APPROVED: '#22c55e',
    DECLINED: '#ef4444',
    AVAILABLE: '#22c55e',
    PARTIALLY_AVAILABLE: '#3b82f6',
    UNKNOWN: '#64748b',
  }

  const MEDIA_STATUS_COLOR = {
    UNKNOWN: '#64748b',
    PENDING: '#f59e0b',
    PROCESSING: '#3b82f6',
    PARTIALLY_AVAILABLE: '#8b5cf6',
    AVAILABLE: '#22c55e',
    DELETED: '#ef4444',
  }

  $: mediaStatusColor = MEDIA_STATUS_COLOR[item.mediaStatusLabel] ?? '#64748b'
  $: isTV = item.type === 'tv'
  $: tmdbId = item.media?.tmdbId
  $: tvdbId = item.media?.tvdbId
  $: imdbId = item.media?.imdbId

  function handleCheck(e) {
    e.stopPropagation()
    e.preventDefault()
    dispatch('toggleSelect', item._key)
  }
</script>

<article
  class="card"
  class:card--selected={selected}
  class:card--flagged={item.flagged}
  class:card--orphan={item.orphan}
  on:click={() => dispatch('click', item)}
  role="button"
  tabindex="0"
  aria-label={item.title}
  on:keydown={(e) => e.key === 'Enter' && dispatch('click', item)}
>
  <div class="card__poster">
    {#if item.posterUrl}
      <img src={item.posterUrl} alt={item.title} loading="lazy" />
    {:else}
      <div class="card__no-poster">
        {isTV ? '📺' : '🎬'}
      </div>
    {/if}

    <div
      class="card__check"
      role="checkbox"
      aria-checked={selected}
      tabindex="0"
      on:click={handleCheck}
      on:keydown={(e) => { if (e.key === ' ') { e.preventDefault(); handleCheck(e) } }}
    >
      <span class="card__checkmark" class:card__checkmark--checked={selected}></span>
    </div>

    {#if item.flagged}
      <span class="card__flag" title={item.flagReasons?.join('\n')}>⚑</span>
    {/if}

    <span class="card__type" class:card__type--tv={isTV}>
      {isTV ? 'TV' : 'MOVIE'}
    </span>
  </div>

  <div class="card__body">
    <p class="card__title" title={item.title}>{item.title}</p>
    {#if item.year}
      <p class="card__year">{item.year}</p>
    {/if}

    <div class="card__badges">
      <span class="badge" style="color:{mediaStatusColor};border-color:{mediaStatusColor}20;background:{mediaStatusColor}15">
        {item.mediaStatusLabel}
      </span>
    </div>

    <div class="card__ids">
      <span class="id-tag" class:id-tag--missing={!tmdbId} title="TMDB ID">
        TMDB {tmdbId ?? '✕'}
      </span>
      {#if tvdbId || isTV}
        <span class="id-tag" class:id-tag--missing={!tvdbId} class:id-tag--tvdb={!!tvdbId} title="TVDB ID">
          TVDB {tvdbId ?? '✕'}
        </span>
      {/if}
      {#if imdbId}
        <span class="id-tag id-tag--imdb" title="IMDB ID">{imdbId}</span>
      {/if}
    </div>
  </div>
</article>

<style>
  .card {
    background: #131720;
    border: 1.5px solid #1e293b;
    border-radius: 0.625rem;
    cursor: pointer;
    overflow: hidden;
    transition: border-color 0.15s, box-shadow 0.15s;
    display: flex;
    flex-direction: column;
    user-select: none;
  }
  .card:hover { border-color: #334155; box-shadow: 0 4px 20px rgba(0,0,0,0.35); }
  .card--selected { border-color: #6366f1; box-shadow: 0 0 0 1px #6366f1; }
  .card--flagged { border-color: #92400e; }
  .card--flagged.card--selected { border-color: #6366f1; }
  .card--orphan { border-style: dashed; }

  .card__poster {
    position: relative;
    aspect-ratio: 2/3;
    background: #0d1117;
    overflow: hidden;
  }
  .card__poster img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  .card__no-poster {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 2.5rem;
    color: #334155;
  }

  .card__check {
    position: absolute;
    top: 0.4rem;
    left: 0.4rem;
    cursor: pointer;
  }
  .card__check input { display: none; }
  .card__checkmark {
    display: block;
    width: 1.1rem;
    height: 1.1rem;
    border-radius: 0.25rem;
    border: 2px solid rgba(255,255,255,0.5);
    background: rgba(0,0,0,0.5);
    transition: all 0.15s;
  }
  .card__checkmark--checked {
    background: #6366f1;
    border-color: #6366f1;
  }
  .card__checkmark--checked::after {
    content: '✓';
    display: block;
    color: #fff;
    font-size: 0.7rem;
    text-align: center;
    line-height: 1.1rem;
  }

  .card__flag {
    position: absolute;
    top: 0.35rem;
    right: 0.35rem;
    color: #f59e0b;
    font-size: 0.85rem;
    text-shadow: 0 1px 3px rgba(0,0,0,0.8);
  }

  .card__type {
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
  .card__type--tv { background: rgba(139,92,246,0.85); }

  .card__body {
    padding: 0.5rem 0.5rem 0.6rem;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    flex: 1;
  }

  .card__title {
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
  .card__year {
    font-size: 0.65rem;
    color: #94a3b8;
    margin: 0;
  }

  .card__badges { display: flex; flex-wrap: wrap; gap: 0.25rem; }

  .badge {
    font-size: 0.55rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    padding: 0.1rem 0.3rem;
    border-radius: 0.25rem;
    border: 1px solid;
    white-space: nowrap;
  }

  .card__ids {
    display: flex;
    flex-wrap: wrap;
    gap: 0.2rem;
    margin-top: auto;
    padding-top: 0.2rem;
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
  .id-tag--imdb { background: #3b2800; color: #fbbf24; }
  .id-tag--missing { background: #3b0f0f; color: #f87171; }
</style>
