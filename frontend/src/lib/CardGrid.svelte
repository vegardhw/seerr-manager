<script>
  import { createEventDispatcher } from 'svelte'
  import MediaCard from './MediaCard.svelte'

  export let items = []
  export let selected = new Set()

  const dispatch = createEventDispatcher()
</script>

{#if items.length === 0}
  <div class="empty">
    <span class="empty__icon">📭</span>
    <p>No requests match your filters.</p>
  </div>
{:else}
  <div class="grid">
    {#each items as item (item._key)}
      <MediaCard
        {item}
        selected={selected.has(item._key)}
        on:click={(e) => dispatch('cardClick', e.detail)}
        on:toggleSelect={(e) => dispatch('toggleSelect', e.detail)}
      />
    {/each}
  </div>
{/if}

<style>
  .grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0.5rem;
    padding: 0.625rem;
  }

  @media (min-width: 540px) {
    .grid { grid-template-columns: repeat(4, 1fr); }
  }
  @media (min-width: 768px) {
    .grid { grid-template-columns: repeat(5, 1fr); gap: 0.75rem; padding: 0.875rem; }
  }
  @media (min-width: 1200px) {
    .grid { grid-template-columns: repeat(6, 1fr); }
  }
  @media (min-width: 1600px) {
    .grid { grid-template-columns: repeat(7, 1fr); }
  }

  .empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    padding: 4rem 1rem;
    color: #475569;
  }
  .empty__icon { font-size: 3rem; }
  .empty p { font-size: 0.9rem; margin: 0; }
</style>
