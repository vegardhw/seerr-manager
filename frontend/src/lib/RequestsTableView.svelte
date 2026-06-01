<script>
  import { createEventDispatcher, onDestroy } from 'svelte'

  export let items = []
  export let selected = new Set()

  const dispatch = createEventDispatcher()

  // ── Column definitions ────────────────────────────────────────────────────
  // Resizable columns only (the leading checkbox col is fixed).
  const COLS = [
    { key: 'title',  label: 'Title',        defaultW: 220 },
    { key: 'type',   label: 'Type',         defaultW: 90  },
    { key: 'status', label: 'Media Status', defaultW: 155 },
    { key: 'ids',    label: 'IDs',          defaultW: 210 },
    { key: 'user',   label: 'Requested by', defaultW: 130 },
    { key: 'date',   label: 'Created',      defaultW: 115 },
  ]
  const CHECK_W = 36   // px, fixed, non-resizable

  let colWidths = COLS.map((c) => c.defaultW)

  // ── Resize logic ──────────────────────────────────────────────────────────
  let resizing = null  // { idx, startX, startW }
  let isResizing = false

  function startResize(e, idx) {
    e.preventDefault()
    e.stopPropagation()
    resizing = { idx, startX: e.clientX, startW: colWidths[idx] }
    isResizing = true
    window.addEventListener('mousemove', doResize)
    window.addEventListener('mouseup', stopResize)
  }

  function doResize(e) {
    if (!resizing) return
    const delta = e.clientX - resizing.startX
    const nw = Math.max(50, resizing.startW + delta)
    colWidths = colWidths.map((w, i) => (i === resizing.idx ? nw : w))
  }

  function stopResize() {
    resizing = null
    isResizing = false
    window.removeEventListener('mousemove', doResize)
    window.removeEventListener('mouseup', stopResize)
  }

  onDestroy(() => {
    window.removeEventListener('mousemove', doResize)
    window.removeEventListener('mouseup', stopResize)
  })

  $: tableWidth = CHECK_W + colWidths.reduce((a, b) => a + b, 0)

  // ── Cell helpers ──────────────────────────────────────────────────────────
  const MEDIA_STATUS_COLOR = {
    UNKNOWN:             '#64748b',
    PENDING:             '#f59e0b',
    PROCESSING:          '#3b82f6',
    PARTIALLY_AVAILABLE: '#8b5cf6',
    AVAILABLE:           '#22c55e',
    DELETED:             '#ef4444',
  }

  function statusColor(label) {
    return MEDIA_STATUS_COLOR[label] ?? '#64748b'
  }

  function formatDate(dateStr) {
    if (!dateStr) return '—'
    return new Date(dateStr).toLocaleDateString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
    })
  }

  function handleCheck(e, key) {
    e.stopPropagation()
    dispatch('toggleSelect', key)
  }
</script>

