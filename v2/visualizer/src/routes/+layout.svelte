<script lang="ts">
  import '../app.css';
  import { setContext } from 'svelte';
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import favicon from '$lib/assets/favicon.svg';
  import { QuestionStore } from '$lib/stores/questionStore';
  import CalendarSidebar from '$lib/components/CalendarSidebar.svelte';
  import MaraudersAuth from '$lib/components/MaraudersAuth.svelte';

  let { children, data } = $props();

  // Data is static (prerendered), so we construct the store once from the initial load.
  // eslint-disable-next-line svelte/no-unused-svelte-ignore
  // svelte-ignore state_referenced_locally
  const store = new QuestionStore(data.questions, data.sessions, data.members);
  setContext('store', store);

  let authenticated = $state<boolean | null>(null);
  let darkMode = $state(false);

  onMount(() => {
    authenticated = localStorage.getItem('kvizzing_auth') === 'true';
    darkMode = localStorage.getItem('kvizzing_dark') === 'true';
    if (darkMode) document.documentElement.classList.add('dark');
  });

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

        <!-- Desktop nav links -->
        <div class="hidden sm:flex items-center gap-1">
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
          <button
            onclick={toggleDark}
            class="p-1.5 rounded-lg text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700 transition-colors"
            aria-label="Toggle dark mode"
          >
            {#if darkMode}
              <!-- Sun icon -->
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
              </svg>
            {:else}
              <!-- Moon icon -->
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
          <div class="sticky top-6">
            <CalendarSidebar {store} />
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

{/if}
