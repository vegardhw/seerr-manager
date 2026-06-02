<script>
  import { createEventDispatcher, onDestroy } from 'svelte'

  export let items = []
  export let selected = new Set()
  export let selectable = false

  const dispatch = createEventDispatcher()

  // ── Column definitions ────────────────────────────────────────────────────
  const COLS = [
    { key: 'title',   label: 'Title',   defaultW: 240 },
    { key: 'type',    label: 'Type',    defaultW: 80  },
    { key: 'source',  label: 'Source',  defaultW: 100 },
    { key: 'year',    label: 'Year',    defaultW: 70  },
    { key: 'file',    label: 'File',    defaultW: 80  },
    { key: 'size',    label: 'Size',    defaultW: 90  },
    { key: 'status',  label: 'Status',  defaultW: 160 },
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
    colWidths = colWidths.map((w, i) => (i === resizing.idx ? Math.max(50, resizing.startW + delta) : w))
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

  // ── Helpers ───────────────────────────────────────────────────────────────
  const SOURCE_COLOR = {
    radarr: '#f59e0b',
    sonarr: '#10b981',
  }

  const SEERR_STATUS_COLOR = {
    UNKNOWN:             '#64748b',
    PENDING:             '#f59e0b',
    PROCESSING:          '#3b82f6',
    PARTIALLY_AVAILABLE: '#8b5cf6',
    AVAILABLE:           '#22c55e',
    DELETED:             '#ef4444',
  }

  function formatSize(bytes) {
    if (!bytes) return '—'
    if (bytes >= 1099511627776) return (bytes / 1099511627776).toFixed(1) + ' TB'
    if (bytes >= 1073741824)    return (bytes / 1073741824).toFixed(1) + ' GB'
    if (bytes >= 1048576)       return (bytes / 1048576).toFixed(0) + ' MB'
    return bytes + ' B'
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
        {#each items as item (item.tmdbId ?? item.libraryId)}
          {@const isTV = item.type === 'tv'}
          {@const srcColor = SOURCE_COLOR[item.source] ?? '#94a3b8'}
          {@const sc = SEERR_STATUS_COLOR[item.seerrMediaStatus] ?? '#64748b'}
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

            <!-- Source -->
            <td>
              <span
                class="source-pill"
                style="color:{srcColor};background:{srcColor}18;border-color:{srcColor}25"
              >
                {item.source?.toUpperCase() ?? '—'}
              </span>
            </td>

            <!-- Year -->
            <td><span class="muted">{item.year ?? '—'}</span></td>

            <!-- Has file -->
            <td>
              {#if item.hasFile}
                <span class="file-yes" title="File present">✓</span>
              {:else}
                <span class="file-no" title="No file on disk">✗</span>
              {/if}
            </td>

            <!-- Size -->
            <td><span class="muted">{formatSize(item.sizeOnDisk)}</span></td>

            <!-- Seerr status -->
            <td>
              {#if item.seerrMediaStatus}
                <span
                  class="status-pill"
                  style="color:{sc};border-color:{sc}22;background:{sc}18"
                >{item.seerrMediaStatus}</span>
              {:else}
                <span class="muted">—</span>
              {/if}
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
  .table-wrap.is-resizing * { cursor: col-resize !important; user-select: none !important; }

  .table { border-collapse: collapse; font-size: 0.8rem; table-layout: fixed; }
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

  .resize-handle {
    position: absolute;
    top: 0; right: 0; bottom: 0;
    width: 5px;
    cursor: col-resize;
    background: transparent;
    transition: background 0.15s;
    z-index: 1;
  }
  .resize-handle:hover, .is-resizing .resize-handle { background: #6366f1; }

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
  .td-check { padding-right: 0.25rem; }

  .checkmark {
    width: 1.05rem; height: 1.05rem;
    border-radius: 0.25rem;
    border: 2px solid #334155;
    background: transparent;
    cursor: pointer;
    transition: all 0.12s;
    display: flex; align-items: center; justify-content: center;
  }
  .checkmark:hover { border-color: #6366f1; }
  .checkmark--checked { background: #6366f1; border-color: #6366f1; }
  .checkmark--checked::after { content: '✓'; color: #fff; font-size: 0.65rem; line-height: 1; }

  .title-cell { display: flex; flex-direction: column; gap: 0.2rem; min-width: 0; }
  .title-text {
    font-size: 0.82rem; font-weight: 600; color: #e2e8f0;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .year { font-size: 0.7rem; color: #94a3b8; }

  .type-pill {
    font-size: 0.6rem; font-weight: 700; letter-spacing: 0.05em;
    padding: 0.15rem 0.4rem; border-radius: 0.25rem;
    background: rgba(59,130,246,0.2); color: #60a5fa;
  }
  .type-pill--tv { background: rgba(139,92,246,0.2); color: #a78bfa; }

  .source-pill {
    font-size: 0.6rem; font-weight: 800; letter-spacing: 0.05em;
    padding: 0.15rem 0.4rem; border-radius: 0.25rem; border: 1px solid;
  }

  .status-pill {
    font-size: 0.62rem; font-weight: 700; letter-spacing: 0.04em;
    padding: 0.15rem 0.45rem; border-radius: 0.25rem; border: 1px solid;
    white-space: nowrap;
  }

  .file-yes { color: #22c55e; font-weight: 700; font-size: 0.85rem; }
  .file-no  { color: #475569; font-weight: 700; font-size: 0.85rem; }
  .muted    { color: #64748b; }

  .empty {
    display: flex; flex-direction: column; align-items: center;
    justify-content: center; gap: 0.75rem; padding: 4rem 1rem; color: #64748b;
  }
  .empty__icon { font-size: 3rem; }
  .empty p { font-size: 0.9rem; margin: 0; }
</style>
