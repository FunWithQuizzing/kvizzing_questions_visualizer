<script lang="ts">
  import { getContext } from 'svelte';
  import type { QuestionStore } from '$lib/stores/questionStore';
  import type { Question } from '$lib/types';
  import { formatDate, formatTime } from '$lib/utils/time';
  import MemberAvatar from '$lib/components/MemberAvatar.svelte';
  import { topicCls, topicLabel } from '$lib/utils/topicColors';
  import { isCorrect, isAlmost } from '$lib/utils/fuzzy';
  import { filterHints } from '$lib/utils/hints';

  let { data } = $props();
  const store = getContext<QuestionStore>('store');

  const session = $derived(data.session);
  const sessionQuestions = $derived(data.sessionQuestions);
  const adj = $derived(store.getAdjacentSessions(session.id));

  let revealAll = $state(false);
  let revealedIds = $state(new Set<string>());
  let inputs = $state(new Map<string, string>());
  let results = $state(new Map<string, 'correct' | 'almost' | 'wrong'>());
  let hintsShown = $state(new Map<string, number>());

  function toggleReveal(id: string) {
    const next = new Set(revealedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    revealedIds = next;
  }

  function submitGuess(id: string, correctAnswer: string) {
    const input = (inputs.get(id) ?? '').trim();
    if (!input) return;
    let result: 'correct' | 'almost' | 'wrong';
    if (isCorrect(input, correctAnswer)) result = 'correct';
    else if (isAlmost(input, correctAnswer)) result = 'almost';
    else result = 'wrong';
    results = new Map(results).set(id, result);
    if (result === 'correct') {
      revealedIds = new Set(revealedIds).add(id);
    }
  }
</script>

<svelte:head>
  <title>{session.theme ?? `${session.quizmaster}'s Quiz`} — KVizzing</title>
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
      class="absolute inset-0 bg-cover bg-center opacity-30 transition-opacity"
      style="background-image: url('/images/sessions/{session.id}.jpg')"
    ></div>
    <div class="relative">
    <div>
      <h1 class="text-xl font-bold mb-1">
        {session.theme ?? `${session.quizmaster}'s Quiz`}
      </h1>
      <p class="text-primary-100 text-sm">
        Hosted by {session.quizmaster} · {formatDate(session.date)}
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
  <div class="flex items-center justify-between">
    <p class="text-sm text-gray-500 dark:text-gray-400">{sessionQuestions.length} question{sessionQuestions.length !== 1 ? 's' : ''}</p>
    <button
      onclick={() => { revealAll = !revealAll; revealedIds = new Set(); }}
      class="px-4 py-2 text-sm font-medium rounded-lg border transition-colors {revealAll ? 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 border-gray-200 dark:border-gray-600 hover:bg-gray-200 dark:hover:bg-gray-600' : 'bg-primary-500 text-white border-primary-500 hover:bg-primary-600 dark:bg-primary-600 dark:border-primary-600'}"
    >
      {revealAll ? 'Hide all answers' : 'Reveal all answers'}
    </button>
  </div>

  <!-- Question grid -->
  {#if sessionQuestions.length === 0}
    <div class="text-center py-16 text-gray-400">
      <div class="text-4xl mb-3">🤔</div>
      <p class="font-medium">No questions found for this session</p>
    </div>
  {:else}
    <div class="grid gap-4">
      {#each sessionQuestions as question, i (question.id)}
        {@const isRevealed = revealAll || revealedIds.has(question.id)}
        <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
          <!-- Question number badge + link -->
          <div class="p-4">
            <div class="flex items-start gap-3">
              <!-- Number badge -->
              <div class="w-7 h-7 rounded-lg bg-primary-100 text-primary-600 dark:bg-primary-900/40 dark:text-primary-300 font-bold text-sm flex items-center justify-center flex-shrink-0 mt-0.5">
                {i + 1}
              </div>
              <div class="flex-1 min-w-0">
                <div class="flex items-center justify-between gap-2 mb-2">
                  <div class="flex items-center gap-2">
                    <MemberAvatar username={question.question.asker} size="xs" />
                    <span class="text-xs font-medium text-gray-700 dark:text-gray-300">{question.question.asker}</span>
                  </div>
                  {#if question.question.topic}
                    <a href="/?topic={question.question.topic}" class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium {topicCls(question.question.topic)} hover:opacity-80 transition-opacity flex-shrink-0">
                      {topicLabel(question.question.topic)}
                    </a>
                  {/if}
                </div>
                <a href="/question/{question.id}" class="text-sm text-gray-800 dark:text-gray-200 hover:text-primary-600 transition-colors leading-relaxed line-clamp-4 block">
                  {question.question.text}
                </a>
              </div>
            </div>
          </div>

          <!-- Answer area -->
          <div class="border-t border-gray-100 dark:border-gray-700">
            {#if isRevealed}
              <div class="px-4 py-3 bg-green-50 dark:bg-green-900/30 flex items-center justify-between gap-2">
                <div class="flex items-center gap-2">
                  <span class="text-xs font-medium text-green-600 dark:text-green-400 uppercase tracking-wide">Answer</span>
                  <span class="text-sm font-semibold text-green-800 dark:text-green-200">{question.answer?.text ?? '—'}</span>
                </div>
                {#if question.answer?.solver}
                  <div class="flex items-center gap-1.5 text-xs text-green-600 dark:text-green-400">
                    <MemberAvatar username={question.answer.solver} size="xs" />
                    {question.answer.solver}
                  </div>
                {/if}
              </div>
            {:else}
              {@const result = results.get(question.id)}
              {@const hints = filterHints(question.discussion?.filter((d: {role: string}) => d.role === 'hint').map((d: {text: string}) => d.text) ?? [])}
              {@const shown = hintsShown.get(question.id) ?? 0}
              {#if shown > 0}
                <div class="px-4 py-2 bg-amber-50 dark:bg-amber-900/30 border-b border-amber-100 dark:border-amber-800 space-y-1">
                  {#each hints.slice(0, shown) as hint}
                    <p class="text-xs text-amber-700 dark:text-amber-300 flex items-start gap-1.5">
                      <svg class="w-3.5 h-3.5 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                      </svg>
                      {hint}
                    </p>
                  {/each}
                </div>
              {/if}
              <div class="px-4 py-2.5 flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                <input
                  type="text"
                  placeholder="Your answer…"
                  value={inputs.get(question.id) ?? ''}
                  oninput={(e) => { inputs = new Map(inputs).set(question.id, (e.target as HTMLInputElement).value); }}
                  onkeydown={(e) => { if (e.key === 'Enter') submitGuess(question.id, question.answer?.text ?? ''); }}
                  class="flex-1 min-w-0 px-2.5 py-1.5 text-xs border rounded-lg focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 transition-all
                    {result === 'correct' ? 'border-green-300 bg-green-50 dark:bg-green-900/30' : result === 'almost' ? 'border-amber-300 bg-amber-50 dark:bg-amber-900/30' : result === 'wrong' ? 'border-red-300 bg-red-50' : 'border-gray-200 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200 dark:placeholder-gray-400'}"
                  autocomplete="off" spellcheck="false"
                  title={result === 'almost' ? 'Close! Try again.' : result === 'wrong' ? 'Not quite. Try again or reveal.' : ''}
                />
                <div class="flex items-center gap-2 flex-shrink-0">
                  <button
                    onclick={() => submitGuess(question.id, question.answer?.text ?? '')}
                    class="px-3 py-1.5 text-xs font-medium bg-primary-500 text-white rounded-lg hover:bg-primary-600 dark:bg-primary-600 transition-colors"
                  >Submit</button>
                  <button
                    onclick={() => hintsShown = new Map(hintsShown).set(question.id, Math.min(shown + 1, hints.length))}
                    disabled={hints.length === 0 || shown >= hints.length}
                    title={hints.length === 0 ? 'No hints available' : shown >= hints.length ? 'No more hints' : `Hint ${shown + 1} of ${hints.length}`}
                    class="flex items-center gap-1 text-xs font-medium transition-colors {hints.length === 0 || shown >= hints.length ? 'text-gray-300 cursor-default' : 'text-amber-500 hover:text-amber-600'}"
                  >
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                    </svg>
                    Hint
                  </button>
                  <span class="text-gray-200 dark:text-gray-600">|</span>
                  <button
                    onclick={() => toggleReveal(question.id)}
                    class="text-xs text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 font-medium transition-colors"
                  >Reveal</button>
                </div>
              </div>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}

  <!-- Prev / Next session navigation -->
  <div class="flex justify-between pt-4 border-t border-gray-200 dark:border-gray-700">
    {#if adj.next}
      <a href="/session/{adj.next.id}" class="flex items-center gap-2 text-sm text-gray-500 hover:text-primary-600 dark:hover:text-primary-400 transition-colors group">
        <svg class="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
        </svg>
        <div>
          <p class="text-xs text-gray-400 dark:text-gray-500">Older</p>
          <p class="font-medium text-gray-700 dark:text-gray-300 group-hover:text-primary-600">{adj.next.theme ?? `${adj.next.quizmaster}'s Quiz`}</p>
        </div>
      </a>
    {:else}
      <div></div>
    {/if}

    {#if adj.prev}
      <a href="/session/{adj.prev.id}" class="flex items-center gap-2 text-sm text-gray-500 hover:text-primary-600 dark:hover:text-primary-400 transition-colors group text-right">
        <div>
          <p class="text-xs text-gray-400 dark:text-gray-500">Newer</p>
          <p class="font-medium text-gray-700 dark:text-gray-300 group-hover:text-primary-600 dark:group-hover:text-primary-400">{adj.prev.theme ?? `${adj.prev.quizmaster}'s Quiz`}</p>
        </div>
        <svg class="w-4 h-4 group-hover:translate-x-0.5 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
        </svg>
      </a>
    {:else}
      <div></div>
    {/if}
  </div>
</div>
