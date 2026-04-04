<script lang="ts">
  import type { Snippet } from 'svelte';

  export type Cell = { day: number; dateStr: string; inMonth: boolean };

  let {
    year,
    month,
    canGoPrev,
    canGoNext,
    prevMonth,
    nextMonth,
    dayContent,
    legend,
  }: {
    year: number;
    month: number;
    canGoPrev: boolean;
    canGoNext: boolean;
    prevMonth: () => void;
    nextMonth: () => void;
    dayContent: Snippet<[Cell]>;
    legend?: Snippet;
  } = $props();

  const WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];
  const MONTH_NAMES = ['January','February','March','April','May','June',
                       'July','August','September','October','November','December'];

  function buildGrid(y: number, m: number): Cell[] {
    const firstDay = new Date(y, m - 1, 1).getDay();
    const daysInMonth = new Date(y, m, 0).getDate();
    const daysInPrev = new Date(y, m - 1, 0).getDate();
    const cells: Cell[] = [];
    for (let i = firstDay - 1; i >= 0; i--) {
      const d = daysInPrev - i;
      const pm = m === 1 ? 12 : m - 1;
      const py = m === 1 ? y - 1 : y;
      cells.push({ day: d, dateStr: `${py}-${String(pm).padStart(2,'0')}-${String(d).padStart(2,'0')}`, inMonth: false });
    }
    for (let d = 1; d <= daysInMonth; d++) {
      cells.push({ day: d, dateStr: `${y}-${String(m).padStart(2,'0')}-${String(d).padStart(2,'0')}`, inMonth: true });
    }
    const remaining = (7 - (cells.length % 7)) % 7;
    const nm = m === 12 ? 1 : m + 1;
    const ny = m === 12 ? y + 1 : y;
    for (let d = 1; d <= remaining; d++) {
      cells.push({ day: d, dateStr: `${ny}-${String(nm).padStart(2,'0')}-${String(d).padStart(2,'0')}`, inMonth: false });
    }
    return cells;
  }

  const grid = $derived(buildGrid(year, month));
</script>

<div class="relative bg-white dark:bg-neutral-900 rounded-xl border border-gray-200 dark:border-neutral-700 shadow-sm">
  <!-- Header -->
  <div class="bg-gradient-to-br from-primary-600 to-primary-900 dark:from-primary-700 dark:to-primary-900 rounded-t-xl px-4 pt-4 pb-2 flex items-center justify-center">
    <div class="flex items-center gap-1">
      <button
        onclick={prevMonth}
        disabled={!canGoPrev}
        class="p-1 rounded transition-colors {canGoPrev ? 'hover:bg-primary-400 dark:hover:bg-primary-500 text-primary-100' : 'text-primary-300 dark:text-primary-400 cursor-default'}"
        aria-label="Previous month"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
        </svg>
      </button>
      <span class="text-sm font-semibold text-white w-36 text-center">
        {MONTH_NAMES[month - 1]} {year}
      </span>
      <button
        onclick={nextMonth}
        disabled={!canGoNext}
        class="p-1 rounded transition-colors {canGoNext ? 'hover:bg-primary-400 dark:hover:bg-primary-500 text-primary-100' : 'text-primary-300 dark:text-primary-400 cursor-default'}"
        aria-label="Next month"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
        </svg>
      </button>
    </div>
  </div>

  <!-- Weekday headers -->
  <div class="grid grid-cols-7 px-2 bg-primary-50 dark:bg-primary-900/20">
    {#each WEEKDAYS as wd}
      <div class="text-center text-[11px] font-semibold text-primary-600 dark:text-primary-400 py-1.5">{wd}</div>
    {/each}
  </div>

  <!-- Day grid -->
  <div class="grid grid-cols-7 px-2 pb-3 gap-1">
    {#each grid as cell}
      <div class="border border-gray-100 dark:border-neutral-700/40 rounded-lg bg-gray-50/50 dark:bg-neutral-800 {cell.inMonth ? '' : 'bg-transparent border-transparent dark:bg-transparent dark:border-transparent'}">
        {@render dayContent(cell)}
      </div>
    {/each}
  </div>

  <!-- Legend -->
  {#if legend}
    <div class="px-3 pb-3 flex items-center gap-3 justify-center">
      {@render legend()}
    </div>
  {/if}
</div>