{#if items.length === 0}
  <div class="empty">
    <span class="empty__icon">📭</span>
    <p>No requests match your filters.</p>
  </div>
{:else}
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="table-wrap" class:is-resizing={isResizing}>
    <table class="table" style="width:{tableWidth}px">
      <colgroup>
        <col style="width:{CHECK_W}px" />
        {#each colWidths as w}
          <col style="width:{w}px" />
        {/each}
      </colgroup>

      <thead>
        <tr>
          <!-- Fixed checkbox col — no resize handle -->
          <th class="th-check"></th>

          {#each COLS as col, i}
            <th style="width:{colWidths[i]}px">
              <span class="th-label">{col.label}</span>
              <!-- Don't put a handle on the very last column -->
              {#if i < COLS.length - 1}
                <span
                  class="resize-handle"
                  on:mousedown={(e) => startResize(e, i)}
                  title="Drag to resize"
                ></span>
              {/if}
            </th>
          {/each}
        </tr>
      </thead>

      <tbody>
        {#each items as item (item._key)}
          {@const sc = statusColor(item.mediaStatusLabel)}
          {@const isTV = item.type === 'tv'}
          <tr
            class="row"
            class:row--selected={selected.has(item._key)}
            class:row--flagged={item.flagged}
            class:row--orphan={item.orphan}
            on:click={() => dispatch('cardClick', item)}
            role="button"
            tabindex="0"
            aria-label={item.title}
            on:keydown={(e) => e.key === 'Enter' && dispatch('cardClick', item)}
          >
            <!-- Checkbox -->
            <td class="td-check" on:click|stopPropagation>
              <div
                class="checkmark"
                class:checkmark--checked={selected.has(item._key)}
                role="checkbox"
                aria-checked={selected.has(item._key)}
                tabindex="0"
                on:click={(e) => handleCheck(e, item._key)}
                on:keydown={(e) => { if (e.key === ' ') { e.preventDefault(); handleCheck(e, item._key) } }}
              ></div>
            </td>

            <!-- Title -->
            <td class="td-overflow">
              <div class="title-cell">
                <span class="title-text">{item.title}</span>
                <div class="title-meta">
                  {#if item.year}<span class="year">{item.year}</span>{/if}
                  {#if item.flagged}
                    <span class="flag-icon" title={item.flagReasons?.join('\n')}>⚑</span>
                  {/if}
                  {#if item.orphan}<span class="orphan-tag">ORPHAN</span>{/if}
                </div>
              </div>
            </td>

            <!-- Type -->
            <td>
              <span class="type-pill" class:type-pill--tv={isTV}>
                {isTV ? 'TV' : 'MOVIE'}
              </span>
            </td>

            <!-- Media status -->
            <td>
              <span
                class="status-pill"
                style="color:{sc};border-color:{sc}22;background:{sc}18"
              >
                {item.mediaStatusLabel}
              </span>
            </td>

            <!-- IDs -->
            <td class="td-overflow">
              <div class="id-group">
                <span class="id-tag" class:id-tag--missing={!item.media?.tmdbId} title="TMDB ID">
                  TMDB {item.media?.tmdbId ?? '✕'}
                </span>
                {#if item.media?.tvdbId || isTV}
                  <span
                    class="id-tag id-tag--tvdb"
                    class:id-tag--missing={!item.media?.tvdbId}
                    title="TVDB ID"
                  >TVDB {item.media?.tvdbId ?? '✕'}</span>
                {/if}
                {#if item.media?.imdbId}
                  <span class="id-tag id-tag--imdb" title="IMDB ID">{item.media.imdbId}</span>
                {/if}
              </div>
            </td>

            <!-- Requested by -->
            <td class="td-overflow">
              <span class="user-name">{item.requestedBy?.displayName ?? '—'}</span>
            </td>

            <!-- Created date -->
            <td>
              <span class="date-text">{formatDate(item.createdAt)}</span>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<style>
  .table-wrap {
    overflow-x: auto;
    padding: 0.625rem;
    -webkit-overflow-scrolling: touch;
  }
  /* Freeze cursor + kill text-select for the whole page while dragging */
  .table-wrap.is-resizing,
  .table-wrap.is-resizing * {
    cursor: col-resize !important;
    user-select: none !important;
  }

  .table {
    border-collapse: collapse;
    font-size: 0.8rem;
    table-layout: fixed;
  }

  thead tr {
    border-bottom: 1px solid #1e293b;
  }

  th {
    position: relative;
    padding: 0.45rem 0.75rem;
    text-align: left;
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: #a5b4fc;
    background: #0d1117;
    overflow: hidden;
    white-space: nowrap;
  }

  .th-check { width: 36px; padding-right: 0; }

  .th-label {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    /* leave room so the handle never overlaps the text */
    padding-right: 0.5rem;
  }

  /* ── Resize handle ── */
  .resize-handle {
    position: absolute;
    top: 0;
    right: 0;
    bottom: 0;
    width: 5px;
    cursor: col-resize;
    background: transparent;
    transition: background 0.15s;
    z-index: 1;
  }
  .resize-handle:hover,
  .is-resizing .resize-handle {
    background: #6366f1;
  }

  /* ── Rows ── */
  .row {
    border-bottom: 1px solid #1a2030;
    cursor: pointer;
    transition: background 0.1s;
  }
  .row:hover           { background: #131c2a; }
  .row--selected       { background: rgba(99,102,241,0.08); }
  .row--selected:hover { background: rgba(99,102,241,0.12); }
  .row--flagged td:first-child { border-left: 2px solid #92400e; }
  .row--orphan         { opacity: 0.85; }

  td {
    padding: 0.5rem 0.75rem;
    vertical-align: middle;
    color: #cbd5e1;
    overflow: hidden;
  }

  /* Cells that need text clipping */
  .td-overflow { overflow: hidden; }

  /* ── Checkbox ── */
  .td-check { padding-right: 0.25rem; }
  .checkmark {
    width: 1.05rem;
    height: 1.05rem;
    border-radius: 0.25rem;
    border: 2px solid #334155;
    background: transparent;
    cursor: pointer;
    transition: all 0.12s;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  .checkmark:hover { border-color: #6366f1; }
  .checkmark--checked { background: #6366f1; border-color: #6366f1; }
  .checkmark--checked::after {
    content: '✓';
    color: #fff;
    font-size: 0.65rem;
    line-height: 1;
  }

  /* ── Title cell ── */
  .title-cell {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    min-width: 0;
  }
  .title-text {
    font-size: 0.82rem;
    font-weight: 600;
    color: #e2e8f0;
    line-height: 1.3;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .title-meta {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    flex-wrap: wrap;
  }
  .year      { font-size: 0.7rem; color: #94a3b8; }
  .flag-icon { font-size: 0.72rem; color: #f59e0b; }
  .orphan-tag {
    font-size: 0.58rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    padding: 0.1rem 0.3rem;
    border-radius: 0.2rem;
    background: rgba(99,102,241,0.15);
    color: #a5b4fc;
    border: 1px solid rgba(99,102,241,0.25);
  }

  /* ── Type pill ── */
  .type-pill {
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    padding: 0.15rem 0.4rem;
    border-radius: 0.25rem;
    background: rgba(59,130,246,0.2);
    color: #60a5fa;
    white-space: nowrap;
  }
  .type-pill--tv { background: rgba(139,92,246,0.2); color: #a78bfa; }

  /* ── Status pill ── */
  .status-pill {
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    padding: 0.15rem 0.45rem;
    border-radius: 0.25rem;
    border: 1px solid;
    white-space: nowrap;
  }

  /* ── IDs ── */
  .id-group { display: flex; flex-wrap: wrap; gap: 0.2rem; }
  .id-tag {
    font-size: 0.58rem;
    font-weight: 600;
    padding: 0.1rem 0.3rem;
    border-radius: 0.2rem;
    background: #1e3a5f;
    color: #60a5fa;
    white-space: nowrap;
  }
  .id-tag--tvdb    { background: #2d1a4a; color: #a78bfa; }
  .id-tag--imdb    { background: #3b2800; color: #fbbf24; }
  .id-tag--missing { background: #3b0f0f; color: #f87171; }

  /* ── User / Date ── */
  .user-name {
    font-size: 0.75rem;
    color: #b0bec5;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    display: block;
  }
  .date-text {
    font-size: 0.72rem;
    color: #94a3b8;
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
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
  }
  .empty__icon { font-size: 3rem; }
  .empty p     { font-size: 0.9rem; margin: 0; }
</style>
