<script lang="ts">
  import { getContext, onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import type { QuestionStore } from '$lib/stores/questionStore';
  import type { Question } from '$lib/types';
  import { formatDateTz, formatTime, dateInTz } from '$lib/utils/time';
  import MemberAvatar from '$lib/components/MemberAvatar.svelte';
  import { topicCls, topicLabel, TOPICS } from '$lib/utils/topicColors';
  import { isCorrect, isAlmost } from '$lib/utils/fuzzy';
  import { filterHints } from '$lib/utils/hints';
  import { SESSION_IMAGE_OPACITY, sessionBgUrl } from '$lib/config/ui';
  import SearchInput from '$lib/components/SearchInput.svelte';
  import FiltersToggleButton from '$lib/components/FiltersToggleButton.svelte';
  import TagFilter from '$lib/components/TagFilter.svelte';
  import TopicFilter from '$lib/components/TopicFilter.svelte';
  import ActiveFilterChips from '$lib/components/ActiveFilterChips.svelte';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import ConnectBadge from '$lib/components/ConnectBadge.svelte';
  import { tagFrequency } from '$lib/utils/tags';
  import QuestionCard from '$lib/components/QuestionCard.svelte';

  let { data } = $props();
  const store = getContext<QuestionStore>('store');
  const tzCtx = getContext<{ value: string }>('timezone');

  const session = $derived(data.session);
  const sessionQuestions = $derived(data.sessionQuestions);
  const adj = $derived(store.getAdjacentSessions(session.id));

  const isConnect = $derived(session.quiz_type === 'connect');

  let revealAll = $state(false);
  const _defaultState = () => ({ revealed: false, input: '', result: null as 'correct' | 'almost' | 'wrong' | null, hintsShown: 0 });
  let qStates = $state<Record<string, { revealed: boolean; input: string; result: 'correct' | 'almost' | 'wrong' | null; hintsShown: number }>>(
    Object.fromEntries(
      [...store.getQuestions(), ...sessionQuestions].map((q: Question) => [q.id, _defaultState()])
    )
  );
  function qs(id: string) {
    if (!qStates[id]) qStates[id] = _defaultState();
    return qStates[id];
  }

  // Search & filters
  let search = $state('');
  let filtersOpen = $state(false);
  let filterAsker = $state('');
  let filterSolver = $state('');
  let filterHasMedia = $state<boolean | undefined>(undefined);
  let filterTopics = $state(new Set<string>());
  let filterTags = $state(new Set<string>());
  let sortBy = $state<'newest' | 'oldest' | 'quickest'>('newest');

  const askers = $derived([...new Set(sessionQuestions.map((q: Question) => q.question.asker))].filter(Boolean).sort());
  const solvers = $derived([...new Set(sessionQuestions.map((q: Question) => q.answer?.solver).filter(Boolean))].sort());

  const { tagFreq, allTags } = $derived(tagFrequency(sessionQuestions));

  const activeFilterCount = $derived(
    [isConnect ? '' : filterAsker, filterSolver].filter(Boolean).length +
    (filterHasMedia !== undefined ? 1 : 0) +
    (sortBy !== 'newest' ? 1 : 0) +
    filterTags.size + filterTopics.size
  );

  const filteredQuestions = $derived.by(() => {
    const q = search.trim().toLowerCase();
    let results = sessionQuestions.filter((question: Question) => {
      if (q && !question.question.text.toLowerCase().includes(q)) return false;
      if (filterAsker && question.question.asker !== filterAsker) return false;
      if (filterSolver && question.answer?.solver !== filterSolver) return false;
      if (filterHasMedia !== undefined && !!question.question.has_media !== filterHasMedia) return false;
      if (filterTopics.size > 0 && !question.question.topics?.some((t: string) => filterTopics.has(t))) return false;
      if (filterTags.size > 0 && ![...filterTags].every(t => question.question.tags?.includes(t))) return false;
      return true;
    });
    if (sortBy === 'oldest') results = [...results].reverse();
    else if (sortBy === 'quickest') results = [...results].sort((a, b) => (a.answer?.time_to_answer_seconds ?? Infinity) - (b.answer?.time_to_answer_seconds ?? Infinity));
    return results;
  });

  const hasFilters = $derived(!!(search || filterAsker || filterSolver || filterHasMedia !== undefined || filterTopics.size > 0 || filterTags.size > 0 || sortBy !== 'newest'));

  function clearFilters() {
    search = '';
    filterAsker = '';
    filterSolver = '';
    filterHasMedia = undefined;
    filterTopics = new Set();
    filterTags = new Set();
    sortBy = 'newest';
  }

  const selectCls = "flex-1 basis-[calc(50%-4px)] sm:flex-none sm:w-[129px] text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 dark:focus:ring-primary-900 text-gray-600";
  const filterSizeCls = "flex-1 basis-[calc(50%-4px)] sm:flex-none sm:w-[129px]";

  const MOBILE_PAGE_SIZE = 8;
  let isMobile = $state(false);
  let mobileLimit = $state(MOBILE_PAGE_SIZE);

  onMount(() => {
    const mq = window.matchMedia('(max-width: 1023px)');
    isMobile = mq.matches;
    mq.addEventListener('change', e => { isMobile = e.matches; });
  });

  $effect(() => {
    search; filterAsker; filterSolver; filterHasMedia; filterTopics; filterTags; sortBy;
    mobileLimit = MOBILE_PAGE_SIZE;
  });

  // Connect quiz state
  let connectGuess = $state('');
  let connectResult = $state<'correct' | 'almost' | 'wrong' | null>(null);
  let connectRevealed = $state(false);

  function submitConnectGuess() {
    const input = connectGuess.trim();
    const answer = session.connect_answer || session.theme;
    if (!input || !answer) return;
    if (isCorrect(input, answer)) { connectResult = 'correct'; connectRevealed = true; }
    else if (isAlmost(input, answer)) connectResult = 'almost';
    else connectResult = 'wrong';
  }


</script>

<svelte:head>
  <title>{isConnect && !connectRevealed ? `${session.quizmaster}'s Connect Quiz` : (session.theme ?? `${session.quizmaster}'s Quiz`)} — KVizzing</title>
</svelte:head>

<div class="space-y-6">
  <!-- Back nav -->
  <a href="/sessions" class="inline-flex items-center gap-1.5 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors">
    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
    </svg>
    All quiz sessions
  </a>

  <!-- Session header -->
  <div class="relative overflow-hidden bg-gray-900 rounded-2xl p-6 text-white shadow-lg">
    <div
      class="absolute inset-0 bg-cover bg-center transition-opacity"
      style="background-image: url('{sessionBgUrl(session)}'); opacity: {SESSION_IMAGE_OPACITY.header}"
    ></div>
    <div class="relative">
    <div>
      <div class="flex items-center gap-2 mb-1">
        {#if isConnect}
          <ConnectBadge variant="on-dark" label="Connect Quiz" />
        {/if}
      </div>
      <h1 class="text-xl font-bold mb-1">
        {#if isConnect && !connectRevealed}
          {session.quizmaster}'s Connect Quiz
        {:else}
          {session.theme ?? `${session.quizmaster}'s Quiz`}
        {/if}
      </h1>
      <p class="text-primary-100 text-sm">
        Hosted by {session.quizmaster} · {formatDateTz(sessionQuestions[0]?.question?.timestamp ?? session.date, tzCtx?.value ?? 'Europe/London')}
      </p>
    </div>

    <!-- Stats row -->
    <div class="flex flex-wrap gap-6 mt-4 pt-4 border-t border-primary-400">
      <div>
        <p class="text-primary-200 text-xs">Questions</p>
        <p class="text-xl font-bold">{session.question_count}</p>
      </div>
      {#if session.participant_count}
        <div>
          <p class="text-primary-200 text-xs">Participants</p>
          <p class="text-xl font-bold">{session.participant_count}</p>
        </div>
      {/if}
      {#if session.avg_time_to_answer_seconds}
        <div>
          <p class="text-primary-200 text-xs">Avg solve time</p>
          <p class="text-xl font-bold">{formatTime(session.avg_time_to_answer_seconds)}</p>
        </div>
      {/if}
      {#if session.avg_wrong_attempts}
        <div>
          <p class="text-primary-200 text-xs">Avg wrong guesses</p>
          <p class="text-xl font-bold">{session.avg_wrong_attempts.toFixed(1)}</p>
        </div>
      {/if}
    </div>
    </div>
  </div>

  <!-- Controls -->
  <div class="space-y-3">
    <!-- Search + filters toggle + reveal all -->
    <div class="flex gap-2">
      <SearchInput bind:value={search} placeholder="Search questions…" />
      <FiltersToggleButton bind:open={filtersOpen} count={activeFilterCount} />
      <button
        onclick={() => { 
          revealAll = !revealAll;
          sessionQuestions.forEach((q: Question) => {
            qs(q.id).revealed = revealAll;
          });
        }}
        class="flex-none px-4 py-2 text-sm font-medium rounded-xl border transition-colors {revealAll ? 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 border-gray-200 dark:border-gray-600 hover:bg-gray-200 dark:hover:bg-gray-600' : 'bg-primary-500 text-white border-primary-500 hover:bg-primary-600 dark:bg-primary-600 dark:border-primary-600'}"
      >
        {revealAll ? 'Hide all' : 'Reveal all'}
      </button>
    </div>

    {#if filtersOpen}
    <div class="space-y-2">
      <!-- Row 1: main filters -->
      <div class="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
        {#if !isConnect}
          <select bind:value={filterAsker} class={selectCls}>
            <option value="">All askers</option>
            {#each askers as asker}
              <option value={asker}>{asker}</option>
            {/each}
          </select>
        {/if}
        <select bind:value={filterSolver} class={selectCls}>
          <option value="">All solvers</option>
          {#each solvers as solver}
            <option value={solver}>{solver}</option>
          {/each}
        </select>
        <select bind:value={sortBy} class={selectCls}>
          <option value="newest">Newest first</option>
          <option value="oldest">Oldest first</option>
          <option value="quickest">Quickest solve</option>
        </select>
        <div class="col-span-2 sm:col-auto sm:flex-none inline-flex rounded-lg border border-gray-200 dark:border-gray-600 overflow-hidden text-sm">
          {#each ([undefined, true, false] as const) as val, i}
            <button
              onclick={() => filterHasMedia = val}
              class="flex-1 sm:flex-none px-2.5 py-1.5 leading-5 whitespace-nowrap transition-colors
                {filterHasMedia === val ? 'bg-primary-500 text-white' : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'}
                {i > 0 ? 'border-l border-gray-200 dark:border-gray-600' : ''}"
            >{val === undefined ? 'All' : val ? 'Media' : 'No Media'}</button>
          {/each}
        </div>
      </div>
      <!-- Row 2: tag + topic filters -->
      <div class="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
        <TagFilter bind:tags={filterTags} {allTags} {tagFreq} class={filterSizeCls} />
        <TopicFilter bind:topics={filterTopics} class={selectCls} />
      </div>
    </div>
    {/if}

    <ActiveFilterChips bind:tags={filterTags} bind:topics={filterTopics} hasFilters={hasFilters} onClear={clearFilters} />

    {#if session.announcement}
      <div class="bg-primary-50/50 dark:bg-primary-900/10 border border-primary-100 dark:border-primary-800/30 rounded-xl px-4 py-3">
        <p class="text-sm font-semibold text-primary-500 dark:text-primary-400 mb-1">Announcement Message</p>
        <p class="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">{session.announcement}</p>
      </div>
    {/if}

    <p class="text-sm text-gray-500 dark:text-gray-400">
      {filteredQuestions.length}{filteredQuestions.length !== sessionQuestions.length ? ` of ${sessionQuestions.length}` : ''} question{filteredQuestions.length !== 1 ? 's' : ''}
      {#if hasFilters}<span class="text-primary-500 font-medium"> (filtered)</span>{/if}
    </p>
  </div>

  <!-- Question grid -->
  {#if sessionQuestions.length === 0}
    <EmptyState emoji="🤔" message="No questions found for this session" />
  {:else if filteredQuestions.length === 0}
    <EmptyState message="No questions match your filters" onClear={clearFilters} />
  {:else}
    {@const sessionDate = formatDateTz(sessionQuestions[0]?.question?.timestamp ?? session.date, tzCtx?.value ?? 'Europe/London')}
    <div class="relative pl-7">
      <!-- Timeline vertical line -->
      <div class="absolute left-[6px] top-[22px] bottom-3 w-[3px] rounded-full bg-primary-200 dark:bg-primary-800/60"></div>
      <!-- Date header with dot -->
      <div class="flex items-center gap-3">
        <div class="absolute left-0 w-3.5 h-3.5 rounded-full bg-primary-500 dark:bg-primary-400 border-[3px] border-white dark:border-gray-900 shadow-sm z-10"></div>
        <span class="text-sm font-semibold text-gray-900 dark:text-gray-100">{sessionDate}</span>
        <span class="text-xs text-gray-400 dark:text-gray-500">{filteredQuestions.length} question{filteredQuestions.length !== 1 ? 's' : ''}</span>
        <div class="flex-1 border-t border-gray-200 dark:border-gray-700"></div>
      </div>
      <div class="grid gap-4 mt-3">
        {#each (isMobile ? filteredQuestions.slice(0, mobileLimit) : filteredQuestions) as question, i (question.id)}
          {@const state = qs(question.id)}
          <QuestionCard
            {question}
            questionNumber={i + 1}
            hideSession={true}
            bind:revealed={state.revealed}
            bind:input={state.input}
            bind:result={state.result}
            bind:hintsShown={state.hintsShown}
          />
        {/each}
      </div>
      {#if isMobile && mobileLimit < filteredQuestions.length}
        <button
          onclick={() => mobileLimit += MOBILE_PAGE_SIZE}
          class="w-full py-3 mt-4 text-sm font-medium text-primary-600 dark:text-primary-400 border border-primary-200 dark:border-primary-800 rounded-xl hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors"
        >
          Show more ({filteredQuestions.length - mobileLimit} remaining)
        </button>
      {/if}
    </div>
  {/if}

  <!-- Connect: guess the theme panel -->
  {#if isConnect}
    <div class="rounded-xl border-2 {connectRevealed ? 'border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/20' : 'border-dashed border-primary-300 dark:border-primary-700 bg-primary-50/50 dark:bg-primary-900/10'} p-5">
      <div class="flex items-center gap-2 mb-3">
        <svg class="w-4 h-4 {connectRevealed ? 'text-green-500' : 'text-primary-500'}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
        </svg>
        <h3 class="text-sm font-semibold {connectRevealed ? 'text-green-700 dark:text-green-300' : 'text-primary-700 dark:text-primary-300'}">
          {connectRevealed ? 'Connect revealed!' : 'Guess the connect'}
        </h3>
      </div>

      {#if connectRevealed}
        <div class="flex items-start justify-between gap-3">
          <div>
            <p class="text-lg font-bold text-green-800 dark:text-green-200">{session.connect_answer || session.theme || 'Connect quiz'}</p>
            {#if connectResult === 'correct'}
              <p class="text-xs text-green-600 dark:text-green-400 mt-1">You got it!</p>
            {/if}
          </div>
          <button
            onclick={() => { connectRevealed = false; connectResult = null; connectGuess = ''; }}
            class="text-xs text-green-600 dark:text-green-400 hover:text-green-800 dark:hover:text-green-200 transition-colors flex items-center gap-1 flex-shrink-0"
          >
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
            </svg>
            Hide
          </button>
        </div>
      {:else}
        <p class="text-xs text-gray-500 dark:text-gray-400 mb-3">What's the common theme connecting all these questions?</p>
        <div class="flex gap-2">
          <input
            type="text"
            bind:value={connectGuess}
            placeholder="Your guess…"
            onkeydown={(e) => { if (e.key === 'Enter') submitConnectGuess(); }}
            class="flex-1 min-w-0 px-3 py-2 text-sm border rounded-lg focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 transition-all
              {connectResult === 'almost' ? 'border-amber-300 bg-amber-50 dark:bg-amber-900/30 dark:border-amber-700' : connectResult === 'wrong' ? 'border-red-300 bg-red-50 dark:bg-red-900/30 dark:border-red-700' : 'border-gray-200 bg-white dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200 dark:placeholder-gray-400'}"
            autocomplete="off" spellcheck="false"
          />
          <button
            onclick={submitConnectGuess}
            class="px-4 py-2 text-sm font-medium bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors flex-shrink-0"
          >Guess</button>
          <button
            onclick={() => { connectRevealed = true; connectResult = null; }}
            class="px-3 py-2 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 font-medium transition-colors flex-shrink-0"
          >Reveal</button>
        </div>
        {#if connectResult === 'almost'}
          <p class="text-xs text-amber-600 dark:text-amber-400 mt-2">Close! Try again.</p>
        {:else if connectResult === 'wrong'}
          <p class="text-xs text-red-500 dark:text-red-400 mt-2">Not quite. Keep trying!</p>
        {/if}
      {/if}
    </div>
  {/if}

  <!-- Prev / Next session navigation -->
  <div class="flex justify-between pt-4 border-t border-gray-200 dark:border-gray-700 gap-4">
    {#if adj.next}
      <a href="/session/{adj.next.id}" class="flex items-center gap-2 text-sm text-gray-500 hover:text-primary-600 dark:hover:text-primary-400 transition-colors group max-w-[45%]">
        <svg class="w-4 h-4 flex-shrink-0 group-hover:-translate-x-0.5 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
        </svg>
        <div class="min-w-0">
          <p class="text-xs text-gray-400 dark:text-gray-500">Older</p>
          <p class="font-medium text-gray-700 dark:text-gray-300 group-hover:text-primary-600 truncate">{adj.next.quiz_type === 'connect' ? `${adj.next.quizmaster}'s Connect Quiz` : (adj.next.theme ?? `${adj.next.quizmaster}'s Quiz`)}</p>
        </div>
      </a>
    {:else}
      <div></div>
    {/if}

    {#if adj.prev}
      <a href="/session/{adj.prev.id}" class="flex items-center gap-2 text-sm text-gray-500 hover:text-primary-600 dark:hover:text-primary-400 transition-colors group text-right max-w-[45%]">
        <div class="min-w-0">
          <p class="text-xs text-gray-400 dark:text-gray-500">Newer</p>
          <p class="font-medium text-gray-700 dark:text-gray-300 group-hover:text-primary-600 dark:group-hover:text-primary-400 truncate">{adj.prev.quiz_type === 'connect' ? `${adj.prev.quizmaster}'s Connect Quiz` : (adj.prev.theme ?? `${adj.prev.quizmaster}'s Quiz`)}</p>
        </div>
        <svg class="w-4 h-4 flex-shrink-0 group-hover:translate-x-0.5 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
        </svg>
      </a>
    {:else}
      <div></div>
    {/if}
  </div>
</div>
