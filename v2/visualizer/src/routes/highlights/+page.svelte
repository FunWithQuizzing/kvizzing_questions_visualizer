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

  // Pie chart — primary category (topics[0]) per question; uncategorised → "general"
  const primaryCounts = new Map<string, number>();
  for (const q of questions) {
    const primary = q.question.topics?.[0] ?? 'general';
    primaryCounts.set(primary, (primaryCounts.get(primary) ?? 0) + 1);
  }
  const pieTotal = questions.length;
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
  const allTopTags = [...tagCounts.entries()]
    .sort((a, b) => b[1] - a[1]);
  const topTags = allTopTags.slice(0, 60);
  const maxTagCount = topTags[0]?.[1] ?? 1;
  let tagView = $state<'bubbles' | 'bars'>('bubbles');

  // Bubble chart
  let bubbleContainerW = $state(500);
  const BUBBLE_H = 700;
  let hoveredBubble = $state<{ tag: string; count: number; x: number; y: number; r: number } | null>(null);

  function computeBubbles(W: number) {
    const H = BUBBLE_H;
    const totalCount = topTags.reduce((s, [, c]) => s + c, 0);
    const k = Math.sqrt((W * H * 0.38) / (Math.PI * totalCount));
    const items = topTags.map(([tag, count]) => ({
      tag, count,
      r: Math.max(10, k * Math.sqrt(count))
    }));

    // Place first bubble at center
    const placed: Array<{ tag: string; count: number; r: number; x: number; y: number }> = [];
    if (items.length > 0) {
      placed.push({ ...items[0], x: W / 2, y: H / 2 });
    }

    // For each subsequent bubble, find the closest valid position to center
    // by testing positions tangent to already-placed bubbles
    for (let idx = 1; idx < items.length; idx++) {
      const item = items[idx];
      let bestX = W / 2, bestY = H / 2, bestDist = Infinity, found = false;

      // Try positions tangent to each placed bubble at various angles
      for (const p of placed) {
        const gap = 2;
        const dist = item.r + p.r + gap;
        for (let a = 0; a < 36; a++) {
          const angle = (a / 36) * Math.PI * 2;
          const cx = p.x + dist * Math.cos(angle);
          const cy = p.y + dist * Math.sin(angle);
          if (cx - item.r < 2 || cx + item.r > W - 2 || cy - item.r < 2 || cy + item.r > H - 2) continue;
          let ok = true;
          for (const q of placed) {
            if (Math.sqrt((cx - q.x) ** 2 + (cy - q.y) ** 2) < item.r + q.r + 2) { ok = false; break; }
          }
          if (ok) {
            const d = Math.sqrt((cx - W / 2) ** 2 + (cy - H / 2) ** 2);
            if (d < bestDist) { bestX = cx; bestY = cy; bestDist = d; found = true; }
          }
        }
      }

      // Fallback: spiral search if tangent placement failed
      if (!found) {
        for (let i = 0; i < 15000; i++) {
          const cx = W / 2 + 1.8 * Math.sqrt(i) * Math.cos(i * 2.399963229);
          const cy = H / 2 + 1.8 * Math.sqrt(i) * Math.sin(i * 2.399963229);
          if (cx - item.r < 2 || cx + item.r > W - 2 || cy - item.r < 2 || cy + item.r > H - 2) continue;
          let ok = true;
          for (const q of placed) {
            if (Math.sqrt((cx - q.x) ** 2 + (cy - q.y) ** 2) < item.r + q.r + 2) { ok = false; break; }
          }
          if (ok) { bestX = cx; bestY = cy; found = true; break; }
        }
      }

      if (found) placed.push({ ...item, x: bestX, y: bestY });
    }
    return placed;
  }

  const bubbles = $derived(computeBubbles(bubbleContainerW));

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

  const memes = [
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2011.55.00.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2012.34.31.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2012.35.57.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2012.37.29.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2012.41.02.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2012.42.49.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2012.44.44.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2012.50.00.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2012.53.24.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2012.56.42.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2013.00.55.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2013.01.37.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2013.01.54.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2013.01.57.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2013.02.01.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2013.02.06.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2013.02.11.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2013.02.16.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2013.02.21.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2013.02.26.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2013.02.31.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2013.02.36.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2013.02.42.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2013.02.47.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2013.02.53.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2013.03.12.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2013.03.19.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2013.03.26.jpeg",
    "/images/memes/WhatsApp%20Image%202026-03-28%20at%2013.03.33.jpeg",
    "/images/memes/WhatsApp%20Video%202026-03-28%20at%2013.00.54.mp4",
    "/images/memes/WhatsApp%20Video%202026-03-28%20at%2013.01.28.mp4",
    "/images/memes/WhatsApp%20Video%202026-03-28%20at%2013.03.43.mp4",
  ];

  let lightbox = $state<string | null>(null);
  let currentMemeIdx = $state(Math.floor(Math.random() * memes.length));

  function shuffleMeme() {
    let next;
    do { next = Math.floor(Math.random() * memes.length); } while (next === currentMemeIdx && memes.length > 1);
    currentMemeIdx = next;
  }

  type Tab = 'leaderboard' | 'topics' | 'memes';
  let activeTab = $state<Tab>('topics');

  const tabs: { id: Tab; label: string }[] = [
    { id: 'topics', label: 'Tags & Topics' },
    { id: 'memes', label: 'Wall of Fame' },
    { id: 'leaderboard', label: 'Wall of Fun' },
  ];
