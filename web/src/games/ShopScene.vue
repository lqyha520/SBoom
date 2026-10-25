<script setup lang="ts">
import { customers } from './little-shop'
defineProps<{ customer: number; upgrade: number; closed: boolean }>()
</script>

<template>
  <svg class="shop-art" viewBox="0 0 800 590" fill="none" role="img" aria-label="晴天下的水果小店，红白遮阳棚，货架和等待购物的顾客">
    <path d="M0 0h800v590H0Z" fill="#e9f5f8" />
    <circle cx="674" cy="75" r="35" fill="#f9d777" />
    <path d="M62 90c0-16 24-25 34-10 13-26 50-15 48 8 22-5 31 22 12 26H73c-18 0-25-18-11-24Zm472 50c-2-13 17-21 27-10 10-20 39-11 37 8 20-5 25 16 10 20h-65c-15 0-20-13-9-18Z" fill="white" />
    <path d="M0 323c110-58 171-18 265 1 120-59 252-66 535 0v266H0V323Z" fill="#c9e3d2" />
    <path d="M0 405c280-55 558-47 800 3v182H0V405Z" fill="#b4d2be" />
    <path d="M0 479c209-25 556-11 800 40v71H0V479Z" fill="#e1e8dc" />
    <g stroke="#b4c4bd" stroke-width="6" stroke-linecap="round"><path d="M32 344v83m32-86v77m-41-48h50m-50 28h50M725 340v72m32-76v76m-42-45h52m-52 29h52" /></g>
    <path d="M75 397v-81m0 42-23-25m23 9 23-20" stroke="#789380" stroke-width="8" stroke-linecap="round" />
    <circle cx="62" cy="308" r="30" fill="#90ba9c" /><circle cx="91" cy="292" r="37" fill="#98c3a3" /><circle cx="63" cy="278" r="28" fill="#a9cfad" />
    <ellipse cx="401" cy="514" rx="251" ry="21" fill="#52665b" opacity=".12" />
    <path d="M150 220h450v272H150V220Z" fill="#fffaf0" />
    <path d="M162 243h424v183H162V243Z" fill="#e5eddf" />
    <path d="M185 266h90v105h-90V266Zm297 0h82v105h-82V266Z" fill="#b7d8de" stroke="#8cbbb9" stroke-width="7" />
    <path d="M230 269v100m-43-48h87m248-52v100m-39-48h78" stroke="#f5faf0" stroke-width="6" />
    <path d="M297 256h163v155H297V256Z" fill="#f9fbf5" />
    <path d="M311 272h134v113H311V272Z" fill="#47776d" />
    <path d="M326 297h99m-99 20h65m-65 20h91" stroke="#d2e1d5" stroke-width="5" stroke-linecap="round" />
    <path d="M147 163h456l26 62H120l27-62Z" fill="#ed7c7e" />
    <path d="m205 163-17 62h57l10-62m61 0-3 62h59v-62m61 0 8 62h58l-16-62m59 0 23 62h57l-29-62" fill="#fff8ed" />
    <path d="M120 225h63v19c0 29-63 29-63 0v-19Z" fill="#e67075" /><path d="M183 225h64v19c0 29-64 29-64 0v-19Z" fill="#fff8ed" />
    <path d="M247 225h63v19c0 29-63 29-63 0v-19Z" fill="#e67075" /><path d="M310 225h64v19c0 29-64 29-64 0v-19Z" fill="#fff8ed" />
    <path d="M374 225h63v19c0 29-63 29-63 0v-19Z" fill="#e67075" /><path d="M437 225h64v19c0 29-64 29-64 0v-19Z" fill="#fff8ed" />
    <path d="M501 225h63v19c0 29-63 29-63 0v-19Z" fill="#e67075" /><path d="M564 225h65v19c0 29-65 29-65 0v-19Z" fill="#fff8ed" />
    <rect x="260" y="116" width="230" height="63" rx="8" fill="#fffaf0" stroke="#dce6d8" stroke-width="4" />
    <text x="375" y="158" text-anchor="middle" fill="#527e6f" font-size="29" font-family="Microsoft YaHei, sans-serif" font-weight="700">小小水果铺</text>
    <path d="M140 407h473v31H140v-31Z" fill="#729f90" />
    <path d="M151 438h450v66H151v-66Z" fill="#92b7a1" />
    <path d="M163 500h429v12H163v-12Z" fill="#729f90" />
    <path d="M188 453h28v35h-28v-35Zm57 0h28v35h-28v-35Zm57 0h28v35h-28v-35Zm57 0h28v35h-28v-35Zm57 0h28v35h-28v-35Zm57 0h28v35h-28v-35Zm57 0h28v35h-28v-35Z" fill="#a9c7b4" />
    <g v-if="!closed" class="scene-customer" :key="customer" transform="translate(622 316)">
      <ellipse cx="28" cy="196" rx="41" ry="9" fill="#52665b" opacity=".16" />
      <path d="M10 136v47m36-47v47" stroke="#5a6e82" stroke-width="17" stroke-linecap="round" />
      <path d="M1 187h22m16 0h22" stroke="#f8fafb" stroke-width="13" stroke-linecap="round" />
      <path d="M-6 80c-8 20-10 35-7 53m75-53c9 20 12 32 7 46" stroke="#edbb9e" stroke-width="14" stroke-linecap="round" />
      <path d="M0 72c12-13 41-13 56 0l3 74H-3l3-74Z" :fill="customers[customer].color" />
      <circle cx="28" cy="34" r="36" :fill="customers[customer].hair" />
      <ellipse cx="28" cy="43" rx="30" ry="32" fill="#f6c7a7" />
      <path d="M-2 34C-8-13 71-6 59 32 43 31 30 20 23 12 20 24 9 29-2 34Z" :fill="customers[customer].hair" />
      <circle cx="17" cy="43" r="2.5" fill="#505d60" /><circle cx="39" cy="43" r="2.5" fill="#505d60" />
      <path d="M22 58c4 3 9 3 13-1" stroke="#c48373" stroke-width="2.5" stroke-linecap="round" />
      <circle cx="8" cy="54" r="5" fill="#eea69b" opacity=".6" /><circle cx="49" cy="54" r="5" fill="#eea69b" opacity=".6" />
      <path d="M63 132h37l-5 43H66l-3-43Z" fill="#e9cf98" /><path d="M70 132v-6c0-14 22-14 22 0v6" stroke="#bdab85" stroke-width="3" />
    </g>
    <g v-if="upgrade > 0" transform="translate(93 434)"><rect width="46" height="60" rx="5" fill="#eaa39a" /><path d="M4 14h38M10 0V-26m25 26v-26" stroke="#729f90" stroke-width="3" /><circle cx="12" cy="-26" r="13" fill="#ef858d" /><circle cx="36" cy="-24" r="12" fill="#f1c85e" /><circle cx="24" cy="-41" r="13" fill="#bb96c0" /></g>
    <g v-if="upgrade > 1" transform="translate(540 344)"><rect width="51" height="64" rx="5" fill="#a5c5dc" /><rect x="6" y="6" width="39" height="42" rx="3" fill="#e1f2f7" /><path d="M31 55h12" stroke="#7197ae" stroke-width="3" /></g>
  </svg>
</template>

<style scoped>
.shop-art { width: 100%; height: 100%; display: block; }
.scene-customer { animation: arrive .5s ease-out; }
@keyframes arrive { from { opacity: 0; translate: 35px 0; } to { opacity: 1; translate: 0 0; } }
@media (prefers-reduced-motion: reduce) { .scene-customer { animation: none; } }
</style>
