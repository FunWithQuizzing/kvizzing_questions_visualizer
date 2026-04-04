<script lang="ts">
  import '../app.css';
  import { setContext } from 'svelte';
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import favicon from '$lib/assets/favicon.svg';
  import { QuestionStore } from '$lib/stores/questionStore';
  import { tzAbbr, dateInTz, formatDateTz } from '$lib/utils/time';
  import { SESSION_IMAGE_OPACITY, sessionBgUrl } from '$lib/config/ui';
  import CalendarSidebar from '$lib/components/CalendarSidebar.svelte';
  import BaseCalendar, { type Cell } from '$lib/components/BaseCalendar.svelte';
  import MaraudersAuth from '$lib/components/MaraudersAuth.svelte';

  let { children, data } = $props();

  // Data is static (prerendered), so we construct the store once from the initial load.
  // eslint-disable-next-line svelte/no-unused-svelte-ignore
  // svelte-ignore state_referenced_locally
  const store = new QuestionStore(data.questions, data.sessions, data.members, data.tags ?? [], data.stats ?? null);
  setContext('store', store);

  const TIMEZONES = [
    { id: 'UTC',                   label: 'UTC',                aliases: 'universal gmt' },
    { id: 'Europe/London',         label: 'London',             aliases: 'uk england britain ireland' },
    { id: 'Europe/Paris',          label: 'Paris / Berlin',     aliases: 'france germany amsterdam brussels rome milan madrid spain italy netherlands europe' },
    { id: 'Europe/Helsinki',       label: 'Helsinki / Athens',  aliases: 'finland greece sofia bucharest riga tallinn vilnius' },
    { id: 'Europe/Moscow',         label: 'Moscow',             aliases: 'russia st petersburg' },
    { id: 'Africa/Nairobi',        label: 'Nairobi',            aliases: 'kenya east africa ethiopia somalia tanzania uganda' },
    { id: 'Asia/Dubai',            label: 'Dubai',              aliases: 'uae abu dhabi gulf oman muscat' },
    { id: 'Asia/Karachi',          label: 'Karachi',            aliases: 'pakistan lahore islamabad' },
    { id: 'Asia/Kolkata',          label: 'India (IST)',        aliases: 'india mumbai delhi bangalore chennai hyderabad pune kolkata ahmedabad indian' },
    { id: 'Asia/Dhaka',            label: 'Dhaka',              aliases: 'bangladesh' },
    { id: 'Asia/Bangkok',          label: 'Bangkok / Jakarta',  aliases: 'thailand indonesia vietnam cambodia' },
    { id: 'Asia/Singapore',        label: 'Singapore / KL',     aliases: 'malaysia kuala lumpur philippines manila' },
    { id: 'Asia/Tokyo',            label: 'Tokyo / Seoul',      aliases: 'japan korea' },
    { id: 'Australia/Perth',       label: 'Perth',              aliases: 'australia western' },
    { id: 'Australia/Sydney',      label: 'Sydney',             aliases: 'australia melbourne brisbane canberra aest' },
    { id: 'Pacific/Auckland',      label: 'Auckland',           aliases: 'new zealand nzt nzst nzdt' },
    { id: 'America/New_York',      label: 'New York (ET)',      aliases: 'usa east coast boston washington dc miami atlanta' },
    { id: 'America/Chicago',       label: 'Chicago (CT)',       aliases: 'usa central dallas houston' },
    { id: 'America/Denver',        label: 'Denver (MT)',        aliases: 'usa mountain phoenix' },
    { id: 'America/Los_Angeles',   label: 'Los Angeles (PT)',   aliases: 'usa west coast california san francisco seattle' },
    { id: 'America/Sao_Paulo',     label: 'São Paulo',          aliases: 'brazil rio' },
  ];
  function tzOffsetMinutes(tzId: string): number {
    try {
      const now = new Date();
      const parts = new Intl.DateTimeFormat('en', {
        timeZone: tzId,
        year: 'numeric', month: 'numeric', day: 'numeric',
        hour: 'numeric', minute: 'numeric', second: 'numeric', hour12: false,
      }).formatToParts(now);
      const get = (t: string) => Number(parts.find(p => p.type === t)?.value ?? 0);
      const local = Date.UTC(get('year'), get('month') - 1, get('day'), get('hour') % 24, get('minute'), get('second'));
      return Math.round((local - now.getTime()) / 60000);
    } catch { return 0; }
  }

  const TIMEZONES_SORTED = [...TIMEZONES].sort((a, b) => tzOffsetMinutes(a.id) - tzOffsetMinutes(b.id));

  const tz = $state({ value: 'Europe/London' });
  setContext('timezone', tz);

  // ── Site-wide user identity ───────────────────────────────────────────────
  let username = $state({ value: '' });
  let showUsernamePrompt = $state(false);
  let usernameInput = $state('');
  setContext('username', username);

  // ── Flagged question IDs (loaded once, shared with all QuestionCards) ──
  let flaggedIds = $state({ value: new Set<string>() });
  setContext('flaggedIds', flaggedIds);

  async function loadFlaggedIds(reporter: string) {
    if (!reporter) return;
    try {
      const { supabase: sb } = await import('$lib/supabase');
      const { data } = await sb.from('question_flags').select('question_id').eq('reporter', reporter);
      if (data) flaggedIds.value = new Set(data.map(r => r.question_id));
    } catch {}
  }

  async function setUsername() {
    const name = usernameInput.trim();
    if (!name) return;
    username.value = name;
    localStorage.setItem('kvizzing-reviewer-name', name);
    showUsernamePrompt = false;
    loadFlaggedIds(name);
    // Upsert to Supabase users table
    try {
      const { supabase: sb } = await import('$lib/supabase');
      await sb.from('users').upsert(
        { username: name, last_seen_at: new Date().toISOString() },
        { onConflict: 'username' }
      );
    } catch {}
  }

  const sidebarSessions = store.getSessions();
  const sidebarQuestions = store.getQuestions();
  const sidebarSessionTs = store.getSessionEarliestTimestamps();
  const totalStats = store.getTotalStats();
  const sessionQuestionCount = sidebarSessions.reduce((sum, s) => sum + s.question_count, 0);
  const askerCount = store.getAskers().length;
  const solverCount = store.getSolvers().length;
  const sinceDate = $derived(totalStats.earliestTimestamp ? formatDateTz(totalStats.earliestTimestamp, tz.value) : '');
  function surpriseMe() { const q = store.random(); if (q) goto(`/question/${q.id}`); }
  function randomQuiz() { if (sidebarSessions.length === 0) return; const s = sidebarSessions[Math.floor(Math.random() * sidebarSessions.length)]; goto(`/session/${s.id}`); }

  // ── Review sidebar data ────────────────────────────────────────────────────
  type ReviewThread = { id: string; date: string; candidates: { timestamp: string; username: string; text: string }[] };

  let reviewThreads = $state<ReviewThread[]>([]);

  onMount(() => {
    fetch('/data/rejected_candidates.json')
      .then(r => r.ok ? r.json() : [])
      .then(d => { reviewThreads = d; })
      .catch(() => {});
  });

  // Review calendar month navigation
  let reviewCalendarMonth = $state('');  // '' = auto-detect first month with data

  // Review calendar data: dates → { total, threads with any votes }
  let reviewAllVotes = $state<{ thread_id: string; status: string }[]>([]);

  async function refreshReviewVotes() {
    if (reviewThreads.length === 0) return;
    try {
      const { supabase: sb } = await import('$lib/supabase');
      const { data: rows } = await sb.from('votes').select('thread_id, status');
      if (rows) reviewAllVotes = rows;
    } catch {}
  }

  // Load votes for calendar (runs on mount)
  $effect(() => {
    if (reviewThreads.length > 0 && reviewAllVotes.length === 0) {
      refreshReviewVotes();
    }
  });

  const reviewDateStats = $derived(() => {
    const map = new Map<string, { total: number; reviewed: number; valid: number; maybe: number; notValid: number }>();
    for (const t of reviewThreads) {
      if (!map.has(t.date)) map.set(t.date, { total: 0, reviewed: 0, valid: 0, maybe: 0, notValid: 0 });
      const s = map.get(t.date)!;
      s.total++;
      // Count threads that have at least one vote
      const threadVotes = reviewAllVotes.filter(v => v.thread_id === t.id);
      if (threadVotes.length > 0) {
        s.reviewed++;
        // Use majority vote for color
        const validCount = threadVotes.filter(v => v.status === 'valid').length;
        const maybeCount = threadVotes.filter(v => v.status === 'maybe').length;
        const notCount = threadVotes.filter(v => v.status === 'not_valid').length;
        if (validCount >= maybeCount && validCount >= notCount) s.valid++;
        else if (maybeCount >= notCount) s.maybe++;
        else s.notValid++;
      }
    }
    return map;
  });

  // Review leaderboard from Supabase
  let reviewLeaderboardData = $state<{ reviewer: string; count: number }[]>([]);
  let currentReviewer = $state('');

  async function refreshLeaderboard() {
    try {
      const { supabase: sb } = await import('$lib/supabase');
      const { data: rows } = await sb.from('votes').select('reviewer');
      if (rows) {
        const counts = new Map<string, number>();
        for (const r of rows) counts.set(r.reviewer, (counts.get(r.reviewer) || 0) + 1);
        const board: { reviewer: string; count: number }[] = [];
        for (const [name, count] of counts) {
          if (count > 0) board.push({ reviewer: name, count });
        }
        reviewLeaderboardData = board.sort((a, b) => b.count - a.count || a.reviewer.localeCompare(b.reviewer));
      }
    } catch {}
  }

  onMount(() => {
    const saved = localStorage.getItem('kvizzing-reviewer-name') || '';
    if (saved) {
      username.value = saved;
      usernameInput = saved;
    } else {
      showUsernamePrompt = true;
    }
    currentReviewer = saved;
    if (saved) loadFlaggedIds(saved);
    refreshLeaderboard();
    // Update last_seen_at on every visit
    if (saved) {
      import('$lib/supabase').then(({ supabase: sb }) => {
        sb.from('users').upsert(
          { username: saved, last_seen_at: new Date().toISOString() },
          { onConflict: 'username' }
        );
      }).catch(() => {});
    }
    // Listen for vote changes from the review page
    window.addEventListener('kvizzing-vote-changed', () => { refreshLeaderboard(); refreshReviewVotes(); });
  });

  const MONTHS_SHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  function ordinalDate(dateStr: string): string {
    const [y, m, d] = dateStr.split('-').map(Number);
    const suffix = [11,12,13].includes(d) ? 'th'
      : d % 10 === 1 ? 'st' : d % 10 === 2 ? 'nd' : d % 10 === 3 ? 'rd' : 'th';
    return `${d}${suffix} ${MONTHS_SHORT[m - 1]} ${y}`;
  }

  let authenticated = $state<boolean | null>(null);
  const dm = $state({ value: false });
  let showTzPicker = $state(false);

  // R2 free-tier usage alert (75% threshold)
  const R2_WARN_PCT = 75;
  let r2AlertDismissed = $state(false);
  const r2Alerts = $derived.by(() => {
    const u = data.r2Usage;
    if (!u) return [];
    const alerts: { label: string; pct: number; used: string; limit: string }[] = [];
    if (u.storage_pct >= R2_WARN_PCT)
      alerts.push({ label: 'Storage', pct: u.storage_pct, used: `${(u.storage_bytes / 1024 ** 3).toFixed(2)} GB`, limit: '10 GB' });
    if (u.class_a_pct >= R2_WARN_PCT)
      alerts.push({ label: 'Class A ops', pct: u.class_a_pct, used: u.class_a_ops.toLocaleString(), limit: '1M' });
    if (u.class_b_pct >= R2_WARN_PCT)
      alerts.push({ label: 'Class B ops', pct: u.class_b_pct, used: u.class_b_ops.toLocaleString(), limit: '10M' });
    return alerts;
  });
  let tzSearch = $state('');
  let showThemePicker = $state(false);
  let showUserMenu = $state(false);

  const THEMES = [
    { id: 'sky',     label: 'Blue',   color: '#0ea5e9' },
    { id: 'violet',  label: 'Violet', color: '#8b5cf6' },
    { id: 'emerald', label: 'Green',  color: '#10b981' },
    { id: 'rose',    label: 'Rose',   color: '#f43f5e' },
    { id: 'amber',   label: 'Amber',  color: '#f59e0b' },
  ];
  let colorTheme = $state('sky');

  onMount(() => {
    authenticated = localStorage.getItem('kvizzing_auth_v2') === 'true';
    dm.value = localStorage.getItem('kvizzing_dark') === 'true';
    if (dm.value) document.documentElement.classList.add('dark');
    const saved = localStorage.getItem('kvizzing_theme') ?? 'sky';
    colorTheme = saved;
    applyTheme(saved);
    const savedTz = localStorage.getItem('kvizzing_tz');
    if (savedTz) {
      tz.value = savedTz;
    } else {
      showTzPicker = true;
    }
  });

  // Clear search when picker reopens so it never starts pre-filtered
  $effect(() => { if (showTzPicker) tzSearch = ''; });

  function applyTheme(id: string) {
    document.documentElement.classList.add('no-transitions');
    if (id === 'sky') {
      document.documentElement.removeAttribute('data-theme');
    } else {
      document.documentElement.setAttribute('data-theme', id);
    }
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        document.documentElement.classList.remove('no-transitions');
      });
    });
  }

  function cycleTheme() {
    const idx = THEMES.findIndex(t => t.id === colorTheme);
    const next = THEMES[(idx + 1) % THEMES.length];
    colorTheme = next.id;
    localStorage.setItem('kvizzing_theme', next.id);
    applyTheme(next.id);
  }

  function toggleDark() {
    // Disable transitions during theme switch to prevent lag from
    // hundreds of elements animating background/color simultaneously
    document.documentElement.classList.add('no-transitions');
    dm.value = !dm.value;
    localStorage.setItem('kvizzing_dark', String(dm.value));
    document.documentElement.classList.toggle('dark', dm.value);
    // Re-enable after a single frame so the browser paints the new colors first
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        document.documentElement.classList.remove('no-transitions');
      });
    });
  }

  function onAuthenticated() {
    localStorage.setItem('kvizzing_auth_v2', 'true');
    authenticated = true;
  }

  function logout() {
    localStorage.removeItem('kvizzing_auth_v2');
    authenticated = false;
  }

  let mobileMenuOpen = $state(false);

  const navLinks = [
    { href: '/', label: 'Feed' },
    { href: '/sessions', label: 'Quiz sessions' },
    { href: '/highlights', label: 'Highlights' },
  ];

  function isActive(href: string, currentPath: string): boolean {
    if (href === '/') return currentPath === '/';
    return currentPath.startsWith(href);
  }