</script>

<svelte:head>
  <title>Highlights — KVizzing</title>
</svelte:head>

<div class="space-y-6">
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
      <div class="bg-ui-card rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
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
      <div class="bg-ui-card rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
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
        <div class="bg-ui-card rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
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

      <!-- Best Moments -->
      <div class="grid sm:grid-cols-2 gap-6 lg:col-span-3 mt-2">
        <!-- Most discussed -->
        <div class="bg-ui-card rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
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
        <div class="bg-ui-card rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
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
        <div class="bg-ui-card rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden sm:col-span-2">
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
    </div>
  {/if}

  <!-- Tags & Topics tab -->
  {#if activeTab === 'topics'}
    <div class="space-y-5">
      <!-- Categories pie chart -->
      {#if pieSlices.length > 0}
        <div class="bg-ui-card rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm p-5">
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
      <div class="bg-ui-card rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm p-5">
        <div class="flex items-center justify-between mb-4">
          <h2 class="font-semibold text-gray-900 dark:text-gray-100">Top Tags</h2>
          <div class="flex items-center gap-2">
            <span class="text-xs text-gray-400 dark:text-gray-500">{allTopTags.length} tags</span>
            <div class="inline-flex rounded-lg border border-gray-200 dark:border-gray-600 overflow-hidden text-xs">
              <button
                onclick={() => tagView = 'bubbles'}
                class="px-2.5 py-1 transition-colors {tagView === 'bubbles' ? 'bg-primary-500 text-white' : 'bg-white dark:bg-gray-700 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-600'}"
              >Bubbles</button>
              <button
                onclick={() => tagView = 'bars'}
                class="px-2.5 py-1 transition-colors border-l border-gray-200 dark:border-gray-600 {tagView === 'bars' ? 'bg-primary-500 text-white' : 'bg-white dark:bg-gray-700 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-600'}"
              >Bars</button>
            </div>
          </div>
        </div>

        {#if tagView === 'bubbles'}
        <div bind:clientWidth={bubbleContainerW} class="relative">
          {#if hoveredBubble}
            {@const ty = hoveredBubble.y - hoveredBubble.r - 10}
            <div
              class="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-lg bg-gray-900 dark:bg-gray-700 px-2.5 py-1.5 text-xs text-white shadow-lg whitespace-nowrap"
              style="left:{hoveredBubble.x}px;top:{ty}px"
            >
              <span class="font-semibold">{hoveredBubble.tag}</span>
              <span class="ml-1.5 text-gray-300">{hoveredBubble.count}</span>
            </div>
          {/if}
          <svg width={bubbleContainerW} height={BUBBLE_H}>
            {#each bubbles as b, i}
              {@const opacity = 0.35 + 0.65 * Math.sqrt(b.count / maxTagCount)}
              {@const fs = Math.max(8, Math.min(13, b.r * 0.36))}
              {@const maxChars = Math.floor(b.r * 2 / (fs * 0.62))}
              {@const label = b.tag.length > maxChars ? b.tag.slice(0, maxChars) + '…' : b.tag}
              {@const showCount = b.r > 26}
              {@const floatDur = 3.0 + (i * 0.47) % 2}
              {@const floatDelay = (i * 0.33) % 2.5}
              {@const floatDist = 6 + (i * 3) % 8}
              {@const floatDx = 3 + (i * 2) % 5}
              <g
                class="bubble-float"
                style="--dur:{floatDur}s;--delay:{floatDelay}s;--dist:-{floatDist}px;--dx:{(i % 2 ? 1 : -1) * floatDx}px"
                onmouseenter={() => hoveredBubble = { tag: b.tag, count: b.count, x: b.x, y: b.y, r: b.r }}
                onmouseleave={() => hoveredBubble = null}
              >
                <a href="/?tag={encodeURIComponent(b.tag)}" class="bubble-link" style="text-decoration:none;cursor:pointer" style:--cx="{b.x}px" style:--cy="{b.y}px">
                  <circle cx={b.x} cy={b.y} r={b.r} fill="var(--color-primary-450, color-mix(in srgb, var(--color-primary-400) 50%, var(--color-primary-500)))" fill-opacity={opacity} class="bubble-circle" />
                  {#if b.r > 14}
                    <text
                      x={b.x}
                      y={showCount ? b.y - fs * 0.65 : b.y}
                      text-anchor="middle"
                      dominant-baseline="middle"
                      font-size={fs}
                      font-weight="600"
                      fill="white"
                      pointer-events="none"
                      style="user-select:none"
                    >{label}</text>
                    {#if showCount}
                      <text
                        x={b.x}
                        y={b.y + fs * 0.85}
                        text-anchor="middle"
                        dominant-baseline="middle"
                        font-size={Math.max(7, fs * 0.78)}
                        fill="rgba(255,255,255,0.7)"
                        pointer-events="none"
                        style="user-select:none"
                      >{b.count}</text>
                    {/if}
                  {/if}
                </a>
              </g>
            {/each}
          </svg>
        </div>
        {:else}
        <!-- Bar chart view — all tags -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5 overflow-y-auto pr-1" style="height:{BUBBLE_H}px">
          {#each allTopTags as [tag, count]}
            <a href="/?tag={encodeURIComponent(tag)}" class="group flex items-center gap-2 py-1 hover:bg-gray-50 dark:hover:bg-gray-800/50 rounded px-1 -mx-1 transition-colors">
              <span class="text-xs text-gray-700 dark:text-gray-300 w-28 sm:w-32 truncate flex-shrink-0 group-hover:text-primary-600 dark:group-hover:text-primary-400 transition-colors" title={tag}>{tag}</span>
              <div class="flex-1 h-4 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full bg-primary-400 dark:bg-primary-500 transition-all duration-300"
                  style="width: {Math.max(2, (count / maxTagCount) * 100)}%"
                ></div>
              </div>
              <span class="text-xs text-gray-400 dark:text-gray-500 w-8 text-right flex-shrink-0 tabular-nums">{count}</span>
            </a>
          {/each}
        </div>
        {/if}
      </div>
    </div>
  {/if}

  <!-- Memes tab -->
  {#if activeTab === 'memes'}
    {@const currentMeme = memes[currentMemeIdx]}
    <div class="flex flex-col items-center gap-4">
      <!-- Controls — always at top, never moves -->
      <div class="flex items-center justify-center gap-2 w-full max-w-lg">
        <button
          onclick={() => currentMemeIdx = (currentMemeIdx - 1 + memes.length) % memes.length}
          class="inline-flex items-center justify-center w-9 h-9 rounded-xl border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
          aria-label="Previous"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg>
        </button>

        <span class="text-sm text-gray-400 dark:text-gray-500 w-16 text-center flex-shrink-0">{currentMemeIdx + 1} / {memes.length}</span>

        <button
          onclick={shuffleMeme}
          class="inline-flex items-center justify-center gap-2 px-4 py-2 bg-primary-500 hover:bg-primary-600 text-white font-semibold text-sm rounded-xl transition-colors shadow-sm"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Shuffle
        </button>

        <button
          onclick={() => currentMemeIdx = (currentMemeIdx + 1) % memes.length}
          class="inline-flex items-center justify-center w-9 h-9 rounded-xl border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
          aria-label="Next"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
        </button>
      </div>

      <!-- Reel -->
      <div class="w-full max-w-lg">
        {#if currentMeme.endsWith('.mp4')}
          <video
            src={currentMeme}
            controls
            playsinline
            class="w-full rounded-2xl border border-gray-200 dark:border-gray-700 shadow-md cursor-zoom-in"
            onclick={() => lightbox = currentMeme}
          ></video>
        {:else}
          <img
            src={currentMeme}
            alt="meme"
            class="w-full rounded-2xl border border-gray-200 dark:border-gray-700 shadow-md cursor-zoom-in hover:shadow-lg transition-shadow"
            onclick={() => lightbox = currentMeme}
          />
        {/if}
      </div>
    </div>
  {/if}

  <!-- Lightbox -->
  {#if lightbox}
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <div
      class="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-4"
      onclick={() => lightbox = null}
    >
      <button
        class="absolute top-4 right-4 text-white/70 hover:text-white transition-colors"
        onclick={() => lightbox = null}
        aria-label="Close"
      >
        <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
      {#if lightbox.endsWith('.mp4')}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <video
          src={lightbox}
          controls
          autoplay
          playsinline
          class="max-h-[90vh] max-w-[90vw] rounded-xl"
          onclick={(e) => e.stopPropagation()}
        ></video>
      {:else}
        <img
          src={lightbox}
          alt="meme"
          class="max-h-[90vh] max-w-[90vw] rounded-xl object-contain"
          onclick={(e) => e.stopPropagation()}
        />
      {/if}
    </div>
  {/if}


</div>

<style>
  @keyframes bubble-float {
    0%, 100% { transform: translate(0px, 0px); }
    25% { transform: translate(calc(var(--dx) * var(--scale)), calc(var(--dist) * var(--scale))); }
    50% { transform: translate(0px, calc(var(--dist) * var(--scale) * 1.2)); }
    75% { transform: translate(calc(var(--dx) * var(--scale) * -1), calc(var(--dist) * var(--scale))); }
  }
  .bubble-float {
    --scale: 1;
    animation: bubble-float var(--dur) ease-in-out var(--delay) infinite;
  }
  .bubble-float:hover {
    --scale: 3;
    animation-duration: calc(var(--dur) * 0.6);
  }
  .bubble-link {
    transform-origin: var(--cx) var(--cy);
    transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
  }
  .bubble-link:hover {
    transform: scale(1.15);
  }
  .bubble-link:hover .bubble-circle {
    fill-opacity: 1;
  }
  .bubble-circle {
    transition: fill-opacity 0.2s ease;
  }
</style>
