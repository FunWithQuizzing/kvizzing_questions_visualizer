<script lang="ts">
  import { isCorrect, isAlmost } from '$lib/utils/fuzzy';

  let {
    correctAnswer,
    solver = null,
    hints = [],
    maxAttempts = 3,
    onReveal,
  }: {
    correctAnswer: string;
    solver?: string | null;
    hints?: string[];
    maxAttempts?: number;
    onReveal?: () => void;
  } = $props();

  let hintsShown = $state(0);

  let input = $state('');
  let attempts = $state<{ text: string; result: 'correct' | 'almost' | 'wrong' }[]>([]);
  let done = $state(false);
  let revealed = $state(false);
  let inputEl: HTMLInputElement | undefined = $state();

  const remainingAttempts = $derived(maxAttempts - attempts.length);
  const hasWon = $derived(attempts.some(a => a.result === 'correct'));

  function submit() {
    if (!input.trim() || done) return;

    const text = input.trim();
    let result: 'correct' | 'almost' | 'wrong';

    if (isCorrect(text, correctAnswer)) {
      result = 'correct';
    } else if (isAlmost(text, correctAnswer)) {
      result = 'almost';
    } else {
      result = 'wrong';
    }

    attempts = [...attempts, { text, result }];
    input = '';

    if (result === 'correct' || attempts.length >= maxAttempts) {
      done = true;
      if (result === 'correct') {
        onReveal?.();
      }
    }
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') submit();
  }

  function revealAnswer() {
    revealed = true;
    done = true;
    onReveal?.();
  }

  const resultConfig = {
    correct: {
      icon: '✓',
      label: 'Correct!',
      bg: 'bg-green-50 border-green-200',
      text: 'text-green-700',
      badge: 'bg-green-100 text-green-700',
    },
    almost: {
      icon: '~',
      label: 'Close!',
      bg: 'bg-amber-50 border-amber-200',
      text: 'text-amber-700',
      badge: 'bg-amber-100 text-amber-700',
    },
    wrong: {
      icon: '✗',
      label: 'Not quite',
      bg: 'bg-red-50 border-red-200',
      text: 'text-red-700',
      badge: 'bg-red-100 text-red-700',
    },
  };
</script>

<div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-5">
  <h3 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4 flex items-center gap-2">
    <span class="w-6 h-6 bg-primary-100 dark:bg-primary-900/40 text-primary-600 dark:text-primary-400 rounded-full flex items-center justify-center text-xs">?</span>
    Try to answer
  </h3>

  <!-- Previous attempts -->
  {#if attempts.length > 0}
    <div class="space-y-2 mb-3">
      {#each attempts as attempt, i}
        {@const cfg = resultConfig[attempt.result]}
        <div class="flex items-center gap-3 px-3 py-2 rounded-lg border {cfg.bg}">
          <span class="text-sm font-bold {cfg.text} w-4 text-center">{cfg.icon}</span>
          <span class="text-sm {cfg.text} flex-1">{attempt.text}</span>
          <span class="text-xs px-2 py-0.5 rounded-full font-medium {cfg.badge}">{cfg.label}</span>
        </div>
      {/each}
    </div>
  {/if}

  <!-- Input area -->
  {#if !done}
    <div class="flex gap-2">
      <input
        bind:this={inputEl}
        bind:value={input}
        onkeydown={handleKeydown}
        type="text"
        placeholder="Your answer…"
        class="flex-1 px-3 py-2 text-sm border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:border-primary-400 dark:focus:border-primary-500 focus:ring-2 focus:ring-primary-100 dark:focus:ring-primary-900 bg-white dark:bg-gray-700 dark:text-gray-200 dark:placeholder-gray-400 transition-all"
        autocomplete="off"
        autocorrect="off"
        spellcheck="false"
      />
      <button
        onclick={submit}
        disabled={!input.trim()}
        class="px-4 py-2 bg-primary-500 dark:bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-600 dark:hover:bg-primary-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        Submit
      </button>
    </div>

    <div class="flex items-center justify-between mt-2">
      <p class="text-xs text-gray-400 dark:text-gray-500">
        {remainingAttempts} attempt{remainingAttempts !== 1 ? 's' : ''} remaining
      </p>
      <div class="flex items-center gap-3">
        <button
          onclick={() => hintsShown = Math.min(hintsShown + 1, hints.length)}
          disabled={hints.length === 0 || hintsShown >= hints.length}
          class="flex items-center gap-1 text-xs transition-colors {hints.length === 0 || hintsShown >= hints.length ? 'text-gray-300 cursor-default' : 'text-amber-500 hover:text-amber-600'}"
          title={hints.length === 0 ? 'No hints available' : hintsShown >= hints.length ? 'No more hints' : `Hint ${hintsShown + 1} of ${hints.length}`}
        >
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            Hint{hints.length > 1 ? ` (${hintsShown}/${hints.length})` : ''}
          </button>
        <button
          onclick={revealAnswer}
          class="text-xs text-gray-400 hover:text-gray-600 transition-colors"
        >
          Give up & reveal
        </button>
      </div>
    </div>

    {#if hintsShown > 0}
      <div class="mt-3 space-y-1.5">
        {#each hints.slice(0, hintsShown) as hint}
          <div class="flex items-start gap-2 px-3 py-2 bg-amber-50 border border-amber-100 rounded-lg">
            <svg class="w-3.5 h-3.5 text-amber-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            <p class="text-xs text-amber-700">{hint}</p>
          </div>
        {/each}
      </div>
    {/if}
  {:else if hasWon}
    <div class="text-center py-3">
      <div class="text-2xl mb-1">🎉</div>
      <p class="text-sm font-semibold text-green-700">You got it!</p>
      <p class="text-xs text-gray-500 mt-0.5">in {attempts.length} attempt{attempts.length !== 1 ? 's' : ''}</p>
    </div>
  {:else if revealed || done}
    <div class="px-4 py-3 bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 rounded-lg">
      <p class="text-xs font-medium text-green-600 dark:text-green-400 uppercase tracking-wide mb-1">Answer</p>
      <p class="text-base font-semibold text-green-900 dark:text-green-200">{correctAnswer}</p>
      {#if solver}
        <p class="text-xs text-green-600 dark:text-green-400 mt-1">Answered by <span class="font-semibold">{solver}</span></p>
      {/if}
    </div>
  {/if}
</div>
