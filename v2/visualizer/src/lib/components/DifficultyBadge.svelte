<script lang="ts">
  let { difficulty }: { difficulty: string | null | undefined } = $props();

  const styles: Record<string, string> = {
    easy: 'bg-green-100 text-green-700',
    medium: 'bg-amber-100 text-amber-700',
    hard: 'bg-red-100 text-red-700',
  };
</script>

{#if difficulty}
  <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium {styles[difficulty] ?? 'bg-gray-100 text-gray-600'}">
    {difficulty}
  </span>
{/if}
