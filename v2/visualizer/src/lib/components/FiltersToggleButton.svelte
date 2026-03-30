<script lang="ts">
  let { open = $bindable(false), count = 0 }: { open?: boolean; count?: number } = $props();
</script>

<button
  onclick={() => open = !open}
  class="lg:hidden relative flex-none inline-flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium rounded-xl border transition-colors
    {open || count > 0
      ? 'bg-primary-500 border-primary-500 text-white'
      : 'bg-white dark:bg-gray-700 border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-200'}"
>
  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2a1 1 0 01-.293.707L13 13.414V19a1 1 0 01-.553.894l-4 2A1 1 0 017 21v-7.586L3.293 6.707A1 1 0 013 6V4z" />
  </svg>
  Filters
  {#if count > 0}
    <span class="inline-flex items-center justify-center w-4 h-4 text-[10px] font-bold rounded-full bg-white text-primary-600">{count}</span>
  {/if}
</button>
