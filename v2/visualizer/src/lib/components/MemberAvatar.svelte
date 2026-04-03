<script lang="ts">
  import { getMemberColor, getMemberInitials } from '$lib/utils/memberColors';

  let {
    username,
    displayName = username,
    color = null,
    size = 'sm',
  }: {
    username: string;
    displayName?: string;
    color?: string | null;
    size?: 'xs' | 'sm' | 'md';
  } = $props();

  const bg = $derived(getMemberColor(username, color));
  const initials = $derived(getMemberInitials(displayName));

  const sizeClass = $derived({
    xs: 'w-5 h-5 text-[9px]',
    sm: 'w-7 h-7 text-xs',
    md: 'w-9 h-9 text-sm',
  }[size]);
</script>

<div
  class="rounded-full flex items-center justify-center font-bold text-white flex-shrink-0 {sizeClass}"
  style="background-color: {bg};"
  title={displayName}
>
  {initials}
</div>
