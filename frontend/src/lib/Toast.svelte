<script>
  export let toasts = []

  export function addToast(message, type = 'info', duration = 4000) {
    const id = Date.now() + Math.random()
    toasts = [...toasts, { id, message, type }]
    if (duration > 0) {
      setTimeout(() => removeToast(id), duration)
    }
    return id
  }

  export function removeToast(id) {
    toasts = toasts.filter((t) => t.id !== id)
  }
</script>

<div class="toast-container">
  {#each toasts as toast (toast.id)}
    <div class="toast toast--{toast.type}" role="alert">
      <span class="toast__icon">
        {#if toast.type === 'success'}✓{:else if toast.type === 'error'}✕{:else if toast.type === 'loading'}⟳{:else}ℹ{/if}
      </span>
      <span class="toast__msg">{toast.message}</span>
      <button class="toast__close" on:click={() => removeToast(toast.id)}>×</button>
    </div>
  {/each}
</div>

<style>
  .toast-container {
    position: fixed;
    bottom: 1.25rem;
    right: 1.25rem;
    left: 1.25rem;
    z-index: 9999;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    pointer-events: none;
  }

  @media (min-width: 480px) {
    .toast-container {
      left: auto;
      max-width: 22rem;
    }
  }

  .toast {
    display: flex;
    align-items: center;
    gap: 0.625rem;
    padding: 0.75rem 1rem;
    border-radius: 0.5rem;
    font-size: 0.875rem;
    font-weight: 500;
    pointer-events: all;
    animation: slide-up 0.2s ease;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
  }

  @keyframes slide-up {
    from { transform: translateY(0.5rem); opacity: 0; }
    to   { transform: translateY(0);      opacity: 1; }
  }

  .toast--info    { background: #1e293b; color: #94a3b8; border-left: 3px solid #6366f1; }
  .toast--success { background: #14231a; color: #4ade80; border-left: 3px solid #22c55e; }
  .toast--error   { background: #2a1010; color: #f87171; border-left: 3px solid #ef4444; }
  .toast--loading { background: #1e293b; color: #93c5fd; border-left: 3px solid #3b82f6; }

  .toast__icon { font-size: 1rem; flex-shrink: 0; }
  .toast__msg  { flex: 1; line-height: 1.3; }

  .toast__close {
    background: none;
    border: none;
    color: inherit;
    cursor: pointer;
    font-size: 1.1rem;
    opacity: 0.6;
    padding: 0;
    line-height: 1;
    flex-shrink: 0;
  }
  .toast__close:hover { opacity: 1; }
</style>
