<script lang="ts">
  import { getContext, onMount } from 'svelte';
  import { page } from '$app/stores';
  import Fuse from 'fuse.js';
  import type { QuestionStore } from '$lib/stores/questionStore';
  import type { Question, QuestionFilters, SortOption } from '$lib/types';
  import QuestionCard from '$lib/components/QuestionCard.svelte';
  import SearchInput from '$lib/components/SearchInput.svelte';
  import FiltersToggleButton from '$lib/components/FiltersToggleButton.svelte';
  import TagFilter from '$lib/components/TagFilter.svelte';
  import TopicFilter from '$lib/components/TopicFilter.svelte';
  import ActiveFilterChips from '$lib/components/ActiveFilterChips.svelte';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import { tagFrequency } from '$lib/utils/tags';

  const store = getContext<QuestionStore>('store');
  const tzCtx = getContext<{ value: string }>('timezone');

  let searchQuery = $state('');
  let filterAsker = $state('');
  let filterSolver = $state('');
  let filterDateFrom = $state('');
  let filterDateTo = $state('');
  let filterHasMedia = $state(false as boolean | undefined);
  let filterSessionId = $state('');
  let filterTags = $state(new Set<string>());
  let filterTopics = $state(new Set<string>());

  $effect(() => {
    const p = $page.url.searchParams;
    searchQuery = p.get('q') ?? '';
    filterAsker = p.get('asker') ?? '';
    filterSolver = p.get('solver') ?? '';
    filterDateFrom = p.get('dateFrom') ?? '';
    filterDateTo = p.get('dateTo') ?? '';
    const hm = p.get('has_media');
    filterHasMedia = hm === '0' ? false : hm === '1' ? true : undefined as boolean | undefined;
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

  let showMoreFilters = $state(false);
  let mobileFiltersOpen = $state(false);
  let sortBy = $state<SortOption>('newest');
  let revealAll = $state(false);

  const activeFilterCount = $derived(
    [filterAsker, filterSolver, filterSessionId].filter(Boolean).length +
    (filterHasMedia !== undefined ? 1 : 0) +
    ((filterDateFrom || filterDateTo) ? 1 : 0) +
    filterTags.size + filterTopics.size +
    (sortBy !== 'newest' ? 1 : 0)
  );

  const askers = store.getAskers();
  const solvers = store.getSolvers();
  const allSessions = store.getSessions();

  const allQuestions = store.getQuestions();
  const { tagFreq, allTags } = tagFrequency(allQuestions);

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
    if (filterDateFrom || filterDateTo) filters.tz = tzCtx?.value;
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

  function clearFilters() {
    searchQuery = '';
    filterAsker = '';
    filterSolver = '';
    filterDateFrom = '';
    filterDateTo = '';
    filterHasMedia = false;
    filterSessionId = '';
    filterTags = new Set();
    filterTopics = new Set();
  }

  const hasActiveFilters = $derived(
    searchQuery || filterAsker || filterSolver ||
    filterDateFrom || filterDateTo || filterHasMedia !== undefined ||
    filterSessionId || filterTags.size > 0 || filterTopics.size > 0
  );

  const MOBILE_PAGE_SIZE = 8;
  let isMobile = $state(false);
  let mobileLimit = $state(MOBILE_PAGE_SIZE);

  onMount(() => {
    const mq = window.matchMedia('(max-width: 1023px)');
    isMobile = mq.matches;
    mq.addEventListener('change', e => { isMobile = e.matches; });
  });

  // Reset mobile limit and revealAll when filters change
  $effect(() => {
    // touch all filter deps
    searchQuery; filterAsker; filterSolver; filterDateFrom; filterDateTo;
    filterHasMedia; filterSessionId; filterTags; filterTopics;
    mobileLimit = MOBILE_PAGE_SIZE;
    revealAll = false;
  });

  let questionsAtBottom = $state(false);
  function onQuestionsScroll(e: Event) {
    const el = e.currentTarget as HTMLElement;
    questionsAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 8;
  }

  const selectCls = "flex-1 basis-[calc(50%-4px)] lg:flex-none lg:w-[129px] text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 dark:focus:ring-primary-900 text-gray-600";
  const filterSizeCls = "flex-1 basis-[calc(50%-4px)] lg:flex-none lg:w-[129px]";
  const filterBtnCls = "flex-none text-sm border rounded-lg px-3 py-1.5 leading-5 transition-colors inline-flex items-center gap-1.5 justify-center whitespace-nowrap";
</script>

<div class="space-y-6">
  <!-- Search + Filters -->
  <div class="space-y-3">
    <!-- Search bar + mobile filters toggle -->
    <div class="flex gap-2">
      <SearchInput bind:value={searchQuery} placeholder="Search questions and answers…" />
      <FiltersToggleButton bind:open={mobileFiltersOpen} count={activeFilterCount} />
      <button
        onclick={() => revealAll = !revealAll}
        class="flex-none px-4 py-2 text-sm font-medium rounded-xl border transition-colors {revealAll ? 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 border-gray-200 dark:border-gray-600 hover:bg-gray-200 dark:hover:bg-gray-600' : 'bg-primary-500 text-white border-primary-500 hover:bg-primary-600 dark:bg-primary-600 dark:border-primary-600'}"
      >
        {revealAll ? 'Hide all' : 'Reveal all'}
      </button>
    </div>

    <!-- Primary filters — shown when filters open -->
    {#if mobileFiltersOpen}
    <div class="space-y-2">
      <!-- Row 1: main filters -->
      <div class="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
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

        <div class="col-span-2 sm:col-auto sm:flex-none inline-flex rounded-lg border border-gray-200 dark:border-gray-600 overflow-hidden text-sm">
          {#each ([undefined, true, false] as const) as val, i}
            <button
              onclick={() => filterHasMedia = val}
              class="flex-1 sm:flex-none px-2.5 py-1.5 leading-5 whitespace-nowrap transition-colors
                {filterHasMedia === val ? 'bg-primary-500 text-white' : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'}
                {i > 0 ? 'border-l border-gray-200 dark:border-gray-600' : ''}"
            >{val === undefined ? 'All' : val ? 'Media' : 'No Media'}</button>
          {/each}
        </div>

        <button
          onclick={() => showMoreFilters = !showMoreFilters}
          class="col-span-2 sm:col-auto sm:w-auto {filterBtnCls} {showMoreFilters ? 'bg-primary-500 border-primary-500 text-white' : 'border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'}"
        >
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
          Date range
        </button>
      </div>

      <!-- Row 2: tag + topic filters -->
      <div class="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
        <TagFilter bind:tags={filterTags} {allTags} {tagFreq} class={filterSizeCls} />
        <TopicFilter bind:topics={filterTopics} class={selectCls} />
      </div>
    </div>
    {/if}

    <!-- Date range filter -->
    {#if showMoreFilters && mobileFiltersOpen}
      <div class="flex flex-wrap gap-2 p-3 bg-ui-inset rounded-xl border border-stone-200/80 dark:border-zinc-700/80">
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

    <ActiveFilterChips bind:tags={filterTags} bind:topics={filterTopics} hasFilters={!!hasActiveFilters} onClear={clearFilters} />
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
  {#if !questionsAtBottom && filteredQuestions.length > 0}
    <div class="hidden lg:block pointer-events-none absolute inset-x-0 bottom-0 h-50 bg-gradient-to-t from-gray-50 dark:from-gray-900 to-transparent z-10 transition-opacity duration-300"></div>
  {/if}
  <div class="lg:max-h-[92vh] lg:overflow-y-auto space-y-4 pr-1 scrollbar-hide" onscroll={onQuestionsScroll}>
    {#if filteredQuestions.length === 0}
      <EmptyState message="No questions match your filters" onClear={clearFilters} />
    {:else}
      {#each (isMobile ? filteredQuestions.slice(0, mobileLimit) : filteredQuestions) as question (question.id)}
        <QuestionCard {question} hideSession={!!filterSessionId} {revealAll} />
      {/each}
      {#if isMobile && mobileLimit < filteredQuestions.length}
        <button
          onclick={() => mobileLimit += MOBILE_PAGE_SIZE}
          class="w-full py-3 text-sm font-medium text-primary-600 dark:text-primary-400 border border-primary-200 dark:border-primary-800 rounded-xl hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors"
        >
          Show more ({filteredQuestions.length - mobileLimit} remaining)
        </button>
      {/if}
    {/if}
  </div>
  </div>
</div>
