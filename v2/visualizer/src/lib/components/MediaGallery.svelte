<script lang="ts">
  import type { MediaAttachment } from '$lib/types';

  let {
    attachments,
    compact = false,
  }: {
    attachments: MediaAttachment[];
    compact?: boolean;
  } = $props();

  const images = $derived(attachments.filter(a => a.url && a.type === 'image'));
  const videos = $derived(attachments.filter(a => a.url && a.type === 'video'));
  const audios = $derived(attachments.filter(a => a.url && a.type === 'audio'));
  const hasAny = $derived(images.length > 0 || videos.length > 0 || audios.length > 0);

  let currentIndex = $state(0);
  let scrollEl: HTMLDivElement | undefined = $state();

  // Lightbox
  let lightboxUrl = $state<string | null>(null);

  function openLightbox(e: MouseEvent, url: string) {
    e.preventDefault();
    e.stopPropagation();
    lightboxUrl = url;
  }

  function closeLightbox(e: MouseEvent | KeyboardEvent) {
    if (e instanceof KeyboardEvent && e.key !== 'Escape') return;
    lightboxUrl = null;
  }

  function goTo(index: number) {
    currentIndex = index;
    if (scrollEl) {
      const slide = scrollEl.children[index] as HTMLElement;
      slide?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'start' });
    }
  }

  function onScroll() {
    if (!scrollEl) return;
    const width = scrollEl.clientWidth;
    if (width === 0) return;
    currentIndex = Math.round(scrollEl.scrollLeft / width);
  }
</script>

<svelte:window onkeydown={closeLightbox} />

{#if hasAny}
  <div class="space-y-2 overflow-hidden">
    {#if images.length === 1}
      <button
        onclick={(e) => openLightbox(e, images[0].url!)}
        class="block cursor-zoom-in mx-auto max-w-full"
      >
        <img
          src={images[0].url ?? ''}
          alt={images[0].caption ?? ''}
          class="rounded-lg block mx-auto max-w-full object-contain {compact ? 'max-h-[300px] sm:max-w-[400px]' : 'max-h-[500px] sm:max-w-[600px]'}"
        />
      </button>
      {#if images[0].caption}
        <p class="text-xs text-gray-500 dark:text-gray-400">{images[0].caption}</p>
      {/if}
    {:else if images.length > 1}
      <!-- Carousel -->
      <div class="relative group/carousel">
        <!-- Scroll track -->
        <div
          bind:this={scrollEl}
          onscroll={onScroll}
          class="flex overflow-x-auto snap-x snap-mandatory scrollbar-hide rounded-lg gap-0"
          style="scroll-behavior: smooth;"
        >
          {#each images as img}
            <button
              onclick={(e) => openLightbox(e, img.url!)}
              class="flex-none w-full snap-start flex justify-center cursor-zoom-in"
            >
              <img
                src={img.url ?? ''}
                alt={img.caption ?? ''}
                class="rounded-lg block max-w-full object-contain {compact ? 'max-h-[300px] sm:max-w-[400px]' : 'max-h-[500px] sm:max-w-[600px]'}"
                draggable="false"
              />
            </button>
          {/each}
        </div>

        <!-- Prev arrow -->
        {#if currentIndex > 0}
          <button
            onclick={(e) => { e.preventDefault(); e.stopPropagation(); goTo(currentIndex - 1); }}
            class="absolute left-1.5 top-1/2 -translate-y-1/2 w-7 h-7 rounded-full bg-black/50 text-white flex items-center justify-center opacity-0 group-hover/carousel:opacity-100 transition-opacity hover:bg-black/70 z-10"
            aria-label="Previous"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M15 19l-7-7 7-7" />
            </svg>
          </button>
        {/if}

        <!-- Next arrow -->
        {#if currentIndex < images.length - 1}
          <button
            onclick={(e) => { e.preventDefault(); e.stopPropagation(); goTo(currentIndex + 1); }}
            class="absolute right-1.5 top-1/2 -translate-y-1/2 w-7 h-7 rounded-full bg-black/50 text-white flex items-center justify-center opacity-0 group-hover/carousel:opacity-100 transition-opacity hover:bg-black/70 z-10"
            aria-label="Next"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M9 5l7 7-7 7" />
            </svg>
          </button>
        {/if}

        <!-- Dot indicators -->
        <div class="absolute bottom-2 left-1/2 -translate-x-1/2 flex gap-1.5 z-10">
          {#each images as _, i}
            <button
              onclick={(e) => { e.preventDefault(); e.stopPropagation(); goTo(i); }}
              class="w-1.5 h-1.5 rounded-full transition-all {i === currentIndex ? 'bg-white scale-125' : 'bg-white/50 hover:bg-white/75'}"
              aria-label="Go to image {i + 1}"
            />
          {/each}
        </div>

        <!-- Counter badge (top-right) -->
        <div class="absolute top-2 right-2 px-2 py-0.5 rounded-full bg-black/50 text-white text-xs font-medium z-10">
          {currentIndex + 1}/{images.length}
        </div>
      </div>
    {/if}

    {#each videos as vid}
      <!-- svelte-ignore a11y_media_has_caption -->
      <video
        controls
        src={vid.url ?? ''}
        class="rounded-lg w-full {compact ? 'max-h-52' : 'max-h-80'}"
      />
    {/each}

    {#each audios as aud}
      <audio controls src={aud.url ?? ''} class="w-full" />
    {/each}
  </div>
{/if}

<!-- Lightbox -->
{#if lightboxUrl}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-4"
    onclick={(e) => { if (e.target === e.currentTarget) closeLightbox(e); }}
  >
    <button
      onclick={closeLightbox}
      class="absolute top-4 right-4 w-9 h-9 rounded-full bg-white/10 hover:bg-white/20 text-white flex items-center justify-center transition-colors"
      aria-label="Close"
    >
      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
      </svg>
    </button>
    <img
      src={lightboxUrl}
      alt=""
      class="max-w-full max-h-full object-contain rounded-lg"
    />
  </div>
{/if}
