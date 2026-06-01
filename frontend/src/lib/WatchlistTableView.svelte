<script>
  import { createEventDispatcher, onDestroy } from 'svelte'

  export let items = []
  export let selected = new Set()
  /** Only show checkbox in the 'watchlist_only' column */
  export let selectable = false

  const dispatch = createEventDispatcher()

  // ── Column definitions ────────────────────────────────────────────────────
  const COLS = [
    { key: 'title',  label: 'Title',   defaultW: 260 },
    { key: 'type',   label: 'Type',    defaultW: 90  },
    { key: 'status', label: 'Status',  defaultW: 155 },
    { key: 'id',     label: 'TMDB ID', defaultW: 120 },
  ]
  const CHECK_W = 36

  let colWidths = COLS.map((c) => c.defaultW)

  // ── Resize logic ──────────────────────────────────────────────────────────
  let resizing = null
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

  $: tableWidth = (selectable ? CHECK_W : 0) + colWidths.reduce((a, b) => a + b, 0)

  // ── Status helpers ────────────────────────────────────────────────────────
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

  function resolveStatus(item) {
    const ms = (item.mediaStatus && item.mediaStatus !== 'UNKNOWN') ? item.mediaStatus : null
    return {
      label: ms || item.requestStatus || null,
      color: ms
        ? (MEDIA_STATUS_COLOR[ms] ?? '#64748b')
        : (REQUEST_STATUS_COLOR[item.requestStatus] ?? '#64748b'),
    }
  }

  function handleCheck(e, tmdbId) {
    e.stopPropagation()
    dispatch('toggleSelect', tmdbId)
  }
</script>

{#if items.length === 0}
  <div class="empty">
    <span class="empty__icon">📭</span>
    <p>No items match your filters.</p>
  </div>
{:else}
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="table-wrap" class:is-resizing={isResizing}>
    <table class="table" style="width:{tableWidth}px">
      <colgroup>
        {#if selectable}<col style="width:{CHECK_W}px" />{/if}
        {#each colWidths as w}
          <col style="width:{w}px" />
        {/each}
      </colgroup>

      <thead>
        <tr>
          {#if selectable}<th class="th-check"></th>{/if}

          {#each COLS as col, i}
            <th style="width:{colWidths[i]}px">
              <span class="th-label">{col.label}</span>
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
        {#each items as item (item.tmdbId)}
          {@const { label, color } = resolveStatus(item)}
          {@const isTV = item.type === 'tv'}
          <tr
            class="row"
            class:row--selected={selected.has(item.tmdbId)}
            class:row--selectable={selectable}
            on:click={() => selectable && dispatch('toggleSelect', item.tmdbId)}
          >
            {#if selectable}
              <td class="td-check" on:click|stopPropagation>
                <div
                  class="checkmark"
                  class:checkmark--checked={selected.has(item.tmdbId)}
                  role="checkbox"
                  aria-checked={selected.has(item.tmdbId)}
                  tabindex="0"
                  on:click={(e) => handleCheck(e, item.tmdbId)}
                  on:keydown={(e) => { if (e.key === ' ') { e.preventDefault(); handleCheck(e, item.tmdbId) } }}
                ></div>
              </td>
            {/if}

            <!-- Title + year -->
            <td class="td-overflow">
              <div class="title-cell">
                <span class="title-text">{item.title}</span>
                {#if item.year}<span class="year">{item.year}</span>{/if}
              </div>
            </td>

            <!-- Type -->
            <td>
              <span class="type-pill" class:type-pill--tv={isTV}>
                {isTV ? 'TV' : 'MOVIE'}
              </span>
            </td>

            <!-- Status -->
            <td>
              {#if label}
                <span
                  class="status-pill"
                  style="color:{color};border-color:{color}22;background:{color}18"
                >
                  {label}
                </span>
              {:else}
                <span class="no-status">—</span>
              {/if}
            </td>

            <!-- TMDB ID -->
            <td>
              <span class="id-tag">TMDB {item.tmdbId}</span>
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

  thead tr { border-bottom: 1px solid #1e293b; }

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
  .row { border-bottom: 1px solid #1a2030; transition: background 0.1s; }
  .row--selectable { cursor: pointer; }
  .row--selectable:hover { background: #131c2a; }
  .row--selected       { background: rgba(99,102,241,0.08); }
  .row--selected:hover { background: rgba(99,102,241,0.12); }

  td {
    padding: 0.5rem 0.75rem;
    vertical-align: middle;
    color: #cbd5e1;
    overflow: hidden;
  }

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
  }
  .checkmark:hover { border-color: #6366f1; }
  .checkmark--checked { background: #6366f1; border-color: #6366f1; }
  .checkmark--checked::after {
    content: '✓';
    color: #fff;
    font-size: 0.65rem;
    line-height: 1;
  }

  /* ── Title ── */
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
  .year { font-size: 0.7rem; color: #94a3b8; }

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
  .no-status { color: #64748b; }

  /* ── ID tag ── */
  .id-tag {
    font-size: 0.6rem;
    font-weight: 600;
    padding: 0.1rem 0.3rem;
    border-radius: 0.2rem;
    background: #1e3a5f;
    color: #60a5fa;
    white-space: nowrap;
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
