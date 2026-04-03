<script lang="ts">
  let {
    variant = 'primary',
    label = 'Connect',
  }: {
    variant?: 'primary' | 'on-dark';
    label?: string;
  } = $props();
</script>

{#if variant === 'on-dark'}
  <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold bg-white/20 text-white border border-white/30 flex-shrink-0">
    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
    </svg>
    {label}
  </span>
{:else}
  <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-primary-100 text-primary-600 dark:bg-primary-900/40 dark:text-primary-300 flex-shrink-0">
    <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
    </svg>
    {label}
  </span>
{/if}
