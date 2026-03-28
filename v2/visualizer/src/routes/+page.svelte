<script lang="ts">
  import { getContext } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import Fuse from 'fuse.js';
  import type { QuestionStore } from '$lib/stores/questionStore';
  import type { Question, QuestionFilters, SortOption } from '$lib/types';
  import QuestionCard from '$lib/components/QuestionCard.svelte';
  import { formatDate } from '$lib/utils/time';
  import { TOPICS } from '$lib/utils/topicColors';

  const store = getContext<QuestionStore>('store');
  const stats = store.getTotalStats();

  let searchQuery = $state('');
  let filterAsker = $state('');
  let filterSolver = $state('');
  let filterDateFrom = $state('');
  let filterDateTo = $state('');
  let filterHasMedia = $state(undefined as boolean | undefined);
  let filterSessionId = $state('');
  let filterTags = $state(new Set<string>());
  let filterTopics = $state(new Set<string>());

  // Tag combobox state
  let tagInput = $state('');
  let tagInputFocused = $state(false);

  $effect(() => {
    const p = $page.url.searchParams;
    searchQuery = p.get('q') ?? '';
    filterAsker = p.get('asker') ?? '';
    filterSolver = p.get('solver') ?? '';
    filterDateFrom = p.get('dateFrom') ?? '';
    filterDateTo = p.get('dateTo') ?? '';
    filterHasMedia = p.get('has_media') === '0' ? false : undefined as boolean | undefined;
    filterSessionId = p.get('session') ?? '';
    // ?tag=X from detail page tag clicks (single), or ?tags=X,Y for multi
    const singleTag = p.get('tag') ?? '';
    const multiTags = p.get('tags') ?? '';
    const rawTags = multiTags || singleTag;
    filterTags = new Set(rawTags.split(',').filter(Boolean));
    // Topics
    const single = p.get('topic') ?? '';
    const multi = p.get('topics') ?? '';
    const raw = multi || single;
    filterTopics = new Set(raw.split(',').filter(Boolean));
  });

  function toggleTopic(id: string) {
    const next = new Set(filterTopics);
    if (next.has(id)) next.delete(id); else next.add(id);
    filterTopics = next;
  }

  function addTag(tag: string) {
    const next = new Set(filterTags);
    next.add(tag);
    filterTags = next;
    tagInput = '';
  }

  function removeTag(tag: string) {
    const next = new Set(filterTags);
    next.delete(tag);
    filterTags = next;
  }

  let showMoreFilters = $state(false);
  let sortBy = $state<SortOption>('newest');

  const askers = store.getAskers();
  const solvers = store.getSolvers();
  const allSessions = store.getSessions();

  const allQuestions = store.getQuestions();

  // Tags sorted by frequency
  const tagFreq = new Map<string, number>();
  for (const q of allQuestions) {
    for (const tag of q.question.tags ?? []) {
      tagFreq.set(tag, (tagFreq.get(tag) ?? 0) + 1);
    }
  }
  const allTags = [...tagFreq.entries()].sort((a, b) => b[1] - a[1]).map(([t]) => t);

  // Live tag suggestions
  const tagSuggestions = $derived(
    tagInput.trim().length > 0
      ? allTags.filter(t => t.toLowerCase().includes(tagInput.toLowerCase()) && !filterTags.has(t)).slice(0, 8)
      : allTags.filter(t => !filterTags.has(t)).slice(0, 8)
  );

  const fuse = new Fuse(allQuestions, {
    keys: [
      { name: 'question.text', weight: 0.7 },
      { name: 'answer.text', weight: 0.3 },
      { name: 'question.asker', weight: 0.1 },
    ],
    threshold: 0.4,
    includeScore: true,
  });

  const filteredQuestions = $derived.by(() => {
    const filters: QuestionFilters = {};
    if (filterAsker) filters.asker = filterAsker;
    if (filterSolver) filters.solver = filterSolver;
    if (filterDateFrom) filters.dateFrom = filterDateFrom;
    if (filterDateTo) filters.dateTo = filterDateTo;
    if (filterHasMedia !== undefined) filters.has_media = filterHasMedia;
    if (filterSessionId) filters.session_id = filterSessionId;

    let results = store.getQuestions(filters, sortBy);

    if (filterTags.size > 0) {
      results = results.filter(q => [...filterTags].every(tag => q.question.tags?.includes(tag)));
    }

    if (filterTopics.size > 0) {
      results = results.filter(q => q.question.topics?.some(t => filterTopics.has(t)));
    }

    if (searchQuery.trim()) {
      const fuseResults = fuse.search(searchQuery.trim());
      const matchedIds = new Set(fuseResults.map(r => r.item.id));
      results = results.filter(q => matchedIds.has(q.id));
      if (sortBy === 'newest') {
        const scoreMap = new Map(fuseResults.map(r => [r.item.id, r.score ?? 1]));
        results = results.sort((a, b) => (scoreMap.get(a.id) ?? 1) - (scoreMap.get(b.id) ?? 1));
      }
    }

    return results;
  });

  function surpriseMe() {
    const q = store.random();
    if (q) goto(`/question/${q.id}`);
  }

  function clearFilters() {
    searchQuery = '';
    filterAsker = '';
    filterSolver = '';
    filterDateFrom = '';
    filterDateTo = '';
    filterHasMedia = undefined;
    filterSessionId = '';
    filterTags = new Set();
    filterTopics = new Set();
    tagInput = '';
  }

  const hasActiveFilters = $derived(
    searchQuery || filterAsker || filterSolver ||
    filterDateFrom || filterDateTo || filterHasMedia !== undefined ||
    filterSessionId || filterTags.size > 0 || filterTopics.size > 0
  );

  const sinceDate = stats.earliestDate ? formatDate(stats.earliestDate) : '';
  const selectCls = "flex-1 min-w-[7rem] sm:flex-none sm:w-34 text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 dark:focus:ring-primary-900 text-gray-600";
  const filterBtnCls = "flex-1 min-w-[7rem] sm:flex-none sm:w-34 text-sm border rounded-lg px-3 py-1.5 leading-5 transition-colors inline-flex items-center gap-1.5 justify-center";
