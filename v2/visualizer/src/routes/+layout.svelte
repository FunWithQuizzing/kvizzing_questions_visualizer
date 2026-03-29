<script lang="ts">
  import '../app.css';
  import { setContext } from 'svelte';
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import favicon from '$lib/assets/favicon.svg';
  import { QuestionStore } from '$lib/stores/questionStore';
  import { tzAbbr } from '$lib/utils/time';
  import CalendarSidebar from '$lib/components/CalendarSidebar.svelte';
  import MaraudersAuth from '$lib/components/MaraudersAuth.svelte';

  let { children, data } = $props();

  // Data is static (prerendered), so we construct the store once from the initial load.
  // eslint-disable-next-line svelte/no-unused-svelte-ignore
  // svelte-ignore state_referenced_locally
  const store = new QuestionStore(data.questions, data.sessions, data.members);
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
  const sidebarSessions = store.getSessions();
  const sidebarQuestions = store.getQuestions();

  const MONTHS_SHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  function ordinalDate(dateStr: string): string {
    const [y, m, d] = dateStr.split('-').map(Number);
    const suffix = [11,12,13].includes(d) ? 'th'
      : d % 10 === 1 ? 'st' : d % 10 === 2 ? 'nd' : d % 10 === 3 ? 'rd' : 'th';
    return `${d}${suffix} ${MONTHS_SHORT[m - 1]} ${y}`;
  }

  let authenticated = $state<boolean | null>(null);
  let darkMode = $state(false);
  let showTzPicker = $state(false);
  let tzSearch = $state('');

  const THEMES = [
    { id: 'sky',     label: 'Blue',   color: '#0ea5e9' },
    { id: 'violet',  label: 'Violet', color: '#8b5cf6' },
    { id: 'emerald', label: 'Green',  color: '#10b981' },
    { id: 'rose',    label: 'Rose',   color: '#f43f5e' },
    { id: 'amber',   label: 'Amber',  color: '#f59e0b' },
  ];
  let colorTheme = $state('sky');

  onMount(() => {
    authenticated = localStorage.getItem('kvizzing_auth') === 'true';
    darkMode = localStorage.getItem('kvizzing_dark') === 'true';
    if (darkMode) document.documentElement.classList.add('dark');
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
    if (id === 'sky') {
      document.documentElement.removeAttribute('data-theme');
    } else {
      document.documentElement.setAttribute('data-theme', id);
    }
  }

  function cycleTheme() {
    const idx = THEMES.findIndex(t => t.id === colorTheme);
    const next = THEMES[(idx + 1) % THEMES.length];
    colorTheme = next.id;
    localStorage.setItem('kvizzing_theme', next.id);
    applyTheme(next.id);
  }

  function toggleDark() {
    darkMode = !darkMode;
    localStorage.setItem('kvizzing_dark', String(darkMode));
    document.documentElement.classList.toggle('dark', darkMode);
  }

  function onAuthenticated() {
    localStorage.setItem('kvizzing_auth', 'true');
    authenticated = true;
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

<div class="h-screen flex flex-col bg-gray-50 dark:bg-gray-900 overflow-hidden">
  <!-- Top nav -->
  <nav class="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 flex-shrink-0 z-40 shadow-sm">
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
          <!-- Feedback -->
          <a
            href="https://docs.google.com/forms/d/e/1FAIpQLSeFsl3cKK7Tf3-iuzkPxPWmWkvRpZfB3U27PeZDun9NIqAt6A/viewform"
            target="_blank"
            rel="noopener noreferrer"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-gray-500 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-white dark:hover:bg-gray-700 transition-colors"
            aria-label="Give feedback"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
            <span class="text-sm font-medium">Feedback</span>
          </a>

          <!-- Divider -->
          <div class="w-px h-5 bg-gray-200 dark:bg-gray-600 mx-1"></div>

          <!-- Timezone -->
          <button
            onclick={() => { showTzPicker = true; tzSearch = ''; }}
            class="flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            title="Change timezone"
          >
            <svg class="w-3.5 h-3.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span class="text-xs font-medium">{tzAbbr(tz.value)}</span>
          </button>

          <!-- Color theme -->
          <button
            onclick={cycleTheme}
            class="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            aria-label="Change color theme"
            title="Theme: {THEMES.find(t => t.id === colorTheme)?.label}"
          >
            <span class="block w-4 h-4 rounded-full border-2 border-white dark:border-gray-800 ring-1 ring-gray-300 dark:ring-gray-600 shadow-sm" style="background-color: {THEMES.find(t => t.id === colorTheme)?.color}"></span>
          </button>

          <!-- Dark mode -->
          <button
            onclick={toggleDark}
            class="p-1.5 rounded-lg text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700 transition-colors"
            aria-label="Toggle dark mode"
          >
            {#if darkMode}
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
              </svg>
            {:else}
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
              </svg>
            {/if}
          </button>
        </div>

        <!-- Mobile menu button -->
        <button
          class="sm:hidden p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700"
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

    <!-- Mobile menu dropdown -->
    {#if mobileMenuOpen}
      <div class="sm:hidden border-t border-gray-100 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-2">
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
          onclick={cycleTheme}
          class="w-full text-left px-3 py-2 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700 transition-colors flex items-center gap-2"
        >
          <span class="w-4 h-4 rounded-full border-2 border-white dark:border-gray-800 ring-1 ring-gray-300 dark:ring-gray-600 flex-shrink-0" style="background-color: {THEMES.find(t => t.id === colorTheme)?.color}"></span>
          Theme: {THEMES.find(t => t.id === colorTheme)?.label}
        </button>
        <button
          onclick={toggleDark}
          class="w-full text-left px-3 py-2 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700 transition-colors flex items-center gap-2"
          aria-label="Toggle dark mode"
        >
          {#if darkMode}
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
            </svg>
            Light mode
          {:else}
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
            </svg>
            Dark mode
          {/if}
        </button>
      </div>
    {/if}
  </nav>

  <!-- Main layout -->
  <div class="flex-1 overflow-y-auto">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 py-6">
      <div class="flex gap-6">
        <!-- Main content -->
        <main class="flex-1 min-w-0">
          {@render children()}
        </main>

        <!-- Calendar sidebar — desktop only -->
        <aside class="hidden lg:block w-80 flex-shrink-0">
          <div class="sticky top-6 space-y-4">
            <CalendarSidebar {store} tz={tz.value} />

            {#if $page.url.pathname === '/sessions'}
              <!-- Questions list (shown on /sessions page) -->
              {#if sidebarQuestions.length > 0}
                <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
                  <div class="px-4 py-3 border-b border-gray-100 dark:border-gray-700 flex items-center justify-between">
                    <h2 class="text-xs font-semibold text-gray-500 dark:text-gray-400">All Questions</h2>
                    <a href="/" class="text-xs text-primary-500 dark:text-primary-400 hover:text-primary-600 dark:hover:text-primary-300 transition-colors">Feed →</a>
                  </div>
                  <div class="relative">
                    <div class="pointer-events-none absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-white dark:from-gray-800 to-transparent z-10"></div>
                    <div class="divide-y divide-gray-100 dark:divide-gray-700 max-h-80 overflow-y-auto">
                      {#each sidebarQuestions as question}
                        <a
                          href="/question/{question.id}"
                          class="flex items-center gap-3 px-4 py-2.5 hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors group"
                        >
                          <span class="text-[10px] text-gray-400 dark:text-gray-500 flex-shrink-0 w-20">{ordinalDate(question.date)}</span>
                          <div class="min-w-0 flex-1 text-right">
                            <p class="text-xs font-semibold text-gray-700 dark:text-gray-300 truncate group-hover:text-primary-600 dark:group-hover:text-primary-400 transition-colors">
                              {question.question.text}
                            </p>
                            <p class="text-xs text-gray-400 dark:text-gray-500">{question.question.asker}</p>
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
                <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
                  <div class="px-4 py-3 border-b border-gray-100 dark:border-gray-700 flex items-center justify-between">
                    <h2 class="text-xs font-semibold text-gray-500 dark:text-gray-400">Quiz Sessions</h2>
                    <a href="/sessions" class="text-xs text-primary-500 dark:text-primary-400 hover:text-primary-600 dark:hover:text-primary-300 transition-colors">All →</a>
                  </div>
                  <div class="relative">
                    <div class="pointer-events-none absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-white dark:from-gray-800 to-transparent z-10"></div>
                    <div class="divide-y divide-gray-100 dark:divide-gray-700 max-h-80 overflow-y-auto">
                      {#each sidebarSessions as session}
                        <a
                          href="/session/{session.id}"
                          class="relative overflow-hidden flex items-center gap-3 px-4 py-2.5 hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors group"
                        >
                          <div class="absolute inset-0 bg-cover bg-center opacity-40 dark:opacity-40 transition-opacity group-hover:opacity-50" style="background-image: url('/images/sessions/{session.id}.jpg')"></div>
                          <div class="absolute inset-0 bg-white/70 dark:bg-gray-800/70"></div>
                          <span class="relative text-[10px] text-gray-400 dark:text-gray-500 flex-shrink-0 w-20">{ordinalDate(session.date)}</span>
                          <div class="relative min-w-0 flex-1 text-right">
                            <p class="text-xs font-semibold text-gray-700 dark:text-gray-300 truncate group-hover:text-primary-600 dark:group-hover:text-primary-400 transition-colors">
                              {session.theme ?? `${session.quizmaster}'s Quiz`}
                            </p>
                            <p class="text-xs text-gray-400 dark:text-gray-500 truncate">{session.quizmaster} · {session.question_count} questions</p>
                          </div>
                        </a>
                      {/each}
                    </div>
                  </div>
                </div>
              {/if}
            {/if}
          </div>
        </aside>
      </div>
    </div>

    <!-- Footer -->
    <footer class="mt-8 px-6 py-4 bg-primary-500 text-white text-center">
      <p class="text-sm font-medium tracking-wide">Apes together strong 🦍</p>
    </footer>
  </div>

</div>

<!-- Timezone picker modal -->
{#if showTzPicker}
  {@const filtered = TIMEZONES_SORTED.filter(z => (z.label + ' ' + z.id + ' ' + tzAbbr(z.id) + ' ' + z.aliases).toLowerCase().includes(tzSearch.toLowerCase().trim()))}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
    onclick={(e) => { if (e.target === e.currentTarget && localStorage.getItem('kvizzing_tz')) showTzPicker = false; }}
  >
    <div class="bg-white dark:bg-gray-800 rounded-2xl shadow-xl p-6 w-full max-w-sm mx-4">
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
