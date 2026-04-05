<script lang="ts">
  import { getContext, onMount } from 'svelte';
  import type { QuestionStore } from '$lib/stores/questionStore';
  import { formatDateTz, formatTime, dateInTz } from '$lib/utils/time';
  import { SESSION_IMAGE_OPACITY, sessionBgUrl } from '$lib/config/ui';
  import SearchInput from '$lib/components/SearchInput.svelte';
  import FiltersToggleButton from '$lib/components/FiltersToggleButton.svelte';
  import TagFilter from '$lib/components/TagFilter.svelte';
  import TopicFilter from '$lib/components/TopicFilter.svelte';
  import ActiveFilterChips from '$lib/components/ActiveFilterChips.svelte';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import ConnectBadge from '$lib/components/ConnectBadge.svelte';
  import SearchableSelect from '$lib/components/SearchableSelect.svelte';
  import { supabase } from '$lib/supabase';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';

  const store = getContext<QuestionStore>('store');
  const usernameCtx = getContext<{ value: string } | undefined>('username');
  const savedSessionIds = getContext<{ value: Set<string> } | undefined>('savedSessionIds');
  const tzCtx = getContext<{ value: string }>('timezone');
  const sessions = store.getSessions();
  const sessionTs = store.getSessionEarliestTimestamps();

  function sessionDate(session: { id: string; date: string }): string {
    const ts = sessionTs.get(session.id);
    return formatDateTz(ts ?? session.date, tzCtx?.value ?? 'Europe/London');
  }

  const quizmasters = [...new Set(sessions.map(s => s.quizmaster))].sort();

  // Build per-session tag/topic index
  const sessionTopics = new Map<string, Set<string>>();
  const sessionTags = new Map<string, Set<string>>();
  for (const q of store.getQuestions()) {
    const sid = q.session?.id;
    if (!sid) continue;
    if (!sessionTopics.has(sid)) sessionTopics.set(sid, new Set());
    if (!sessionTags.has(sid)) sessionTags.set(sid, new Set());
    for (const t of q.question.topics ?? []) sessionTopics.get(sid)!.add(t);
    for (const t of q.question.tags ?? []) sessionTags.get(sid)!.add(t);
  }

  const tagFreq = new Map<string, number>();
  for (const tags of sessionTags.values()) {
    for (const tag of tags) tagFreq.set(tag, (tagFreq.get(tag) ?? 0) + 1);
  }
  const allTags = [...tagFreq.entries()].sort((a, b) => b[1] - a[1]).map(([t]) => t);

  let search = $state('');
  let filtersOpen = $state(false);
  let filterQuizmaster = $state('');
  let filterConnect = $state<'all' | 'connect' | 'regular'>('all');
  let filterTopics = $state(new Set<string>());
  let filterTags = $state(new Set<string>());
  let sortBy = $state<'newest' | 'oldest' | 'most_questions'>('newest');
  let minQuestions = $state(0);
  let filterSaved = $state(false);

  $effect(() => {
    const saved = $page.url.searchParams.get('saved') === '1';
    filterSaved = saved;
    if (saved) filtersOpen = true;
  });

  const activeFilterCount = $derived(
    [filterQuizmaster].filter(Boolean).length +
    (filterConnect !== 'all' ? 1 : 0) +
    (minQuestions > 0 ? 1 : 0) +
    filterTags.size + filterTopics.size +
    (filterSaved ? 1 : 0)
  );

  const filtered = $derived.by(() => {
    let results = sessions.filter(s => {
      const q = search.trim().toLowerCase();
      const searchable = s.quiz_type === 'connect'
        ? s.quizmaster.toLowerCase()
        : (s.theme?.toLowerCase() ?? '') + ' ' + s.quizmaster.toLowerCase();
      if (q && !searchable.includes(q)) return false;
      if (filterQuizmaster && s.quizmaster !== filterQuizmaster) return false;
      if (filterConnect === 'connect' && s.quiz_type !== 'connect') return false;
      if (filterConnect === 'regular' && s.quiz_type === 'connect') return false;
      if (filterTopics.size > 0 && ![...filterTopics].some(t => sessionTopics.get(s.id)?.has(t))) return false;
      if (filterTags.size > 0 && ![...filterTags].every(t => sessionTags.get(s.id)?.has(t))) return false;
      if (minQuestions > 0 && s.question_count < minQuestions) return false;
      if (filterSaved && !savedSessionIds?.value?.has(s.id)) return false;
      return true;
    });

    if (sortBy === 'newest') results = [...results].sort((a, b) => b.date.localeCompare(a.date));
    else if (sortBy === 'oldest') results = [...results].sort((a, b) => a.date.localeCompare(b.date));
    else if (sortBy === 'most_questions') results = [...results].sort((a, b) => b.question_count - a.question_count);

    return results;
  });

  // Group sessions by date for timeline display
  const sessionsByDate = $derived.by(() => {
    const tz = tzCtx?.value ?? 'Europe/London';
    const groups: { date: string; displayDate: string; sessions: typeof filtered }[] = [];
    const map = new Map<string, typeof filtered>();
    for (const s of filtered) {
      const ts = sessionTs.get(s.id);
      const d = ts ? dateInTz(ts, tz) : s.date;
      if (!map.has(d)) map.set(d, []);
      map.get(d)!.push(s);
    }
    for (const [date, sessions] of map) {
      groups.push({ date, displayDate: formatDateTz(date, tz), sessions });
    }
    return groups;
  });

  const hasFilters = $derived(!!(search || filterQuizmaster || filterConnect !== 'all' || sortBy !== 'newest' || filterTags.size > 0 || filterTopics.size > 0 || minQuestions > 0));

  function clearFilters() {
    search = '';
    filterQuizmaster = '';
    filterConnect = 'all';
    filterTopics = new Set();
    filterTags = new Set();
    sortBy = 'newest';
    minQuestions = 0;
    filterSaved = false;
    if ($page.url.searchParams.has('saved')) { const u = new URL(window.location.href); u.searchParams.delete('saved'); history.replaceState({}, '', u); }
  }

  const selectCls = 'w-full sm:w-40 text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 dark:focus:ring-primary-900 text-gray-600';

  const MOBILE_PAGE_SIZE = 6;
  let isMobile = $state(false);
  let mobileLimit = $state(MOBILE_PAGE_SIZE);

  onMount(() => {
    const mq = window.matchMedia('(max-width: 1023px)');
    isMobile = mq.matches;
    mq.addEventListener('change', e => { isMobile = e.matches; });
  });

  $effect(() => {
    search; filterQuizmaster; filterConnect; filterTopics; filterTags; sortBy; minQuestions;
    mobileLimit = MOBILE_PAGE_SIZE;
  });

  let sessionsAtBottom = $state(true);
  let sessionsScrollEl = $state<HTMLElement | null>(null);
  function onSessionsScroll(e: Event) {
    const el = e.currentTarget as HTMLElement;
    sessionsAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 8;
  }
  // Check overflow after content renders
  $effect(() => {
    filtered;
    if (sessionsScrollEl) {
      requestAnimationFrame(() => {
        if (sessionsScrollEl) {
          sessionsAtBottom = sessionsScrollEl.scrollHeight - sessionsScrollEl.scrollTop - sessionsScrollEl.clientHeight < 8;
        }
      });
    }
  });

  let showSortMenu = $state(false);
  const sortOptions = [
    { value: 'newest', label: 'Newest first' },
    { value: 'oldest', label: 'Oldest first' },
    { value: 'most_questions', label: 'Most questions' },
  ] as const;
  const sortLabel = $derived(sortOptions.find(o => o.value === sortBy)?.label ?? 'Sort');

  async function toggleSessionSave(e: MouseEvent, sessionId: string) {
    e.preventDefault();
    e.stopPropagation();
    const user = usernameCtx?.value || '';
    if (!user || !savedSessionIds) return;
    const isSaved = savedSessionIds.value.has(sessionId);
    if (isSaved) {
      const next = new Set(savedSessionIds.value); next.delete(sessionId); savedSessionIds.value = next;
      await supabase.from('session_saves').delete().eq('session_id', sessionId).eq('username', user);
    } else {
      savedSessionIds.value = new Set([...savedSessionIds.value, sessionId]);
      await supabase.from('session_saves').upsert({ session_id: sessionId, username: user }, { onConflict: 'session_id,username' });
    }
  }
