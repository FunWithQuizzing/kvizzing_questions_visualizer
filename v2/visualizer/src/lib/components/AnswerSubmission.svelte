<script lang="ts">
  import { isCorrect, isAlmost } from '$lib/utils/fuzzy';
  import MemberAvatar from './MemberAvatar.svelte';

  type Part = { label: string; text: string; solver: string | null };

  let {
    correctAnswer,
    solver = null,
    parts = null,
    hints = [],
    maxAttempts = 3,
    onReveal,
    onHide,
  }: {
    correctAnswer: string;
    solver?: string | null;
    parts?: Part[] | null;
    hints?: string[];
    maxAttempts?: number;
    onReveal?: () => void;
    onHide?: () => void;
  } = $props();

  let hintsShown = $state(0);

  // ── Single-answer mode state ──
  let input = $state('');
  let attempts = $state<{ text: string; result: 'correct' | 'almost' | 'wrong' }[]>([]);
  let done = $state(false);
  let revealed = $state(false);

  // ── Multi-part mode state ──
  let partInputs = $state<string[]>(parts ? parts.map(() => '') : []);
  let partResults = $state<('correct' | 'almost' | 'wrong' | null)[]>(parts ? parts.map(() => null) : []);
  let partAttemptCounts = $state<number[]>(parts ? parts.map(() => 0) : []);

  const remainingAttempts = $derived(maxAttempts - attempts.length);
  const hasWon = $derived(parts ? partResults.every(r => r === 'correct') : attempts.some(a => a.result === 'correct'));

  function submit() {
    if (!input.trim() || done) return;
    const text = input.trim();
    let result: 'correct' | 'almost' | 'wrong';
    if (isCorrect(text, correctAnswer)) result = 'correct';
    else if (isAlmost(text, correctAnswer)) result = 'almost';
    else result = 'wrong';
    attempts = [...attempts, { text, result }];
    input = '';
    if (result === 'correct' || attempts.length >= maxAttempts) {
      done = true;
      if (result === 'correct') onReveal?.();
    }
  }

  function submitPart(i: number) {
    if (!parts || !partInputs[i]?.trim() || partResults[i] === 'correct') return;
    const text = partInputs[i].trim();
    const correct = parts[i].text;
    let result: 'correct' | 'almost' | 'wrong';
    if (isCorrect(text, correct)) result = 'correct';
    else if (isAlmost(text, correct)) result = 'almost';
    else result = 'wrong';
    partResults[i] = result;
    partAttemptCounts[i] = partAttemptCounts[i] + 1;
    if (result !== 'correct') {
      // Reset after a short delay so user can see the result
      setTimeout(() => {
        if (partResults[i] !== 'correct') partResults[i] = null;
      }, 1200);
    }
    if (result === 'correct') {
      partInputs[i] = parts[i].text;
      // Check if all parts are done
      if (partResults.every(r => r === 'correct')) {
        done = true;
        onReveal?.();
      }
    }
  }

  function revealAnswer() {
    revealed = true;
    done = true;
    if (parts) {
      partResults = parts.map(() => 'correct' as const);
      partInputs = parts.map(p => p.text);
    }
    onReveal?.();
  }

  function hideAnswer() {
    revealed = false;
    done = false;
    if (parts) {
      partResults = parts.map(() => null);
      partInputs = parts.map(() => '');
      partAttemptCounts = parts.map(() => 0);
    } else {
      attempts = [];
    }
    onHide?.();
  }

  const resultConfig = {
    correct: {
      icon: '✓', label: 'Correct!',
      bg: 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800',
      text: 'text-green-700 dark:text-green-400',
      badge: 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-400',
      border: 'border-green-300 dark:border-green-700',
    },
    almost: {
      icon: '~', label: 'Close!',
      bg: 'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800',
      text: 'text-amber-700 dark:text-amber-400',
      badge: 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-400',
      border: 'border-amber-300 dark:border-amber-700',
    },
    wrong: {
      icon: '✗', label: 'Not quite',
      bg: 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800',
      text: 'text-red-700 dark:text-red-400',
      badge: 'bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-400',
      border: 'border-red-300 dark:border-red-700',
    },
  };
</script>

