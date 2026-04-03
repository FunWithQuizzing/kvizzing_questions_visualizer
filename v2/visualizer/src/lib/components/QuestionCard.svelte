<script lang="ts">
  import type { Question } from '$lib/types';
  import { getContext } from 'svelte';
  import { goto } from '$app/navigation';
  import { formatDateTz, formatTime } from '$lib/utils/time';
  import MemberAvatar from './MemberAvatar.svelte';
  import { topicCls, topicClsSecondary, topicLabel } from '$lib/utils/topicColors';
  import { filterHints } from '$lib/utils/hints';
  import { isCorrect, isAlmost } from '$lib/utils/fuzzy';
  import MediaGallery from './MediaGallery.svelte';
  import { displayText } from '$lib/utils/text';
  import { supabase } from '$lib/supabase';

  const tzCtx = getContext<{ value: string } | undefined>('timezone');
  const usernameCtx = getContext<{ value: string }>('username');

  let {
    question,
    hideSession = false,
    questionNumber = undefined,
    revealed = $bindable(false),
    hintsShown = $bindable(0),
    input = $bindable(''),
    result = $bindable(null),
  }: {
    question: Question;
    hideSession?: boolean;
    questionNumber?: number;
    revealed?: boolean;
    hintsShown?: number;
    input?: string;
    result?: 'correct' | 'almost' | 'wrong' | null;
  } = $props();

  function submitGuess() {
    const val = input.trim();
    if (!val || !a?.text) return;
    if (isCorrect(val, a.text)) { result = 'correct'; revealed = true; }
    else if (isAlmost(val, a.text)) result = 'almost';
    else result = 'wrong';
  }

  let flagged = $state(false);
  let showFlagModal = $state(false);
  let flagReason = $state('');
  const flagPresets = ['Not a trivia question', 'Duplicate question', 'Wrong answer', 'Missing context', 'Incorrect category'];

  // Check flag state from shared context (loaded once at page level)
  const flaggedIds = getContext<{ value: Set<string> } | undefined>('flaggedIds');
  $effect(() => {
    flagged = flaggedIds?.value?.has(question.id) ?? false;
  });

  function openFlagModal(e: MouseEvent) {
    e.stopPropagation();
    if (flagged) { unflag(); return; }
    showFlagModal = true;
    flagReason = '';
  }

  let vanishing = $state(false);
  let hidden = $state(false);

  async function submitFlag(reason: string) {
    const reporter = usernameCtx?.value || '';
    if (!reporter) { showFlagModal = false; return; }
    showFlagModal = false;
    flagged = true;
    if (flaggedIds) flaggedIds.value = new Set([...flaggedIds.value, question.id]);
    vanishing = true;
    setTimeout(() => { hidden = true; }, 400);
    await supabase.from('question_flags').upsert(
      { question_id: question.id, reporter, reason },
      { onConflict: 'question_id,reporter' }
    );
  }

  async function unflag() {
    const reporter = usernameCtx?.value || '';
    if (!reporter) return;
    flagged = false;
    if (flaggedIds) {
      const next = new Set(flaggedIds.value);
      next.delete(question.id);
      flaggedIds.value = next;
    }
    await supabase.from('question_flags').delete().eq('question_id', question.id).eq('reporter', reporter);
  }

  const q = $derived(question.question);
  const a = $derived(question.answer);
  const stats = $derived(question.stats);
  const hints = $derived(filterHints(question.discussion?.filter(d => d.role === 'hint').map(d => d.text) ?? []));
  const questionMedia = $derived((q.media ?? []).filter(m => m.url));
  const answerMedia = $derived(
    (question.discussion ?? [])
      .filter(d => d.role === 'answer_reveal' && d.media?.some(m => m.url))
      .flatMap(d => d.media ?? [])
      .filter(m => m.url)
  );
</script>