</script>

<div class="space-y-6">
  <!-- Search + filters -->
  <div class="space-y-3">
    <!-- Search + toggle -->
    <div class="flex items-center gap-2">
      <SearchInput bind:value={search} placeholder="Search by theme or quizmaster…" />
      <FiltersToggleButton bind:open={filtersOpen} count={activeFilterCount} />
      <!-- Sort dropdown -->
      <div class="relative">
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
    </div>

    <!-- Collapsible filters -->
    {#if filtersOpen}
      <div class="space-y-2">
        <!-- Row 1: quizmaster + connect/regular -->
        <div class="flex items-center gap-2">
          <SearchableSelect
            bind:value={filterQuizmaster}
            options={quizmasters.map(qm => ({ value: qm, label: qm }))}
            placeholder="All quizmasters"
            class="flex-1 sm:flex-none sm:w-[140px]"
          />
          <div class="inline-flex items-center rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm overflow-hidden">
            {#each [['all', 'All'], ['connect', 'Connect'], ['regular', 'Regular']] as [val, label]}
              <button
                onclick={() => filterConnect = val as typeof filterConnect}
                class="px-3 py-1.5 transition-colors {filterConnect === val ? 'bg-primary-500 text-white' : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'}"
              >{label}</button>
            {/each}
          </div>
        </div>
        <!-- Row 2: question count + saved -->
        <div class="flex items-center gap-2">
          <div class="flex-1 inline-flex items-center rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm overflow-hidden sm:flex-none">
            {#each [0, 5, 10, 20] as n}
              <button
                onclick={() => minQuestions = minQuestions === n ? 0 : n}
                class="flex-1 sm:flex-none px-2.5 py-1.5 transition-colors
                  {minQuestions === n ? 'bg-primary-500 text-white' : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'}
                  {n > 0 ? 'border-l border-gray-200 dark:border-gray-600' : ''}"
              >{n === 0 ? 'All' : `${n}+ Qs`}</button>
            {/each}
          </div>
          <button
            onclick={() => { filterSaved = !filterSaved; if (!filterSaved && $page.url.searchParams.has('saved')) { const u = new URL(window.location.href); u.searchParams.delete('saved'); history.replaceState({}, '', u); } }}
            class="inline-flex items-center gap-1.5 rounded-lg border text-sm px-2.5 py-1.5 leading-5 whitespace-nowrap transition-colors {filterSaved ? 'bg-primary-500 text-white border-primary-500' : 'border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'}"
          >
            <svg class="w-3.5 h-3.5" fill={filterSaved ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
            </svg>
            Saved
          </button>
        </div>
        <!-- Row 3: tags, topics -->
        <div class="flex items-center gap-2">
          <TagFilter bind:tags={filterTags} {allTags} {tagFreq} class="flex-1 sm:flex-none sm:w-[140px]" />
          <TopicFilter bind:topics={filterTopics} class="flex-1 sm:flex-none sm:w-[140px]" />
        </div>
      </div>
    {/if}

    <ActiveFilterChips bind:tags={filterTags} bind:topics={filterTopics} hasFilters={hasFilters} onClear={clearFilters} />
  </div>

  <!-- Results count -->
  <p class="text-sm text-gray-500 dark:text-gray-400">
    {filtered.length} session{filtered.length !== 1 ? 's' : ''}
    {#if hasFilters}<span class="text-primary-500 font-medium"> (filtered)</span>{/if}
  </p>

  {#if sessions.length === 0}
    <EmptyState emoji="📅" message="No sessions yet" />
  {:else if filtered.length === 0}
    <EmptyState message="No sessions match your filters" onClear={clearFilters} />
  {:else}
    <div class="relative">
    {#if !sessionsAtBottom && filtered.length > 0}
      <div class="hidden lg:block pointer-events-none absolute inset-x-0 bottom-0 h-50 bg-gradient-to-t from-gray-50 dark:from-gray-900 to-transparent z-10 transition-opacity duration-300"></div>
    {/if}
    <div class="lg:max-h-[92vh] lg:overflow-y-auto space-y-6 pr-1 scrollbar-hide" bind:this={sessionsScrollEl} onscroll={onSessionsScroll}>
      {#each sessionsByDate as group, gi}
        {@const visibleSessions = isMobile ? group.sessions.filter(s => filtered.indexOf(s) < mobileLimit) : group.sessions}
        {#if visibleSessions.length > 0}
        <div class="relative pl-7">
          <!-- Timeline vertical line -->
          <div class="absolute left-[6px] top-[22px] bottom-3 w-[3px] rounded-full bg-primary-200 dark:bg-primary-800/60"></div>
          <!-- Date header with dot -->
          <div class="flex items-center gap-3 {gi > 0 ? 'pt-2' : ''}">
            <div class="absolute left-0 w-3.5 h-3.5 rounded-full bg-primary-500 dark:bg-primary-400 border-[3px] border-white dark:border-gray-900 shadow-sm z-10"></div>
            <span class="text-sm font-semibold text-gray-900 dark:text-gray-100">{group.displayDate}</span>
            <span class="text-xs text-gray-400 dark:text-gray-500">{visibleSessions.length} session{visibleSessions.length !== 1 ? 's' : ''}</span>
            <div class="flex-1 border-t border-gray-200 dark:border-gray-700"></div>
          </div>
          <div class="space-y-4 mt-3">
      {#each visibleSessions as session}
        <a
          href="/session/{session.id}"
          class="relative overflow-hidden block bg-ui-card rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm hover:shadow-md hover:border-primary-200 transition-all p-5 group"
          onmouseenter={(e) => { const bg = e.currentTarget.querySelector('.session-bg') as HTMLElement | null; if (bg) bg.style.opacity = String(SESSION_IMAGE_OPACITY.card.hover); }}
          onmouseleave={(e) => { const bg = e.currentTarget.querySelector('.session-bg') as HTMLElement | null; if (bg) bg.style.opacity = String(SESSION_IMAGE_OPACITY.card.default); }}
        >
          <div
            class="session-bg absolute inset-0 bg-cover bg-center transition-opacity"
            style="background-image: url('{sessionBgUrl(session)}'); opacity: {SESSION_IMAGE_OPACITY.card.default}"
          ></div>
          <!-- Text protection overlay — stronger on hover -->
          <div class="absolute inset-0 bg-gradient-to-r from-white/80 via-white/50 to-white/20 dark:from-gray-900/85 dark:via-gray-900/55 dark:to-gray-900/20 group-hover:from-white/90 group-hover:via-white/65 group-hover:to-white/30 dark:group-hover:from-gray-900/92 dark:group-hover:via-gray-900/70 dark:group-hover:to-gray-900/35 transition-all pointer-events-none"></div>

          {#if session.quiz_type === 'connect'}
            <div class="absolute left-0 top-0 bottom-0 w-1 rounded-l-xl bg-primary-500 z-10"></div>
          {/if}
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
                  </div>
                  <p class="text-xs text-gray-700 dark:text-gray-300">Hosted by {session.quizmaster} · {sessionDate(session)}</p>
                </div>
              </div>
              {#if session.announcement}
                <p class="mt-2 text-sm text-gray-700 dark:text-gray-300 italic truncate">"{session.announcement}"</p>
              {/if}

              <!-- Stats row -->
              <div class="flex flex-wrap gap-4 mt-3 text-sm">
                <div class="flex items-center gap-1.5 text-gray-800 dark:text-gray-200">
                  <svg class="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span class="font-medium">{session.question_count}</span>
                  <span class="text-gray-700 dark:text-gray-300">questions</span>
                </div>
                {#if session.participant_count > 0}
                  <div class="flex items-center gap-1.5 text-gray-800 dark:text-gray-200">
                    <svg class="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                    <span class="font-medium">{session.participant_count}</span>
                    <span class="text-gray-700 dark:text-gray-300">participants</span>
                  </div>
                {/if}
                {#if session.avg_time_to_answer_seconds}
                  <div class="flex items-center gap-1.5 text-gray-800 dark:text-gray-200">
                    <svg class="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span class="font-medium">{formatTime(session.avg_time_to_answer_seconds)}</span>
                    <span class="text-gray-700 dark:text-gray-300">avg solve</span>
                  </div>
                {/if}
                {#if session.avg_wrong_attempts}
                  <div class="flex items-center gap-1.5 text-gray-800 dark:text-gray-200">
                    <svg class="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                    <span class="font-medium">{session.avg_wrong_attempts.toFixed(1)}</span>
                    <span class="text-gray-700 dark:text-gray-300">avg wrong</span>
                  </div>
                {/if}
              </div>
            </div>

            <div class="flex-shrink-0 flex items-center gap-1">
              <button
                onclick={(e) => toggleSessionSave(e, session.id)}
                class="p-1 rounded-lg transition-colors {savedSessionIds?.value?.has(session.id) ? 'text-primary-500 dark:text-primary-400' : 'text-gray-300 dark:text-gray-600 hover:text-primary-400 dark:hover:text-primary-500'}"
                title={savedSessionIds?.value?.has(session.id) ? 'Unsave session' : 'Save session'}
              >
                <svg class="w-4 h-4" fill={savedSessionIds?.value?.has(session.id) ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
                </svg>
              </button>
              <div class="text-gray-300 group-hover:text-primary-400 transition-colors">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                </svg>
              </div>
            </div>
          </div>
        </a>
      {/each}
          </div>
        </div>
        {/if}
      {/each}
      {#if isMobile && mobileLimit < filtered.length}
        <button
          onclick={() => mobileLimit += MOBILE_PAGE_SIZE}
          class="w-full py-3 text-sm font-medium text-primary-600 dark:text-primary-400 border border-primary-200 dark:border-primary-800 rounded-xl hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors"
        >
          Show more ({filtered.length - mobileLimit} remaining)
        </button>
      {/if}
    </div>
    </div>
  {/if}
</div>
