<script lang="ts">
  import '../app.css';
  import { setContext } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import favicon from '$lib/assets/favicon.svg';
  import { QuestionStore } from '$lib/stores/questionStore';
  import CalendarSidebar from '$lib/components/CalendarSidebar.svelte';

  let { children, data } = $props();

  // Data is static (prerendered), so we construct the store once from the initial load.
  // eslint-disable-next-line svelte/no-unused-svelte-ignore
  // svelte-ignore state_referenced_locally
  const store = new QuestionStore(data.questions, data.sessions, data.members);
  setContext('store', store);

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

<div class="min-h-screen bg-gray-50">
  <!-- Top nav -->
  <nav class="bg-white border-b border-gray-200 sticky top-0 z-40 shadow-sm">
    <div class="max-w-7xl mx-auto px-4 sm:px-6">
      <div class="flex items-center justify-between h-14">
        <!-- Logo -->
        <a href="/" class="flex items-center gap-2 group">
          <div class="w-8 h-8 rounded-lg bg-orange-500 flex items-center justify-center text-white font-bold text-sm group-hover:bg-orange-600 transition-colors">
            KV
          </div>
          <span class="font-bold text-gray-900 text-lg tracking-tight">KVizzing</span>
        </a>

        <!-- Desktop nav links -->
        <div class="hidden sm:flex items-center gap-1">
          {#each navLinks as link}
            <a
              href={link.href}
              class="px-3 py-1.5 rounded-lg text-sm font-medium transition-colors {isActive(link.href, $page.url.pathname)
                ? 'bg-orange-50 text-orange-600'
                : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'}"
            >
              {link.label}
            </a>
          {/each}
        </div>

        <!-- Mobile menu button -->
        <button
          class="sm:hidden p-2 rounded-lg text-gray-500 hover:bg-gray-100"
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
      <div class="sm:hidden border-t border-gray-100 bg-white px-4 py-2">
        {#each navLinks as link}
          <a
            href={link.href}
            class="block px-3 py-2 rounded-lg text-sm font-medium transition-colors {isActive(link.href, $page.url.pathname)
              ? 'bg-orange-50 text-orange-600'
              : 'text-gray-600 hover:bg-gray-100'}"
            onclick={() => mobileMenuOpen = false}
          >
            {link.label}
          </a>
        {/each}
      </div>
    {/if}
  </nav>

  <!-- Main layout -->
  <div class="max-w-7xl mx-auto px-4 sm:px-6 py-6">
    <div class="flex gap-6">
      <!-- Main content -->
      <main class="flex-1 min-w-0">
        {@render children()}
      </main>

      <!-- Calendar sidebar — desktop only -->
      <aside class="hidden lg:block w-80 flex-shrink-0">
        <div class="sticky top-20">
          <CalendarSidebar {store} />
        </div>
      </aside>
    </div>
  </div>
</div>