{#if !hidden}
<article class="bg-ui-card rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm hover:shadow-md hover:border-gray-300 transition-all duration-300 overflow-hidden group {vanishing ? 'opacity-0 scale-95 -translate-x-4 max-h-0 !my-0 !py-0 !border-0' : ''}">
  <!-- Clickable card body -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div
    class="p-5 cursor-pointer overflow-hidden"
    role="link"
    tabindex="0"
    onclick={(e) => { if (!(e.target as HTMLElement).closest('a,button,input')) goto(`/question/${question.id}`); }}
    onkeydown={(e) => { if (e.key === 'Enter') goto(`/question/${question.id}`); }}
  >
    <!-- Header row -->
    <div class="flex items-start justify-between gap-3 mb-3">
      <div class="flex items-center gap-2 flex-wrap">
        {#if questionNumber !== undefined}
          <div class="w-7 h-7 rounded-lg bg-primary-100 text-primary-600 dark:bg-primary-900/40 dark:text-primary-300 font-bold text-sm flex items-center justify-center flex-shrink-0">
            {questionNumber}
          </div>
        {/if}
        <MemberAvatar username={q.asker} />
        <div>
          <span class="text-sm font-medium text-gray-900 dark:text-gray-100">{q.asker}</span>
          <span class="text-xs text-gray-400 dark:text-gray-500 ml-1.5">{formatDateTz(question.question.timestamp ?? question.date, tzCtx?.value ?? 'Europe/London')}</span>
        </div>
      </div>
      <div class="flex items-center gap-1.5 flex-wrap justify-end min-w-0">
        {#if question.session && !hideSession}
          <a
            href="/session/{question.session.id}"
            class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-primary-100 text-primary-700 hover:bg-primary-200 dark:bg-primary-900/40 dark:text-primary-300 dark:hover:bg-primary-900/40 transition-colors max-w-[300px] truncate"
          >
            #{question.session.question_number} {question.session.quiz_type === 'connect' ? `${question.session.quizmaster}'s Connect Quiz` : (question.session.theme ?? 'Session')}
          </a>
        {/if}
        {#each (q.topics ?? []) as topic, i}
          <button
            onclick={(e) => { e.stopPropagation(); goto(`/?topic=${topic}`); }}
            class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium transition-colors {i === 0 ? topicCls(topic) : topicClsSecondary(topic)}"
          >
            {topicLabel(topic)}
          </button>
        {/each}
        {#if q.has_media && questionMedia.length === 0}
          <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300">
            📎 media
          </span>
        {/if}
      </div>
    </div>

    <!-- Question text -->
    <a href="/question/{question.id}" class="block">
      <p class="text-gray-800 dark:text-gray-200 text-sm leading-relaxed group-hover:text-gray-900 dark:group-hover:text-gray-100">
        {displayText(q.text, questionMedia.length > 0)}
      </p>
    </a>

    <!-- Question media (shown when CDN URLs are available) -->
    {#if questionMedia.length > 0}
      <div class="mt-3" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()} role="presentation">
        <MediaGallery attachments={questionMedia} compact />
      </div>
    {/if}

    <!-- Stats row + tags -->
    <div class="flex items-center justify-between gap-3 mt-3">
      <div class="flex items-center gap-4 text-xs text-gray-400 dark:text-gray-500 min-w-0">
        {#if stats?.time_to_answer_seconds}
          <span class="flex items-center gap-1 flex-shrink-0">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {formatTime(stats.time_to_answer_seconds)}
          </span>
        {/if}
        {#if stats?.wrong_attempts > 0}
          <span class="flex items-center gap-1 flex-shrink-0">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
            {stats.wrong_attempts} wrong
          </span>
        {/if}
        {#if question.discussion?.length > 0}
          <span class="flex items-center gap-1 flex-shrink-0">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            {question.discussion.length} messages
          </span>
        {/if}
      </div>
      <button
        onclick={openFlagModal}
        class="flex items-center gap-1.5 flex-shrink-0 px-2 py-1 rounded-lg text-xs font-medium transition-colors {flagged ? 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400' : 'text-gray-400 dark:text-gray-500 hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-900/20 dark:hover:text-red-400'}"
        title={flagged ? 'Unflag — this is a valid question' : 'Flag this question'}
      >
        <svg class="w-4 h-4" fill={flagged ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 21v-4m0 0V5a2 2 0 012-2h6.5l1 1H21l-3 6 3 6h-8.5l-1-1H5a2 2 0 00-2 2z" />
        </svg>
        {flagged ? 'Flagged' : 'Flag'}
      </button>
    </div>
  </div>

  <!-- Answer reveal strip -->
  <div class="border-t border-gray-100 dark:border-gray-700">
    {#if revealed}
      <div class="bg-green-50 dark:bg-green-900/30">
        <div class="px-3 py-2.5 min-h-[48px] flex flex-wrap items-center gap-x-3 gap-y-1">
          <span class="text-xs font-medium text-green-600 dark:text-green-400 uppercase tracking-wide flex-shrink-0">Answer</span>
          <span class="text-sm font-semibold text-green-800 dark:text-green-200 flex-1 min-w-0">{a?.text ?? '—'}</span>
          <div class="flex items-center gap-2 flex-shrink-0 ml-auto">
            {#if a?.solver}
              <div class="flex items-center gap-1.5 text-xs text-green-600 dark:text-green-400">
                <MemberAvatar username={a.solver} size="xs" />
                <span class="hidden sm:inline">{a.solver}</span>
              </div>
            {/if}
            <button
              onclick={() => { revealed = false; result = null; input = ''; }}
              class="text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors flex items-center gap-1"
              title="Hide Answer"
            >
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
              </svg>
              Hide
            </button>
          </div>
        </div>
        {#if a?.parts && a.parts.length > 1}
          <div class="px-3 pb-2.5 flex flex-wrap gap-x-4 gap-y-1">
            {#each a.parts as part}
              <span class="text-xs text-green-700 dark:text-green-300">
                <span class="font-semibold">{part.label}:</span>
                {part.text}{#if part.solver}<span class="text-green-500 dark:text-green-400"> ({part.solver})</span>{/if}
              </span>
            {/each}
          </div>
        {/if}
        {#if answerMedia.length > 0}
          <div class="px-3 pb-3" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()} role="presentation">
            <MediaGallery attachments={answerMedia} compact />
          </div>
        {/if}
      </div>
    {:else}
      {#if hintsShown > 0}
        <div class="px-5 py-2 bg-amber-50 dark:bg-amber-900/30 border-b border-amber-100 dark:border-amber-800 space-y-1">
          {#each hints.slice(0, hintsShown) as hint}
            <p class="text-xs text-amber-700 dark:text-amber-300 flex items-start gap-1.5">
              <svg class="w-3.5 h-3.5 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
              {hint}
            </p>
          {/each}
        </div>
      {/if}
      <div class="px-3 py-2.5 flex items-center gap-2">
        {#if a?.parts && a.parts.length > 1}
          <a
            href="/question/{question.id}"
            class="flex-1 min-w-0 px-2.5 py-2 text-xs text-gray-400 dark:text-gray-500 hover:text-primary-500 dark:hover:text-primary-400 transition-colors"
          >{a.parts.length}-part answer — try each part →</a>
        {:else}
          <input
            type="text"
            placeholder="Your answer…"
            bind:value={input}
            onkeydown={(e) => { if (e.key === 'Enter') submitGuess(); }}
            class="flex-1 min-w-0 px-2.5 py-2 text-xs border rounded-lg focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 transition-all
              {result === 'correct' ? 'border-green-300 bg-green-50 dark:bg-green-900/30' : result === 'almost' ? 'border-amber-300 bg-amber-50 dark:bg-amber-900/30' : result === 'wrong' ? 'border-red-300 bg-red-50' : 'border-gray-200 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200 dark:placeholder-gray-400'}"
            autocomplete="off" spellcheck="false"
            title={result === 'almost' ? 'Close! Try again.' : result === 'wrong' ? 'Not quite. Try again or reveal.' : ''}
          />
          <button
            onclick={submitGuess}
            class="px-3 py-2 text-xs font-medium bg-primary-500 text-white rounded-lg hover:bg-primary-600 dark:bg-primary-600 transition-colors flex-shrink-0"
          >Submit</button>
        {/if}
        <div class="flex items-center gap-2 flex-shrink-0">
          <button
            onclick={() => hintsShown = Math.min(hintsShown + 1, hints.length)}
            disabled={hints.length === 0 || hintsShown >= hints.length}
            title={hints.length === 0 ? 'No hints available' : hintsShown >= hints.length ? 'No more hints' : `Hint ${hintsShown + 1} of ${hints.length}`}
            class="p-1.5 rounded-lg transition-colors {hints.length === 0 || hintsShown >= hints.length ? 'text-gray-300 cursor-default' : 'text-amber-500 hover:bg-amber-50 dark:hover:bg-amber-900/20'}"
          >
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </button>
          <button
            onclick={() => revealed = true}
            class="text-xs text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 font-medium transition-colors"
          >Reveal</button>
        </div>
      </div>
    {/if}
  </div>
</article>

<!-- Flag modal -->
{#if showFlagModal}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
    onclick={() => showFlagModal = false}
  >
    <div
      class="bg-white dark:bg-gray-800 rounded-2xl shadow-xl p-5 w-full max-w-sm space-y-3"
      onclick={(e) => e.stopPropagation()}
    >
      <h3 class="text-sm font-bold text-gray-900 dark:text-gray-100">Flag this question</h3>
      <p class="text-xs text-gray-500 dark:text-gray-400">Why should this question be reviewed?</p>
      <div class="flex flex-wrap gap-1.5">
        {#each flagPresets as preset}
          <button
            onclick={() => submitFlag(preset)}
            class="px-2.5 py-1 rounded-full text-xs font-medium bg-red-100 text-red-700 hover:bg-red-200 dark:bg-red-900/30 dark:text-red-300 dark:hover:bg-red-900/50 transition-colors"
          >{preset}</button>
        {/each}
      </div>
      <div class="flex gap-2">
        <input
          type="text"
          placeholder="Or type a reason..."
          bind:value={flagReason}
          onkeydown={(e) => { if (e.key === 'Enter' && flagReason.trim()) submitFlag(flagReason.trim()); }}
          class="flex-1 text-xs border border-gray-200 dark:border-gray-600 rounded-lg px-2.5 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-red-400"
        />
        <button
          onclick={() => { if (flagReason.trim()) submitFlag(flagReason.trim()); }}
          disabled={!flagReason.trim()}
          class="px-3 py-1.5 text-xs font-medium rounded-lg transition-colors {flagReason.trim() ? 'bg-red-500 text-white hover:bg-red-600' : 'bg-gray-200 text-gray-400 dark:bg-gray-700 dark:text-gray-500'}"
        >Flag</button>
      </div>
      <button onclick={() => showFlagModal = false} class="w-full text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors">Cancel</button>
    </div>
  </div>
{/if}
{/if}
