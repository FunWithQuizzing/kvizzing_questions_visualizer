<script lang="ts">
  import { getContext } from 'svelte';
  import { goto } from '$app/navigation';
  import type { QuestionStore } from '$lib/stores/questionStore';
  import { formatDateTz, formatTime } from '$lib/utils/time';
  import { SESSION_IMAGE_OPACITY } from '$lib/config/ui';

  const store = getContext<QuestionStore>('store');
  const tzCtx = getContext<{ value: string }>('timezone');
  const sessions = store.getSessions();
  const stats = store.getTotalStats();
  const sessionTs = store.getSessionEarliestTimestamps();

  function sessionDate(session: { id: string; date: string }): string {
    const ts = sessionTs.get(session.id);
    return formatDateTz(ts ?? session.date, tzCtx?.value ?? 'Europe/London');
  }
  const sessionQuestionCount = sessions.reduce((sum, s) => sum + s.question_count, 0);
  const sinceDate = $derived(stats.earliestTimestamp ? formatDateTz(stats.earliestTimestamp, tzCtx?.value ?? 'Europe/London') : '');

  function randomQuiz() {
    if (sessions.length === 0) return;
    const s = sessions[Math.floor(Math.random() * sessions.length)];
    goto(`/session/${s.id}`);
  }

  const quizmasters = [...new Set(sessions.map(s => s.quizmaster))].sort();

  let search = $state('');
  let filterQuizmaster = $state('');
  let filterConnect = $state<'all' | 'connect' | 'regular'>('all');
  let sortBy = $state<'newest' | 'oldest' | 'most_questions'>('newest');

  const filtered = $derived.by(() => {
    let results = sessions.filter(s => {
      const q = search.trim().toLowerCase();
      // Don't match on theme for connect quizzes — the theme is the answer
      const searchable = s.quiz_type === 'connect'
        ? s.quizmaster.toLowerCase()
        : (s.theme?.toLowerCase() ?? '') + ' ' + s.quizmaster.toLowerCase();
      if (q && !searchable.includes(q)) return false;
      if (filterQuizmaster && s.quizmaster !== filterQuizmaster) return false;
      if (filterConnect === 'connect' && s.quiz_type !== 'connect') return false;
      if (filterConnect === 'regular' && s.quiz_type === 'connect') return false;
      return true;
    });

    if (sortBy === 'newest') results = [...results].sort((a, b) => b.date.localeCompare(a.date));
    else if (sortBy === 'oldest') results = [...results].sort((a, b) => a.date.localeCompare(b.date));
    else if (sortBy === 'most_questions') results = [...results].sort((a, b) => b.question_count - a.question_count);

    return results;
  });

  const hasFilters = $derived(search || filterQuizmaster || filterConnect !== 'all' || sortBy !== 'newest');

  function clearFilters() {
    search = '';
    filterQuizmaster = '';
    filterConnect = 'all';
    sortBy = 'newest';
  }
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
    <h1 class="text-2xl font-bold mb-1">Quiz Sessions</h1>
    <p class="text-primary-100 text-sm mb-4">Curated quiz sessions hosted by group members</p>
    <div class="flex items-center justify-between gap-3">
      <div class="flex flex-wrap gap-x-4 gap-y-1 text-sm">
        <span class="font-semibold">{stats.sessions} quiz sessions</span>
        <span class="text-primary-200 hidden sm:inline">·</span>
        <span class="font-semibold">{sessionQuestionCount} questions</span>
      </div>
      <button
        onclick={randomQuiz}
        class="flex-shrink-0 inline-flex items-center gap-1.5 px-4 py-2 bg-white hover:bg-primary-50 text-primary-600 dark:bg-slate-700 dark:hover:bg-slate-600 dark:text-white font-semibold text-sm rounded-lg transition-colors shadow-sm cursor-pointer"
      >
        <svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" /></svg>
        <span class="hidden sm:inline">Random quiz</span>
      </button>
    </div>
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
        class="w-full pl-9 pr-4 py-2.5 text-sm border border-gray-200 dark:border-gray-600 rounded-xl focus:outline-none focus:border-primary-400 focus:ring-2 focus:ring-primary-100 dark:focus:ring-primary-900 bg-white dark:bg-gray-700 dark:text-gray-200 dark:placeholder-gray-400 shadow-sm transition-all"
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
        class="flex-1 min-w-[8rem] sm:flex-none sm:w-40 text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 dark:focus:ring-primary-900 text-gray-600"
      >
        <option value="">All quizmasters</option>
        {#each quizmasters as qm}
          <option value={qm}>{qm}</option>
        {/each}
      </select>

      <select
        bind:value={sortBy}
        class="flex-1 min-w-[8rem] sm:flex-none sm:w-40 text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 dark:focus:ring-primary-900 text-gray-600"
      >
        <option value="newest">Newest first</option>
        <option value="oldest">Oldest first</option>
        <option value="most_questions">Most questions</option>
      </select>

      <!-- Connect quiz filter toggle -->
      <div class="flex items-center rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm overflow-hidden flex-shrink-0">
        {#each [['all', 'All'], ['connect', 'Connect'], ['regular', 'Regular']] as [val, label]}
          <button
            onclick={() => filterConnect = val as typeof filterConnect}
            class="px-3 py-1.5 transition-colors
              {filterConnect === val
                ? 'bg-primary-500 text-white'
                : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'}"
          >{label}</button>
        {/each}
      </div>

      {#if hasFilters}
        <button
          onclick={clearFilters}
          class="text-sm text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300 px-2 py-1.5 transition-colors"
        >
          Clear all
        </button>
      {/if}
    </div>
  </div>

  <!-- Results count -->
  <p class="text-sm text-gray-500 dark:text-gray-400">
    {filtered.length} session{filtered.length !== 1 ? 's' : ''}
    {#if hasFilters}<span class="text-primary-500 font-medium"> (filtered)</span>{/if}
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
      <button onclick={clearFilters} class="mt-2 text-sm text-primary-500 hover:text-primary-600">Clear filters</button>
    </div>
  {:else}
    <div class="space-y-4">
      {#each filtered as session}
        <a
          href="/session/{session.id}"
          class="relative overflow-hidden block bg-ui-card rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm hover:shadow-md hover:border-primary-200 transition-all p-5 group"
          onmouseenter={(e) => { const bg = e.currentTarget.querySelector('.session-bg') as HTMLElement | null; if (bg) bg.style.opacity = String(SESSION_IMAGE_OPACITY.card.hover); }}
          onmouseleave={(e) => { const bg = e.currentTarget.querySelector('.session-bg') as HTMLElement | null; if (bg) bg.style.opacity = String(SESSION_IMAGE_OPACITY.card.default); }}
        >
          <div
            class="session-bg absolute inset-0 bg-cover bg-center transition-opacity"
            style="background-image: url('{session.quiz_type === 'connect' ? '/images/connect-quiz-bg.png' : '/images/sessions/' + session.id + '.jpg'}'); opacity: {SESSION_IMAGE_OPACITY.card.default}"
          ></div>

          <div class="relative flex items-start justify-between gap-4">
            <div class="flex-1 min-w-0">
              <!-- Title -->
              <div class="flex items-center gap-2 mb-1">
                <div class="w-8 h-8 rounded-lg bg-primary-500 flex items-center justify-center flex-shrink-0">
                  <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                  </svg>
                </div>
                <div>
                  <div class="flex items-center gap-2">
                    <h2 class="text-base font-semibold text-primary-700 dark:text-primary-200 group-hover:text-primary-800 dark:group-hover:text-primary-100 transition-colors">
                      {session.quiz_type === 'connect' ? `${session.quizmaster}'s Connect Quiz` : (session.theme ?? `${session.quizmaster}'s Quiz`)}
                    </h2>
                    {#if session.quiz_type === 'connect'}
                      <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-primary-100 text-primary-600 dark:bg-primary-900/40 dark:text-primary-300 flex-shrink-0">
                        <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
                        </svg>
                        Connect
                      </span>
                    {/if}
                  </div>
                  <p class="text-xs text-gray-700 dark:text-gray-300">Hosted by {session.quizmaster} · {sessionDate(session)}</p>
                </div>
              </div>

              <!-- Stats row -->
              <div class="flex flex-wrap gap-4 mt-3 text-sm">
                <div class="flex items-center gap-1.5 text-gray-800 dark:text-gray-200">
                  <svg class="w-4 h-4 text-primary-300 dark:text-primary-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span class="font-medium">{session.question_count}</span>
                  <span class="text-gray-700 dark:text-gray-300">questions</span>
                </div>
                {#if session.participant_count > 0}
                  <div class="flex items-center gap-1.5 text-gray-800 dark:text-gray-200">
                    <svg class="w-4 h-4 text-primary-300 dark:text-primary-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                    <span class="font-medium">{session.participant_count}</span>
                    <span class="text-gray-700 dark:text-gray-300">participants</span>
                  </div>
                {/if}
                {#if session.avg_time_to_answer_seconds}
                  <div class="flex items-center gap-1.5 text-gray-800 dark:text-gray-200">
                    <svg class="w-4 h-4 text-primary-300 dark:text-primary-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span class="font-medium">{formatTime(session.avg_time_to_answer_seconds)}</span>
                    <span class="text-gray-700 dark:text-gray-300">avg solve</span>
                  </div>
                {/if}
                {#if session.avg_wrong_attempts}
                  <div class="flex items-center gap-1.5 text-gray-800 dark:text-gray-200">
                    <svg class="w-4 h-4 text-primary-300 dark:text-primary-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                    <span class="font-medium">{session.avg_wrong_attempts.toFixed(1)}</span>
                    <span class="text-gray-700 dark:text-gray-300">avg wrong</span>
                  </div>
                {/if}
              </div>
            </div>

            <div class="flex-shrink-0 text-gray-300 group-hover:text-primary-400 transition-colors">
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
