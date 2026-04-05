<script lang="ts">
  import { getContext } from 'svelte';
  import type { DiscussionEntry } from '$lib/types';
  import { formatTimestampTz } from '$lib/utils/time';
  import MemberAvatar from './MemberAvatar.svelte';

  const tz = getContext<{ value: string }>('timezone');

  let { entries }: { entries: DiscussionEntry[] } = $props();

  function roleStyle(role: string, isCorrect: boolean | null): string {
    switch (role) {
      case 'attempt':
        return isCorrect
          ? 'bg-green-50 dark:bg-green-900/30 border-green-200 dark:border-green-700'
          : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-600';
      case 'hint':
        return 'bg-amber-50 dark:bg-amber-900/30 border-amber-200 dark:border-amber-700';
      case 'confirmation':
        return 'bg-green-50 dark:bg-green-900/30 border-green-200 dark:border-green-700';
      case 'answer_reveal':
        return 'bg-indigo-50 dark:bg-indigo-900/30 border-indigo-200 dark:border-indigo-700';
      case 'elaboration':
        return 'bg-cyan-50 dark:bg-cyan-900/30 border-cyan-200 dark:border-cyan-700';
      case 'chat':
        return 'bg-gray-50 dark:bg-gray-800 border-gray-200 dark:border-gray-600';
      default:
        return 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-600';
    }
  }

  function roleLabel(role: string, isCorrect: boolean | null): string | null {
    switch (role) {
      case 'hint': return 'hint';
      case 'answer_reveal': return 'reveal';
      case 'elaboration': return 'info';
      case 'confirmation': return isCorrect ? 'correct' : 'confirmation';
      default: return null;
    }
  }

  function roleLabelStyle(role: string): string {
    switch (role) {
      case 'hint': return 'text-amber-600 bg-amber-100 dark:text-amber-400 dark:bg-amber-900/40';
      case 'answer_reveal': return 'text-indigo-600 bg-indigo-100 dark:text-indigo-400 dark:bg-indigo-900/40';
      case 'elaboration': return 'text-cyan-600 bg-cyan-100 dark:text-cyan-400 dark:bg-cyan-900/40';
      case 'confirmation': return 'text-green-600 bg-green-100 dark:text-green-400 dark:bg-green-900/40';
      default: return 'text-gray-500 bg-gray-100 dark:text-gray-400 dark:bg-gray-700';
    }
  }
</script>

<div class="space-y-2">
  {#each entries as entry}
    <div class="flex gap-2.5 items-start">
      <MemberAvatar username={entry.username} size="xs" />
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-1.5 mb-0.5 flex-wrap">
          <span class="text-xs font-semibold text-gray-700 dark:text-gray-200 break-all">{entry.username}</span>
          {#if roleLabel(entry.role, entry.is_correct)}
            <span class="text-[10px] px-1.5 py-0.5 rounded font-medium {roleLabelStyle(entry.role)}">
              {roleLabel(entry.role, entry.is_correct)}
            </span>
          {/if}
          {#if entry.role === 'attempt' && entry.is_correct === false}
            <span class="text-[10px] px-1.5 py-0.5 rounded font-medium text-red-600 bg-red-100 dark:text-red-400 dark:bg-red-900/40">wrong</span>
          {/if}
          {#if entry.role === 'attempt' && entry.is_correct === true}
            <span class="text-[10px] px-1.5 py-0.5 rounded font-medium text-green-600 bg-green-100 dark:text-green-400 dark:bg-green-900/40">✓ correct</span>
          {/if}
          <span class="text-[10px] text-gray-400 ml-auto">{formatTimestampTz(entry.timestamp, tz?.value ?? 'Europe/London')}</span>
        </div>
        <div
          class="rounded-lg border px-3 py-2 text-sm {roleStyle(entry.role, entry.is_correct)} {entry.role === 'hint' ? 'italic' : ''}"
        >
          {#if entry.role === 'answer_reveal'}
            <span class="font-medium text-indigo-800 dark:text-indigo-300">{entry.text}</span>
          {:else}
            <span class="text-gray-700 dark:text-gray-200">{entry.text}</span>
          {/if}
          {#if entry.media}
            <div class="mt-1.5">
              <span class="text-xs text-purple-500">📎 {entry.media}</span>
            </div>
          {/if}
        </div>
      </div>
    </div>
  {/each}
</div>
