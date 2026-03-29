<script lang="ts">
  import { goto } from '$app/navigation';
  import type { QuestionStore } from '$lib/stores/questionStore';
  import { dateInTz } from '$lib/utils/time';

  let { store, tz = 'Europe/London' }: { store: QuestionStore; tz?: string } = $props();

  const allSessions = store.getSessions();
  const questions = store.getQuestions();

  type SessionInfo = { id: string; label: string; tooltip: string };
  type DayActivity = { sessions: SessionInfo[]; questionCount: number };

  function initials(name: string): string {
    return name.split(' ').map(w => w[0] ?? '').join('').slice(0, 2).toUpperCase();
  }

  const activityByDate = $derived.by(() => {
    const map = new Map<string, DayActivity>();

    // Derive each session's date from its earliest question timestamp in the selected tz
    const sessionEarliestTs = new Map<string, string>();
    for (const q of questions) {
      if (q.session?.id && q.question?.timestamp) {
        const existing = sessionEarliestTs.get(q.session.id);
        if (!existing || q.question.timestamp < existing) {
          sessionEarliestTs.set(q.session.id, q.question.timestamp);
        }
      }
    }

    for (const session of allSessions) {
      const ts = sessionEarliestTs.get(session.id);
      const d = ts ? dateInTz(ts, tz) : session.date;
      if (!map.has(d)) map.set(d, { sessions: [], questionCount: 0 });
      const label = initials(session.quizmaster);
      const tooltip = session.theme
        ? `${session.quizmaster} — ${session.theme}`
        : `${session.quizmaster}'s Quiz`;
      map.get(d)!.sessions.push({ id: session.id, label, tooltip });
    }

    for (const q of questions) {
      const d = q.question?.timestamp ? dateInTz(q.question.timestamp, tz) : q.date;
      if (!map.has(d)) map.set(d, { sessions: [], questionCount: 0 });
      map.get(d)!.questionCount++;
    }

    return map;
  });

  // Start on most recent date with activity — recompute when tz changes
  const initView = $derived.by(() => {
    const allDates = [...activityByDate.keys()].sort();
    const earliest = allDates.at(0) ?? new Date().toISOString().slice(0, 10);
    const latest = allDates.at(-1) ?? new Date().toISOString().slice(0, 10);
    return { earliest, latest };
  });

  const [initYear, initMonth] = initView.latest.split('-').map(Number);

  let year = $state(initYear);
  let month = $state(initMonth);

  const canGoPrev = $derived.by(() => {
    const [minY, minM] = initView.earliest.split('-').map(Number);
    return year > minY || (year === minY && month > minM);
  });
  const canGoNext = $derived.by(() => {
    const [maxY, maxM] = initView.latest.split('-').map(Number);
    return year < maxY || (year === maxY && month < maxM);
  });

  function prevMonth() {
    if (!canGoPrev) return;
    if (month === 1) { year--; month = 12; } else month--;
  }
  function nextMonth() {
    if (!canGoNext) return;
    if (month === 12) { year++; month = 1; } else month++;
  }

  const WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];
  const MONTH_NAMES = ['January','February','March','April','May','June',
                       'July','August','September','October','November','December'];

  type Cell = { day: number; dateStr: string; inMonth: boolean };

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
    // Fill only to the end of the last partial week
    const remaining = (7 - (cells.length % 7)) % 7;
    const nm = m === 12 ? 1 : m + 1;
    const ny = m === 12 ? y + 1 : y;
    for (let d = 1; d <= remaining; d++) {
      cells.push({ day: d, dateStr: `${ny}-${String(nm).padStart(2,'0')}-${String(d).padStart(2,'0')}`, inMonth: false });
    }
    return cells;
  }

  const grid = $derived(buildGrid(year, month));
  const todayStr = $derived(dateInTz(new Date().toISOString(), tz));

  function handleDayClick(cell: Cell) {
    if (!cell.inMonth) return;
    const activity = activityByDate.get(cell.dateStr);
    if (!activity) return;
    goto(`/?dateFrom=${cell.dateStr}&dateTo=${cell.dateStr}`);
  }

  // Session popover
  let popoverDate = $state<string | null>(null);
  let popoverTop = $state(0);
  let popoverLeft = $state(0);
  let hideTimer: ReturnType<typeof setTimeout> | null = null;

  function openPopover(e: MouseEvent, dateStr: string) {
    if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    popoverDate = dateStr;
    popoverTop = rect.bottom + 4;
    popoverLeft = rect.left;
  }

  function scheduleClose() {
    hideTimer = setTimeout(() => { popoverDate = null; }, 120);
  }

  function cancelClose() {
    if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
  }
</script>

