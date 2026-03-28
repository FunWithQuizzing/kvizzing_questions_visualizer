<script lang="ts">
  import { goto } from '$app/navigation';
  import type { QuestionStore } from '$lib/stores/questionStore';

  let { store }: { store: QuestionStore } = $props();

  const allSessions = store.getSessions();
  const questions = store.getQuestions();

  type SessionInfo = { id: string; label: string; tooltip: string };
  type DayActivity = { sessions: SessionInfo[]; questionCount: number };
  const activityByDate = new Map<string, DayActivity>();

  function initials(name: string): string {
    return name.split(' ').map(w => w[0] ?? '').join('').slice(0, 2).toUpperCase();
  }

  for (const session of allSessions) {
    if (!activityByDate.has(session.date)) {
      activityByDate.set(session.date, { sessions: [], questionCount: 0 });
    }
    const label = initials(session.quizmaster);
    const tooltip = session.theme
      ? `${session.quizmaster} — ${session.theme}`
      : `${session.quizmaster}'s Quiz`;
    activityByDate.get(session.date)!.sessions.push({ id: session.id, label, tooltip });
  }
  for (const q of questions) {
    if (!activityByDate.has(q.date)) {
      activityByDate.set(q.date, { sessions: [], questionCount: 0 });
    }
    activityByDate.get(q.date)!.questionCount++;
  }

  // Start on most recent date with activity
  const allDates = [...activityByDate.keys()].sort();
  const latestDate = allDates.at(-1) ?? new Date().toISOString().slice(0, 10);
  const [initYear, initMonth] = latestDate.split('-').map(Number);

  let year = $state(initYear);
  let month = $state(initMonth);

  function prevMonth() {
    if (month === 1) { year--; month = 12; } else month--;
  }
  function nextMonth() {
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
    const remaining = 42 - cells.length;
    const nm = m === 12 ? 1 : m + 1;
    const ny = m === 12 ? y + 1 : y;
    for (let d = 1; d <= remaining; d++) {
      cells.push({ day: d, dateStr: `${ny}-${String(nm).padStart(2,'0')}-${String(d).padStart(2,'0')}`, inMonth: false });
    }
    return cells;
  }

  const grid = $derived(buildGrid(year, month));
  const todayStr = new Date().toISOString().slice(0, 10);

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
    class="fixed z-50 bg-white border border-gray-200 rounded-xl shadow-xl py-1.5 min-w-[170px]"
    style="top: {popoverTop}px; left: {popoverLeft}px;"
    onmouseenter={cancelClose}
    onmouseleave={scheduleClose}
  >
    <p class="text-[10px] font-semibold text-gray-400 uppercase tracking-wide px-3 pb-1">Quiz sessions</p>
    {#each popSessions as s}
      <a
        href="/session/{s.id}"
        class="flex items-center gap-2 px-3 py-1.5 hover:bg-orange-50 transition-colors"
      >
        <span class="w-5 h-5 rounded bg-orange-500 text-white text-[9px] font-bold flex items-center justify-center flex-shrink-0">
          {s.label}
        </span>
        <span class="text-xs text-gray-700 leading-snug">{s.tooltip}</span>
      </a>
    {/each}
  </div>
{/if}

<div class="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
  <!-- Header -->
  <div class="px-4 pt-4 pb-2 flex items-center justify-center">
    <div class="flex items-center gap-1">
      <button
        onclick={prevMonth}
        class="p-1 rounded hover:bg-gray-100 text-gray-500 transition-colors"
        aria-label="Previous month"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7" />
        </svg>
      </button>
      <span class="text-sm font-semibold text-gray-800 w-36 text-center">
        {MONTH_NAMES[month - 1]} {year}
      </span>
      <button
        onclick={nextMonth}
        class="p-1 rounded hover:bg-gray-100 text-gray-500 transition-colors"
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
      <div class="text-center text-[11px] font-medium text-gray-400 py-1">{wd}</div>
    {/each}
  </div>

  <!-- Day grid -->
  <div class="grid grid-cols-7 px-2 pb-3 gap-y-0.5">
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
        class="flex flex-col items-center py-1 px-0.5 rounded-lg transition-colors
          {hasActivity ? 'cursor-pointer hover:bg-orange-50' : 'cursor-default'}
          {!cell.inMonth ? 'opacity-20' : ''}"
      >
        <!-- Date number -->
        <span class="
          text-xs font-medium w-6 h-6 flex items-center justify-center rounded-full mb-0.5
          {isToday ? 'bg-orange-500 text-white' : hasActivity ? 'text-gray-800 font-semibold' : 'text-gray-400'}
        ">
          {cell.day}
        </span>

        <!-- Question count pill (always on top) -->
        {#if questionCount > 0 && cell.inMonth}
          <span
            title="{questionCount} question{questionCount > 1 ? 's' : ''}"
            class="w-full text-center text-[10px] font-semibold leading-none px-0.5 py-[3px] mb-[2px] rounded bg-blue-100 text-blue-700"
          >
            {questionCount}
          </span>
        {/if}

        <!-- Session pill (below questions) -->
        {#if sessionInfos.length > 0 && cell.inMonth}
          <button
            onmouseenter={(e) => openPopover(e, cell.dateStr)}
            onmouseleave={scheduleClose}
            onclick={(e) => { e.stopPropagation(); goto(`/?dateFrom=${cell.dateStr}&dateTo=${cell.dateStr}`); }}
            class="w-full text-center text-[10px] font-bold leading-none px-0.5 py-[3px] rounded bg-orange-500 text-white hover:bg-orange-600 transition-colors"
          >
            {sessionInfos.length}
          </button>
        {/if}
      </div>
    {/each}
  </div>

  <!-- Legend -->
  <div class="px-4 pb-3 flex items-center gap-4 border-t border-gray-100 pt-2">
    <div class="flex items-center gap-1.5">
      <span class="w-4 h-4 rounded bg-blue-100"></span>
      <span class="text-xs text-gray-500">Ad-hoc questions</span>
    </div>
    <div class="flex items-center gap-1.5">
      <span class="w-4 h-4 rounded bg-orange-500"></span>
      <span class="text-xs text-gray-500">Quiz sessions</span>
    </div>
  </div>
</div>