</script>

{#snippet reviewSidebar()}
  <!-- Review Calendar -->
  {@const stats = reviewDateStats()}
  {@const dates = [...stats.keys()].sort()}
  {@const months = [...new Set(dates.map(d => d.slice(0, 7)))].sort()}
  {@const activeMonth = reviewCalendarMonth || (months.length > 0 ? months[0] : new Date().toISOString().slice(0, 7))}
  {@const monthIdx = months.indexOf(activeMonth)}
  {@const [calY, calM] = activeMonth.split('-').map(Number)}
  <BaseCalendar
    year={calY} month={calM}
    canGoPrev={monthIdx > 0}
    canGoNext={monthIdx < months.length - 1}
    prevMonth={() => { if (monthIdx > 0) reviewCalendarMonth = months[monthIdx - 1]; }}
    nextMonth={() => { if (monthIdx < months.length - 1) reviewCalendarMonth = months[monthIdx + 1]; }}
  >
    {#snippet dayContent(cell: Cell)}
      {@const dayStat = cell.inMonth ? stats.get(cell.dateStr) : undefined}
      {@const pct = dayStat && dayStat.total > 0 ? dayStat.reviewed / dayStat.total : 0}
      <svelte:element this={dayStat ? 'a' : 'div'}
        href={dayStat ? `/review?date=${cell.dateStr}` : undefined}
        class="flex flex-col items-center py-0.5 px-0.5 rounded-lg transition-colors
          {dayStat ? 'cursor-pointer' : 'cursor-default'}
          {dayStat && pct === 1 ? 'hover:bg-green-50 dark:hover:bg-green-900/20' :
           dayStat && pct > 0 ? 'hover:bg-amber-50 dark:hover:bg-amber-900/20' :
           dayStat ? 'hover:bg-primary-50 dark:hover:bg-primary-900/20' : ''}
          {!cell.inMonth ? 'opacity-20' : ''}"
        title={dayStat ? `${cell.dateStr}: ${dayStat.reviewed}/${dayStat.total} reviewed` : undefined}
      >
        <span class="text-xs font-medium w-6 h-6 flex items-center justify-center rounded-full flex-shrink-0
          {dayStat && pct === 1 ? 'text-green-700 dark:text-green-300 font-semibold' :
           dayStat && pct > 0 ? 'text-amber-700 dark:text-amber-300 font-semibold' :
           dayStat ? 'text-gray-800 dark:text-gray-200 font-semibold' :
           'text-gray-400 dark:text-gray-500'}"
        >{cell.day}</span>
        <span class="w-full text-center text-[10px] font-semibold leading-none px-0.5 py-[2px] rounded mt-px
          {dayStat && pct === 1 ? 'bg-green-100 dark:bg-green-900/40 text-green-600 dark:text-green-400' :
           dayStat && pct > 0 ? 'bg-amber-100 dark:bg-amber-900/40 text-amber-600 dark:text-amber-400' :
           dayStat ? 'bg-primary-50 dark:bg-primary-900/20 text-primary-500 dark:text-primary-400' :
           'invisible'}"
        >{dayStat ? `${dayStat.reviewed}/${dayStat.total}` : '0'}</span>
      </svelte:element>
    {/snippet}
  </BaseCalendar>

  <!-- Top Reviewers -->
  {@const leaderboard = reviewLeaderboardData}
  {@const myIdx = leaderboard.findIndex(s => s.reviewer === currentReviewer)}
  <div class="bg-ui-card rounded-xl border border-stone-200/80 dark:border-zinc-600/80 shadow-sm overflow-hidden">
    <div class="px-4 py-3 border-b border-stone-100 dark:border-zinc-700/80">
      <h2 class="text-xs font-semibold text-gray-500 dark:text-gray-400">Top Reviewers</h2>
    </div>
    <div class="relative">
      {#if leaderboard.length > 8}
        <div class="pointer-events-none absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-white dark:from-[#1c1c1c] to-transparent z-10"></div>
      {/if}
      <div class="divide-y divide-stone-100 dark:divide-zinc-700/80 max-h-80 overflow-y-auto">
        {#each leaderboard as sub, i}
          {@const isMe = sub.reviewer === currentReviewer}
          <a
            href="/review?reviewer={encodeURIComponent(sub.reviewer)}"
            class="px-4 py-2.5 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors {isMe ? 'bg-primary-50/50 dark:bg-primary-900/10' : ''}"
          >
            <div class="flex items-center gap-2.5">
              <span class="text-xs font-bold w-5 text-center {i === 0 ? 'text-yellow-500' : i === 1 ? 'text-slate-400' : i === 2 ? 'text-orange-700 dark:text-orange-500' : 'text-gray-300 dark:text-gray-600'}">{i + 1}</span>
              <span class="text-sm font-medium {isMe ? 'text-primary-600 dark:text-primary-400' : 'text-gray-900 dark:text-gray-100'}">{sub.reviewer}{isMe ? ' (you)' : ''}</span>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-xs font-semibold {sub.count > 0 ? 'text-primary-500' : 'text-gray-300 dark:text-gray-600'}">{sub.count}</span>
              <span class="text-[10px] text-gray-400">reviews</span>
            </div>
          </a>
        {/each}
      </div>
    </div>
    <!-- Pinned current user row (always visible if not in view or not on board) -->
    {#if currentReviewer && (myIdx >= 8 || myIdx < 0)}
      {@const meCount = myIdx >= 0 ? leaderboard[myIdx].count : 0}
      {@const meRank = myIdx >= 0 ? myIdx + 1 : leaderboard.length + 1}
      <a
        href="/review?reviewer={encodeURIComponent(currentReviewer)}"
        class="px-4 py-2.5 flex items-center justify-between border-t border-stone-200 dark:border-zinc-600 bg-primary-50/50 dark:bg-primary-900/10"
      >
        <div class="flex items-center gap-2.5">
          <span class="text-xs font-bold w-5 text-center text-gray-400 dark:text-gray-500">{meRank}</span>
          <span class="text-sm font-medium text-primary-600 dark:text-primary-400">{currentReviewer} (you)</span>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-xs font-semibold {meCount > 0 ? 'text-primary-500' : 'text-gray-300 dark:text-gray-600'}">{meCount}</span>
          <span class="text-[10px] text-gray-400">reviews</span>
        </div>
      </a>
    {/if}
  </div>
{/snippet}

<svelte:head>
  <link rel="icon" href={favicon} />
  <meta name="robots" content="noindex" />
  <title>KVizzing</title>
</svelte:head>

{#if authenticated === null}
  <!-- waiting for localStorage check — render nothing to avoid flash -->
{:else if !authenticated}
  <MaraudersAuth {onAuthenticated} />
{:else}

<div class="h-screen flex flex-col bg-ui-parchment overflow-hidden">
  <!-- R2 free-tier usage alert -->
  {#if r2Alerts.length > 0 && !r2AlertDismissed}
    <div class="flex-shrink-0 bg-amber-50 dark:bg-amber-950/60 border-b border-amber-300 dark:border-amber-700 px-4 py-2 flex items-center gap-3 z-50">
      <span class="text-amber-600 dark:text-amber-400 text-lg leading-none">⚠</span>
      <p class="flex-1 text-sm text-amber-800 dark:text-amber-300">
        <span class="font-semibold">R2 free-tier alert:</span>
        {#each r2Alerts as alert, i}
          {#if i > 0}<span class="mx-1 opacity-50">·</span>{/if}
          <span>{alert.label} at <span class="font-semibold">{alert.pct}%</span> ({alert.used} / {alert.limit})</span>
        {/each}
        <span class="ml-1 opacity-70">— run <code class="font-mono bg-amber-100 dark:bg-amber-900/50 px-1 rounded">check-r2</code> for details.</span>
      </p>
      <button
        onclick={() => r2AlertDismissed = true}
        class="text-amber-600 dark:text-amber-400 hover:text-amber-800 dark:hover:text-amber-200 transition-colors p-1 rounded"
        aria-label="Dismiss alert"
      >✕</button>
    </div>
  {/if}

  <!-- Top nav -->
  <nav class="bg-white/97 dark:bg-zinc-900/88 backdrop-blur-md border-b border-stone-200/90 dark:border-zinc-700/70 flex-shrink-0 z-40 shadow-sm">
    <div class="max-w-7xl mx-auto px-4 sm:px-6">
      <div class="flex items-center justify-between h-14">
        <!-- Logo -->
        <a href="/" class="flex items-center gap-2 group">
          <div class="w-8 h-8 rounded-lg bg-primary-500 flex items-center justify-center text-white font-bold text-sm group-hover:bg-primary-600 transition-colors">
            KV
          </div>
          <span class="font-bold text-gray-900 dark:text-white text-lg tracking-tight">KVizzing</span>
        </a>

        <!-- Desktop nav links (left) -->
        <div class="hidden sm:flex items-center gap-1 ml-4">
          {#each navLinks as link}
            <a
              href={link.href}
              class="px-3 py-1.5 rounded-lg text-sm font-medium transition-colors {isActive(link.href, $page.url.pathname)
                ? 'bg-primary-50 text-primary-600 dark:bg-primary-500/20 dark:text-primary-400'
                : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-300 dark:hover:text-white dark:hover:bg-gray-700'}"
            >
              {link.label}
            </a>
          {/each}
        </div>

        <!-- Spacer -->
        <div class="hidden sm:block flex-1"></div>

        <!-- Preferences (right) -->
        <div class="hidden sm:flex items-center gap-1">
          <!-- Review -->
          <a
            href="/review"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors {isActive('/review', $page.url.pathname)
              ? 'text-primary-600 dark:text-primary-400'
              : 'text-gray-500 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-white dark:hover:bg-gray-700'}"
          ><span class="text-xs font-medium">Review</span></a>
          <!-- Feedback -->
          <a
            href="https://docs.google.com/forms/d/e/1FAIpQLSeFsl3cKK7Tf3-iuzkPxPWmWkvRpZfB3U27PeZDun9NIqAt6A/viewform"
            target="_blank"
            rel="noopener noreferrer"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-gray-500 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-white dark:hover:bg-gray-700 transition-colors"
            aria-label="Give feedback"
          >
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
            <span class="text-xs font-medium">Feedback</span>
          </a>

          <!-- Color theme -->
          <div class="relative">
            <button
              onclick={() => showThemePicker = !showThemePicker}
              class="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              aria-label="Change color theme"
              title="Theme: {THEMES.find(t => t.id === colorTheme)?.label}"
            >
              <span class="block w-4 h-4 rounded-full border-2 border-white dark:border-gray-800 ring-1 ring-gray-300 dark:ring-gray-600 shadow-sm" style="background-color: {THEMES.find(t => t.id === colorTheme)?.color}"></span>
            </button>
            {#if showThemePicker}
              <!-- svelte-ignore a11y_click_events_have_key_events -->
              <div class="fixed inset-0 z-40" role="presentation" onclick={() => showThemePicker = false}></div>
              <div
                class="absolute right-0 top-full mt-1 z-50 bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 p-2 flex gap-2"
                role="menu"
              >
                {#each THEMES as theme}
                  <button
                    onclick={() => { colorTheme = theme.id; localStorage.setItem('kvizzing_theme', theme.id); applyTheme(theme.id); showThemePicker = false; }}
                    class="w-6 h-6 rounded-full border-2 transition-transform hover:scale-110 {colorTheme === theme.id ? 'border-gray-800 dark:border-white scale-110' : 'border-white dark:border-gray-800 ring-1 ring-gray-300 dark:ring-gray-600'}"
                    style="background-color: {theme.color}"
                    title={theme.label}
                    aria-label={theme.label}
                  ></button>
                {/each}
              </div>
            {/if}
          </div>

          <!-- Dark mode -->
          <button
            onclick={toggleDark}
            class="p-1.5 rounded-lg text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700 transition-colors"
            aria-label="Toggle dark mode"
          >
            {#if dm.value}
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
              </svg>
            {:else}
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
              </svg>
            {/if}
          </button>

          <!-- Divider -->
          <div class="w-px h-5 bg-gray-200 dark:bg-gray-600 mx-1"></div>

          <!-- User menu -->
          <div class="relative">
            <button
              onclick={() => showUserMenu = !showUserMenu}
              class="flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            >
              <svg class="w-3.5 h-3.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
              </svg>
              <span class="text-xs font-medium">{username.value || 'Set name'}</span>
              <svg class="w-3 h-3 transition-transform {showUserMenu ? 'rotate-180' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {#if showUserMenu}
              <!-- svelte-ignore a11y_click_events_have_key_events -->
              <div class="fixed inset-0 z-40" role="presentation" onclick={() => showUserMenu = false}></div>
              <div class="absolute right-0 top-full mt-1 z-50 bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 py-1 w-56">
                <!-- Timezone -->
                <button
                  onclick={() => { showUserMenu = false; showTzPicker = true; tzSearch = ''; }}
                  class="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                >
                  <svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span class="flex-1 text-left">{TIMEZONES.find(z => z.id === tz.value)?.label ?? tzAbbr(tz.value)}</span>
                  <span class="text-xs text-gray-400 font-mono">{tzAbbr(tz.value)}</span>
                </button>
                <!-- Change name -->
                <button
                  onclick={() => { showUserMenu = false; showUsernamePrompt = true; usernameInput = username.value; }}
                  class="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                >
                  <svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                  Change name
                </button>
                <!-- Divider -->
                <div class="border-t border-gray-100 dark:border-gray-700 my-1"></div>
                <!-- Logout -->
                <button
                  onclick={() => { showUserMenu = false; logout(); }}
                  class="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                >
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                  </svg>
                  Logout
                </button>
              </div>
            {/if}
          </div>
        </div>

        <!-- Mobile: theme + dark mode + hamburger -->
        <div class="sm:hidden flex items-center gap-1">
          <!-- Color theme -->
          <button
            onclick={cycleTheme}
            class="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            aria-label="Change color theme"
          >
            <span class="block w-4 h-4 rounded-full border-2 border-white dark:border-gray-800 ring-1 ring-gray-300 dark:ring-gray-600 shadow-sm" style="background-color: {THEMES.find(t => t.id === colorTheme)?.color}"></span>
          </button>
          <!-- Dark mode -->
          <button
            onclick={toggleDark}
            class="p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700 transition-colors"
            aria-label="Toggle dark mode"
          >
            {#if dm.value}
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
              </svg>
            {:else}
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
              </svg>
            {/if}
          </button>
          <!-- Hamburger -->
          <button
            class="p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700"
            onclick={() => mobileMenuOpen = !mobileMenuOpen}
            aria-label="Toggle menu"
          >
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            {#if mobileMenuOpen}
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            {:else}
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
            {/if}
          </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- Mobile menu dropdown -->
    {#if mobileMenuOpen}
      <div class="sm:hidden border-t border-stone-200/80 dark:border-zinc-700/80 bg-white/[0.99] dark:bg-zinc-900/95 px-4 py-2">
        {#each navLinks as link}
          <a
            href={link.href}
            class="block px-3 py-2 rounded-lg text-sm font-medium transition-colors {isActive(link.href, $page.url.pathname)
              ? 'bg-primary-50 text-primary-600 dark:bg-primary-500/20 dark:text-primary-400'
              : 'text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'}"
            onclick={() => mobileMenuOpen = false}
          >
            {link.label}
          </a>
        {/each}
        <a
          href="/review"
          class="block px-3 py-2 rounded-lg text-sm font-medium transition-colors {isActive('/review', $page.url.pathname)
            ? 'bg-primary-50 text-primary-600 dark:bg-primary-500/20 dark:text-primary-400'
            : 'text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'}"
          onclick={() => mobileMenuOpen = false}
        >Review</a>
        <a
          href="https://docs.google.com/forms/d/e/1FAIpQLSeFsl3cKK7Tf3-iuzkPxPWmWkvRpZfB3U27PeZDun9NIqAt6A/viewform"
          target="_blank"
          rel="noopener noreferrer"
          class="block px-3 py-2 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700 transition-colors flex items-center gap-2"
          onclick={() => mobileMenuOpen = false}
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
          </svg>
          Give feedback
        </a>
        <!-- User section -->
        <div class="border-t border-stone-200/80 dark:border-zinc-700/80 mt-1 pt-1">
          <div class="px-3 py-2 flex items-center gap-2 text-sm font-medium text-gray-800 dark:text-gray-200">
            <svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
            {username.value || 'No name set'}
          </div>
          <button
            onclick={() => { mobileMenuOpen = false; showUsernamePrompt = true; usernameInput = username.value; }}
            class="w-full text-left px-3 py-2 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700 transition-colors flex items-center gap-2"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
            Change name
          </button>
        </div>
        <div class="px-3 py-2 flex items-center gap-2 text-sm font-medium text-gray-600 dark:text-gray-300">
          <svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <select
            bind:value={tz.value}
            onchange={(e) => localStorage.setItem('kvizzing_tz', (e.target as HTMLSelectElement).value)}
            class="bg-transparent text-sm font-medium text-gray-600 dark:text-gray-300 focus:outline-none cursor-pointer flex-1"
          >
            {#each TIMEZONES as zone}
              <option value={zone.id}>{zone.label} ({tzAbbr(zone.id)})</option>
            {/each}
          </select>
        </div>
        <button
          onclick={() => { mobileMenuOpen = false; logout(); }}
          class="w-full text-left px-3 py-2 rounded-lg text-sm font-medium text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors flex items-center gap-2"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>
          Logout
        </button>
      </div>
    {/if}
  </nav>

  <!-- Main layout -->
  <div class="flex-1 overflow-y-auto flex flex-col">
    <div class="max-w-7xl w-full mx-auto px-4 sm:px-6 py-6 flex-1">
      <div class="flex gap-6">
        <!-- Main content -->
        <main class="flex-1 min-w-0">
          <!-- Hero banner — / and /sessions -->
          {#if $page.url.pathname === '/'}
            <div class="bg-gradient-to-br from-primary-300 to-primary-900 rounded-2xl p-4 sm:p-6 text-white shadow-lg relative mb-6">
              {#if sinceDate}
                <div class="absolute top-4 sm:top-6 right-4 sm:right-6 flex items-center gap-1.5 text-xs text-primary-100">
                  <span class="relative flex h-2.5 w-2.5">
                    <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-300 opacity-90"></span>
                    <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-green-400"></span>
                  </span>
                  since {sinceDate}
                </div>
              {/if}
              <h1 class="text-xl sm:text-2xl font-bold mb-1">All Questions</h1>
              <p class="text-primary-100 text-sm mb-4">Every question the group ever asked. Right here.</p>
              <div class="flex items-center justify-between gap-3">
                <div class="flex flex-wrap gap-x-4 gap-y-1 text-sm">
                  <span class="font-semibold">{totalStats.total} total questions</span>
                  <span class="text-primary-200 hidden sm:inline">·</span>
                  <a href="/sessions" class="font-semibold hover:text-primary-100 transition-colors cursor-pointer">{totalStats.sessions} quiz sessions</a>
                </div>
                <button
                  onclick={surpriseMe}
                  class="flex-shrink-0 inline-flex items-center gap-1.5 px-4 py-2 bg-white hover:bg-primary-50 text-primary-600 dark:bg-gray-900 dark:hover:bg-gray-800 dark:text-primary-300 font-semibold text-sm rounded-lg transition-colors shadow-sm cursor-pointer"
                >
                  <svg class="w-4 h-4 flex-shrink-0 animate-spin" style="animation-duration:1s" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" /></svg>
                  <span class="hidden sm:inline">Random question</span>
                  <span class="sm:hidden">Random</span>
                </button>
              </div>
            </div>
          {:else if $page.url.pathname === '/sessions'}
            <div class="bg-gradient-to-br from-primary-300 to-primary-900 rounded-2xl p-4 sm:p-6 text-white shadow-lg relative mb-6">
              {#if sinceDate}
                <div class="absolute top-4 sm:top-6 right-4 sm:right-6 flex items-center gap-1.5 text-xs text-primary-100">
                  <span class="relative flex h-2.5 w-2.5">
                    <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-300 opacity-90"></span>
                    <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-green-400"></span>
                  </span>
                  since {sinceDate}
                </div>
              {/if}
              <h1 class="text-xl sm:text-2xl font-bold mb-1">Quiz Sessions</h1>
              <p class="text-primary-100 text-sm mb-4">Curated quiz sessions hosted by group members</p>
              <div class="flex items-center justify-between gap-3">
                <div class="flex flex-wrap gap-x-4 gap-y-1 text-sm">
                  <span class="font-semibold">{totalStats.sessions} quiz sessions</span>
                  <span class="text-primary-200 hidden sm:inline">·</span>
                  <a href="/" class="font-semibold hover:text-primary-100 transition-colors">{sessionQuestionCount} questions</a>
                </div>
                <button
                  onclick={randomQuiz}
                  class="flex-shrink-0 inline-flex items-center gap-1.5 px-4 py-2 bg-white hover:bg-primary-50 text-primary-600 dark:bg-gray-900 dark:hover:bg-gray-800 dark:text-primary-300 font-semibold text-sm rounded-lg transition-colors shadow-sm cursor-pointer"
                >
                  <svg class="w-4 h-4 flex-shrink-0 animate-spin" style="animation-duration:1s" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" /></svg>
                  <span>Random quiz</span>
                </button>
              </div>
            </div>
          {:else if $page.url.pathname === '/highlights'}
            <div class="mb-6 space-y-4">
              <div>
                <h1 class="text-2xl font-bold text-gray-900 dark:text-gray-100">Highlights</h1>
                <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">The group's story</p>
              </div>
              <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <a href="/" class="bg-ui-card rounded-xl border border-gray-200 dark:border-gray-700 p-4 shadow-sm text-center hover:border-primary-300 hover:shadow-md transition-all">
                  <p class="text-2xl font-bold text-primary-500 dark:text-primary-400">{totalStats.total}</p>
                  <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">Total questions</p>
                </a>
                <a href="/sessions" class="bg-ui-card rounded-xl border border-gray-200 dark:border-gray-700 p-4 shadow-sm text-center hover:border-primary-300 hover:shadow-md transition-all">
                  <p class="text-2xl font-bold text-primary-500 dark:text-primary-400">{totalStats.sessions}</p>
                  <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">Quiz sessions</p>
                </a>
                <a href="/?asker=" class="bg-ui-card rounded-xl border border-gray-200 dark:border-gray-700 p-4 shadow-sm text-center hover:border-primary-300 hover:shadow-md transition-all">
                  <p class="text-2xl font-bold text-primary-500 dark:text-primary-400">{askerCount}</p>
                  <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">Askers</p>
                </a>
                <a href="/?solver=" class="bg-ui-card rounded-xl border border-gray-200 dark:border-gray-700 p-4 shadow-sm text-center hover:border-primary-300 hover:shadow-md transition-all">
                  <p class="text-2xl font-bold text-primary-500 dark:text-primary-400">{solverCount}</p>
                  <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">Solvers</p>
                </a>
              </div>
            </div>
          {/if}

          {@render children()}

          <!-- Calendar + side panels — mobile only (below content) -->
          <div class="lg:hidden mt-6 space-y-4">
            {#if $page.url.pathname === '/review'}
              {@render reviewSidebar()}
            {:else}
            <CalendarSidebar {store} tz={tz.value} />

            {#if $page.url.pathname === '/sessions'}
              {#if sidebarQuestions.length > 0}
                <div class="bg-ui-card rounded-xl border border-stone-200/80 dark:border-zinc-600/80 shadow-sm overflow-hidden">
                  <a href="/" class="px-4 py-3 border-b border-stone-100 dark:border-zinc-700/80 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                    <h2 class="text-xs font-semibold text-gray-500 dark:text-gray-400">All Questions</h2>
                    <span class="text-xs text-primary-500 dark:text-primary-400">Feed →</span>
                  </a>
                  <div class="divide-y divide-stone-100 dark:divide-zinc-700/80">
                    {#each sidebarQuestions.slice(0, 8) as question}
                      <a href="/question/{question.id}" class="relative overflow-hidden flex items-center gap-3 px-4 py-2.5 transition-colors group">
                        <div class="absolute inset-0" style="background-image: url('/images/connect-quiz-bg-old.png'); background-size: cover; background-position: center; background-repeat: no-repeat; opacity: {SESSION_IMAGE_OPACITY.sidebar.default}"></div>
                        <span class="relative text-[10px] text-gray-600 dark:text-gray-400 flex-shrink-0 w-20">{ordinalDate(question.question?.timestamp ? dateInTz(question.question.timestamp, tz.value) : question.date)}</span>
                        <div class="relative min-w-0 flex-1 text-right">
                          <p class="text-xs font-semibold text-primary-700 dark:text-primary-200 truncate">{question.question.text}</p>
                          <p class="text-xs text-gray-600 dark:text-gray-400">{question.question.asker}</p>
                        </div>
                      </a>
                    {/each}
                  </div>
                  {#if sidebarQuestions.length > 8}
                    <a href="/" class="block px-4 py-2.5 text-xs text-center text-primary-500 dark:text-primary-400 border-t border-stone-100 dark:border-zinc-700/80 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                      See all {sidebarQuestions.length} questions →
                    </a>
                  {/if}
                </div>
              {/if}
            {:else}
              {#if sidebarSessions.length > 0}
                <div class="bg-ui-card rounded-xl border border-stone-200/80 dark:border-zinc-600/80 shadow-sm overflow-hidden">
                  <a href="/sessions" class="px-4 py-3 border-b border-stone-100 dark:border-zinc-700/80 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                    <h2 class="text-xs font-semibold text-gray-500 dark:text-gray-400">Quiz Sessions</h2>
                    <span class="text-xs text-primary-500 dark:text-primary-400">All →</span>
                  </a>
                  <div class="divide-y divide-stone-100 dark:divide-zinc-700/80">
                    {#each sidebarSessions.slice(0, 8) as session}
                      <a href="/session/{session.id}" class="relative overflow-hidden flex items-center gap-3 px-4 py-2.5 transition-colors group">
                        <div class="session-bg absolute inset-0 bg-cover bg-center transition-opacity" style="background-image: url('{sessionBgUrl(session)}'); opacity: {SESSION_IMAGE_OPACITY.sidebar.default}"></div>
                        <span class="relative text-[10px] text-gray-600 dark:text-gray-400 flex-shrink-0 w-20">{ordinalDate(dateInTz(sidebarSessionTs.get(session.id) ?? session.date, tz.value))}</span>
                        <div class="relative min-w-0 flex-1 text-right">
                          <p class="text-xs font-semibold text-primary-700 dark:text-primary-200 truncate">{session.quiz_type === 'connect' ? `${session.quizmaster}'s Connect Quiz` : (session.theme ?? `${session.quizmaster}'s Quiz`)}</p>
                          <p class="text-xs text-gray-600 dark:text-gray-400 truncate">{session.quizmaster} · {session.question_count} questions</p>
                        </div>
                      </a>
                    {/each}
                  </div>
                  {#if sidebarSessions.length > 8}
                    <a href="/sessions" class="block px-4 py-2.5 text-xs text-center text-primary-500 dark:text-primary-400 border-t border-stone-100 dark:border-zinc-700/80 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                      See all {sidebarSessions.length} sessions →
                    </a>
                  {/if}
                </div>
              {/if}
            {/if}
            {/if}
          </div>
        </main>

        <!-- Calendar sidebar — desktop only -->
        <aside class="hidden lg:block w-80 min-w-80 max-w-80 flex-shrink-0">
          <div class="sticky top-6 space-y-4">
            {#if $page.url.pathname === '/review'}
              <!-- Review calendar + leaderboard -->
              {@render reviewSidebar()}
            {:else}
            <CalendarSidebar {store} tz={tz.value} />

            {#if $page.url.pathname === '/sessions'}
              <!-- Questions list (shown on /sessions page) -->
              {#if sidebarQuestions.length > 0}
                <div class="bg-ui-card rounded-xl border border-stone-200/80 dark:border-zinc-600/80 shadow-sm overflow-hidden">
                  <a href="/" class="px-4 py-3 border-b border-stone-100 dark:border-zinc-700/80 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                    <h2 class="text-xs font-semibold text-gray-500 dark:text-gray-400">All Questions</h2>
                    <span class="text-xs text-primary-500 dark:text-primary-400">Feed →</span>
                  </a>
                  <div class="relative">
                    {#if sidebarQuestions.length > 8}
                      <div class="pointer-events-none absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-white dark:from-[#1c1c1c] to-transparent z-10"></div>
                    {/if}
                    <div class="divide-y divide-stone-100 dark:divide-zinc-700/80 max-h-80 overflow-y-auto">
                      {#each sidebarQuestions as question}
                        <a
                          href="/question/{question.id}"
                          class="relative overflow-hidden flex items-center gap-3 px-4 py-2.5 transition-colors group"
                          onmouseenter={(e) => { const bg = e.currentTarget.querySelector('.question-bg') as HTMLElement | null; if (bg) bg.style.opacity = String(SESSION_IMAGE_OPACITY.sidebar.hover); }}
                          onmouseleave={(e) => { const bg = e.currentTarget.querySelector('.question-bg') as HTMLElement | null; if (bg) bg.style.opacity = String(SESSION_IMAGE_OPACITY.sidebar.default); }}
                        >
                          <div
                            class="question-bg absolute inset-0 transition-opacity"
                            style="background-image: url('/images/connect-quiz-bg-old.png'); background-size: cover; background-position: center; background-repeat: no-repeat; opacity: {SESSION_IMAGE_OPACITY.sidebar.default}"
                          ></div>
                          <span class="relative text-[10px] text-gray-600 dark:text-gray-400 flex-shrink-0 w-20 group-hover:text-gray-900 dark:group-hover:text-white transition-colors">{ordinalDate(question.question?.timestamp ? dateInTz(question.question.timestamp, tz.value) : question.date)}</span>
                          <div class="relative min-w-0 flex-1 text-right">
                            <p class="text-xs font-semibold text-primary-700 dark:text-primary-200 truncate group-hover:text-primary-900 dark:group-hover:text-primary-100 transition-colors">
                              {question.question.text}
                            </p>
                            <p class="text-xs text-gray-600 dark:text-gray-400 group-hover:text-gray-900 dark:group-hover:text-white transition-colors">{question.question.asker}</p>
                          </div>
                        </a>
                      {/each}
                    </div>
                  </div>
                </div>
              {/if}
            {:else}
              <!-- Sessions list (shown on all other pages) -->
              {#if sidebarSessions.length > 0}
                <div class="bg-ui-card rounded-xl border border-stone-200/80 dark:border-zinc-600/80 shadow-sm overflow-hidden">
                  <a href="/sessions" class="px-4 py-3 border-b border-stone-100 dark:border-zinc-700/80 flex items-center justify-between hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                    <h2 class="text-xs font-semibold text-gray-500 dark:text-gray-400">Quiz Sessions</h2>
                    <span class="text-xs text-primary-500 dark:text-primary-400">All →</span>
                  </a>
                  <div class="relative">
                    {#if sidebarSessions.length > 8}
                      <div class="pointer-events-none absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-white dark:from-[#1c1c1c] to-transparent z-10"></div>
                    {/if}
                    <div class="divide-y divide-stone-100 dark:divide-zinc-700/80 max-h-80 overflow-y-auto">
                      {#each sidebarSessions as session}
                        <a
                          href="/session/{session.id}"
                          class="relative overflow-hidden flex items-center gap-3 px-4 py-2.5 hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors group"
                          onmouseenter={(e) => { const bg = e.currentTarget.querySelector('.session-bg') as HTMLElement | null; if (bg) bg.style.opacity = String(SESSION_IMAGE_OPACITY.sidebar.hover); }}
                          onmouseleave={(e) => { const bg = e.currentTarget.querySelector('.session-bg') as HTMLElement | null; if (bg) bg.style.opacity = String(SESSION_IMAGE_OPACITY.sidebar.default); }}
                        >
                          <div
                            class="session-bg absolute inset-0 bg-cover bg-center transition-opacity"
                            style="background-image: url('{sessionBgUrl(session)}'); opacity: {SESSION_IMAGE_OPACITY.sidebar.default}"
                          ></div>

                          <span class="relative text-[10px] text-gray-600 dark:text-gray-400 flex-shrink-0 w-20 group-hover:text-gray-900 dark:group-hover:text-white transition-colors">{ordinalDate(dateInTz(sidebarSessionTs.get(session.id) ?? session.date, tz.value))}</span>
                          <div class="relative min-w-0 flex-1 text-right">
                            <p class="text-xs font-semibold text-primary-700 dark:text-primary-200 truncate group-hover:text-primary-900 dark:group-hover:text-primary-100 transition-colors">
                              {session.quiz_type === 'connect' ? `${session.quizmaster}'s Connect Quiz` : (session.theme ?? `${session.quizmaster}'s Quiz`)}
                            </p>
                            <p class="text-xs text-gray-600 dark:text-gray-400 truncate group-hover:text-gray-900 dark:group-hover:text-white transition-colors">{session.quizmaster} · {session.question_count} questions</p>
                          </div>
                        </a>
                      {/each}
                    </div>
                  </div>
                </div>
              {/if}
            {/if}
            {/if}
          </div>
        </aside>
      </div>
    </div>

    <!-- Footer -->
    <footer class="mt-auto pt-8 px-4 sm:px-6">
      <div class="max-w-7xl mx-auto px-6 py-4 rounded-t-2xl bg-gradient-to-br from-primary-300 to-primary-900 text-white text-center">
        <p class="text-xs font-medium tracking-wide">Apes together strong 🦍</p>
        <div class="flex items-center justify-center gap-3 mt-1.5 text-xs text-primary-100">
          <span>Made with <span class="text-primary-300">&#9829;</span> by <a href="https://github.com/Saumay" target="_blank" rel="noopener noreferrer" class="hover:text-white transition-colors">Saumay</a></span>
          <span class="text-primary-300">·</span>
          <a href="https://github.com/Saumay/kvizzing_questions_visualizer" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1 hover:text-white transition-colors">
            <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>
            Contribute on GitHub
          </a>
        </div>
      </div>
    </footer>
  </div>

</div>

<!-- Username prompt modal -->
{#if showUsernamePrompt}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
    onclick={() => { if (username.value) showUsernamePrompt = false; }}
  >
    <div class="bg-ui-card rounded-2xl shadow-xl p-6 w-full max-w-sm mx-4 space-y-4" onclick={(e) => e.stopPropagation()}>
      <h2 class="text-lg font-bold text-gray-900 dark:text-gray-100">{username.value ? 'Change your name' : 'Welcome to KVizzing!'}</h2>
      <p class="text-sm text-gray-500 dark:text-gray-400">{username.value ? 'Update how your name appears on reviews and flags.' : 'Enter your name to get started. This is how your reviews and flags will be attributed.'}</p>
      <input
        type="text"
        placeholder="Your name"
        bind:value={usernameInput}
        onkeydown={(e) => { if (e.key === 'Enter') setUsername(); }}
        class="w-full text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100"
        autofocus
      />
      <button
        onclick={setUsername}
        disabled={!usernameInput.trim()}
        class="w-full px-4 py-2 text-sm font-medium rounded-lg transition-colors {usernameInput.trim() ? 'bg-primary-500 text-white hover:bg-primary-600' : 'bg-gray-200 text-gray-400 cursor-not-allowed'}"
      >{username.value ? 'Update Name' : 'Get Started'}</button>
      {#if username.value}
        <button onclick={() => showUsernamePrompt = false} class="w-full text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors">Cancel</button>
      {/if}
    </div>
  </div>
{/if}

<!-- Timezone picker modal -->
{#if showTzPicker}
  {@const filtered = TIMEZONES_SORTED.filter(z => (z.label + ' ' + z.id + ' ' + tzAbbr(z.id) + ' ' + z.aliases).toLowerCase().includes(tzSearch.toLowerCase().trim()))}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
    onclick={(e) => { if (e.target === e.currentTarget && localStorage.getItem('kvizzing_tz')) showTzPicker = false; }}
  >
    <div class="bg-ui-card rounded-2xl shadow-xl p-6 w-full max-w-sm mx-4">
      <div class="flex items-center gap-2 mb-1">
        <svg class="w-5 h-5 text-primary-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <h2 class="text-base font-semibold text-gray-900 dark:text-gray-100">Choose your timezone</h2>
      </div>
      <p class="text-xs text-gray-500 dark:text-gray-400 mb-3">Timestamps will be shown in your local time.</p>
      <div class="relative mb-3">
        <svg class="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <input
          type="text"
          bind:value={tzSearch}
          placeholder="Search city or timezone…"
          class="w-full pl-8 pr-3 py-1.5 text-sm border border-gray-200 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-200 placeholder-gray-400 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 dark:focus:ring-primary-900"
          autocomplete="off"
          spellcheck="false"
        />
      </div>
      <div class="grid grid-cols-1 gap-1.5 max-h-64 overflow-y-auto pr-1">
        {#if filtered.length === 0}
          <p class="text-sm text-gray-400 text-center py-4">No results for "{tzSearch}"</p>
        {/if}
        {#each filtered as zone}
          <button
            onclick={() => {
              tz.value = zone.id;
              localStorage.setItem('kvizzing_tz', zone.id);
              showTzPicker = false;
            }}
            class="flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors text-left
              {tz.value === zone.id
                ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 font-medium'
                : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'}"
          >
            <span>{zone.label}</span>
            <span class="text-xs font-mono px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400">{tzAbbr(zone.id)}</span>
          </button>
        {/each}
      </div>
    </div>
  </div>
{/if}

{/if}
