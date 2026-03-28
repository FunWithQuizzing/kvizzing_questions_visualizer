<script lang="ts">
  import type { Question } from '$lib/types';
  import { goto } from '$app/navigation';
  import { formatDate, formatTime } from '$lib/utils/time';
  import MemberAvatar from './MemberAvatar.svelte';
  import { topicCls, topicLabel } from '$lib/utils/topicColors';
  import { filterHints } from '$lib/utils/hints';
  import { isCorrect, isAlmost } from '$lib/utils/fuzzy';

  let {
    question,
    showAnswer = false,
    compact = false,
  }: {
    question: Question;
    showAnswer?: boolean;
    compact?: boolean;
  } = $props();

  // showAnswer is a one-time initial prop — intentional
  // svelte-ignore state_referenced_locally
  let revealed = $state(showAnswer);
  let hintsShown = $state(0);
  let input = $state('');
  let result = $state<'correct' | 'almost' | 'wrong' | null>(null);

  function submitGuess() {
    const val = input.trim();
    if (!val || !a?.text) return;
    if (isCorrect(val, a.text)) { result = 'correct'; revealed = true; }
    else if (isAlmost(val, a.text)) result = 'almost';
    else result = 'wrong';
  }

  const q = $derived(question.question);
  const a = $derived(question.answer);
  const stats = $derived(question.stats);
  const hints = $derived(filterHints(question.discussion?.filter(d => d.role === 'hint').map(d => d.text) ?? []));

  function navigateToQuestion(e: MouseEvent) {
    // Don't navigate if clicking on a child link or button
    const target = e.target as HTMLElement;
    if (target.closest('a') !== e.currentTarget || target.closest('button')) return;
    goto(`/question/${question.id}`);
  }
</script>

<article class="bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-md hover:border-gray-300 transition-all duration-200 overflow-hidden group">
  <!-- Clickable card body -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div
    class="p-5 cursor-pointer"
    role="link"
    tabindex="0"
    onclick={(e) => { if (!(e.target as HTMLElement).closest('a,button')) goto(`/question/${question.id}`); }}
    onkeydown={(e) => { if (e.key === 'Enter') goto(`/question/${question.id}`); }}
  >
    <!-- Header row -->
    <div class="flex items-start justify-between gap-3 mb-3">
      <div class="flex items-center gap-2 flex-wrap">
        <MemberAvatar username={q.asker} />
        <div>
          <span class="text-sm font-medium text-gray-900">{q.asker}</span>
          <span class="text-xs text-gray-400 ml-1.5">{formatDate(question.date)}</span>
        </div>
      </div>
      <div class="flex items-center gap-1.5 flex-shrink-0 flex-wrap justify-end">
        {#if question.session}
          <a
            href="/session/{question.session.id}"
            class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-700 hover:bg-orange-200 transition-colors"
          >
            #{question.session.question_number} {question.session.theme ?? 'Session'}
          </a>
        {/if}
        {#if q.topic}
          <button
            onclick={(e) => { e.stopPropagation(); goto(`/?topic=${q.topic}`); }}
            class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium transition-colors {topicCls(q.topic)}"
          >
            {topicLabel(q.topic)}
          </button>
        {/if}
        {#if q.has_media}
          <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-700">
            📎 media
          </span>
        {/if}
      </div>
    </div>

    <!-- Question text -->
    <a href="/question/{question.id}" class="block">
      <p class="text-gray-800 text-sm leading-relaxed group-hover:text-gray-900 {compact ? 'line-clamp-3' : ''}">
        {q.text}
      </p>
    </a>

    <!-- Stats row -->
    <div class="flex items-center gap-4 mt-3 text-xs text-gray-400">
      {#if stats?.time_to_answer_seconds}
        <span class="flex items-center gap-1">
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          {formatTime(stats.time_to_answer_seconds)}
        </span>
      {/if}
      {#if stats?.wrong_attempts > 0}
        <span class="flex items-center gap-1">
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
          {stats.wrong_attempts} wrong
        </span>
      {/if}
      {#if question.discussion?.length > 0}
        <span class="flex items-center gap-1">
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
          {question.discussion.length} messages
        </span>
      {/if}
    </div>
  </div>

  <!-- Answer reveal strip -->
  <div class="border-t border-gray-100">
    {#if revealed}
      <div class="px-4 py-3 bg-green-50 flex items-center justify-between gap-2">
        <div class="flex items-center gap-2">
          <span class="text-xs font-medium text-green-600 uppercase tracking-wide">Answer</span>
          <span class="text-sm font-semibold text-green-800">{a?.text ?? '—'}</span>
        </div>
        <div class="flex items-center gap-2">
          {#if a?.solver}
            <div class="flex items-center gap-1.5 text-xs text-green-600">
              <MemberAvatar username={a.solver} size="xs" />
              {a.solver}
            </div>
          {/if}
          <button
            onclick={() => { revealed = false; result = null; input = ''; }}
            class="text-xs text-gray-400 hover:text-gray-600 transition-colors ml-2"
          >Hide</button>
        </div>
      </div>
    {:else}
      {#if hintsShown > 0}
        <div class="px-5 py-2 bg-amber-50 border-b border-amber-100 space-y-1">
          {#each hints.slice(0, hintsShown) as hint}
            <p class="text-xs text-amber-700 flex items-start gap-1.5">
              <svg class="w-3.5 h-3.5 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
              {hint}
            </p>
          {/each}
        </div>
      {/if}
      <div class="px-4 py-2.5 flex items-center gap-2">
        <input
          type="text"
          placeholder="Your answer…"
          bind:value={input}
          onkeydown={(e) => { if (e.key === 'Enter') submitGuess(); }}
          class="flex-1 min-w-0 px-2.5 py-1.5 text-xs border rounded-lg focus:outline-none focus:border-orange-400 focus:ring-1 focus:ring-orange-100 transition-all
            {result === 'correct' ? 'border-green-300 bg-green-50' : result === 'almost' ? 'border-amber-300 bg-amber-50' : result === 'wrong' ? 'border-red-300 bg-red-50' : 'border-gray-200'}"
          autocomplete="off" spellcheck="false"
          title={result === 'almost' ? 'Close! Try again.' : result === 'wrong' ? 'Not quite. Try again or reveal.' : ''}
        />
        <button
          onclick={submitGuess}
          class="px-3 py-1.5 text-xs font-medium bg-orange-500 text-white rounded-lg hover:bg-orange-600 transition-colors flex-shrink-0"
        >Submit</button>
        <button
          onclick={() => hintsShown = Math.min(hintsShown + 1, hints.length)}
          disabled={hints.length === 0 || hintsShown >= hints.length}
          title={hints.length === 0 ? 'No hints available' : hintsShown >= hints.length ? 'No more hints' : `Hint ${hintsShown + 1} of ${hints.length}`}
          class="flex-shrink-0 flex items-center gap-1 text-xs font-medium transition-colors {hints.length === 0 || hintsShown >= hints.length ? 'text-gray-300 cursor-default' : 'text-amber-500 hover:text-amber-600'}"
        >
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
          Hint
        </button>
        <span class="text-gray-200 flex-shrink-0">|</span>
        <button
          onclick={() => revealed = true}
          class="text-xs text-gray-600 hover:text-gray-900 font-medium transition-colors flex-shrink-0"
        >Reveal</button>
      </div>
    {/if}
  </div>
</article>
