<script setup lang="ts">
import type { ProductId } from './little-shop'
defineProps<{ fruit: ProductId }>()
</script>

<template>
  <svg viewBox="0 0 100 100" fill="none" aria-hidden="true">
    <ellipse cx="50" cy="87" rx="29" ry="5" fill="#344b5c" opacity=".08" />
    <g v-if="fruit === 'apple'">
      <path d="M50 30C19 11 9 44 21 70c10 23 22 17 29 15 8 2 22 8 31-16C93 41 80 11 50 30Z" fill="#f16d73" />
      <path d="M50 30c1-10 3-15 8-20" stroke="#68765a" stroke-width="5" stroke-linecap="round" />
      <path d="M53 22c1-13 17-13 23-11-3 10-12 14-23 11Z" fill="#73aa73" />
      <path d="M29 39c-6 6-7 14-5 20" stroke="#ffa0a0" stroke-width="6" stroke-linecap="round" />
    </g>
    <g v-else-if="fruit === 'banana'">
      <path d="M20 30c9 42 40 42 65 12-10 47-59 58-73 13L20 30Z" fill="#f2c642" />
      <path d="M31 24c7 32 25 33 52 9-8 39-44 44-58 17l6-26Z" fill="#ffdc63" />
      <path d="m29 23 2-7m51 18 5-5M18 29l-2-6" stroke="#7f8160" stroke-width="5" stroke-linecap="round" />
      <path d="M29 57c11 18 26 19 40 10" stroke="#e8af35" stroke-width="3" stroke-linecap="round" />
    </g>
    <g v-else-if="fruit === 'pear'">
      <path d="M39 27c-1 18-5 22-15 34-15 23 0 29 25 28s40-12 23-32c-11-13-9-28-17-32-6-4-11-4-16 2Z" fill="#acd16e" />
      <path d="M49 24c0-9 4-16 9-19" stroke="#727c55" stroke-width="5" stroke-linecap="round" />
      <path d="M53 17c10-10 21-5 25-1-8 8-16 8-25 1Z" fill="#6d9e68" />
      <path d="M33 59c-7 9-8 15-2 20" stroke="#cfe99c" stroke-width="6" stroke-linecap="round" />
      <circle cx="59" cy="64" r="1.5" fill="#87ac50" /><circle cx="64" cy="74" r="1.5" fill="#87ac50" />
    </g>
    <g v-else>
      <circle cx="50" cy="55" r="33" fill="#f3a34f" />
      <path d="M48 23c6-15 18-18 30-14-6 12-16 16-30 14Z" fill="#6d9f6e" />
      <path d="m48 24 1-8" stroke="#7b8259" stroke-width="4" stroke-linecap="round" />
      <path d="M28 45c-3 4-4 9-3 15" stroke="#ffca7d" stroke-width="6" stroke-linecap="round" />
      <circle cx="63" cy="64" r="2" fill="#e8903c" /><circle cx="68" cy="53" r="2" fill="#e8903c" /><circle cx="54" cy="74" r="2" fill="#e8903c" />
    </g>
  </svg>
</template>
