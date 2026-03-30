<script lang="ts">
  import { TOPICS } from '$lib/utils/topicColors';

  let { topics = $bindable(new Set<string>()) }: { topics?: Set<string> } = $props();

  function toggleTopic(id: string) {
    const next = new Set(topics);
    if (next.has(id)) next.delete(id); else next.add(id);
    topics = next;
  }
</script>

<select
  value=""
  onchange={(e) => { const v = (e.target as HTMLSelectElement).value; if (v) toggleTopic(v); (e.target as HTMLSelectElement).value = ''; }}
  class="text-sm border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-1.5 bg-white dark:bg-gray-700 dark:text-gray-200 focus:outline-none focus:border-primary-400 focus:ring-1 focus:ring-primary-100 dark:focus:ring-primary-900 text-gray-600"
>
  <option value="">Filter by topic…</option>
  {#each TOPICS as t}
    {#if !topics.has(t.id)}<option value={t.id}>{t.label}</option>{/if}
  {/each}
</select>
