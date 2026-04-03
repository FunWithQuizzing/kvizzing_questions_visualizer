<script lang="ts">
  import { TOPICS } from '$lib/utils/topicColors';

  let {
    tags = $bindable(new Set<string>()),
    topics = $bindable(new Set<string>()),
    hasFilters = false,
    onClear
  }: {
    tags?: Set<string>;
    topics?: Set<string>;
    hasFilters?: boolean;
    onClear?: () => void;
  } = $props();

  function removeTag(tag: string) {
    const next = new Set(tags);
    next.delete(tag);
    tags = next;
  }

  function removeTopic(id: string) {
    const next = new Set(topics);
    next.delete(id);
    topics = next;
  }
</script>

{#if tags.size > 0 || topics.size > 0 || hasFilters}
  <div class="flex flex-wrap items-center gap-2">
    {#each [...tags] as tag}
      <span class="inline-flex items-center gap-1 pl-3 pr-1.5 py-1 rounded-full text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 ring-2 ring-gray-300 dark:ring-gray-500">
        #{tag}
        <button onclick={() => removeTag(tag)} class="ml-0.5 rounded-full p-0.5 opacity-80 hover:opacity-100 transition-opacity" aria-label="Remove {tag} filter">
          <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
        </button>
      </span>
    {/each}
    {#each TOPICS.filter(t => topics.has(t.id)) as t}
      <span class="inline-flex items-center gap-1 pl-3 pr-1.5 py-1 rounded-full text-xs font-medium ring-2 {t.cls} {t.ring}">
        {t.label}
        <button onclick={() => removeTopic(t.id)} class="ml-0.5 rounded-full p-0.5 opacity-80 hover:opacity-100 transition-opacity" aria-label="Remove {t.label} filter">
          <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12" /></svg>
        </button>
      </span>
    {/each}
    {#if hasFilters}
      <button onclick={onClear} class="text-sm text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300 px-2 py-1 transition-colors">Clear all</button>
    {/if}
  </div>
{/if}