<!-- Session hover popover — fixed so it escapes overflow clipping -->
{#if popoverDate}
  {@const popSessions = activityByDate.get(popoverDate)?.sessions ?? []}
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="fixed z-50 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl shadow-xl py-1.5 min-w-[170px]"
    style="top: {popoverTop}px; left: {popoverLeft}px;"
    onmouseenter={cancelClose}
    onmouseleave={scheduleClose}
  >
    <p class="text-[10px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide px-3 pb-1">Quiz sessions</p>
    {#each popSessions as s}
      <a
        href="/session/{s.id}"
        class="flex items-center gap-2 px-3 py-1.5 hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors"
      >
        <span class="w-5 h-5 rounded bg-primary-500 dark:bg-primary-600 text-white text-[9px] font-bold flex items-center justify-center flex-shrink-0">
          {s.label}
        </span>
        <span class="text-xs text-gray-700 dark:text-gray-300 leading-snug">{s.tooltip}</span>
      </a>
    {/each}
  </div>
{/if}

<div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
  <!-- Header -->
  <div class="px-4 pt-4 pb-2 flex items-center justify-center">
    <div class="flex items-center gap-1">
      <button
        onclick={prevMonth}
        disabled={!canGoPrev}
        class="p-1 rounded transition-colors {canGoPrev ? 'hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400' : 'text-gray-200 dark:text-gray-600 cursor-default'}"
        aria-label="Previous month"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
        </svg>
      </button>
      <span class="text-sm font-semibold text-gray-800 dark:text-gray-200 w-36 text-center">
        {MONTH_NAMES[month - 1]} {year}
      </span>
      <button
        onclick={nextMonth}
        disabled={!canGoNext}
        class="p-1 rounded transition-colors {canGoNext ? 'hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400' : 'text-gray-200 dark:text-gray-600 cursor-default'}"
        aria-label="Next month"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
        </svg>
      </button>
    </div>
  </div>

  <!-- Weekday headers -->
  <div class="grid grid-cols-7 px-2">
    {#each WEEKDAYS as wd}
      <div class="text-center text-[11px] font-medium text-gray-400 dark:text-gray-500 py-1">{wd}</div>
    {/each}
  </div>

  <!-- Day grid -->
  <div class="grid grid-cols-7 px-2 pb-3 gap-y-0.5"
    style="mask-image: linear-gradient(to right, transparent, black 8%, black 92%, transparent); -webkit-mask-image: linear-gradient(to right, transparent, black 8%, black 92%, transparent);"
  >
    {#each grid as cell}
      {@const activity = activityByDate.get(cell.dateStr)}
      {@const isToday = cell.dateStr === todayStr}
      {@const hasActivity = !!activity && cell.inMonth}
      {@const sessionInfos = activity?.sessions ?? []}
      {@const questionCount = activity?.questionCount ?? 0}

      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <div
        onclick={() => handleDayClick(cell)}
        onkeydown={(e) => { if (e.key === 'Enter') handleDayClick(cell); }}
        role={hasActivity ? 'button' : undefined}
        tabindex={hasActivity ? 0 : undefined}
        class="flex flex-col items-center py-0.5 px-0.5 rounded-lg transition-colors
          {hasActivity ? 'cursor-pointer hover:bg-primary-50 dark:hover:bg-primary-900/20' : 'cursor-default'}
          {!cell.inMonth ? 'opacity-20' : ''}"
      >
        <!-- Date number -->
        <span class="
          text-xs font-medium w-6 h-6 flex items-center justify-center rounded-full flex-shrink-0
          {isToday ? 'bg-primary-500 dark:bg-primary-600 text-white' : hasActivity ? 'text-gray-800 dark:text-gray-200 font-semibold' : 'text-gray-400 dark:text-gray-500'}
        ">
          {cell.day}
        </span>

        <!-- Question count pill (invisible placeholder keeps row height uniform) -->
        <span
          title="{questionCount} question{questionCount > 1 ? 's' : ''}"
          class="w-full text-center text-[10px] font-semibold leading-none px-0.5 py-[2px] rounded mt-px
            {questionCount > 0 && cell.inMonth ? 'bg-primary-100 text-primary-600 dark:bg-primary-900/40 dark:text-primary-300' : 'invisible'}"
        >
          {questionCount}
        </span>

        <!-- Session pill (invisible placeholder keeps row height uniform) -->
        <button
          onmouseenter={(e) => { if (sessionInfos.length > 0 && cell.inMonth) openPopover(e, cell.dateStr); }}
          onmouseleave={scheduleClose}
          onclick={(e) => { e.stopPropagation(); if (sessionInfos.length > 0 && cell.inMonth) goto(`/?dateFrom=${cell.dateStr}&dateTo=${cell.dateStr}`); }}
          class="w-full text-center text-[10px] font-bold leading-none px-0.5 py-[2px] rounded mt-px transition-colors
            {sessionInfos.length > 0 && cell.inMonth ? 'bg-primary-500 dark:bg-primary-600 text-white hover:bg-primary-600 dark:hover:bg-primary-700' : 'invisible'}"
        >
          {sessionInfos.length}
        </button>
      </div>
    {/each}
  </div>

</div>
