<script lang="ts">
  import type { DiscussionEntry } from '$lib/types';
  import { formatTimestamp } from '$lib/utils/time';
  import MemberAvatar from './MemberAvatar.svelte';

  let { entries }: { entries: DiscussionEntry[] } = $props();

  function roleStyle(role: string, isCorrect: boolean | null): string {
    switch (role) {
      case 'attempt':
        return isCorrect
          ? 'bg-green-50 border-green-200'
          : 'bg-white border-gray-200';
      case 'hint':
        return 'bg-amber-50 border-amber-200';
      case 'confirmation':
        return 'bg-green-50 border-green-200';
      case 'answer_reveal':
        return 'bg-indigo-50 border-indigo-200';
      case 'chat':
        return 'bg-gray-50 border-gray-200';
      default:
        return 'bg-white border-gray-200';
    }
  }

  function roleLabel(role: string, isCorrect: boolean | null): string | null {
    switch (role) {
      case 'hint': return 'hint';
      case 'answer_reveal': return 'reveal';
      case 'confirmation': return isCorrect ? 'correct' : 'confirmation';
      default: return null;
    }
  }

  function roleLabelStyle(role: string): string {
    switch (role) {
      case 'hint': return 'text-amber-600 bg-amber-100';
      case 'answer_reveal': return 'text-indigo-600 bg-indigo-100';
      case 'confirmation': return 'text-green-600 bg-green-100';
      default: return 'text-gray-500 bg-gray-100';
    }
  }
</script>

<div class="space-y-2">
  {#each entries as entry}
    <div class="flex gap-2.5 items-start">
      <MemberAvatar username={entry.username} size="xs" />
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-1.5 mb-0.5">
          <span class="text-xs font-semibold text-gray-700">{entry.username}</span>
          {#if roleLabel(entry.role, entry.is_correct)}
            <span class="text-[10px] px-1.5 py-0.5 rounded font-medium {roleLabelStyle(entry.role)}">
              {roleLabel(entry.role, entry.is_correct)}
            </span>
          {/if}
          {#if entry.role === 'attempt' && entry.is_correct === false}
            <span class="text-[10px] px-1.5 py-0.5 rounded font-medium text-red-600 bg-red-100">wrong</span>
          {/if}
          {#if entry.role === 'attempt' && entry.is_correct === true}
            <span class="text-[10px] px-1.5 py-0.5 rounded font-medium text-green-600 bg-green-100">✓ correct</span>
          {/if}
          <span class="text-[10px] text-gray-400 ml-auto">{formatTimestamp(entry.timestamp)}</span>
        </div>
        <div
          class="rounded-lg border px-3 py-2 text-sm {roleStyle(entry.role, entry.is_correct)} {entry.role === 'hint' ? 'italic' : ''}"
        >
          {#if entry.role === 'answer_reveal'}
            <span class="font-medium text-indigo-800">{entry.text}</span>
          {:else}
            <span class="text-gray-700">{entry.text}</span>
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
