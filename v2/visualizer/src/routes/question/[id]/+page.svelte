<script lang="ts">
  import { getContext } from 'svelte';
  import { goto } from '$app/navigation';
  import type { QuestionStore } from '$lib/stores/questionStore';
  import { formatDate, formatTime, formatTimestamp } from '$lib/utils/time';
  import { topicCls, topicLabel } from '$lib/utils/topicColors';
  import { filterHints } from '$lib/utils/hints';
  import MemberAvatar from '$lib/components/MemberAvatar.svelte';
  import AnswerSubmission from '$lib/components/AnswerSubmission.svelte';
  import DiscussionThread from '$lib/components/DiscussionThread.svelte';

  let { data } = $props();
  const store = getContext<QuestionStore>('store');

  const question = $derived(data.question);
  const q = $derived(question.question);
  const a = $derived(question.answer);
  const stats = $derived(question.stats);
  const adj = $derived(store.getAdjacentQuestions(question.id));

  let discussionVisible = $state(false);
  let revealed = $state(false);

  function onAnswerReveal() {
    revealed = true;
  }
</script>

<svelte:head>
  <title>{q.asker}'s question — KVizzing</title>
</svelte:head>

<div class="space-y-5 max-w-2xl">
  <!-- Back nav -->
  <div class="flex items-center gap-3">
    <a href="/" class="inline-flex items-center gap-1.5 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors">
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
      </svg>
      Feed
    </a>
    {#if question.session}
      <span class="text-gray-300 dark:text-gray-600">/</span>
      <a href="/session/{question.session.id}" class="text-sm text-orange-500 dark:text-orange-400 hover:text-orange-600 dark:hover:text-orange-300 transition-colors">
        {question.session.theme ?? 'Session'} #{question.session.question_number}
      </a>
    {/if}
    <button
      onclick={() => { const q = store.random(); if (q) goto(`/question/${q.id}`); }}
      class="ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-orange-500 dark:bg-orange-600 text-white hover:bg-orange-600 dark:hover:bg-orange-700 rounded-lg transition-colors cursor-pointer flex-shrink-0"
    >
      <svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h12a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V6zm4 0v2m0 4v2m4-8v2m0 4v2m4-8v2m0 4v2" /></svg>
      <span class="hidden sm:inline">Random question</span>
    </button>
  </div>

  <!-- Context bar -->
  <div class="flex items-center gap-3 flex-wrap">
    <div class="flex items-center gap-2">
      <MemberAvatar username={q.asker} size="sm" />
      <div>
        <p class="text-sm font-semibold text-gray-800 dark:text-gray-200">{q.asker}</p>
        <p class="text-xs text-gray-400 dark:text-gray-500">{formatDate(question.date)}</p>
      </div>
    </div>

    <div class="flex items-center gap-2 ml-auto flex-wrap">
      {#if question.session}
        <a
          href="/session/{question.session.id}"
          class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-orange-100 dark:bg-orange-900/40 text-orange-700 dark:text-orange-300 hover:bg-orange-200 dark:hover:bg-orange-900/60 transition-colors"
        >
          #{question.session.question_number} {question.session.theme ?? 'Session'}
        </a>
      {/if}
      {#if q.topic}
        <a href="/?topic={q.topic}" class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium {topicCls(q.topic)} hover:opacity-80 transition-opacity">
          {topicLabel(q.topic)}
        </a>
      {/if}
      {#if q.type && q.type !== 'unknown'}
        <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400">
          {q.type.replace(/_/g, ' ')}
        </span>
      {/if}
    </div>
  </div>

  <!-- Question card -->
  <div class="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm p-6">
    <p class="text-gray-900 dark:text-gray-100 text-base leading-relaxed font-medium">{q.text}</p>
    {#if q.has_media}
      <p class="mt-2 text-sm text-purple-500 flex items-center gap-1">
        <span>📎</span> This question has media attached
      </p>
    {/if}
    {#if revealed && q.tags && q.tags.length > 0}
      <div class="flex gap-2 mt-3 flex-wrap">
        {#each q.tags as tag}
          <span class="text-xs px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 rounded-full">{tag}</span>
        {/each}
      </div>
    {/if}
  </div>

  <!-- Answer submission -->
  {#if a?.text}
    <AnswerSubmission
      correctAnswer={a.text}
      hints={filterHints(question.discussion?.filter((d: {role: string}) => d.role === 'hint').map((d: {text: string}) => d.text) ?? [])}
      maxAttempts={3}
      onReveal={onAnswerReveal}
    />
  {/if}

  <!-- Stats panel -->
  {#if stats}
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {#if stats.time_to_answer_seconds}
        <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-3 text-center shadow-sm">
          <p class="text-lg font-bold text-gray-900 dark:text-gray-100">{formatTime(stats.time_to_answer_seconds)}</p>
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Solve time</p>
        </div>
      {/if}
      <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-3 text-center shadow-sm">
        <p class="text-lg font-bold text-gray-900 dark:text-gray-100">{stats.wrong_attempts}</p>
        <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Wrong attempts</p>
      </div>
      {#if stats.hints_given > 0}
        <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-3 text-center shadow-sm">
          <p class="text-lg font-bold text-gray-900 dark:text-gray-100">{stats.hints_given}</p>
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Hints given</p>
        </div>
      {/if}
      {#if stats.unique_participants > 0}
        <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-3 text-center shadow-sm">
          <p class="text-lg font-bold text-gray-900 dark:text-gray-100">{stats.unique_participants}</p>
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Participants</p>
        </div>
      {/if}
    </div>
  {/if}

  <!-- Solved by -->
  {#if revealed && a?.solver}
    <div class="flex items-center gap-3 bg-green-50 dark:bg-green-900/30 border border-green-200 rounded-xl px-4 py-3">
      <svg class="w-4 h-4 text-green-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <div class="flex items-center gap-2">
        <MemberAvatar username={a.solver} size="xs" />
        <span class="text-sm text-green-800 dark:text-green-200">
          Solved by <a href="/?solver={encodeURIComponent(a.solver)}" class="font-semibold hover:underline">{a.solver}</a>
        </span>
      </div>
      {#if a.confirmation_text}
        <span class="text-xs text-green-600 dark:text-green-400 ml-auto italic">"{a.confirmation_text}"</span>
      {/if}
    </div>
  {/if}

  <!-- Discussion thread -->
  {#if question.discussion?.length > 0}
    <div class="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
      <button
        class="w-full px-5 py-4 flex items-center justify-between text-left hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
        onclick={() => discussionVisible = !discussionVisible}
      >
        <div class="flex items-center gap-2">
          <svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
          <span class="text-sm font-semibold text-gray-700 dark:text-gray-300">Discussion</span>
          <span class="text-xs text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded-full">{question.discussion.length}</span>
        </div>
        <svg class="w-4 h-4 text-gray-400 transition-transform {discussionVisible ? 'rotate-180' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {#if discussionVisible}
        <div class="px-5 pb-5 border-t border-gray-100 dark:border-gray-700">
          <div class="pt-4">
            <DiscussionThread entries={question.discussion} />
          </div>
        </div>
      {/if}
    </div>
  {/if}

  <!-- Prev / Next navigation -->
  <div class="flex justify-between pt-4 border-t border-gray-200 dark:border-gray-700">
    {#if adj.next}
      <a href="/question/{adj.next.id}" class="flex items-center gap-2 text-sm text-gray-500 hover:text-orange-600 dark:hover:text-orange-400 transition-colors group max-w-[45%]">
        <svg class="w-4 h-4 flex-shrink-0 group-hover:-translate-x-0.5 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
        </svg>
        <div>
          <p class="text-xs text-gray-400 dark:text-gray-500">Previous</p>
          <p class="text-xs font-medium text-gray-700 dark:text-gray-300 group-hover:text-orange-600 dark:group-hover:text-orange-400 line-clamp-2">{adj.next.question.text.slice(0, 60)}…</p>
        </div>
      </a>
    {:else}
      <div></div>
    {/if}

    {#if adj.prev}
      <a href="/question/{adj.prev.id}" class="flex items-center gap-2 text-sm text-gray-500 hover:text-orange-600 dark:hover:text-orange-400 transition-colors group text-right max-w-[45%]">
        <div>
          <p class="text-xs text-gray-400 dark:text-gray-500">Next</p>
          <p class="text-xs font-medium text-gray-700 dark:text-gray-300 group-hover:text-orange-600 dark:group-hover:text-orange-400 line-clamp-2">{adj.prev.question.text.slice(0, 60)}…</p>
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