</script>

<div class="space-y-6">
  <!-- Hero -->
  <div class="bg-gradient-to-br from-primary-500 to-primary-600 rounded-2xl p-6 text-white shadow-lg relative">
    {#if sinceDate}
      <div class="absolute top-4 right-4 flex items-center gap-1.5 text-xs text-primary-100">
        <span class="relative flex h-2.5 w-2.5">
          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-300 opacity-90"></span>
          <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-green-400"></span>
        </span>
        since {sinceDate}
      </div>
    {/if}
    <h1 class="text-2xl font-bold mb-1">All Questions</h1>
    <p class="text-primary-100 text-sm mb-4">Every question the group ever asked. Right here.</p>
    <div class="flex items-center justify-between gap-3">
      <div class="flex flex-wrap gap-x-4 gap-y-1 text-sm">
        <span class="font-semibold">{stats.total} total questions</span>
        <span class="text-primary-200 hidden sm:inline">·</span>
        <a href="/sessions" class="font-semibold hover:text-primary-100 transition-colors cursor-pointer">{stats.sessions} quiz sessions</a>
      </div>
      <button
        onclick={surpriseMe}
        class="flex-shrink-0 inline-flex items-center gap-1.5 px-4 py-2 bg-white hover:bg-primary-50 text-primary-600 dark:bg-slate-700 dark:hover:bg-slate-600 dark:text-white font-semibold text-sm rounded-lg transition-colors shadow-sm cursor-pointer"
      >
        <svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" /></svg>
        <span class="hidden sm:inline">Random question</span>
      </button>
    </div>
  </div>

  <!-- Search + Filters -->
  <div class="space-y-3">
    <!-- Search bar -->
    <div class="relative">
      <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
      </svg>
      <input
        bind:value={searchQuery}
        type="text"
        placeholder="Search questions and answers…"
        class="w-full pl-9 pr-4 py-2.5 text-sm border border-gray-200 dark:border-gray-600 rounded-xl focus:outline-none focus:border-primary-400 focus:ring-2 focus:ring-primary-100 dark:focus:ring-primary-900 bg-white dark:bg-gray-700 dark:text-gray-200 dark:placeholder-gray-400 shadow-sm transition-all"
      />
      {#if searchQuery}
        <button
          onclick={() => searchQuery = ''}
          aria-label="Clear search"
          class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      {/if}
    </div>

    <!-- Primary filters -->
    <div class="flex flex-wrap gap-2">
      <select bind:value={filterAsker} class={selectCls}>
        <option value="">All askers</option>
        {#each askers as asker}
          <option value={asker}>{asker}</option>
        {/each}
      </select>

      <select bind:value={filterSolver} class={selectCls}>
        <option value="">All solvers</option>
        {#each solvers as solver}
          <option value={solver}>{solver}</option>
        {/each}
      </select>

      <select bind:value={sortBy} class={selectCls}>
        <option value="newest">Newest first</option>
        <option value="oldest">Oldest first</option>
        <option value="most_discussed">Most discussed</option>
        <option value="quickest">Quickest solve</option>
      </select>

      <select bind:value={filterSessionId} class={selectCls}>
        <option value="">All sessions</option>
        {#each allSessions as s}
          <option value={s.id}>{s.theme ?? `${s.quizmaster}'s Quiz`}</option>
        {/each}
      </select>

      <button
        onclick={() => filterHasMedia = filterHasMedia === false ? undefined : false}
        class="{filterBtnCls} {filterHasMedia === false ? 'bg-primary-500 border-primary-500 text-white' : 'border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'}"
      >
        No attachments
      </button>

      <button
        onclick={() => showMoreFilters = !showMoreFilters}
        class="{filterBtnCls} {showMoreFilters ? 'bg-primary-500 border-primary-500 text-white' : 'border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'}"
      >
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
        Date range
      </button>
    </div>

    <!-- Tag + Topic filters -->
    <div class="flex flex-wrap items-center gap-2">
      <!-- Tag combobox -->
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
          <div class="absolute z-20 top-full mt-1 left-0 w-48 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg overflow-hidden">
            {#each tagSuggestions as tag}
              <!-- svelte-ignore a11y_click_events_have_key_events -->
              <!-- svelte-ignore a11y_no_static_element_interactions -->
              <div
                onclick={() => addTag(tag)}
                class="px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer flex items-center justify-between"
              >
                <span>{tag}</span>
                <span class="text-xs text-gray-400">{tagFreq.get(tag)}</span>
              </div>
            {/each}
          </div>
        {/if}
      </div>

      <!-- Active tag chips -->
      {#each [...filterTags] as tag}
        <span class="inline-flex items-center gap-1 pl-3 pr-1.5 py-1 rounded-full text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 ring-2 ring-gray-300 dark:ring-gray-500">
          #{tag}
          <button
            onclick={() => removeTag(tag)}
            class="ml-0.5 rounded-full p-0.5 opacity-80 hover:opacity-100 transition-opacity"
            aria-label="Remove {tag} filter"
          >
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </span>
      {/each}

      <!-- Topic filter -->
      <select
        value=""
        onchange={(e) => { const v = (e.target as HTMLSelectElement).value; if (v) toggleTopic(v); (e.target as HTMLSelectElement).value = ''; }}
        class="text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 dark:focus:ring-primary-900 text-gray-600"
      >
        <option value="">Filter by topic…</option>
        {#each TOPICS as t}
          {#if !filterTopics.has(t.id)}
            <option value={t.id}>{t.label}</option>
          {/if}
        {/each}
      </select>

      {#each TOPICS.filter(t => filterTopics.has(t.id)) as t}
        <span class="inline-flex items-center gap-1 pl-3 pr-1.5 py-1 rounded-full text-xs font-medium ring-2 {t.cls} {t.ring}">
          {t.label}
          <button
            onclick={() => toggleTopic(t.id)}
            class="ml-0.5 rounded-full p-0.5 opacity-80 hover:opacity-100 transition-opacity"
            aria-label="Remove {t.label} filter"
          >
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </span>
      {/each}

      {#if hasActiveFilters}
        <button
          onclick={clearFilters}
          class="text-sm text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300 px-2 py-1 transition-colors"
        >
          Clear all
        </button>
      {/if}
    </div>

    <!-- Date range filter -->
    {#if showMoreFilters}
      <div class="flex flex-wrap gap-2 p-3 bg-gray-50 dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
        <div class="flex items-center gap-2">
          <label for="filter-date-from" class="text-xs text-gray-500 dark:text-gray-400 font-medium">From</label>
          <input
            id="filter-date-from"
            bind:value={filterDateFrom}
            type="date"
            class="text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400"
          />
        </div>
        <div class="flex items-center gap-2">
          <label for="filter-date-to" class="text-xs text-gray-500 dark:text-gray-400 font-medium">To</label>
          <input
            id="filter-date-to"
            bind:value={filterDateTo}
            type="date"
            class="text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400"
          />
        </div>
      </div>
    {/if}
  </div>

  <!-- Results count -->
  <div class="flex items-center justify-between">
    <p class="text-sm text-gray-500 dark:text-gray-400">
      {filteredQuestions.length} question{filteredQuestions.length !== 1 ? 's' : ''}
      {#if hasActiveFilters}<span class="text-primary-500 dark:text-primary-400 font-medium"> (filtered)</span>{/if}
    </p>
  </div>

  <!-- Question cards -->
  <div class="relative">
  <div class="pointer-events-none absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-gray-50 dark:from-gray-900 to-transparent z-10"></div>
  <div class="max-h-[80vh] overflow-y-auto space-y-4 pr-1 scrollbar-hide">
    {#each filteredQuestions as question (question.id)}
      <QuestionCard {question} hideSession={!!filterSessionId} />
    {:else}
      <div class="text-center py-16 text-gray-400">
        <div class="text-4xl mb-3">🔍</div>
        <p class="font-medium">No questions match your filters</p>
        <button onclick={clearFilters} class="mt-2 text-sm text-primary-500 dark:text-primary-400 hover:text-primary-600 dark:hover:text-primary-300">
          Clear filters
        </button>
      </div>
    {/each}
  </div>
  </div>
</div>
