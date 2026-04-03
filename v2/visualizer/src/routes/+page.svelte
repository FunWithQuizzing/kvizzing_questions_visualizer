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
  import SearchableSelect from '$lib/components/SearchableSelect.svelte';
  import { tagFrequency } from '$lib/utils/tags';
  import { dateInTz, formatDateTz } from '$lib/utils/time';

  const store = getContext<QuestionStore>('store');
  const tzCtx = getContext<{ value: string }>('timezone');

  let searchQuery = $state('');
  let filterAsker = $state('');
  let filterSolver = $state('');
  let filterDateFrom = $state('');
  let filterDateTo = $state('');
  let filterMedia = $state<'all' | 'media' | 'no_media'>('all');
  let filterParts = $state<'all' | 'multi' | 'single'>('all');
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
    filterMedia = hm === '0' ? 'no_media' : hm === '1' ? 'media' : 'all';
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
  let feedStates = $state<Record<string, { revealed: boolean; input: string; result: 'correct' | 'almost' | 'wrong' | null; hintsShown: number }>>(
    Object.fromEntries(
      store.getQuestions().map((q: Question) => [q.id, { revealed: false, input: '', result: null as 'correct' | 'almost' | 'wrong' | null, hintsShown: 0 }])
    )
  );

  const activeFilterCount = $derived(
    [filterAsker, filterSolver, filterSessionId].filter(Boolean).length +
    (filterMedia !== 'all' ? 1 : 0) +
    (filterParts !== 'all' ? 1 : 0) +
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
    if (filterMedia === 'media') filters.has_media = true;
    else if (filterMedia === 'no_media') filters.has_media = false;
    if (filterSessionId) filters.session_id = filterSessionId;

    let results = store.getQuestions(filters, sortBy);

    if (filterTags.size > 0) {
      results = results.filter(q => [...filterTags].every(tag => q.question.tags?.includes(tag)));
    }

    if (filterTopics.size > 0) {
      results = results.filter(q => q.question.topics?.some(t => filterTopics.has(t)));
    }

    if (filterParts === 'multi') {
      results = results.filter(q => q.answer?.parts && q.answer.parts.length > 1);
    } else if (filterParts === 'single') {
      results = results.filter(q => !q.answer?.parts || q.answer.parts.length <= 1);
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

  // Group questions by date for timeline display
  const questionsByDate = $derived.by(() => {
    const tz = tzCtx?.value ?? 'Europe/London';
    const groups: { date: string; displayDate: string; questions: typeof filteredQuestions }[] = [];
    const map = new Map<string, typeof filteredQuestions>();
    for (const q of filteredQuestions) {
      const d = dateInTz(q.question?.timestamp ?? q.date, tz);
      if (!map.has(d)) map.set(d, []);
      map.get(d)!.push(q);
    }
    for (const [date, questions] of map) {
      groups.push({ date, displayDate: formatDateTz(date, tz), questions });
    }
    return groups;
  });

  function clearFilters() {
    searchQuery = '';
    filterAsker = '';
    filterSolver = '';
    filterDateFrom = '';
    filterDateTo = '';
    filterMedia = 'all';
    filterParts = 'all';
    filterSessionId = '';
    filterTags = new Set();
    filterTopics = new Set();
  }

  const hasActiveFilters = $derived(
    searchQuery || filterAsker || filterSolver ||
    filterDateFrom || filterDateTo || filterMedia !== 'all' || filterParts !== 'all' ||
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
    filterMedia; filterParts; filterSessionId; filterTags; filterTopics;
    mobileLimit = MOBILE_PAGE_SIZE;
    revealAll = false;
  });

  let questionsAtBottom = $state(true);
  let questionsScrollEl = $state<HTMLElement | null>(null);
  function onQuestionsScroll(e: Event) {
    const el = e.currentTarget as HTMLElement;
    questionsAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 8;
  }
  // Check overflow after content renders
  $effect(() => {
    filteredQuestions;
    if (questionsScrollEl) {
      requestAnimationFrame(() => {
        if (questionsScrollEl) {
          questionsAtBottom = questionsScrollEl.scrollHeight - questionsScrollEl.scrollTop - questionsScrollEl.clientHeight < 8;
        }
      });
    }
  });

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
        onclick={() => {
          revealAll = !revealAll;
          filteredQuestions.forEach(q => {
            feedStates[q.id].revealed = revealAll;
          });
        }}
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
        <SearchableSelect
          bind:value={filterAsker}
          options={askers.map(a => ({ value: a, label: a }))}
          placeholder="All askers"
          class={filterSizeCls}
        />

        <SearchableSelect
          bind:value={filterSolver}
          options={solvers.map(s => ({ value: s, label: s }))}
          placeholder="All solvers"
          class={filterSizeCls}
        />

        <SearchableSelect
          bind:value={sortBy}
          options={[
            { value: 'newest', label: 'Newest first' },
            { value: 'oldest', label: 'Oldest first' },
            { value: 'most_discussed', label: 'Most discussed' },
            { value: 'quickest', label: 'Quickest solve' },
          ]}
          placeholder="Newest first"
          class={filterSizeCls}
        />

        <SearchableSelect
          bind:value={filterSessionId}
          options={allSessions.map(s => ({ value: s.id, label: s.theme ?? `${s.quizmaster}'s Quiz` }))}
          placeholder="All sessions"
          class={filterSizeCls}
        />

        <div class="col-span-1 sm:col-auto sm:flex-none inline-flex rounded-lg border border-gray-200 dark:border-gray-600 overflow-hidden text-sm">
          <button
            onclick={() => filterMedia = filterMedia === 'media' ? 'all' : 'media'}
            class="flex-1 sm:flex-none px-2.5 py-1.5 leading-5 whitespace-nowrap transition-colors
              {filterMedia === 'media' ? 'bg-primary-500 text-white' : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'}"
          >Media</button>
          <button
            onclick={() => filterMedia = filterMedia === 'no_media' ? 'all' : 'no_media'}
            class="flex-1 sm:flex-none px-2.5 py-1.5 leading-5 whitespace-nowrap transition-colors border-l border-gray-200 dark:border-gray-600
              {filterMedia === 'no_media' ? 'bg-primary-500 text-white' : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'}"
          >No Media</button>
        </div>
        <div class="col-span-1 sm:col-auto sm:flex-none inline-flex rounded-lg border border-gray-200 dark:border-gray-600 overflow-hidden text-sm">
          <button
            onclick={() => filterParts = filterParts === 'multi' ? 'all' : 'multi'}
            class="flex-1 sm:flex-none px-2.5 py-1.5 leading-5 whitespace-nowrap transition-colors
              {filterParts === 'multi' ? 'bg-primary-500 text-white' : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'}"
          >Multi-part</button>
          <button
            onclick={() => filterParts = filterParts === 'single' ? 'all' : 'single'}
            class="flex-1 sm:flex-none px-2.5 py-1.5 leading-5 whitespace-nowrap transition-colors border-l border-gray-200 dark:border-gray-600
              {filterParts === 'single' ? 'bg-primary-500 text-white' : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'}"
          >Single-part</button>
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
        {#if showMoreFilters}
          <div class="col-span-1 sm:col-auto sm:flex-none flex items-center gap-1.5">
            <label for="filter-date-from" class="text-sm text-gray-600 dark:text-gray-300 font-medium">From</label>
            <input id="filter-date-from" bind:value={filterDateFrom} type="date" class="text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 leading-5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400" />
          </div>
          <div class="col-span-1 sm:col-auto sm:flex-none flex items-center gap-1.5">
            <label for="filter-date-to" class="text-sm text-gray-600 dark:text-gray-300 font-medium">To</label>
            <input id="filter-date-to" bind:value={filterDateTo} type="date" class="text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 leading-5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400" />
          </div>
        {/if}
      </div>

      <!-- Row 2: tag + topic filters -->
      <div class="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
        <TagFilter bind:tags={filterTags} {allTags} {tagFreq} class={filterSizeCls} />
        <TopicFilter bind:topics={filterTopics} class={selectCls} />
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
  <div class="lg:max-h-[92vh] lg:overflow-y-auto space-y-4 pr-1 scrollbar-hide" bind:this={questionsScrollEl} onscroll={onQuestionsScroll}>
    {#if filteredQuestions.length === 0}
      <EmptyState message="No questions match your filters" onClear={clearFilters} />
    {:else}
      {#each questionsByDate as group, gi}
        {@const visibleQuestions = isMobile ? group.questions.filter(q => filteredQuestions.indexOf(q) < mobileLimit) : group.questions}
        {#if visibleQuestions.length > 0}
        <div class="relative pl-7">
          <!-- Timeline vertical line -->
          <div class="absolute left-[6px] top-[22px] bottom-3 w-[3px] rounded-full bg-primary-200 dark:bg-primary-800/60"></div>
          <!-- Date header with dot -->
          <div class="flex items-center gap-3 {gi > 0 ? 'pt-2' : ''}">
            <div class="absolute left-0 w-3.5 h-3.5 rounded-full bg-primary-500 dark:bg-primary-400 border-[3px] border-white dark:border-gray-900 shadow-sm z-10"></div>
            <span class="text-sm font-semibold text-gray-900 dark:text-gray-100">{group.displayDate}</span>
            <span class="text-xs text-gray-400 dark:text-gray-500">{visibleQuestions.length} question{visibleQuestions.length !== 1 ? 's' : ''}</span>
            <div class="flex-1 border-t border-gray-200 dark:border-gray-700"></div>
          </div>
          <!-- Questions for this date -->
          <div class="space-y-4 mt-3">
            {#each visibleQuestions as question (question.id)}
                {@const state = feedStates[question.id] ??= { revealed: false, input: '', result: null, hintsShown: 0 }}
                <QuestionCard
                  {question}
                  hideSession={!!filterSessionId}
                  bind:revealed={state.revealed}
                  bind:input={state.input}
                  bind:result={state.result}
                  bind:hintsShown={state.hintsShown}
                />
            {/each}
          </div>
        </div>
        {/if}
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
