<script lang="ts">
  import { getContext } from 'svelte';
  import type { QuestionStore } from '$lib/stores/questionStore';
  import { getMemberColor, getMemberInitials } from '$lib/utils/memberColors';
  import { formatTime } from '$lib/utils/time';
  import MemberAvatar from '$lib/components/MemberAvatar.svelte';
  import { topicCls, topicLabel, topicHex } from '$lib/utils/topicColors';
  import { goto } from '$app/navigation';

  const store = getContext<QuestionStore>('store');
  const members = store.getMembers();
  const questions = store.getQuestions();

  // Speed leaderboard — members with ≥5 solves
  const MIN_SOLVES = 5;
  const speedLeaderboard = members
    .filter(m => m.questions_solved >= MIN_SOLVES && m.avg_solve_time_seconds != null)
    .sort((a, b) => (a.avg_solve_time_seconds ?? Infinity) - (b.avg_solve_time_seconds ?? Infinity))
    .slice(0, 10);

  // Top askers
  const topAskers = [...members]
    .filter(m => m.questions_asked > 0)
    .sort((a, b) => b.questions_asked - a.questions_asked)
    .slice(0, 10);

  // Top category per asker
  const askerTopCategory = new Map<string, string>();
  {
    const askerTopicCounts = new Map<string, Map<string, number>>();
    for (const q of questions) {
      const asker = q.question.asker;
      const topic = q.question.topics?.[0];
      if (!asker || !topic) continue;
      if (!askerTopicCounts.has(asker)) askerTopicCounts.set(asker, new Map());
      const m = askerTopicCounts.get(asker)!;
      m.set(topic, (m.get(topic) ?? 0) + 1);
    }
    for (const [asker, counts] of askerTopicCounts) {
      const top = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
      if (top) askerTopCategory.set(asker, top[0]);
    }
  }

  // Top solvers
  const topSolvers = [...members]
    .filter(m => m.questions_solved > 0)
    .sort((a, b) => b.questions_solved - a.questions_solved)
    .slice(0, 10);

  // Pie chart — primary category (topics[0]) per question
  const primaryCounts = new Map<string, number>();
  for (const q of questions) {
    const primary = q.question.topics?.[0];
    if (primary) primaryCounts.set(primary, (primaryCounts.get(primary) ?? 0) + 1);
  }
  const pieTotal = [...primaryCounts.values()].reduce((s, n) => s + n, 0);
  const pieRows = [...primaryCounts.entries()].sort((a, b) => b[1] - a[1]);

  // SVG donut helpers
  function polar(cx: number, cy: number, r: number, deg: number) {
    const rad = (deg - 90) * Math.PI / 180;
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
  }
  function donutPath(cx: number, cy: number, ro: number, ri: number, start: number, sweep: number) {
    const s = Math.min(sweep, 359.9999);
    const os = polar(cx, cy, ro, start), oe = polar(cx, cy, ro, start + s);
    const is = polar(cx, cy, ri, start), ie = polar(cx, cy, ri, start + s);
    const lg = s > 180 ? 1 : 0;
    return `M${os.x} ${os.y} A${ro} ${ro} 0 ${lg} 1 ${oe.x} ${oe.y} L${ie.x} ${ie.y} A${ri} ${ri} 0 ${lg} 0 ${is.x} ${is.y}Z`;
  }

  let pieAngle = 0;
  const pieSlices = pieRows.map(([topic, count]) => {
    const sweep = (count / pieTotal) * 360;
    const start = pieAngle;
    pieAngle += sweep;
    return { topic, count, start, sweep };
  });

  let hoveredSlice = $state<string | null>(null);

  // Tags distribution (free-form tags, sorted by frequency, top 25)
  const tagCounts = new Map<string, number>();
  for (const q of questions) {
    for (const tag of q.question.tags ?? []) {
      tagCounts.set(tag, (tagCounts.get(tag) ?? 0) + 1);
    }
  }
  const topTags = [...tagCounts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 25);
  const maxTagCount = topTags[0]?.[1] ?? 1;

  // Most discussed questions
  const mostDiscussed = [...questions]
    .sort((a, b) => (b.discussion?.length ?? 0) - (a.discussion?.length ?? 0))
    .slice(0, 5);

  // Quickest solves
  const quickest = [...questions]
    .filter(q => q.stats?.time_to_answer_seconds != null)
    .sort((a, b) => (a.stats?.time_to_answer_seconds ?? Infinity) - (b.stats?.time_to_answer_seconds ?? Infinity))
    .slice(0, 5);

  // Hardest (most wrong attempts + hardest difficulty)
  const trickiest = [...questions]
    .filter(q => q.stats?.wrong_attempts != null)
    .sort((a, b) => (b.stats?.wrong_attempts ?? 0) - (a.stats?.wrong_attempts ?? 0))
    .slice(0, 5);

  type Tab = 'leaderboard' | 'topics' | 'moments';
  let activeTab = $state<Tab>('topics');

  const tabs: { id: Tab; label: string }[] = [
    { id: 'topics', label: 'Tags & Topics' },
    { id: 'moments', label: 'Best Moments' },
    { id: 'leaderboard', label: 'Leaderboard' },
  ];
