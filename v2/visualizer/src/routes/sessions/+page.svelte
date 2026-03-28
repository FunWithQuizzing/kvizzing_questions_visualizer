<script lang="ts">
  import { getContext } from 'svelte';
  import type { QuestionStore } from '$lib/stores/questionStore';
  import { formatDate, formatTime } from '$lib/utils/time';

  const store = getContext<QuestionStore>('store');
  const sessions = store.getSessions();

  const quizmasters = [...new Set(sessions.map(s => s.quizmaster))].sort();

  let search = $state('');
  let filterQuizmaster = $state('');
  let sortBy = $state<'newest' | 'oldest' | 'most_questions'>('newest');

  const filtered = $derived.by(() => {
    let results = sessions.filter(s => {
      const q = search.trim().toLowerCase();
      if (q && !(s.theme?.toLowerCase().includes(q) || s.quizmaster.toLowerCase().includes(q))) return false;
      if (filterQuizmaster && s.quizmaster !== filterQuizmaster) return false;
      return true;
    });

    if (sortBy === 'newest') results = [...results].sort((a, b) => b.date.localeCompare(a.date));
    else if (sortBy === 'oldest') results = [...results].sort((a, b) => a.date.localeCompare(b.date));
    else if (sortBy === 'most_questions') results = [...results].sort((a, b) => b.question_count - a.question_count);

    return results;
  });

  const hasFilters = $derived(search || filterQuizmaster || sortBy !== 'newest');

  function clearFilters() {
    search = '';
    filterQuizmaster = '';
    sortBy = 'newest';
  }
</script>

<div class="space-y-6">
  <!-- Header -->
  <div>
    <h1 class="text-2xl font-bold text-gray-900 dark:text-gray-100">Quiz sessions</h1>
    <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">Curated quiz sessions hosted by group members</p>
  </div>

  <!-- Search + filters -->
  <div class="space-y-3">
    <!-- Search -->
    <div class="relative">
      <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
      </svg>
      <input
        bind:value={search}
        type="text"
        placeholder="Search by theme or quizmaster…"
        class="w-full pl-9 pr-4 py-2.5 text-sm border border-gray-200 dark:border-gray-600 rounded-xl focus:outline-none focus:border-orange-400 focus:ring-2 focus:ring-orange-100 dark:focus:ring-orange-900 bg-white dark:bg-gray-700 dark:text-gray-200 dark:placeholder-gray-400 shadow-sm transition-all"
      />
      {#if search}
        <button
          onclick={() => search = ''}
          aria-label="Clear search"
          class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      {/if}
    </div>

    <!-- Dropdowns -->
    <div class="flex flex-wrap gap-2">
      <select
        bind:value={filterQuizmaster}
        class="text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-orange-400 focus:ring-1 focus:ring-orange-100 dark:focus:ring-orange-900 text-gray-600"
      >
        <option value="">All quizmasters</option>
        {#each quizmasters as qm}
          <option value={qm}>{qm}</option>
        {/each}
      </select>

      <select
        bind:value={sortBy}
        class="text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-orange-400 focus:ring-1 focus:ring-orange-100 dark:focus:ring-orange-900 text-gray-600"
      >
        <option value="newest">Newest first</option>
        <option value="oldest">Oldest first</option>
        <option value="most_questions">Most questions</option>
      </select>

      {#if hasFilters}
        <button
          onclick={clearFilters}
          class="text-sm text-orange-600 dark:text-orange-400 hover:text-orange-700 dark:hover:text-orange-300 px-2 py-1.5 transition-colors"
        >
          Clear all
        </button>
      {/if}
    </div>
  </div>

  <!-- Results count -->
  <p class="text-sm text-gray-500 dark:text-gray-400">
    {filtered.length} session{filtered.length !== 1 ? 's' : ''}
    {#if hasFilters}<span class="text-orange-500 font-medium"> (filtered)</span>{/if}
  </p>

  {#if sessions.length === 0}
    <div class="text-center py-20 text-gray-400">
      <div class="text-4xl mb-3">📅</div>
      <p class="font-medium">No sessions yet</p>
    </div>
  {:else if filtered.length === 0}
    <div class="text-center py-16 text-gray-400">
      <div class="text-4xl mb-3">🔍</div>
      <p class="font-medium">No sessions match your filters</p>
      <button onclick={clearFilters} class="mt-2 text-sm text-orange-500 hover:text-orange-600">Clear filters</button>
    </div>
  {:else}
    <div class="space-y-4">
      {#each filtered as session}
        <a
          href="/session/{session.id}"
          class="block bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm hover:shadow-md hover:border-orange-200 transition-all p-5 group"
        >
          <div class="flex items-start justify-between gap-4">
            <div class="flex-1 min-w-0">
              <!-- Title -->
              <div class="flex items-center gap-2 mb-1">
                <div class="w-8 h-8 rounded-lg bg-orange-500 flex items-center justify-center flex-shrink-0">
                  <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                  </svg>
                </div>
                <div>
                  <h2 class="text-base font-semibold text-gray-900 dark:text-gray-100 group-hover:text-orange-600 transition-colors">
                    {session.theme ?? `${session.quizmaster}'s Quiz`}
                  </h2>
                  <p class="text-xs text-gray-500 dark:text-gray-400">Hosted by {session.quizmaster} · {formatDate(session.date)}</p>
                </div>
              </div>

              <!-- Stats row -->
              <div class="flex flex-wrap gap-4 mt-3 text-sm">
                <div class="flex items-center gap-1.5 text-gray-600 dark:text-gray-300">
                  <svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span class="font-medium">{session.question_count}</span>
                  <span class="text-gray-400 dark:text-gray-500">questions</span>
                </div>
                {#if session.participant_count > 0}
                  <div class="flex items-center gap-1.5 text-gray-600 dark:text-gray-300">
                    <svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                    <span class="font-medium">{session.participant_count}</span>
                    <span class="text-gray-400 dark:text-gray-500">participants</span>
                  </div>
                {/if}
                {#if session.avg_time_to_answer_seconds}
                  <div class="flex items-center gap-1.5 text-gray-600 dark:text-gray-300">
                    <svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span class="font-medium">{formatTime(session.avg_time_to_answer_seconds)}</span>
                    <span class="text-gray-400 dark:text-gray-500">avg solve</span>
                  </div>
                {/if}
                {#if session.avg_wrong_attempts}
                  <div class="flex items-center gap-1.5 text-gray-600 dark:text-gray-300">
                    <svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                    <span class="font-medium">{session.avg_wrong_attempts.toFixed(1)}</span>
                    <span class="text-gray-400 dark:text-gray-500">avg wrong</span>
                  </div>
                {/if}
              </div>
            </div>

            <div class="flex-shrink-0 text-gray-300 group-hover:text-orange-400 transition-colors">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </div>
        </a>
      {/each}
    </div>
  {/if}
</div>
