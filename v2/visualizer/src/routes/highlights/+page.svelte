<script lang="ts">
  import { getContext } from 'svelte';
  import type { QuestionStore } from '$lib/stores/questionStore';
  import { getMemberColor, getMemberInitials } from '$lib/utils/memberColors';
  import { formatTime } from '$lib/utils/time';
  import MemberAvatar from '$lib/components/MemberAvatar.svelte';
  import { topicCls, topicLabel } from '$lib/utils/topicColors';

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

  // Top solvers
  const topSolvers = [...members]
    .filter(m => m.questions_solved > 0)
    .sort((a, b) => b.questions_solved - a.questions_solved)
    .slice(0, 10);

  // Topics
  const topics = store.getTopics();

  // Difficulty distribution
  const diffCounts = { easy: 0, medium: 0, hard: 0, null: 0 };
  for (const q of questions) {
    const d = q.stats?.difficulty ?? 'null';
    (diffCounts as any)[d] = ((diffCounts as any)[d] ?? 0) + 1;
  }
  const total = questions.length;

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
  let activeTab = $state<Tab>('leaderboard');

  const tabs: { id: Tab; label: string }[] = [
    { id: 'leaderboard', label: 'Leaderboard' },
    { id: 'topics', label: 'Difficulty & Topics' },
    { id: 'moments', label: 'Best Moments' },
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
    <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 shadow-sm text-center">
      <p class="text-2xl font-bold text-orange-500">{questions.length}</p>
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">Total questions</p>
    </div>
    <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 shadow-sm text-center">
      <p class="text-2xl font-bold text-blue-500">{store.getSessions().length}</p>
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">Quiz sessions</p>
    </div>
    <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 shadow-sm text-center">
      <p class="text-2xl font-bold text-green-500">{store.getAskers().length}</p>
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">Askers</p>
    </div>
    <div class="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-4 shadow-sm text-center">
      <p class="text-2xl font-bold text-purple-500">{store.getSolvers().length}</p>
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">Solvers</p>
    </div>
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
    <div class="grid sm:grid-cols-2 gap-6">
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
            <div class="px-5 py-3 flex items-center gap-3 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
              <span class="text-sm font-bold text-gray-300 dark:text-gray-600 w-6 text-right flex-shrink-0">
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
            <div class="px-5 py-3 flex items-center gap-3 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
              <span class="text-sm font-bold text-gray-300 dark:text-gray-600 w-6 text-right flex-shrink-0">
                {i + 1}
              </span>
              <MemberAvatar username={member.username} color={member.color} displayName={member.display_name} size="sm" />
              <div class="flex-1 min-w-0">
                <p class="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">{member.display_name}</p>
              </div>
              <span class="text-sm font-semibold text-orange-500">{member.questions_asked}</span>
            </div>
          {/each}
        </div>
      </div>

      <!-- Speed leaderboard -->
      {#if speedLeaderboard.length > 0}
        <div class="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden sm:col-span-2">
          <div class="px-5 py-4 border-b border-gray-100 dark:border-gray-700">
            <h2 class="font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
              <span class="text-lg">⚡</span> Speed Leaderboard
            </h2>
            <p class="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Average solve time (min. {MIN_SOLVES} solves)</p>
          </div>
          <div class="divide-y divide-gray-50 dark:divide-gray-700">
            {#each speedLeaderboard as member, i}
              <div class="px-5 py-3 flex items-center gap-3 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
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

  <!-- Topics/Difficulty tab -->
  {#if activeTab === 'topics'}
    <div class="space-y-5">
      <!-- Difficulty breakdown -->
      <div class="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm p-5">
        <h2 class="font-semibold text-gray-900 dark:text-gray-100 mb-4">Difficulty Breakdown</h2>
        <div class="space-y-3">
          {#each [['easy', '#10B981', diffCounts.easy], ['medium', '#F59E0B', diffCounts.medium], ['hard', '#EF4444', diffCounts.hard]] as [label, color, count]}
            {@const pct = total > 0 ? Math.round((count as number) / total * 100) : 0}
            <div>
              <div class="flex items-center justify-between text-sm mb-1">
                <span class="font-medium capitalize" style="color: {color}">{label}</span>
                <span class="text-gray-500 dark:text-gray-400">{count} ({pct}%)</span>
              </div>
              <div class="h-2 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all"
                  style="width: {pct}%; background-color: {color};"
                ></div>
              </div>
            </div>
          {/each}
        </div>
      </div>

      <!-- Topics (if any) -->
      {#if topics.length > 0}
        <div class="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm p-5">
          <h2 class="font-semibold text-gray-900 dark:text-gray-100 mb-4">Topics</h2>
          <div class="flex flex-wrap gap-2">
            {#each topics as topic}
              {@const count = questions.filter(q => q.question.topic === topic).length}
              <a
                href="/?topic={encodeURIComponent(topic)}"
                class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-gray-50 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg text-sm text-gray-700 dark:text-gray-300 hover:border-orange-300 hover:bg-orange-50 dark:hover:bg-orange-900/30 transition-colors"
              >
                <span>{topic}</span>
                <span class="text-xs text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-gray-600 px-1.5 py-0.5 rounded">{count}</span>
              </a>
            {/each}
          </div>
        </div>
      {:else}
        <div class="bg-white dark:bg-gray-800 rounded-2xl border border-gray-200 dark:border-gray-700 shadow-sm p-5">
          <h2 class="font-semibold text-gray-900 mb-2">Topics</h2>
          <p class="text-sm text-gray-400 dark:text-gray-500">No topics tagged yet.</p>
        </div>
      {/if}
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
                  {#if q.question.topic}
                    <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium {topicCls(q.question.topic)}">
                      {topicLabel(q.question.topic)}
                    </span>
                  {/if}
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
