<script lang="ts">
  let {
    emoji = '🔍',
    message,
    onClear,
  }: {
    emoji?: string;
    message: string;
    onClear?: () => void;
  } = $props();
</script>

<div class="text-center py-16 text-gray-500 dark:text-gray-400">
  <div class="text-4xl mb-3">{emoji}</div>
  <p class="font-medium">{message}</p>
  {#if onClear}
    <button onclick={onClear} class="mt-2 text-sm text-primary-500 dark:text-primary-400 hover:text-primary-600 dark:hover:text-primary-300">
      Clear filters
    </button>
  {/if}
</div>