</script>

<svelte:head>
  <title>Highlights — KVizzing</title>
</svelte:head>

<div class="space-y-6">
  <!-- Header -->
  <div>
    <h1 class="text-2xl font-bold text-gray-900 dark:text-gray-100">Highlights</h1>
    <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">The group's story, in numbers</p>
  </div>

  <!-- Quick stats row -->
  <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
    <a href="/" class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 shadow-sm text-center hover:border-primary-300 hover:shadow-md transition-all">
      <p class="text-2xl font-bold text-primary-500 dark:text-primary-400">{questions.length}</p>
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">Total questions</p>
    </a>
    <a href="/sessions" class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 shadow-sm text-center hover:border-blue-300 hover:shadow-md transition-all">
      <p class="text-2xl font-bold text-blue-500">{store.getSessions().length}</p>
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">Quiz sessions</p>
    </a>
    <a href="/?asker=" class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 shadow-sm text-center hover:border-green-300 hover:shadow-md transition-all">
      <p class="text-2xl font-bold text-green-500">{store.getAskers().length}</p>
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">Askers</p>
    </a>
    <a href="/?solver=" class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 shadow-sm text-center hover:border-purple-300 hover:shadow-md transition-all">
      <p class="text-2xl font-bold text-purple-500">{store.getSolvers().length}</p>
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">Solvers</p>
    </a>
  </div>

  <!-- Tabs -->
  <div class="flex gap-1 bg-gray-100 dark:bg-gray-700 p-1 rounded-xl w-fit">
    {#each tabs as tab}
      <button
        onclick={() => activeTab = tab.id}
        class="px-4 py-1.5 text-sm font-medium rounded-lg transition-colors {activeTab === tab.id ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100 shadow-sm' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'}"
      >
        {tab.label}
      </button>
    {/each}
  </div>

  <!-- Leaderboard tab -->
  {#if activeTab === 'leaderboard'}
    <div class="grid gap-6 lg:grid-cols-3">
      <!-- Top Solvers -->
      <div class="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
        <div class="px-5 py-4 border-b border-gray-100 dark:border-gray-700">
          <h2 class="font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <span class="text-lg">🏆</span> Top Solvers
          </h2>
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">By questions solved</p>
        </div>
        <div class="divide-y divide-gray-50 dark:divide-gray-700">
          {#each topSolvers as member, i}
            <div class="pl-1 pr-4 py-3 flex items-center gap-3 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
              <span class="text-sm font-bold {i === 0 ? 'text-amber-400' : i === 1 ? 'text-gray-400' : i === 2 ? 'text-amber-600' : 'text-gray-300 dark:text-gray-600'} w-6 text-right flex-shrink-0">
                {i + 1}
              </span>
              <MemberAvatar username={member.username} color={member.color} displayName={member.display_name} size="sm" />
              <div class="flex-1 min-w-0">
                <p class="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">{member.display_name}</p>
                {#if member.avg_solve_time_seconds}
                  <p class="text-xs text-gray-400 dark:text-gray-500">avg {formatTime(member.avg_solve_time_seconds)}</p>
                {/if}
              </div>
              <span class="text-sm font-semibold text-green-600">{member.questions_solved}</span>
            </div>
          {/each}
        </div>
      </div>

      <!-- Top Askers -->
      <div class="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
        <div class="px-5 py-4 border-b border-gray-100 dark:border-gray-700">
          <h2 class="font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <span class="text-lg">💡</span> Top Askers
          </h2>
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">By questions posed</p>
        </div>
        <div class="divide-y divide-gray-50 dark:divide-gray-700">
          {#each topAskers as member, i}
            <div class="pl-1 pr-4 py-3 flex items-center gap-3 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
              <span class="text-sm font-bold {i === 0 ? 'text-amber-400' : i === 1 ? 'text-gray-400' : i === 2 ? 'text-amber-600' : 'text-gray-300 dark:text-gray-600'} w-6 text-right flex-shrink-0">
                {i + 1}
              </span>
              <MemberAvatar username={member.username} color={member.color} displayName={member.display_name} size="sm" />
              <div class="flex-1 min-w-0">
                <p class="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">{member.display_name}</p>
                {#if askerTopCategory.get(member.username)}
                  <p class="text-xs text-gray-400 dark:text-gray-500 truncate">{topicLabel(askerTopCategory.get(member.username)!)}</p>
                {/if}
              </div>
              <span class="text-sm font-semibold text-primary-500 dark:text-primary-400">{member.questions_asked}</span>
            </div>
          {/each}
        </div>
      </div>

      <!-- Speed leaderboard -->
      {#if speedLeaderboard.length > 0}
        <div class="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
          <div class="px-5 py-4 border-b border-gray-100 dark:border-gray-700">
            <h2 class="font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
              <span class="text-lg">⚡</span> Speed Leaderboard
            </h2>
            <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Average solve time (min. {MIN_SOLVES} solves)</p>
          </div>
          <div class="divide-y divide-gray-50 dark:divide-gray-700">
            {#each speedLeaderboard as member, i}
              <div class="pl-1 pr-4 py-3 flex items-center gap-3 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
                <span class="text-sm font-bold {i === 0 ? 'text-amber-400' : i === 1 ? 'text-gray-400' : i === 2 ? 'text-amber-600' : 'text-gray-300'} w-6 text-right flex-shrink-0">
                  {i + 1}
                </span>
                <MemberAvatar username={member.username} color={member.color} displayName={member.display_name} size="sm" />
                <div class="flex-1 min-w-0">
                  <p class="text-sm font-medium text-gray-800 dark:text-gray-200">{member.display_name}</p>
                  <p class="text-xs text-gray-400 dark:text-gray-500">{member.questions_solved} solves</p>
                </div>
                <span class="text-sm font-semibold text-blue-600">{formatTime(member.avg_solve_time_seconds)}</span>
              </div>
            {/each}
          </div>
        </div>
      {/if}
    </div>
  {/if}

  <!-- Tags & Topics tab -->
  {#if activeTab === 'topics'}
    <div class="space-y-5">
      <!-- Categories pie chart -->
      {#if pieSlices.length > 0}
        <div class="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm p-5">
          <h2 class="font-semibold text-gray-900 dark:text-gray-100 mb-5">Categories</h2>
          <div class="flex flex-col sm:flex-row items-center gap-6">
            <!-- Donut SVG -->
            <svg viewBox="0 0 200 200" class="w-44 h-44 flex-shrink-0" role="img" aria-label="Category distribution pie chart">
              {#each pieSlices as slice}
                <path
                  d={donutPath(100, 100, 80, 50, slice.start, slice.sweep)}
                  fill={topicHex(slice.topic)}
                  stroke="white"
                  stroke-width="2"
                  opacity={hoveredSlice === null || hoveredSlice === slice.topic ? 1 : 0.35}
                  class="cursor-pointer transition-opacity duration-150"
                  onmouseenter={() => hoveredSlice = slice.topic}
                  onmouseleave={() => hoveredSlice = null}
                  onclick={() => goto(`/?topic=${encodeURIComponent(slice.topic)}`)}
                  role="button"
                  tabindex="0"
                  aria-label="{topicLabel(slice.topic)}: {slice.count} questions"
                />
              {/each}
              <!-- Centre label -->
              {#if hoveredSlice}
                {@const s = pieSlices.find(s => s.topic === hoveredSlice)!}
                <text x="100" y="96" text-anchor="middle" font-size="13" font-weight="600" fill={topicHex(s.topic)}>
                  {Math.round(s.count / pieTotal * 100)}%
                </text>
                <text x="100" y="112" text-anchor="middle" font-size="9" fill="#9ca3af">
                  {topicLabel(s.topic)}
                </text>
              {:else}
                <text x="100" y="96" text-anchor="middle" font-size="13" font-weight="600" fill="#6b7280">
                  {pieTotal}
                </text>
                <text x="100" y="112" text-anchor="middle" font-size="9" fill="#9ca3af">questions</text>
              {/if}
            </svg>

            <!-- Legend -->
            <div class="grid grid-cols-2 gap-x-5 gap-y-2 flex-1 w-full">
              {#each pieSlices as slice}
                {@const pct = Math.round(slice.count / pieTotal * 100)}
                <button
                  class="flex items-center gap-2 text-left group"
                  onmouseenter={() => hoveredSlice = slice.topic}
                  onmouseleave={() => hoveredSlice = null}
                  onclick={() => goto(`/?topic=${encodeURIComponent(slice.topic)}`)}
                >
                  <span class="w-2.5 h-2.5 rounded-full flex-shrink-0 transition-transform duration-150 {hoveredSlice === slice.topic ? 'scale-125' : ''}" style="background-color: {topicHex(slice.topic)}"></span>
                  <span class="text-xs text-gray-600 dark:text-gray-300 group-hover:text-gray-900 dark:group-hover:text-gray-100 transition-colors truncate">{topicLabel(slice.topic)}</span>
                  <span class="text-xs text-gray-400 dark:text-gray-500 ml-auto flex-shrink-0">{pct}%</span>
                </button>
              {/each}
            </div>
          </div>
        </div>
      {/if}

      <!-- Tags distribution -->
      <div class="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm p-5">
        <h2 class="font-semibold text-gray-900 dark:text-gray-100 mb-4">Top Tags</h2>
        <div class="space-y-2">
          {#each topTags as [tag, count]}
            {@const pct = Math.round(count / maxTagCount * 100)}
            <div class="flex items-center gap-3">
              <a href="/?tag={encodeURIComponent(tag)}" class="w-28 text-xs font-medium text-gray-600 dark:text-gray-300 hover:text-primary-600 dark:hover:text-primary-400 transition-colors truncate flex-shrink-0">{tag}</a>
              <div class="flex-1 h-2 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                <div class="h-full bg-primary-400 dark:bg-primary-500 rounded-full" style="width: {pct}%"></div>
              </div>
              <span class="text-xs text-gray-400 dark:text-gray-500 w-6 text-right flex-shrink-0">{count}</span>
            </div>
          {/each}
        </div>
      </div>
    </div>
  {/if}

  <!-- Best Moments tab -->
  {#if activeTab === 'moments'}
    <div class="grid sm:grid-cols-2 gap-6">
      <!-- Most discussed -->
      <div class="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
        <div class="px-5 py-4 border-b border-gray-100 dark:border-gray-700">
          <h2 class="font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <span class="text-lg">💬</span> Most Discussed
          </h2>
        </div>
        <div class="divide-y divide-gray-50 dark:divide-gray-700">
          {#each mostDiscussed as q}
            <a href="/question/{q.id}" class="px-5 py-3 flex items-start gap-3 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors block">
              <div class="flex-1 min-w-0">
                <p class="text-sm text-gray-700 dark:text-gray-300 line-clamp-2">{q.question.text}</p>
                <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">{q.question.asker}</p>
              </div>
              <span class="text-sm font-semibold text-indigo-600 flex-shrink-0">{q.discussion?.length ?? 0}</span>
            </a>
          {/each}
        </div>
      </div>

      <!-- Quickest solves -->
      <div class="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
        <div class="px-5 py-4 border-b border-gray-100 dark:border-gray-700">
          <h2 class="font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <span class="text-lg">⚡</span> Quickest Solves
          </h2>
        </div>
        <div class="divide-y divide-gray-50 dark:divide-gray-700">
          {#each quickest as q}
            <a href="/question/{q.id}" class="px-5 py-3 flex items-start gap-3 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors block">
              <div class="flex-1 min-w-0">
                <p class="text-sm text-gray-700 dark:text-gray-300 line-clamp-2">{q.question.text}</p>
                <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">{q.answer?.solver ?? '—'}</p>
              </div>
              <span class="text-sm font-semibold text-green-600 flex-shrink-0">{formatTime(q.stats?.time_to_answer_seconds)}</span>
            </a>
          {/each}
        </div>
      </div>

      <!-- Trickiest questions -->
      <div class="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden sm:col-span-2">
        <div class="px-5 py-4 border-b border-gray-100 dark:border-gray-700">
          <h2 class="font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <span class="text-lg">🧩</span> Trickiest Questions
          </h2>
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Most wrong attempts</p>
        </div>
        <div class="divide-y divide-gray-50 dark:divide-gray-700">
          {#each trickiest as q}
            <a href="/question/{q.id}" class="px-5 py-3 flex items-start gap-3 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors block">
              <div class="flex-1 min-w-0">
                <p class="text-sm text-gray-700 dark:text-gray-300 line-clamp-2">{q.question.text}</p>
                <div class="flex items-center gap-2 mt-1">
                  <p class="text-xs text-gray-400 dark:text-gray-500">{q.question.asker}</p>
                  {#each q.question.topics?.slice(0, 1) ?? [] as t}
                    <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium {topicCls(t)}">
                      {topicLabel(t)}
                    </span>
                  {/each}
                </div>
              </div>
              <span class="text-sm font-semibold text-red-500 flex-shrink-0">{q.stats?.wrong_attempts} wrong</span>
            </a>
          {/each}
        </div>
      </div>
    </div>
  {/if}
</div>
