<script lang="ts">
  import { onMount, getContext } from 'svelte';
  import MemberAvatar from '$lib/components/MemberAvatar.svelte';
  import { page } from '$app/stores';
  import { supabase } from '$lib/supabase';
  import { formatDateTz } from '$lib/utils/time';

  const tzCtx = getContext<{ value: string }>('timezone');

  function fmtDateTime(utcTs: string): { date: string; time: string } {
    try {
      const d = new Date(utcTs.endsWith('Z') ? utcTs : utcTs + 'Z');
      const date = d.toLocaleDateString('en-CA', { timeZone: tzCtx.value }); // YYYY-MM-DD
      const time = d.toLocaleTimeString('en-GB', { timeZone: tzCtx.value, hour: '2-digit', minute: '2-digit', hour12: false });
      return { date, time };
    } catch {
      return { date: utcTs.slice(0, 10), time: utcTs.slice(11, 16) };
    }
  }

  let { data } = $props();

  type Candidate = { timestamp: string; username: string; text: string; reason_flagged: string };
  type ContextMsg = { timestamp: string; username: string; text: string; is_candidate: boolean };
  type Thread = { id: string; date: string; candidates: Candidate[]; context: ContextMsg[] };
  type Status = 'valid' | 'not_valid' | 'maybe';
  type Vote = { thread_id: string; reviewer: string; status: Status; reason: string; comment: string };

  const threads: Thread[] = data.threads;
  const questionsByTs: Map<string, { id: string; text: string }> = data.questionsByTs;

  // ── Reviewer identity (from site-wide context) ─────────────────────────────
  const usernameCtx = getContext<{ value: string }>('username');
  let reviewer = $derived(usernameCtx?.value || '');

  onMount(() => {
    if (reviewer) loadVotes();
  });

  // Re-load votes when username changes (e.g. user sets name after page load)
  $effect(() => {
    if (reviewer) loadVotes();
  });

  // ── Votes from Supabase ────────────────────────────────────────────────────
  // allVotes: every vote from every reviewer
  let allVotes = $state<Vote[]>([]);
  let loading = $state(true);

  let loadError = $state(false);

  async function loadVotes() {
    loading = true;
    loadError = false;
    const { data: rows, error } = await supabase.from('votes').select('*');
    if (error) {
      loadError = true;
    } else if (rows) {
      allVotes = rows;
    }
    loading = false;
  }

  // My votes (derived from allVotes)
  const myVotes = $derived(
    new Map(allVotes.filter(v => v.reviewer === reviewer).map(v => [v.thread_id, v]))
  );

  // Vote tallies per thread
  function voteTally(threadId: string) {
    const tv = allVotes.filter(v => v.thread_id === threadId);
    return {
      valid: tv.filter(v => v.status === 'valid').length,
      maybe: tv.filter(v => v.status === 'maybe').length,
      not_valid: tv.filter(v => v.status === 'not_valid').length,
      total: tv.length,
      votes: tv,
    };
  }

  // ── Voting ─────────────────────────────────────────────────────────────────
  let reasonOpenFor = $state<{ id: string; status: Status } | null>(null);
  let customReasonText = $state('');

  function startVote(id: string, status: Status) {
    if (!reviewer) { return; return; }
    const existing = myVotes.get(id);
    if (existing?.status === status) {
      deleteVote(id);
      reasonOpenFor = null;
      return;
    }
    // Collapse if clicking the same button that opened the picker
    if (reasonOpenFor?.id === id && reasonOpenFor?.status === status) {
      reasonOpenFor = null;
      return;
    }
    reasonOpenFor = { id, status };
    customReasonText = '';
  }

  async function confirmVote(reason: string) {
    if (!reasonOpenFor || !reviewer) {
      if (!reviewer) return;
      return;
    }
    const { id, status } = reasonOpenFor;

    const vote = { thread_id: id, reviewer, status, reason, comment: '' };

    // Trigger vanish animation if thread will leave the current filter
    const willDisappear = filterStatus === 'unreviewed' ||
      (filterStatus !== 'all' && filterStatus !== status);
    if (willDisappear) {
      vanishingIds = new Set([...vanishingIds, id]);
      await new Promise(r => setTimeout(r, 400));
      vanishingIds = new Set([...vanishingIds].filter(v => v !== id));
    }

    // Optimistic update — save previous state for rollback
    const prevVotes = [...allVotes];
    const idx = allVotes.findIndex(v => v.thread_id === id && v.reviewer === reviewer);
    if (idx >= 0) allVotes[idx] = { ...allVotes[idx], ...vote };
    else allVotes = [...allVotes, vote as Vote];

    reasonOpenFor = null;
    customReasonText = '';

    // Upsert to Supabase
    const { error } = await supabase.from('votes').upsert(vote, { onConflict: 'thread_id,reviewer' });
    if (error) {
      allVotes = prevVotes; // rollback
      alert('Failed to save vote. Please try again.');
      return;
    }
    window.dispatchEvent(new Event('kvizzing-vote-changed'));
  }

  async function deleteVote(threadId: string) {
    if (!reviewer) return;

    // Trigger vanish animation if removing the vote causes the thread to leave the current filter
    const existing = myVotes.get(threadId);
    const willDisappear =
      // On "Reviewed" tab (filterReviewer set) — un-voting removes it from view
      !!filterReviewer ||
      // On a status filter — un-voting a matching status removes it
      (filterStatus !== 'all' && filterStatus !== 'unreviewed' &&
        existing?.status === filterStatus);
    if (willDisappear) {
      vanishingIds = new Set([...vanishingIds, threadId]);
      await new Promise(r => setTimeout(r, 400));
      vanishingIds = new Set([...vanishingIds].filter(v => v !== threadId));
    }

    const prevVotes = [...allVotes];
    allVotes = allVotes.filter(v => !(v.thread_id === threadId && v.reviewer === reviewer));

    const { error } = await supabase.from('votes').delete().eq('thread_id', threadId).eq('reviewer', reviewer);
    if (error) {
      allVotes = prevVotes; // rollback
      alert('Failed to remove vote. Please try again.');
      return;
    }
    window.dispatchEvent(new Event('kvizzing-vote-changed'));
  }

  function submitCustomReason() {
    if (customReasonText.trim()) confirmVote(customReasonText.trim());
  }

  const reasonPresets: Record<Status, string[]> = {
    valid: [
      'Genuine trivia question',
      'Bonus/follow-up question',
      'Quiz session question missed',
      'Unanswered but valid question',
    ],
    maybe: [
      'Needs more context',
      'Borderline — could be trivia',
      'Interesting discussion point',
      'Partially a question',
    ],
    not_valid: [
      'Guess/answer attempt',
      'Casual conversation',
      'Quiz logistics/coordination',
      'Rhetorical question',
      'Meme/joke',
    ],
  };

  // ── Filters ────────────────────────────────────────────────────────────────
  const allDates = [...new Set(threads.map(t => t.date))].sort();
  let sortBy = $state<'least' | 'most'>('least');

  function toggleSort() {
    if (sortBy === 'most') {
      sortBy = 'least';
    } else {
      const ok = confirm('Your help is most needed on questions with the fewest votes! Switch anyway?');
      if (ok) sortBy = 'most';
    }
  }
  const urlDate = $page.url.searchParams.get('date');
  const urlReviewer = $page.url.searchParams.get('reviewer');
  let selectedDate = $state<string>(urlDate && allDates.includes(urlDate) ? urlDate : '');
  let filterStatus = $state<'all' | 'unreviewed' | 'valid' | 'maybe' | 'not_valid'>(urlReviewer ? 'all' : 'unreviewed');
  let filterReviewer = $state<string>(urlReviewer ?? '');
  let filterDateFrom = $state('');
  let filterDateTo = $state('');
  let showDateRange = $state(false);

  function filterThreads(threadList: Thread[]): Thread[] {
    return threadList
      .filter(t => {
        if (selectedDate && t.date !== selectedDate) return false;
        if (filterDateFrom && t.date < filterDateFrom) return false;
        if (filterDateTo && t.date > filterDateTo) return false;
        // Reviewer filter: show only threads this reviewer voted on
        if (filterReviewer) {
          const hasVote = allVotes.some(v => v.thread_id === t.id && v.reviewer === filterReviewer);
          if (!hasVote) return false;
        }
        const mv = myVotes.get(t.id);
        if (filterStatus === 'unreviewed' && mv) return false;
        if (filterStatus === 'valid' && mv?.status !== 'valid') return false;
        if (filterStatus === 'maybe' && mv?.status !== 'maybe') return false;
        if (filterStatus === 'not_valid' && mv?.status !== 'not_valid') return false;
        return true;
      })
      .sort((a, b) => {
        const aVotes = allVotes.filter(v => v.thread_id === a.id).length;
        const bVotes = allVotes.filter(v => v.thread_id === b.id).length;
        if (aVotes !== bVotes) {
          return sortBy === 'least' ? aVotes - bVotes : bVotes - aVotes;
        }
        return a.date.localeCompare(b.date) || a.id.localeCompare(b.id);
      });
  }

  const filtered = $derived(filterThreads(threads));
  const visibleDates = $derived([...new Set(filtered.map(t => t.date))].sort());

  function dateReviewStats(d: string) {
    const dateThreads = threads.filter(t => t.date === d);
    const total = dateThreads.length;
    const reviewed = dateThreads.filter(t => myVotes.has(t.id)).length;
    return { total, reviewed, done: reviewed === total };
  }

  // React to URL param changes (calendar links, leaderboard clicks)
  $effect(() => {
    const p = $page.url.searchParams.get('date');
    if (p && allDates.includes(p)) selectedDate = p;
    const r = $page.url.searchParams.get('reviewer');
    if (r) { filterReviewer = r; filterStatus = 'all'; }
  });

  // Auto-advance to next unreviewed date when current date is fully reviewed
  $effect(() => {
    if (!selectedDate || filterStatus !== 'unreviewed') return;
    const stats = dateReviewStats(selectedDate);
    if (!stats.done) return;
    // Find next date with unreviewed threads
    const idx = allDates.indexOf(selectedDate);
    const nextDate = allDates.slice(idx + 1).find(d => !dateReviewStats(d).done);
    if (nextDate) {
      // Small delay so the user sees the completion state briefly
      const timer = setTimeout(() => { selectedDate = nextDate; }, 800);
      return () => clearTimeout(timer);
    }
  });

  // ── Stats ──────────────────────────────────────────────────────────────────
  const total = threads.length;
  const reviewed = $derived(myVotes.size);
  const valid = $derived([...myVotes.values()].filter(v => v.status === 'valid').length);
  const maybe = $derived([...myVotes.values()].filter(v => v.status === 'maybe').length);
  const notValid = $derived([...myVotes.values()].filter(v => v.status === 'not_valid').length);
  const pctValid = $derived(total > 0 ? valid / total * 100 : 0);
  const pctMaybe = $derived(total > 0 ? maybe / total * 100 : 0);
  const pctNot = $derived(total > 0 ? notValid / total * 100 : 0);
  const pctReviewed = $derived(total > 0 ? Math.round(reviewed / total * 100) : 0);

  // ── UI state ───────────────────────────────────────────────────────────────
  let expandedIds = $state<Set<string>>(new Set());
  function toggle(id: string) {
    const next = new Set(expandedIds);
    if (next.has(id)) next.delete(id); else next.add(id);
    expandedIds = next;
  }

  // Track threads that are vanishing after being reviewed
  let vanishingIds = $state<Set<string>>(new Set());
  let threadsAtBottom = $state(true);
  let threadsScrollEl = $state<HTMLElement | null>(null);

  function onThreadsScroll(e: Event) {
    const el = e.target as HTMLElement;
    threadsAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 8;
  }
  // Check overflow after content renders
  $effect(() => {
    filtered;
    if (threadsScrollEl) {
      requestAnimationFrame(() => {
        if (threadsScrollEl) {
          threadsAtBottom = threadsScrollEl.scrollHeight - threadsScrollEl.scrollTop - threadsScrollEl.clientHeight < 8;
        }
      });
    }
  });


  const reasonLabels: Record<string, string> = {
    question_mark: '?', question_prefix: 'Q:', media_short_text: 'Media', session_marker: 'Session',
  };
  const reasonColors: Record<string, string> = {
    question_mark: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
    question_prefix: 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
    media_short_text: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
    session_marker: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  };
