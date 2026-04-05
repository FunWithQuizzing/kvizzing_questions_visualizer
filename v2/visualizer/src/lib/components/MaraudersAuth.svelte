<svelte:head>
  <link href="https://fonts.googleapis.com/css2?family=Satisfy&family=Almendra&display=swap" rel="stylesheet" />
</svelte:head>

<script lang="ts">
  import { onMount } from 'svelte';

  let { onAuthenticated }: { onAuthenticated: () => void } = $props();

  let input = $state('');
  let mapOpen = $state(false);
  let error = $state(false);
  let audio: HTMLAudioElement | undefined;
  let inputEl: HTMLInputElement | undefined;

  function startMusic() {
    if (!audio || !audio.paused) return;
    audio.volume = 0.4;
    audio.play().catch(() => {});
  }

  let fading = $state(false);

  const PHRASE = 'mischief managed';

  function isPhrase(raw: string): boolean {
    return raw.toLowerCase().replace(/\s+/g, ' ').trim() === PHRASE;
  }

  function triggerMapOpen() {
    if (mapOpen) return;
    mapOpen = true;
    // Let the map unfold animation play, then fade out and reveal UI
    setTimeout(() => {
      fading = true;
      if (audio) {
        const startVol = audio.volume;
        const steps = 20;
        const interval = 100;
        let step = 0;
        const fadeAudio = setInterval(() => {
          step++;
          try {
            if (audio && step < steps) {
              audio.volume = Math.max(0, startVol * (1 - step / steps));
            } else {
              clearInterval(fadeAudio);
              if (audio) { audio.pause(); audio.volume = 0; }
            }
          } catch {
            clearInterval(fadeAudio);
          }
        }, interval);
      }
      setTimeout(() => {
        if (audio) { try { audio.pause(); } catch {} }
        onAuthenticated();
      }, 2000);
    }, 7000);
  }

  function handleInput(e: Event) {
    startMusic();
    if (isPhrase((e.target as HTMLInputElement).value)) {
      triggerMapOpen();
    }
  }

  function handleKeydown(e: KeyboardEvent) {
    startMusic();
    if (e.key !== 'Enter') return;
    if (isPhrase((e.target as HTMLInputElement).value)) {
      triggerMapOpen();
    } else {
      error = true;
      setTimeout(() => { error = false; }, 600);
    }
  }

  // Reactive backup: catch any case where bind:value updates but event handlers didn't fire
  $effect(() => {
    if (isPhrase(input)) {
      triggerMapOpen();
    }
  });

  // On mount: if the user typed the phrase before hydration, the DOM value
  // may not have synced to state yet — read it directly.
  onMount(() => {
    if (inputEl && inputEl.value && isPhrase(inputEl.value)) {
      triggerMapOpen();
    }
  });
</script>

