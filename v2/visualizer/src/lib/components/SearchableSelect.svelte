<script lang="ts">
  let {
    value = $bindable(''),
    options,
    placeholder = 'All',
    class: cls = '',
  }: {
    value?: string;
    options: { value: string; label: string }[];
    placeholder?: string;
    class?: string;
  } = $props();

  let open = $state(false);
  let search = $state('');
  let containerEl = $state<HTMLElement | null>(null);

  const filtered = $derived(
    search.trim()
      ? options.filter(o => o.label.toLowerCase().includes(search.trim().toLowerCase()))
      : options
  );

  const displayLabel = $derived(
    value ? (options.find(o => o.value === value)?.label ?? value) : placeholder
  );

  function select(val: string) {
    value = val;
    open = false;
    search = '';
  }

  function handleClickOutside(e: MouseEvent) {
    if (containerEl && !containerEl.contains(e.target as Node)) {
      open = false;
      search = '';
    }
  }
</script>

<svelte:document onclick={handleClickOutside} />

<div class="relative {cls}" bind:this={containerEl}>
  <button
    onclick={() => { open = !open; if (!open) search = ''; }}
    class="w-full text-left text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 dark:focus:ring-primary-900 text-gray-600 flex items-center justify-between gap-1"
  >
    <span class="truncate {value ? 'text-gray-900 dark:text-gray-100' : ''}">{displayLabel}</span>
    <svg class="w-3.5 h-3.5 flex-shrink-0 text-gray-400 transition-transform {open ? 'rotate-180' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
    </svg>
  </button>

  {#if open}
    <div class="absolute z-50 top-full mt-1 w-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg overflow-hidden">
      <div class="px-2 py-1.5 border-b border-gray-100 dark:border-gray-700">
        <input
          bind:value={search}
          type="text"
          placeholder="Search…"
          class="w-full text-xs px-2 py-1 border border-gray-200 dark:border-gray-600 rounded bg-gray-50 dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400"
          autofocus
        />
      </div>
      <div class="max-h-48 overflow-y-auto">
        <button
          onclick={() => select('')}
          class="w-full text-left px-3 py-1.5 text-xs hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors {!value ? 'text-primary-600 dark:text-primary-400 font-medium' : 'text-gray-500 dark:text-gray-400'}"
        >{placeholder}</button>
        {#each filtered as opt}
          <button
            onclick={() => select(opt.value)}
            class="w-full text-left px-3 py-1.5 text-xs hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors {value === opt.value ? 'text-primary-600 dark:text-primary-400 font-medium bg-primary-50 dark:bg-primary-900/20' : 'text-gray-700 dark:text-gray-300'}"
          >{opt.label}</button>
        {/each}
        {#if filtered.length === 0}
          <p class="px-3 py-2 text-xs text-gray-400">No matches</p>
        {/if}
      </div>
    </div>
  {/if}
</div>
