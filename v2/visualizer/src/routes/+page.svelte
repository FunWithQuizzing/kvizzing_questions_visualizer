<script lang="ts">
  import { getContext, onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
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
  let filterSaved = $state(false);

  const savedIds = getContext<{ value: Set<string> } | undefined>('savedIds');

  let _lastUrl = '';
  $effect(() => {
    const url = $page.url.href;
    if (url === _lastUrl) return;
    _lastUrl = url;
    const p = $page.url.searchParams;
    searchQuery = p.get('q') ?? '';
    filterAsker = p.get('asker') ?? '';
    filterSolver = p.get('solver') ?? '';
    filterDateFrom = p.get('dateFrom') ?? '';
    filterDateTo = p.get('dateTo') ?? '';
    const hm = p.get('has_media');
    filterMedia = hm === '0' ? 'no_media' : hm === '1' ? 'media' : 'all';
    filterSessionId = p.get('session') ?? '';
    filterSaved = p.get('saved') === '1';
    if (filterSaved) mobileFiltersOpen = true;
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

  // Save counts for "Most liked" sort
  let saveCounts = $state(new Map<string, number>());
  onMount(async () => {
    try {
      const { supabase } = await import('$lib/supabase');
      const { data } = await supabase.from('question_saves').select('question_id');
      if (data) {
        const counts = new Map<string, number>();
        for (const row of data) {
          counts.set(row.question_id, (counts.get(row.question_id) ?? 0) + 1);
        }
        saveCounts = counts;
      }
    } catch {}
  });
  let revealAll = $state(false);
  type FeedState = { revealed: boolean; input: string; result: 'correct' | 'almost' | 'wrong' | null; hintsShown: number };
  const _defaultFeedState = (): FeedState => ({ revealed: false, input: '', result: null, hintsShown: 0 });

  const askers = store.getAskers();
  const solvers = store.getSolvers();
  const allSessions = store.getSessions();
  const allQuestions = store.getQuestions();

  // Build feed states eagerly, then let $state wrap the populated object
  let feedStates = $state<Record<string, FeedState>>(
    Object.fromEntries(allQuestions.map(q => [q.id, _defaultFeedState()]))
  );
  function fs(id: string): FeedState {
    return feedStates[id];
  }

  const activeFilterCount = $derived(
    [filterAsker, filterSolver, filterSessionId].filter(Boolean).length +
    (filterMedia !== 'all' ? 1 : 0) +
    (filterParts !== 'all' ? 1 : 0) +
    ((filterDateFrom || filterDateTo) ? 1 : 0) +
    filterTags.size + filterTopics.size +
    (filterSaved ? 1 : 0)
  );
  const { tagFreq, allTags } = store.getTagFreq();

  // Pre-sort once per sort option (avoid re-sorting on every filter change)
  const sortedCache = new Map<string, Question[]>();
  function getSorted(sort: SortOption): Question[] {
    if (!sortedCache.has(sort)) {
      sortedCache.set(sort, store.getQuestions(undefined, sort));
    }
    return sortedCache.get(sort)!;
  }

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
    let results = getSorted(sortBy);

    if (filterAsker) results = results.filter(q => q.question.asker === filterAsker);
    if (filterSolver) results = results.filter(q => q.answer?.solver === filterSolver);
    if (filterDateFrom || filterDateTo) {
      const tz = tzCtx?.value;
      results = results.filter(q => {
        const d = tz && q.question?.timestamp ? dateInTz(q.question.timestamp, tz) : q.date;
        if (filterDateFrom && d < filterDateFrom) return false;
        if (filterDateTo && d > filterDateTo) return false;
        return true;
      });
    }
    if (filterMedia === 'media') results = results.filter(q => q.question.has_media);
    else if (filterMedia === 'no_media') results = results.filter(q => !q.question.has_media);

    if (filterSessionId === '__none__') {
      results = results.filter(q => !q.session);
    } else if (filterSessionId === '__session__') {
      results = results.filter(q => q.session);
    } else if (filterSessionId) {
      results = results.filter(q => q.session?.id === filterSessionId);
    }

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

    if (filterSaved && savedIds?.value) {
      results = results.filter(q => savedIds.value.has(q.id));
    }

    if (sortBy === 'most_liked' && saveCounts.size > 0) {
      results = [...results].sort((a, b) => (saveCounts.get(b.id) ?? 0) - (saveCounts.get(a.id) ?? 0));
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
    filterSaved = false;
    if ($page.url.searchParams.has('saved')) {
      const u = new URL(window.location.href); u.searchParams.delete('saved'); history.replaceState({}, '', u);
    }
  }

  const hasActiveFilters = $derived(
    searchQuery || filterAsker || filterSolver ||
    filterDateFrom || filterDateTo || filterMedia !== 'all' || filterParts !== 'all' ||
    filterSessionId || filterTags.size > 0 || filterTopics.size > 0
  );

  const MOBILE_PAGE_SIZE = 8;
  const DESKTOP_PAGE_SIZE = 30;
  let isMobile = $state(false);
  let renderLimit = $state(DESKTOP_PAGE_SIZE);

  onMount(() => {
    const mq = window.matchMedia('(max-width: 1023px)');
    isMobile = mq.matches;
    renderLimit = mq.matches ? MOBILE_PAGE_SIZE : DESKTOP_PAGE_SIZE;
    mq.addEventListener('change', e => {
      isMobile = e.matches;
      renderLimit = e.matches ? MOBILE_PAGE_SIZE : DESKTOP_PAGE_SIZE;
    });
  });

  // Reset mobile limit and revealAll when filters change
  $effect(() => {
    // touch all filter deps
    searchQuery; filterAsker; filterSolver; filterDateFrom; filterDateTo;
    filterMedia; filterParts; filterSessionId; filterTags; filterTopics;
    renderLimit = isMobile ? MOBILE_PAGE_SIZE : DESKTOP_PAGE_SIZE;
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

  const selectCls = "w-[calc(50%-4px)] sm:w-auto sm:min-w-[120px] lg:w-[130px] text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 dark:focus:ring-primary-900 text-gray-600";
  const filterSizeCls = "w-[calc(50%-4px)] sm:w-auto sm:min-w-[120px] lg:w-[130px]";
  const filterBtnCls = "flex-none text-sm border rounded-lg px-3 py-1.5 leading-5 transition-colors inline-flex items-center gap-1.5 justify-center whitespace-nowrap";
  let showSortMenu = $state(false);
  let sortContainerEl = $state<HTMLElement>();

  const sortOptions: { value: SortOption; label: string }[] = [
    { value: 'newest', label: 'Newest first' },
    { value: 'oldest', label: 'Oldest first' },
    { value: 'most_discussed', label: 'Most discussed' },
    { value: 'most_liked', label: 'Most liked' },
  ];
  const sortLabel = $derived(sortOptions.find(o => o.value === sortBy)?.label ?? 'Sort');
</script>

<div class="space-y-6">
  <!-- Search + Filters -->
  <div class="space-y-3">
    <!-- Search bar + mobile filters toggle -->
    <div class="flex items-center gap-2">
      <SearchInput bind:value={searchQuery} placeholder="Search questions and answers…" />
      <FiltersToggleButton bind:open={mobileFiltersOpen} count={activeFilterCount} />
      <!-- Sort dropdown -->
      <div class="relative" bind:this={sortContainerEl}>
        <button
          onclick={() => showSortMenu = !showSortMenu}
          class="flex-none px-3 py-2.5 text-sm font-medium rounded-xl border transition-colors inline-flex items-center gap-1.5 {sortBy !== 'newest' ? 'bg-primary-500 text-white border-primary-500' : 'border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'}"
        >
          <svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4h13M3 8h9M3 12h5m0 0l4 4m-4-4l4-4" />
          </svg>
          <span class="hidden sm:inline">Sort</span>
        </button>
        {#if showSortMenu}
          <!-- svelte-ignore a11y_click_events_have_key_events -->
          <div class="fixed inset-0 z-40" role="presentation" onclick={() => showSortMenu = false}></div>
          <div class="absolute right-0 top-full mt-1 z-50 bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 py-1 w-44">
            {#each sortOptions as opt}
              <button
                onclick={() => { sortBy = opt.value; showSortMenu = false; }}
                class="w-full text-left px-3 py-2 text-sm transition-colors {sortBy === opt.value ? 'text-primary-600 dark:text-primary-400 bg-primary-50 dark:bg-primary-900/20 font-medium' : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'}"
              >{opt.label}</button>
            {/each}
          </div>
        {/if}
      </div>
      <button
        onclick={() => {
          revealAll = !revealAll;
          filteredQuestions.forEach(q => {
            fs(q.id).revealed = revealAll;
          });
        }}
        class="flex-none px-3 py-2.5 text-sm font-medium rounded-xl border transition-colors inline-flex items-center gap-1.5 {revealAll ? 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 border-gray-200 dark:border-gray-600 hover:bg-gray-200 dark:hover:bg-gray-600' : 'bg-primary-500 text-white border-primary-500 hover:bg-primary-600 dark:bg-primary-600 dark:border-primary-600'}"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          {#if revealAll}
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
          {:else}
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
          {/if}
        </svg>
        <span class="hidden sm:inline">{revealAll ? 'Hide all' : 'Reveal all'}</span>
      </button>
    </div>

    <!-- Primary filters — shown when filters open -->
    {#if mobileFiltersOpen}
    <div class="space-y-2">
      <!-- ═══ Desktop: single flex-wrap row ═══ -->
      <div class="hidden lg:flex lg:flex-wrap lg:gap-2">
        <SearchableSelect bind:value={filterAsker} options={askers.map(a => ({ value: a, label: a }))} placeholder="All askers" class="w-[130px]" />
        <SearchableSelect bind:value={filterSolver} options={solvers.map(s => ({ value: s, label: s }))} placeholder="All solvers" class="w-[130px]" />
        <div class="inline-flex rounded-lg border border-gray-200 dark:border-gray-600 overflow-hidden text-sm">
          <button onclick={() => filterSessionId = filterSessionId === '__session__' ? '' : '__session__'} class="px-2.5 py-1.5 leading-5 whitespace-nowrap transition-colors {filterSessionId === '__session__' ? 'bg-primary-500 text-white' : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'}">Session</button>
          <button onclick={() => filterSessionId = filterSessionId === '__none__' ? '' : '__none__'} class="px-2.5 py-1.5 leading-5 whitespace-nowrap transition-colors border-l border-gray-200 dark:border-gray-600 {filterSessionId === '__none__' ? 'bg-primary-500 text-white' : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'}">Non-session</button>
        </div>
        <div class="inline-flex rounded-lg border border-gray-200 dark:border-gray-600 overflow-hidden text-sm">
          <button onclick={() => filterMedia = filterMedia === 'media' ? 'all' : 'media'} class="px-2.5 py-1.5 leading-5 whitespace-nowrap transition-colors {filterMedia === 'media' ? 'bg-primary-500 text-white' : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'}">Media</button>
          <button onclick={() => filterMedia = filterMedia === 'no_media' ? 'all' : 'no_media'} class="px-2.5 py-1.5 leading-5 whitespace-nowrap transition-colors border-l border-gray-200 dark:border-gray-600 {filterMedia === 'no_media' ? 'bg-primary-500 text-white' : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'}">No Media</button>
        </div>
        <div class="inline-flex rounded-lg border border-gray-200 dark:border-gray-600 overflow-hidden text-sm">
          <button onclick={() => filterParts = filterParts === 'multi' ? 'all' : 'multi'} class="px-2.5 py-1.5 leading-5 whitespace-nowrap transition-colors {filterParts === 'multi' ? 'bg-primary-500 text-white' : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'}">Multi-part</button>
          <button onclick={() => filterParts = filterParts === 'single' ? 'all' : 'single'} class="px-2.5 py-1.5 leading-5 whitespace-nowrap transition-colors border-l border-gray-200 dark:border-gray-600 {filterParts === 'single' ? 'bg-primary-500 text-white' : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'}">Single-part</button>
        </div>
        <button onclick={() => { filterSaved = !filterSaved; if (!filterSaved && $page.url.searchParams.has('saved')) { const u = new URL(window.location.href); u.searchParams.delete('saved'); history.replaceState({}, '', u); } }} class="inline-flex items-center gap-1.5 rounded-lg border text-sm px-2.5 py-1.5 leading-5 whitespace-nowrap transition-colors {filterSaved ? 'bg-primary-500 text-white border-primary-500' : 'border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'}">
          <svg class="w-3.5 h-3.5" fill={filterSaved ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" /></svg>
          Saved
        </button>
      </div>
      <!-- Desktop row 2: tags, topics, date range -->
      <div class="hidden lg:flex lg:flex-wrap lg:gap-2">
        <TagFilter bind:tags={filterTags} {allTags} {tagFreq} class="w-[130px]" />
        <TopicFilter bind:topics={filterTopics} class="w-[130px]" />
        <button onclick={() => showMoreFilters = !showMoreFilters} class="{filterBtnCls} {showMoreFilters || filterDateFrom || filterDateTo ? 'bg-primary-500 border-primary-500 text-white' : 'border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'}">
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
          Date range
        </button>
        {#if showMoreFilters}
          <div class="flex items-center gap-1.5">
            <label for="filter-date-from-d" class="text-sm text-gray-600 dark:text-gray-300 font-medium">From</label>
            <input id="filter-date-from-d" bind:value={filterDateFrom} type="date" class="text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 leading-5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400" />
          </div>
          <div class="flex items-center gap-1.5">
            <label for="filter-date-to-d" class="text-sm text-gray-600 dark:text-gray-300 font-medium">To</label>
            <input id="filter-date-to-d" bind:value={filterDateTo} type="date" class="text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 leading-5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400" />
          </div>
        {/if}
      </div>

      <!-- ═══ Mobile: explicit rows ═══ -->
      <div class="lg:hidden space-y-1.5">
        <!-- Line 1: askers + solvers -->
        <div class="flex gap-1.5">
          <SearchableSelect bind:value={filterAsker} options={askers.map(a => ({ value: a, label: a }))} placeholder="All askers" class="flex-1" />
          <SearchableSelect bind:value={filterSolver} options={solvers.map(s => ({ value: s, label: s }))} placeholder="All solvers" class="flex-1" />
        </div>
        <!-- Line 2: session + media -->
        <div class="flex gap-1.5">
          <div class="flex-1 inline-flex rounded-lg border border-gray-200 dark:border-gray-600 overflow-hidden text-sm">
            <button onclick={() => filterSessionId = filterSessionId === '__session__' ? '' : '__session__'} class="flex-1 px-2 py-1.5 leading-5 whitespace-nowrap transition-colors {filterSessionId === '__session__' ? 'bg-primary-500 text-white' : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200'}">Session</button>
            <button onclick={() => filterSessionId = filterSessionId === '__none__' ? '' : '__none__'} class="flex-1 px-2 py-1.5 leading-5 whitespace-nowrap transition-colors border-l border-gray-200 dark:border-gray-600 {filterSessionId === '__none__' ? 'bg-primary-500 text-white' : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200'}">Non-session</button>
          </div>
          <div class="flex-1 inline-flex rounded-lg border border-gray-200 dark:border-gray-600 overflow-hidden text-sm">
            <button onclick={() => filterMedia = filterMedia === 'media' ? 'all' : 'media'} class="flex-1 px-2 py-1.5 leading-5 whitespace-nowrap transition-colors {filterMedia === 'media' ? 'bg-primary-500 text-white' : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200'}">Media</button>
            <button onclick={() => filterMedia = filterMedia === 'no_media' ? 'all' : 'no_media'} class="flex-1 px-2 py-1.5 leading-5 whitespace-nowrap transition-colors border-l border-gray-200 dark:border-gray-600 {filterMedia === 'no_media' ? 'bg-primary-500 text-white' : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200'}">No Media</button>
          </div>
        </div>
        <!-- Line 3: multi-part + saved + date range -->
        <div class="flex gap-1.5">
          <div class="flex-1 inline-flex rounded-lg border border-gray-200 dark:border-gray-600 overflow-hidden text-sm">
            <button onclick={() => filterParts = filterParts === 'multi' ? 'all' : 'multi'} class="flex-1 px-2 py-1.5 leading-5 whitespace-nowrap transition-colors {filterParts === 'multi' ? 'bg-primary-500 text-white' : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200'}">Multi-part</button>
            <button onclick={() => filterParts = filterParts === 'single' ? 'all' : 'single'} class="flex-1 px-2 py-1.5 leading-5 whitespace-nowrap transition-colors border-l border-gray-200 dark:border-gray-600 {filterParts === 'single' ? 'bg-primary-500 text-white' : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200'}">Single-part</button>
          </div>
          <button onclick={() => filterSaved = !filterSaved} class="inline-flex items-center gap-1 rounded-lg border text-sm px-2.5 py-1.5 leading-5 whitespace-nowrap transition-colors {filterSaved ? 'bg-primary-500 text-white border-primary-500' : 'border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200'}">
            <svg class="w-3.5 h-3.5" fill={filterSaved ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" /></svg>
            Saved
          </button>
          <button onclick={() => showMoreFilters = !showMoreFilters} class="{filterBtnCls} {showMoreFilters || filterDateFrom || filterDateTo ? 'bg-primary-500 border-primary-500 text-white' : 'border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200'}">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>
            Date
          </button>
        </div>
        {#if showMoreFilters}
          <div class="flex gap-1.5">
            <div class="flex-1 flex items-center gap-1.5">
              <label for="filter-date-from-m" class="text-sm text-gray-600 dark:text-gray-300 font-medium">From</label>
              <input id="filter-date-from-m" bind:value={filterDateFrom} type="date" class="flex-1 text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1.5 leading-5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400" />
            </div>
            <div class="flex-1 flex items-center gap-1.5">
              <label for="filter-date-to-m" class="text-sm text-gray-600 dark:text-gray-300 font-medium">To</label>
              <input id="filter-date-to-m" bind:value={filterDateTo} type="date" class="flex-1 text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1.5 leading-5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400" />
            </div>
          </div>
        {/if}
        <!-- Line 4: tags + topics -->
        <div class="grid grid-cols-2 gap-1.5">
          <TagFilter bind:tags={filterTags} {allTags} {tagFreq} class="w-full" />
          <TopicFilter bind:topics={filterTopics} class="w-full" />
        </div>
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
        {@const visibleQuestions = group.questions.filter(q => filteredQuestions.indexOf(q) < renderLimit)}
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
                {@const state = fs(question.id)}
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
      {#if renderLimit < filteredQuestions.length}
        <button
          onclick={() => renderLimit += isMobile ? MOBILE_PAGE_SIZE : DESKTOP_PAGE_SIZE}
          class="w-full py-3 text-sm font-medium text-primary-600 dark:text-primary-400 border border-primary-200 dark:border-primary-800 rounded-xl hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors"
        >
          Show more ({filteredQuestions.length - renderLimit} remaining)
        </button>
      {/if}
    {/if}
  </div>
  </div>
</div>