</script>


<div class="space-y-5">
  <!-- Hero tile -->
  <div class="bg-gradient-to-br from-primary-300 to-primary-900 rounded-2xl pt-3 sm:pt-6 px-6 pb-5 sm:pb-6 text-white shadow-lg relative">
    <div class="flex items-center justify-between mb-1">
      <h1 class="text-2xl font-bold">Review Candidate Questions</h1>
      {#if reviewer}
        <span class="text-xs text-primary-100 flex items-center gap-1">
          <MemberAvatar username={reviewer} size="xs" />
          {reviewer}
        </span>
      {/if}
    </div>
    <p class="text-primary-100 text-sm mb-4">Help in catching any trivia questions the extraction pipeline might have missed.<br>Your reviews make the archive better for everyone. Thank you for contributing! ❤️</p>
    <div class="flex items-center justify-between gap-3">
      <div class="flex items-center gap-2 text-sm">
        <span class="relative flex h-2.5 w-2.5">
          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-300 opacity-90"></span>
          <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-green-400"></span>
        </span>
        <a href="/review?reviewer={encodeURIComponent(reviewer)}" class="font-semibold hover:text-white/80 transition-colors">Reviewed {reviewed}/{total}</a>
        <span class="text-primary-200">{pctReviewed}% complete</span>
      </div>
    </div>
    <div class="mt-3 h-2 bg-white/20 rounded-full overflow-hidden">
      <div class="h-full flex">
        {#if pctValid > 0}<div class="bg-green-400 transition-all duration-300" style="width: {pctValid}%"></div>{/if}
        {#if pctMaybe > 0}<div class="bg-yellow-300 transition-all duration-300" style="width: {pctMaybe}%"></div>{/if}
        {#if pctNot > 0}<div class="bg-red-400 transition-all duration-300" style="width: {pctNot}%"></div>{/if}
      </div>
    </div>
  </div>

  {#if loading}
    <div class="text-center py-8">
      <p class="text-sm text-gray-400">Loading votes...</p>
    </div>
  {:else if loadError}
    <div class="text-center py-8">
      <p class="text-sm text-red-500">Failed to load votes. Please refresh the page.</p>
      <button onclick={loadVotes} class="mt-2 px-4 py-1.5 text-xs font-medium rounded-lg bg-primary-500 text-white hover:bg-primary-600">Retry</button>
    </div>
  {:else}

  <!-- Category filter pills -->
  <div class="space-y-2">
    <div class="flex flex-wrap gap-2">
      <div class="grid grid-cols-3 gap-2 sm:flex">
        <button onclick={() => { filterStatus = 'all'; selectedDate = ''; filterReviewer = ''; }} class="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all {filterStatus === 'all' && !filterReviewer ? 'bg-primary-500 text-white shadow-sm' : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'}">
          All <span class="font-bold">{total}</span>
        </button>
        <button onclick={() => { filterStatus = 'unreviewed'; selectedDate = ''; filterReviewer = ''; }} class="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all {filterStatus === 'unreviewed' && !filterReviewer ? 'bg-amber-500 dark:bg-amber-600 text-white shadow-sm' : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'}">
          <span class="w-2 h-2 rounded-full {filterStatus === 'unreviewed' ? 'bg-white' : 'bg-gray-400'}"></span>
          Pending <span class="font-bold">{total - reviewed}</span>
        </button>
        <button onclick={() => { filterReviewer = reviewer; filterStatus = 'all'; selectedDate = ''; }} class="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all {filterReviewer ? 'bg-primary-500 text-white shadow-sm' : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'}">
          <span class="w-2 h-2 rounded-full {filterReviewer ? 'bg-white' : 'bg-primary-400'}"></span>
          Reviewed <span class="font-bold">{reviewed}</span>
        </button>
      </div>
    </div>
    <div class="flex flex-wrap items-center gap-2">
      <button
        onclick={toggleSort}
        class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600 transition-all justify-center"
      >
        <svg class="w-3 h-3 transition-transform {sortBy === 'most' ? 'rotate-180' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4h13M3 8h9M3 12h5m0 0l4 4m-4-4l4-4" />
        </svg>
        {sortBy === 'least' ? 'Least votes' : 'Most votes'}
      </button>
      <button
        onclick={() => showDateRange = !showDateRange}
        class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all justify-center {showDateRange || filterDateFrom || filterDateTo ? 'bg-primary-500 text-white shadow-sm' : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'}"
      >
        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
        Date range
      </button>
      {#if showDateRange}
        <div class="flex items-center gap-1.5">
          <label for="review-date-from" class="text-xs text-gray-500 dark:text-gray-400 font-medium">From</label>
          <input id="review-date-from" bind:value={filterDateFrom} type="date" class="text-xs border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400" />
        </div>
        <div class="flex items-center gap-1.5">
          <label for="review-date-to" class="text-xs text-gray-500 dark:text-gray-400 font-medium">To</label>
          <input id="review-date-to" bind:value={filterDateTo} type="date" class="text-xs border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400" />
        </div>
      {/if}
    </div>
  </div>

  {#if filterReviewer}
    <div class="space-y-2">
      <div class="flex items-center gap-3 bg-primary-50 dark:bg-primary-900/20 px-4 py-2 rounded-lg">
        <span class="text-sm text-primary-700 dark:text-primary-300">Showing reviews by <span class="font-semibold">{filterReviewer}{filterReviewer === reviewer ? ' (you)' : ''}</span></span>
        <button
          onclick={() => { filterReviewer = ''; filterStatus = 'unreviewed'; }}
          class="text-xs text-primary-500 hover:text-primary-700 dark:text-primary-400 font-medium"
        >Clear</button>
      </div>
      <div class="flex gap-2">
        <button onclick={() => { filterStatus = filterStatus === 'valid' ? 'all' : 'valid'; }} class="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all {filterStatus === 'valid' ? 'bg-green-500 text-white shadow-sm' : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'}">
          <span class="w-2 h-2 rounded-full {filterStatus === 'valid' ? 'bg-white' : 'bg-green-500'}"></span>
          Missed Q <span class="font-bold">{valid}</span>
        </button>
        <button onclick={() => { filterStatus = filterStatus === 'maybe' ? 'all' : 'maybe'; }} class="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all {filterStatus === 'maybe' ? 'bg-yellow-500 text-white shadow-sm' : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'}">
          <span class="w-2 h-2 rounded-full {filterStatus === 'maybe' ? 'bg-white' : 'bg-yellow-400'}"></span>
          Maybe <span class="font-bold">{maybe}</span>
        </button>
        <button onclick={() => { filterStatus = filterStatus === 'not_valid' ? 'all' : 'not_valid'; }} class="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all {filterStatus === 'not_valid' ? 'bg-red-500 text-white shadow-sm' : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'}">
          <span class="w-2 h-2 rounded-full {filterStatus === 'not_valid' ? 'bg-white' : 'bg-red-400'}"></span>
          Not a Q <span class="font-bold">{notValid}</span>
        </button>
      </div>
    </div>
  {/if}

  {#if selectedDate}
    {@const stats = dateReviewStats(selectedDate)}
    <div class="flex items-center gap-3">
      <button
        onclick={() => selectedDate = ''}
        class="text-xs text-primary-500 hover:text-primary-600 dark:text-primary-400 flex items-center gap-1"
      >
        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" /></svg>
        All dates
      </button>
      <h2 class="text-sm font-semibold text-gray-900 dark:text-gray-100">{selectedDate}</h2>
      <span class="text-xs text-gray-400">{stats.reviewed}/{stats.total} reviewed</span>
      {#if stats.done}
        <svg class="w-3.5 h-3.5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" /></svg>
      {/if}
    </div>
  {/if}

  <!-- Threads -->
  <div class="relative">
  {#if !threadsAtBottom && filtered.length > 0}
    <div class="hidden lg:block pointer-events-none absolute inset-x-0 bottom-0 h-50 bg-gradient-to-t from-gray-50 dark:from-gray-900 to-transparent z-10 transition-opacity duration-300"></div>
  {/if}
  <div class="lg:max-h-[92vh] lg:overflow-y-auto space-y-6 pr-1 scrollbar-hide" bind:this={threadsScrollEl} onscroll={onThreadsScroll}>
    {#each visibleDates as date}
      <div class="relative {!selectedDate ? 'pl-7' : ''}">
      <!-- Date header (only when showing all dates) -->
      {#if !selectedDate}
        {@const stats = dateReviewStats(date)}
        <!-- Timeline vertical line connecting to threads -->
        <div class="absolute left-[6px] top-[22px] bottom-3 w-[3px] rounded-full bg-primary-200 dark:bg-primary-800/60"></div>
        <div class="flex items-center gap-3 {visibleDates.indexOf(date) > 0 ? 'pt-2' : ''}">
          <!-- Timeline dot — inside flex row so it always aligns with the date text -->
          <div class="absolute left-0 w-3.5 h-3.5 rounded-full bg-primary-500 dark:bg-primary-400 border-[3px] border-white dark:border-gray-900 shadow-sm z-10"></div>
          <button onclick={() => selectedDate = date} class="text-sm font-semibold text-gray-900 dark:text-gray-100 hover:text-primary-600 dark:hover:text-primary-400 transition-colors">{date}</button>
          <span class="text-xs text-gray-400 dark:text-gray-500">{filtered.filter(t => t.date === date).length} thread{filtered.filter(t => t.date === date).length > 1 ? 's' : ''}</span>
          <div class="flex items-center gap-2">
            <div class="w-12 h-1.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
              <div class="h-full bg-green-400 rounded-full transition-all duration-300" style="width: {stats.total > 0 ? stats.reviewed / stats.total * 100 : 0}%"></div>
            </div>
            <span class="text-[10px] text-gray-400">{stats.reviewed}/{stats.total}</span>
          </div>
          <div class="flex-1 border-t border-gray-200 dark:border-gray-700"></div>
        </div>
      {/if}

      <div class="space-y-3">
    {#each filtered.filter(t => t.date === date) as thread (thread.id)}
      {@const myVote = myVotes.get(thread.id)}
      {@const status = myVote?.status}
      {@const tally = voteTally(thread.id)}
      <div class="bg-ui-card rounded-xl border overflow-hidden transition-all duration-300 {vanishingIds.has(thread.id) ? 'opacity-0 scale-95 -translate-x-4' : ''} {status === 'valid' ? 'border-green-300 dark:border-green-700 bg-green-50/30 dark:bg-green-900/10' : status === 'maybe' ? 'border-yellow-300 dark:border-yellow-700 bg-yellow-50/30 dark:bg-yellow-900/10' : status === 'not_valid' ? 'border-red-200 dark:border-red-800 opacity-50' : 'border-gray-200 dark:border-gray-700'}">
        <div class="p-4">
          {#each thread.candidates as cand, ci}
            {@const dt = fmtDateTime(cand.timestamp)}
            <div class="flex items-start gap-3 {ci > 0 ? 'mt-3 pt-3 border-t border-gray-100 dark:border-gray-700' : ''}">
              <MemberAvatar username={cand.username} />
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="text-sm font-medium text-gray-900 dark:text-gray-100">{cand.username}</span>
                  <span class="text-xs text-gray-400">{dt.date} {dt.time}</span>
                  <span class="px-1.5 py-0.5 rounded text-[10px] font-medium {reasonColors[cand.reason_flagged] ?? 'bg-gray-100 text-gray-600'}">
                    {reasonLabels[cand.reason_flagged] ?? cand.reason_flagged}
                  </span>
                  {#if ci === 0}
                    <span class="ml-auto relative flex-shrink-0">
                      {#if tally.total > 0}
                        <button
                          onclick={() => { const id = `votes-${thread.id}`; const el = document.getElementById(id); if (el) el.classList.toggle('hidden'); }}
                          class="px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-[10px] font-medium text-gray-500 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600 cursor-pointer transition-colors"
                        >{tally.total} vote{tally.total !== 1 ? 's' : ''}</button>
                        <div id="votes-{thread.id}" class="hidden absolute right-0 top-6 z-10 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg p-2 min-w-[120px]">
                          {#each tally.votes as v}
                            <div class="py-0.5 text-[11px] font-medium text-gray-700 dark:text-gray-300">{v.reviewer}</div>
                          {/each}
                        </div>
                      {:else}
                        <span class="px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-[10px] font-medium text-gray-400 dark:text-gray-400">0 votes</span>
                      {/if}
                    </span>
                  {/if}
                </div>
                <p class="text-sm text-gray-800 dark:text-gray-200 mt-1 leading-relaxed whitespace-pre-wrap">{cand.text}</p>
              </div>
            </div>
          {/each}


          <!-- Actions row -->
          <div class="mt-3 flex items-center justify-between">
            <button
              onclick={() => toggle(thread.id)}
              class="text-xs text-primary-500 dark:text-primary-400 hover:text-primary-600 flex items-center gap-1"
            >
              <svg class="w-3 h-3 transition-transform {expandedIds.has(thread.id) ? 'rotate-90' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
              </svg>
              {expandedIds.has(thread.id) ? 'Hide' : 'Show'} context
            </button>
            <div class="flex items-center gap-1.5">
              <button
                onclick={() => startVote(thread.id, 'valid')}
                class="px-3 py-1 rounded-lg text-xs font-medium transition-all {status === 'valid' ? 'bg-green-500 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-300 hover:bg-green-100 hover:text-green-700 dark:hover:bg-green-900/30 dark:hover:text-green-400'}"
              >Missed Q</button>
              <button
                onclick={() => startVote(thread.id, 'maybe')}
                class="px-3 py-1 rounded-lg text-xs font-medium transition-all {status === 'maybe' ? 'bg-yellow-500 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-300 hover:bg-yellow-100 hover:text-yellow-700 dark:hover:bg-yellow-900/30 dark:hover:text-yellow-400'}"
              >Maybe</button>
              <button
                onclick={() => startVote(thread.id, 'not_valid')}
                class="px-3 py-1 rounded-lg text-xs font-medium transition-all {status === 'not_valid' ? 'bg-red-500 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-300 hover:bg-red-100 hover:text-red-700 dark:hover:bg-red-900/30 dark:hover:text-red-400'}"
              >Not a Q</button>
            </div>
          </div>

          <!-- Reason picker -->
          {#if reasonOpenFor?.id === thread.id}
            {@const presets = reasonPresets[reasonOpenFor.status]}
            {@const statusColors = { valid: 'border-green-300 bg-green-50/50 dark:border-green-700 dark:bg-green-900/10', maybe: 'border-yellow-300 bg-yellow-50/50 dark:border-yellow-700 dark:bg-yellow-900/10', not_valid: 'border-red-200 bg-red-50/50 dark:border-red-800 dark:bg-red-900/10' }}
            {@const chipColors = { valid: 'bg-green-100 text-green-700 hover:bg-green-200 dark:bg-green-900/30 dark:text-green-300 dark:hover:bg-green-900/50', maybe: 'bg-yellow-100 text-yellow-700 hover:bg-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-300 dark:hover:bg-yellow-900/50', not_valid: 'bg-red-100 text-red-700 hover:bg-red-200 dark:bg-red-900/30 dark:text-red-300 dark:hover:bg-red-900/50' }}
            <div class="mt-3 p-3 rounded-lg border {statusColors[reasonOpenFor.status]}">
              <p class="text-[10px] font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">Select a reason</p>
              <div class="flex flex-wrap gap-1.5 mb-2">
                {#each presets as preset}
                  <button
                    onclick={() => confirmVote(preset)}
                    class="px-2.5 py-1 rounded-full text-xs font-medium transition-colors cursor-pointer {chipColors[reasonOpenFor.status]}"
                  >{preset}</button>
                {/each}
              </div>
              <div class="flex gap-2">
                <input
                  type="text"
                  placeholder="Or type a custom reason..."
                  bind:value={customReasonText}
                  onkeydown={(e) => { if (e.key === 'Enter') submitCustomReason(); }}
                  class="flex-1 text-xs border border-gray-200 dark:border-gray-600 rounded-lg px-2.5 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400"
                />
                <button
                  onclick={submitCustomReason}
                  disabled={!customReasonText.trim()}
                  class="px-3 py-1.5 text-xs font-medium rounded-lg transition-colors {customReasonText.trim() ? 'bg-primary-500 text-white hover:bg-primary-600' : 'bg-gray-200 text-gray-400 dark:bg-gray-700 dark:text-gray-500'}"
                >Send</button>
              </div>
            </div>
          {/if}

          <!-- Show saved reason + other votes -->
          {#if myVote?.reason && reasonOpenFor?.id !== thread.id}
            <div class="mt-2 text-xs text-gray-500 dark:text-gray-400 italic">
              You: "{myVote.reason}"
            </div>
          {/if}
          {#if tally.votes.filter(v => v.reviewer !== reviewer && v.reason).length > 0 && expandedIds.has(thread.id)}
            <div class="mt-2 space-y-1">
              {#each tally.votes.filter(v => v.reviewer !== reviewer && v.reason) as v}
                <div class="text-xs text-gray-400 dark:text-gray-500">
                  <span class="font-medium text-gray-500 dark:text-gray-400">{v.reviewer}:</span>
                  <span class="{v.status === 'valid' ? 'text-green-600 dark:text-green-400' : v.status === 'maybe' ? 'text-yellow-600 dark:text-yellow-400' : 'text-red-500 dark:text-red-400'}">{v.status.replace('_', ' ')}</span>
                  — <span class="italic">"{v.reason}"</span>
                </div>
              {/each}
            </div>
          {/if}
        </div>

        <!-- Context as chat bubbles -->
        {#if expandedIds.has(thread.id)}
          <div class="border-t border-gray-100 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 px-4 py-3 max-h-80 overflow-y-auto space-y-2">
            {#each thread.context as msg}
              {@const ctxDt = fmtDateTime(msg.timestamp)}
              {@const linkedQ = questionsByTs.get(msg.timestamp)}
              <div class="flex items-start gap-2
                {msg.is_candidate ? 'bg-primary-50 dark:bg-primary-900/20 -mx-2 px-2 py-1.5 rounded-lg border-l-3 border-primary-400' :
                 linkedQ ? 'bg-green-50 dark:bg-green-900/10 -mx-2 px-2 py-1.5 rounded-lg border-l-3 border-green-400' : ''}">
                <MemberAvatar username={msg.username} size="xs" />
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-1.5">
                    <span class="text-xs font-medium {msg.is_candidate ? 'text-primary-700 dark:text-primary-300' : linkedQ ? 'text-green-700 dark:text-green-300' : 'text-gray-700 dark:text-gray-300'}">{msg.username}</span>
                    <span class="text-[10px] text-gray-400 dark:text-gray-500">{ctxDt.date} {ctxDt.time}</span>
                    {#if linkedQ}
                      <a href="/question/{linkedQ.id}" class="text-[10px] font-medium text-green-600 dark:text-green-400 hover:text-green-700 dark:hover:text-green-300 transition-colors">Extracted Question &rarr;</a>
                    {/if}
                  </div>
                  <p class="text-xs {msg.is_candidate ? 'text-primary-800 dark:text-primary-200 font-medium' : linkedQ ? 'text-green-800 dark:text-green-200' : 'text-gray-600 dark:text-gray-400'} leading-relaxed whitespace-pre-wrap">{msg.text}</p>
                </div>
              </div>
            {/each}
          </div>
        {/if}
      </div>
    {/each}
      </div>
      </div>
    {/each}
  </div>
  </div>

  {#if filtered.length === 0}
    <div class="text-center py-12">
      <p class="text-gray-400 dark:text-gray-500">{reviewed === total ? 'All done! Thank you for reviewing.' : 'No threads match this filter.'}</p>
    </div>
  {/if}

  {/if}
</div>

