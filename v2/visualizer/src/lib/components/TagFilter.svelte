<script lang="ts">
  let {
    tags = $bindable(new Set<string>()),
    allTags = [] as string[],
    tagFreq = new Map<string, number>()
  }: {
    tags?: Set<string>;
    allTags?: string[];
    tagFreq?: Map<string, number>;
  } = $props();

  let tagInput = $state('');
  let tagInputFocused = $state(false);

  const tagSuggestions = $derived(
    tagInput.trim().length > 0
      ? allTags.filter(t => t.toLowerCase().includes(tagInput.toLowerCase()) && !tags.has(t)).slice(0, 8)
      : allTags.filter(t => !tags.has(t)).slice(0, 8)
  );

  function addTag(tag: string) {
    const next = new Set(tags);
    next.add(tag);
    tags = next;
    tagInput = '';
  }
</script>

<div class="relative">
  <input
    bind:value={tagInput}
    onfocus={() => tagInputFocused = true}
    onblur={() => setTimeout(() => tagInputFocused = false, 150)}
    type="text"
    placeholder="Filter by tag…"
    class="text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 w-36 bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 placeholder:text-gray-600 dark:placeholder:text-gray-400 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 dark:focus:ring-primary-900"
  />
  {#if tagInputFocused && tagSuggestions.length > 0}
    <div class="absolute z-20 top-full mt-1 left-0 w-48 bg-ui-card border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg overflow-hidden">
      {#each tagSuggestions as tag}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div
          onmousedown={(e) => { e.preventDefault(); addTag(tag); }}
          class="px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer flex items-center justify-between"
        >
          <span>{tag}</span>
          <span class="text-xs text-gray-400">{tagFreq.get(tag)}</span>
        </div>
      {/each}
    </div>
  {/if}
</div>
