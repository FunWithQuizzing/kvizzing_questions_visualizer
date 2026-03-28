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
  const sessions = store.getSessions();
  const recentSessions = sessions.slice(0, 3);

  // URL-driven filters — initialised from URL and kept in sync on every navigation
  // (initial values are empty; $effect below syncs from URL after mount, avoiding prerender issues)
  let searchQuery = $state('');
  let filterAsker = $state('');
  let filterSolver = $state('');
  let filterDateFrom = $state('');
  let filterDateTo = $state('');
  let filterHasMedia = $state(undefined as boolean | undefined);
  let filterSessionId = $state('');
  let filterTopics = $state(new Set<string>());

  // Re-sync whenever the URL changes (e.g. calendar navigation while already on this page)
  $effect(() => {
    const p = $page.url.searchParams;
    searchQuery = p.get('q') ?? '';
    filterAsker = p.get('asker') ?? '';
    filterSolver = p.get('solver') ?? '';
    filterDateFrom = p.get('dateFrom') ?? '';
    filterDateTo = p.get('dateTo') ?? '';
    filterHasMedia = p.get('has_media') === '1' ? true : undefined as boolean | undefined;
    filterSessionId = p.get('session') ?? '';
    // Support ?topic=X (from card badge clicks) and ?topics=X,Y (multi-select)
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
  let showMoreFilters = $state(false);
  let sortBy = $state<SortOption>('newest');

  const askers = store.getAskers();
  const solvers = store.getSolvers();
  const allSessions = store.getSessions();

  // Build fuse index once
  const allQuestions = store.getQuestions();
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

    // Multi-topic filter (applied after store query)
    if (filterTopics.size > 0) {
      results = results.filter(q => filterTopics.has(q.question.topic ?? ''));
    }

    if (searchQuery.trim()) {
      const fuseResults = fuse.search(searchQuery.trim());
      const matchedIds = new Set(fuseResults.map(r => r.item.id));
      results = results.filter(q => matchedIds.has(q.id));
      // Re-sort by fuse score if searching
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
    filterTopics = new Set();
  }

  const hasActiveFilters = $derived(
    searchQuery || filterAsker || filterSolver ||
    filterDateFrom || filterDateTo || filterHasMedia !== undefined || filterSessionId || filterTopics.size > 0
  );

  const sinceDate = stats.earliestDate ? formatDate(stats.earliestDate) : '';
</script>

<div class="space-y-6">
  <!-- Hero -->
  <div class="bg-gradient-to-br from-orange-500 to-orange-600 rounded-2xl p-6 text-white shadow-lg relative">
    {#if sinceDate}
      <div class="absolute top-4 right-4 flex items-center gap-1.5 text-xs text-orange-100">
        <span class="relative flex h-2.5 w-2.5">
          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-300 opacity-90"></span>
          <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-green-400"></span>
        </span>
        since {sinceDate}
      </div>
    {/if}
    <h1 class="text-2xl font-bold mb-1">KVizzing</h1>
    <p class="text-orange-100 text-sm mb-4">Every question the group ever asked. Right here.</p>
    <div class="flex items-center justify-between gap-3">
      <div class="flex flex-wrap gap-x-4 gap-y-1 text-sm">
        <span class="font-semibold">{stats.total} questions</span>
        <span class="text-orange-200 hidden sm:inline">·</span>
        <a href="/sessions" class="font-semibold hover:text-orange-100 transition-colors cursor-pointer">{stats.sessions} sessions</a>
      </div>
      <button
        onclick={surpriseMe}
        class="flex-shrink-0 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white font-semibold text-sm rounded-lg transition-colors shadow-sm cursor-pointer"
      >
        🎲 <span class="hidden sm:inline">Random question</span>
      </button>
    </div>
  </div>

  <!-- Recent Sessions strip -->
  {#if recentSessions.length > 0}
    <div>
      <h2 class="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-3">Recent Quiz sessions</h2>
      <div class="flex gap-3 overflow-x-auto pb-1">
        {#each recentSessions as session}
          <a
            href="/session/{session.id}"
            class="flex-shrink-0 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl px-4 py-3 hover:border-orange-300 hover:shadow-sm transition-all min-w-[180px]"
          >
            <div class="flex items-center gap-2 mb-1">
              <span class="w-2 h-2 rounded-full bg-orange-400 dark:bg-orange-500"></span>
              <span class="text-xs font-semibold text-gray-700 dark:text-gray-300 truncate">
                {session.theme ?? `${session.quizmaster}'s Quiz`}
              </span>
            </div>
            <p class="text-xs text-gray-500 dark:text-gray-400">{session.quizmaster} · {formatDate(session.date)}</p>
            <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{session.question_count} questions</p>
          </a>
        {/each}
        <a
          href="/sessions"
          class="flex-shrink-0 border-2 border-dashed border-gray-200 dark:border-gray-700 rounded-xl px-4 py-3 hover:border-orange-300 transition-colors flex items-center text-sm text-gray-400 dark:text-gray-500 hover:text-orange-500 dark:hover:text-orange-400 min-w-[120px] justify-center"
        >
          All sessions →
        </a>
      </div>
    </div>
  {/if}

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
        class="w-full pl-9 pr-4 py-2.5 text-sm border border-gray-200 dark:border-gray-600 rounded-xl focus:outline-none focus:border-orange-400 focus:ring-2 focus:ring-orange-100 dark:focus:ring-orange-900 bg-white dark:bg-gray-700 dark:text-gray-200 dark:placeholder-gray-400 shadow-sm transition-all"
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
      <!-- Asker -->
      <select
        bind:value={filterAsker}
        class="text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-orange-400 focus:ring-1 focus:ring-orange-100 dark:focus:ring-orange-900 text-gray-600"
      >
        <option value="">All askers</option>
        {#each askers as asker}
          <option value={asker}>{asker}</option>
        {/each}
      </select>

      <!-- Solver -->
      <select
        bind:value={filterSolver}
        class="text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-orange-400 focus:ring-1 focus:ring-orange-100 dark:focus:ring-orange-900 text-gray-600"
      >
        <option value="">All solvers</option>
        {#each solvers as solver}
          <option value={solver}>{solver}</option>
        {/each}
      </select>

      <!-- Sort -->
      <select
        bind:value={sortBy}
        class="text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-orange-400 focus:ring-1 focus:ring-orange-100 dark:focus:ring-orange-900 text-gray-600"
      >
        <option value="newest">Newest first</option>
        <option value="oldest">Oldest first</option>
        <option value="most_discussed">Most discussed</option>
        <option value="quickest">Quickest solve</option>
      </select>

      <!-- More filters toggle -->
      <button
        onclick={() => showMoreFilters = !showMoreFilters}
        class="text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors flex items-center gap-1.5"
      >
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2a1 1 0 01-.293.707L13 13.414V19a1 1 0 01-.553.894l-4 2A1 1 0 017 21v-7.586L3.293 6.707A1 1 0 013 6V4z" />
        </svg>
        More filters
        {#if showMoreFilters}
          <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7" />
          </svg>
        {:else}
          <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
          </svg>
        {/if}
      </button>

      {#if hasActiveFilters}
        <button
          onclick={clearFilters}
          class="text-sm text-orange-600 dark:text-orange-400 hover:text-orange-700 dark:hover:text-orange-300 px-2 py-1.5 transition-colors"
        >
          Clear all
        </button>
      {/if}
    </div>

    <!-- Topic filter: dropdown + selected chips -->
    <div class="flex flex-wrap items-center gap-2">
      <select
        value=""
        onchange={(e) => { const v = (e.target as HTMLSelectElement).value; if (v) toggleTopic(v); (e.target as HTMLSelectElement).value = ''; }}
        class="text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-orange-400 focus:ring-1 focus:ring-orange-100 dark:focus:ring-orange-900 text-gray-600"
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
    </div>

    <!-- Secondary filters -->
    {#if showMoreFilters}
      <div class="flex flex-wrap gap-2 p-3 bg-gray-50 dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700">
        <div class="flex items-center gap-2">
          <label for="filter-date-from" class="text-xs text-gray-500 dark:text-gray-400 font-medium">From</label>
          <input
            id="filter-date-from"
            bind:value={filterDateFrom}
            type="date"
            class="text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-orange-400"
          />
        </div>
        <div class="flex items-center gap-2">
          <label for="filter-date-to" class="text-xs text-gray-500 dark:text-gray-400 font-medium">To</label>
          <input
            id="filter-date-to"
            bind:value={filterDateTo}
            type="date"
            class="text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-2 py-1 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-orange-400"
          />
        </div>
        <select
          bind:value={filterSessionId}
          class="text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-orange-400 text-gray-600"
        >
          <option value="">All sessions</option>
          {#each allSessions as s}
            <option value={s.id}>{s.theme ?? `${s.quizmaster}'s Quiz`} ({formatDate(s.date)})</option>
          {/each}
        </select>
        <label class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300 cursor-pointer">
          <input
            type="checkbox"
            checked={filterHasMedia === true}
            onchange={(e) => filterHasMedia = e.currentTarget.checked ? true : undefined}
            class="rounded border-gray-300 text-orange-500 focus:ring-orange-200"
          />
          Has media
        </label>
      </div>
    {/if}
  </div>

  <!-- Results count -->
  <div class="flex items-center justify-between">
    <p class="text-sm text-gray-500 dark:text-gray-400">
      {filteredQuestions.length} question{filteredQuestions.length !== 1 ? 's' : ''}
      {#if hasActiveFilters}<span class="text-orange-500 dark:text-orange-400 font-medium"> (filtered)</span>{/if}
    </p>
  </div>

  <!-- Question cards -->
  <div class="max-h-[60vh] overflow-y-auto space-y-4 pr-1">
    {#each filteredQuestions as question (question.id)}
      <QuestionCard {question} />
    {:else}
      <div class="text-center py-16 text-gray-400">
        <div class="text-4xl mb-3">🔍</div>
        <p class="font-medium">No questions match your filters</p>
        <button onclick={clearFilters} class="mt-2 text-sm text-orange-500 dark:text-orange-400 hover:text-orange-600 dark:hover:text-orange-300">
          Clear filters
        </button>
      </div>
    {/each}
  </div>
</div>