<div class="bg-ui-card rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm p-5">
  <h3 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-4 flex items-center gap-2">
    <span class="w-6 h-6 bg-primary-100 dark:bg-primary-900/40 text-primary-600 dark:text-primary-400 rounded-full flex items-center justify-center text-xs">?</span>
    Try to answer{#if parts} ({partResults.filter(r => r === 'correct').length}/{parts.length}){/if}
  </h3>

  {#if parts && !revealed && !(done && hasWon)}
    <!-- Multi-part inputs -->
    <div class="space-y-2.5">
      {#each parts as part, i}
        {@const res = partResults[i]}
        <div class="flex items-center gap-2">
          <span class="text-xs font-semibold text-gray-500 dark:text-gray-400 w-24 flex-shrink-0 truncate" title={part.label}>{part.label}</span>
          {#if res === 'correct'}
            <div class="flex-1 px-3 py-2 text-sm rounded-lg border border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300 font-medium flex items-center gap-2">
              <span class="text-green-500 font-bold">✓</span>
              {part.text}
              {#if part.solver}
                <span class="ml-auto flex items-center gap-1 text-xs text-green-500 dark:text-green-400">
                  <MemberAvatar username={part.solver} size="xs" />
                  {part.solver}
                </span>
              {/if}
            </div>
          {:else}
            <input
              bind:value={partInputs[i]}
              onkeydown={(e) => { if (e.key === 'Enter') submitPart(i); }}
              type="text"
              placeholder="Your answer…"
              class="flex-1 px-3 py-2 text-sm border rounded-lg focus:outline-none focus:border-primary-400 dark:focus:border-primary-500 focus:ring-2 focus:ring-primary-100 dark:focus:ring-primary-900 bg-white dark:bg-gray-700 dark:text-gray-200 dark:placeholder-gray-400 transition-all
                {res === 'almost' ? 'border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20' : res === 'wrong' ? 'border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/20' : 'border-gray-200 dark:border-gray-600'}"
              autocomplete="off" autocorrect="off" spellcheck="false"
            />
            <button
              onclick={() => submitPart(i)}
              disabled={!partInputs[i]?.trim()}
              class="px-3 py-2 bg-primary-500 dark:bg-primary-600 text-white text-xs font-medium rounded-lg hover:bg-primary-600 dark:hover:bg-primary-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex-shrink-0"
            >Go</button>
          {/if}
        </div>
      {/each}
    </div>

    <div class="flex items-center justify-end mt-3 gap-3">
      <button
        onclick={() => hintsShown = Math.min(hintsShown + 1, hints.length)}
        disabled={hints.length === 0 || hintsShown >= hints.length}
        class="flex items-center gap-1 text-xs transition-colors {hints.length === 0 || hintsShown >= hints.length ? 'text-gray-300 cursor-default' : 'text-amber-500 hover:text-amber-600'}"
      >
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
        </svg>
        Hint{hints.length > 1 ? ` (${hintsShown}/${hints.length})` : ''}
      </button>
      <button onclick={revealAnswer} class="text-xs text-gray-400 hover:text-gray-600 transition-colors">Give up & reveal</button>
    </div>

    {#if hintsShown > 0}
      <div class="mt-3 space-y-1.5">
        {#each hints.slice(0, hintsShown) as hint}
          <div class="flex items-start gap-2 px-3 py-2 bg-amber-50 dark:bg-amber-900/20 border border-amber-100 dark:border-amber-800 rounded-lg">
            <svg class="w-3.5 h-3.5 text-amber-500 dark:text-amber-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            <p class="text-xs text-amber-700 dark:text-amber-300">{hint}</p>
          </div>
        {/each}
      </div>
    {/if}

  {:else if !parts}
    <!-- Single-answer mode (original) -->
    {#if attempts.length > 0}
      <div class="space-y-2 mb-3">
        {#each attempts as attempt, i}
          {@const cfg = resultConfig[attempt.result]}
          <div class="flex items-center gap-3 px-3 py-2 rounded-lg border {cfg.bg}">
            <span class="text-sm font-bold {cfg.text} w-4 text-center">{cfg.icon}</span>
            <span class="text-sm {cfg.text} flex-1">{attempt.text}</span>
            <span class="text-xs px-2 py-0.5 rounded-full font-medium {cfg.badge}">{cfg.label}</span>
            <button
              onclick={() => { attempts = attempts.filter((_, j) => j !== i); if (attempts.length === 0) { done = false; } }}
              class="text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 transition-colors flex-shrink-0"
              title="Dismiss"
            >
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        {/each}
      </div>
    {/if}

    {#if !done}
      <div class="flex gap-2">
        <input
          bind:value={input}
          onkeydown={(e) => { if (e.key === 'Enter') submit(); }}
          type="text"
          placeholder="Your answer…"
          class="flex-1 px-3 py-2 text-sm border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:border-primary-400 dark:focus:border-primary-500 focus:ring-2 focus:ring-primary-100 dark:focus:ring-primary-900 bg-white dark:bg-gray-700 dark:text-gray-200 dark:placeholder-gray-400 transition-all"
          autocomplete="off" autocorrect="off" spellcheck="false"
        />
        <button
          onclick={submit}
          disabled={!input.trim()}
          class="px-4 py-2 bg-primary-500 dark:bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-600 dark:hover:bg-primary-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >Submit</button>
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
          >
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            Hint{hints.length > 1 ? ` (${hintsShown}/${hints.length})` : ''}
          </button>
          <button onclick={revealAnswer} class="text-xs text-gray-400 hover:text-gray-600 transition-colors">Give up & reveal</button>
        </div>
      </div>

      {#if hintsShown > 0}
        <div class="mt-3 space-y-1.5">
          {#each hints.slice(0, hintsShown) as hint}
            <div class="flex items-start gap-2 px-3 py-2 bg-amber-50 dark:bg-amber-900/20 border border-amber-100 dark:border-amber-800 rounded-lg">
              <svg class="w-3.5 h-3.5 text-amber-500 dark:text-amber-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
              <p class="text-xs text-amber-700 dark:text-amber-300">{hint}</p>
            </div>
          {/each}
        </div>
      {/if}
    {/if}
  {/if}

  <!-- Won state -->
  {#if done && hasWon}
    <div class="text-center py-3 relative">
      <button
        onclick={hideAnswer}
        class="absolute top-2 right-2 text-xs text-green-600/70 hover:text-green-700 dark:text-green-400/70 dark:hover:text-green-300 transition-colors flex items-center gap-1"
        title="Hide Answer"
      >
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
        </svg>
        Hide
      </button>
      <div class="text-2xl mb-1">🎉</div>
      <p class="text-sm font-semibold text-green-700 dark:text-green-400">You got it!</p>
    </div>
  {:else if done && (revealed || !hasWon)}
    <!-- Revealed / gave up state -->
    <div class="px-4 py-3 bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 rounded-lg {parts ? 'mt-4' : ''}">
      <div class="flex items-center justify-between mb-1">
        <p class="text-xs font-medium text-green-600 dark:text-green-400 uppercase tracking-wide">Answer</p>
        <button
          onclick={hideAnswer}
          class="text-xs text-green-600/70 hover:text-green-700 dark:text-green-400/70 dark:hover:text-green-300 transition-colors flex items-center gap-1"
          title="Hide Answer"
        >
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
          </svg>
          Hide
        </button>
      </div>
      <p class="text-base font-semibold text-green-900 dark:text-green-200">{correctAnswer}</p>
      {#if parts}
        <div class="mt-2 space-y-1">
          {#each parts as part}
            <div class="flex items-center gap-2 text-sm">
              <span class="font-semibold text-green-800 dark:text-green-200">{part.label}:</span>
              <span class="text-green-700 dark:text-green-300">{part.text}</span>
              {#if part.solver}
                <span class="flex items-center gap-1 text-xs text-green-500 dark:text-green-400 ml-auto">
                  <MemberAvatar username={part.solver} size="xs" />
                  {part.solver}
                </span>
              {/if}
            </div>
          {/each}
        </div>
      {:else if solver}
        <p class="text-xs text-green-600 dark:text-green-400 mt-1">Answered by <span class="font-semibold">{solver}</span></p>
      {/if}
    </div>
  {/if}
</div>