<!-- svelte-ignore a11y_media_has_caption -->
<audio bind:this={audio} src="/audio/marauders-map.mp3" loop preload="auto"></audio>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="auth-wrap" class:fading onmousedown={startMusic} ontouchstart={startMusic}>
  <div class="title-text">
    <p>I solemnly swear that I am up to no good.</p>
  </div>

  <div class="main-content">
    <div class="map-blur-wrap" class:active={mapOpen}>
    <div class="map-base" class:active={mapOpen}>
      <div class="footsteps footsteps-1">
        <div class="footstep left"></div>
        <div class="footstep right"></div>
        <div class="scroll-name">
          <p>Fun</p>
        </div>
      </div>
      <div class="footsteps footsteps-2">
        <div class="footstep left"></div>
        <div class="footstep right"></div>
        <div class="scroll-name">
          <p>Lurn</p>
        </div>
      </div>
      <div class="map-flap flap--1">
        <div class="map-flap__front"></div>
        <div class="map-flap__back"></div>
      </div>
      <div class="map-flap flap--2">
        <div class="map-flap__front"></div>
        <div class="map-flap__back"></div>
      </div>
      <div class="map-side side-1">
        <div class="front" style="--image: url('https://meowlivia.s3.us-east-2.amazonaws.com/codepen/map/8.png')"></div>
        <div class="back"></div>
      </div>
      <div class="map-side side-2">
        <div class="front" style="--image: url('https://meowlivia.s3.us-east-2.amazonaws.com/codepen/map/18.png')"></div>
        <div class="back"></div>
      </div>
      <div class="map-side side-3">
        <div class="front" style="--image: url('https://meowlivia.s3.us-east-2.amazonaws.com/codepen/map/7.png')"></div>
        <div class="back"></div>
      </div>
      <div class="map-side side-4">
        <div class="front" style="--image: url('https://meowlivia.s3.us-east-2.amazonaws.com/codepen/map/10.png')"></div>
      </div>
      <div class="map-side side-5">
        <div class="front" style="--image: url('https://meowlivia.s3.us-east-2.amazonaws.com/codepen/map/6.png')"></div>
        <div class="back"></div>
      </div>
      <div class="map-side side-6">
        <div class="front" style="--image: url('https://meowlivia.s3.us-east-2.amazonaws.com/codepen/map/11.png')"></div>
        <div class="back"></div>
      </div>
    </div>
    </div>
  </div>

  {#if !mapOpen}
    <div class="instructions">
      <input
        type="text"
        bind:this={inputEl}
        bind:value={input}
        oninput={handleInput}
        onkeydown={handleKeydown}
        placeholder="Gotta type the right words to enter in.."
        autocomplete="off"
        spellcheck="false"
        autofocus
        class:shake={error}
      />
    </div>
  {/if}
</div>

<style>
  .auth-wrap {
    height: 100dvh;
    font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 1rem;
    overflow: hidden;
    gap: 1rem;
    transition: opacity 2.5s ease;
    /* Force light parchment regardless of dark mode */
    background-color: #f7f6f4;
    background-image:
      linear-gradient(rgba(247, 246, 244, 0.68), rgba(247, 246, 244, 0.68)),
      url("/images/paper-light.png");
    background-position: center, center;
    background-repeat: no-repeat, no-repeat;
    background-size: cover, cover;
    box-shadow: inset 0 0 160px rgba(255, 255, 255, 0.35);
  }
  .auth-wrap.fading {
    opacity: 0;
  }

  .title-text {
    color: #3b2a1a;
    font: 26px 'Satisfy', cursive;
    text-align: center;
    flex-shrink: 0;
  }

  .main-content {
    text-align: center;
    flex: 1 1 auto;
    min-height: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: visible;
  }

  .map-base {
    width: 306px;
    height: 600px;
    margin: auto;
    background: url("https://meowlivia.s3.us-east-2.amazonaws.com/codepen/map/9.png") center center/cover;
    position: relative;
    display: inline-block;
    perspective: 1000px;
    overflow: visible;
    -webkit-mask-image: linear-gradient(to bottom, transparent, black 15%, black 85%, transparent),
                        linear-gradient(to right, transparent, black 10%, black 90%, transparent);
    -webkit-mask-composite: destination-in;
    mask-image: linear-gradient(to bottom, transparent, black 15%, black 85%, transparent),
                linear-gradient(to right, transparent, black 10%, black 90%, transparent);
    mask-composite: intersect;
    transition: mask-image 0.5s, -webkit-mask-image 0.5s;
  }
  .map-base.active {
    overflow: visible;
    -webkit-mask-image: none;
    mask-image: none;
  }

  .map-blur-wrap {
    display: inline-block;
    -webkit-mask-image: linear-gradient(to bottom, transparent, black 15%, black 85%, transparent),
                        linear-gradient(to right, transparent, black 10%, black 90%, transparent);
    -webkit-mask-composite: destination-in;
    mask-image: linear-gradient(to bottom, transparent, black 15%, black 85%, transparent),
                linear-gradient(to right, transparent, black 10%, black 90%, transparent);
    mask-composite: intersect;
  }
  .map-blur-wrap.active {
    -webkit-mask-image: linear-gradient(to bottom, transparent, black 10%, black 90%, transparent),
                        linear-gradient(to right, transparent, black 6%, black 94%, transparent);
    -webkit-mask-composite: destination-in;
    mask-image: linear-gradient(to bottom, transparent, black 10%, black 90%, transparent),
                linear-gradient(to right, transparent, black 6%, black 94%, transparent);
    mask-composite: intersect;
    padding: 20px 200px;
    margin: -20px -200px;
  }

  /* Flaps */
  .map-flap {
    transform-style: preserve-3d;
    position: absolute;
    width: 100%;
    height: 25%;
    margin: auto;
    left: 0;
    right: 0;
    transition: 0.5s ease;
    top: 25%;
  }
  .map-flap__front,
  .map-flap__back {
    backface-visibility: hidden;
    width: 100%;
    height: 100%;
    position: absolute;
  }
  .map-flap__back {
    transform: scale(-1) rotateY(180deg);
  }
  .flap--1 {
    box-shadow: 0 -1px 6px rgba(97, 83, 73, 0.5);
  }
  .flap--1 .map-flap__front {
    background: url("https://meowlivia.s3.us-east-2.amazonaws.com/codepen/map/mini-1.png") center left/cover;
  }
  .flap--1 .map-flap__back {
    background: url("https://meowlivia.s3.us-east-2.amazonaws.com/codepen/map/mini-3.png") -3px 0/cover;
  }
  .flap--2 {
    box-shadow: 0 1px 6px rgba(97, 83, 73, 0.5);
    top: 50%;
  }
  .flap--2 .map-flap__front {
    background: url("https://meowlivia.s3.us-east-2.amazonaws.com/codepen/map/mini-2.png") center left/cover;
  }
  .flap--2 .map-flap__back {
    background: url("https://meowlivia.s3.us-east-2.amazonaws.com/codepen/map/mini-4.png") -3px 0/cover;
  }

  /* Map sides */
  .map-side {
    height: 600px;
    width: 152px;
    position: absolute;
    transform-style: preserve-3d;
    transition: 0.3s ease;
    top: 0;
  }
  .map-side .front,
  .map-side .back {
    width: 100%;
    height: 100%;
    position: absolute;
    background-repeat: no-repeat;
    background-position: left top;
    background-size: cover;
    background-image: var(--image);
    backface-visibility: hidden;
  }
  .map-side .back {
    background-image: url(https://meowlivia.s3.us-east-2.amazonaws.com/codepen/map/back.png);
  }
  .side-1 { left: 0; margin-left: 1.5px; }
  .side-2 { left: 50%; margin-left: -2px; }
  .side-3 { left: 0; margin-left: 3px; }
  .side-3 .back { transform: rotateY(180deg); }
  .side-4 { left: 50%; margin-left: -1px; }
  .side-4 .back { transform: rotateY(180deg); }
  .side-5 { left: 0; }
  .side-5 .back { background-image: url(https://meowlivia.s3.us-east-2.amazonaws.com/codepen/map/1.png); }
  .side-6 { left: 50%; }
  .side-6 .front { background-size: 99.5%; }
  .side-6 .back { background-image: url(https://meowlivia.s3.us-east-2.amazonaws.com/codepen/map/17.png); }

  /* Footsteps */
  .scroll-name {
    position: absolute;
    bottom: 105px;
    left: -60px;
    width: 150px;
    height: 30px;
    font: 15px Satisfy, cursive;
    text-align: center;
    background: url("https://meowlivia.s3.us-east-2.amazonaws.com/codepen/map/scroll.svg") center center/cover;
    z-index: 10;
    color: #615349;
    cursor: default;
    opacity: 0;
  }
  .scroll-name p {
    display: inline-block;
    margin: 4px 0 0 15px;
  }
  .footstep {
    position: absolute;
    background: #615349;
    width: 6px;
    height: 12px;
    border-radius: 80% 80% 70% 70%/130% 130% 25% 25%;
    z-index: 10;
    opacity: 0;
  }
  .footstep::before {
    content: "";
    position: absolute;
    width: 5px;
    height: 5px;
    top: 110%;
    left: 0px;
    background: #615349;
    border-radius: 0 0 100% 100%;
  }
  .footstep.left  { transform: rotate(5deg); }
  .footstep.right { transform: rotate(-3deg) translateY(15px) translateX(10px); }

  .footsteps-1 .footstep.left  { bottom: 150px; left: 18px; transform: rotate(35deg); }
  .footsteps-1 .footstep.right { bottom: 150px; left: 28px; transform: rotate(30deg); }
  .footsteps-2 .footstep.left  { bottom: 285px; left: 230px; transform: rotate(-90deg); }
  .footsteps-2 .footstep.right { bottom: 275px; left: 235px; transform: rotate(-85deg); }
  .footsteps-2 .scroll-name    { bottom: 300px; left: 170px; }

  /* Active / open state */
  .map-base.active .flap--1 {
    transform: rotateX(180deg);
    transform-origin: top center;
    transition: 0.6s transform 1.5s;
  }
  .map-base.active .flap--2 {
    transform: rotateX(180deg);
    transform-origin: bottom center;
    transition: 0.6s transform 1.8s;
  }
  .map-base.active .side-1 {
    transform-origin: center left;
    transform: rotateY(180deg) skewY(2deg);
    transition: 0.5s all ease-in-out 0.6s;
  }
  .map-base.active .side-1 .front { transform: rotateY(180deg); }
  .map-base.active .side-2 {
    transform: rotateY(180deg) skewY(-2deg);
    transform-origin: center right;
    transition: 0.5s all ease-in-out 0.6s;
  }
  .map-base.active .side-2 .front { transform: rotateY(180deg); }
  .map-base.active .side-3 {
    left: -50%;
    transform: skewY(2deg) translateX(-100%);
    top: 8px;
    transition: 0.5s transform ease 0.8s, 0.3s left ease 0.8s, 0.5s top ease 0.8s;
  }
  .map-base.active .side-4 {
    left: 100%;
    transform: skewY(-2deg) translateX(100%);
    top: 8px;
    margin-left: -7px;
    transition: 0.5s transform ease 0.8s, 0.3s left ease 0.8s, 0.5s top ease 0.8s, 0.5s margin ease 0.8s;
  }
  .map-base.active .side-5 {
    left: -100%;
    transform-origin: center left;
    transform: rotateY(180deg);
    transition: 0.5s transform, 0.7s left 0.8s, 0.2s margin 0.8s;
    top: 0px;
    margin-left: 4px;
  }
  .map-base.active .side-5 .front {
    transform: rotateY(180deg);
    transition: 0.1s transform;
  }
  .map-base.active .side-6 {
    left: 150%;
    transform: rotateY(180deg);
    transform-origin: center right;
    margin-left: -8px;
    transition: 0.5s transform 0.3s, 0.7s left 0.8s, 0.5s top 0.8s, 0.5s margin 0.8s;
  }
  .map-base.active .side-6 .front {
    transform: rotateY(180deg);
    transition: 0.1s transform;
  }
  .map-base.active .footstep,
  .map-base.active .scroll-name {
    opacity: 1;
    transition: 0.5s opacity 2.5s;
  }
  .map-base.active .footsteps-1 .footstep {
    animation: 15s footsteps-1 ease 3s forwards;
  }
  .map-base.active .footsteps-1 .scroll-name {
    animation: 15s scroll-1 ease 3s forwards;
  }
  .map-base.active .footsteps-2 .footstep {
    animation: 15s footsteps-2 ease 3.2s forwards;
  }
  .map-base.active .footsteps-2 .scroll-name {
    animation: 15s scroll-2 ease 3.2s forwards;
  }

  /* Footsteps-1: walks up from bottom-left along the left corridor, then turns right */
  @keyframes footsteps-1 {
    8%  { transform: translate(8px, -15px) rotate(30deg); }
    16% { transform: translate(15px, -45px) rotate(25deg); }
    24% { transform: translate(20px, -80px) rotate(15deg); }
    32% { transform: translate(25px, -115px) rotate(10deg); }
    40% { transform: translate(30px, -140px) rotate(5deg); }
    48% { transform: translate(50px, -145px) rotate(-50deg); }
    56% { transform: translate(80px, -140px) rotate(-70deg); }
    64% { transform: translate(110px, -135px) rotate(-80deg); }
    72% { transform: translate(110px, -135px) rotate(-80deg); }
    100% { transform: translate(110px, -135px) rotate(-80deg); }
  }
  /* Footsteps-2: walks left along the horizontal corridor, then turns down */
  @keyframes footsteps-2 {
    8%  { transform: translate(-20px, 0px) rotate(-90deg); }
    16% { transform: translate(-50px, 0px) rotate(-90deg); }
    24% { transform: translate(-85px, 5px) rotate(-85deg); }
    32% { transform: translate(-115px, 10px) rotate(-80deg); }
    40% { transform: translate(-140px, 15px) rotate(-70deg); }
    48% { transform: translate(-150px, 35px) rotate(-30deg); }
    56% { transform: translate(-148px, 60px) rotate(-10deg); }
    64% { transform: translate(-145px, 75px) rotate(0deg); }
    72% { transform: translate(-145px, 75px) rotate(0deg); }
    100% { transform: translate(-145px, 75px) rotate(0deg); }
  }
  @keyframes scroll-1 {
    8%  { transform: translate(8px, -15px); }
    16% { transform: translate(15px, -45px); }
    24% { transform: translate(20px, -80px); }
    32% { transform: translate(25px, -115px); }
    40% { transform: translate(30px, -140px); }
    48% { transform: translate(50px, -145px); }
    56% { transform: translate(80px, -140px); }
    64% { transform: translate(110px, -135px); }
    100% { transform: translate(110px, -135px); }
  }
  @keyframes scroll-2 {
    8%  { transform: translate(-20px, 0px); }
    16% { transform: translate(-50px, 0px); }
    24% { transform: translate(-85px, 5px); }
    32% { transform: translate(-115px, 10px); }
    40% { transform: translate(-140px, 15px); }
    48% { transform: translate(-150px, 35px); }
    56% { transform: translate(-148px, 60px); }
    64% { transform: translate(-145px, 75px); }
    100% { transform: translate(-145px, 75px); }
  }

  /* Input */
  .instructions {
    text-align: center;
    margin-top: 1.5rem;
  }
  .instructions input {
    background: transparent;
    border: none;
    border-bottom: 1px solid #c9b99a;
    color: #3b2a1a;
    font: 18px 'Almendra', serif;
    text-align: center;
    width: 320px;
    padding: 6px 0;
    outline: none;
    caret-color: #3b2a1a;
    transition: border-color 0.2s;
  }
  .instructions input:focus {
    border-bottom-color: #3b2a1a;
  }
  .instructions input::placeholder {
    color: #a0856a;
  }
  .instructions input.shake {
    animation: shake 0.4s ease;
    border-bottom-color: #ef4444;
  }
  @keyframes shake {
    0%, 100% { transform: translateX(0); }
    20%       { transform: translateX(-6px); }
    40%       { transform: translateX(6px); }
    60%       { transform: translateX(-4px); }
    80%       { transform: translateX(4px); }
  }

  .instructions {
    flex-shrink: 0;
    position: relative;
    z-index: 20;
  }

  /*
   * Mobile scaling strategy:
   * The footstep start positions and @keyframes translate() values are
   * hand-tuned in pixels for the desktop 306x600 coordinate system.
   * Instead of re-tuning every number per breakpoint, we keep .map-base
   * at its native 306x600 internal size on every device and apply a
   * uniform transform: scale() on smaller screens. Negative margins
   * reclaim the layout box so the title and input stay positioned
   * correctly above and below the scaled map.
   *
   * Scale math:
   *   --map-scale: s
   *   width reclaimed  = 306 * (1 - s) / 2 per side
   *   height reclaimed = 600 * (1 - s) / 2 per side
   */
  .map-base {
    --map-scale: 1;
    transform: scale(var(--map-scale));
    transform-origin: center center;
    margin: calc(600px * (var(--map-scale) - 1) / 2) calc(306px * (var(--map-scale) - 1) / 2);
  }

  @media (max-width: 640px) {
    .title-text {
      font-size: 20px;
    }
    .map-base {
      --map-scale: 0.82;
    }
    .instructions input {
      width: min(260px, 80vw);
      font-size: 15px;
    }
  }

  @media (max-width: 400px) {
    .title-text {
      font-size: 18px;
    }
    .map-base {
      --map-scale: 0.70;
    }
  }

  @media (max-height: 700px) and (max-width: 640px) {
    .map-base {
      --map-scale: 0.70;
    }
  }
</style>
