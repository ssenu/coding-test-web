<script setup lang="ts">
// 얇은 선 아이콘. 장식용이므로 보조 기술에는 숨긴다(의미는 옆의 글자나 aria-label이 전한다).
const PATHS = {
  'arrow-left': 'M19 12H5M11 6l-6 6 6 6',
  check: 'M5 12.5l4.5 4.5L19 7.5',
  lock: 'M8 11V8a4 4 0 018 0v3M6.5 11h11v9h-11z',
  copy: 'M9 9h10v11H9zM5 15V4h10',
  plus: 'M12 5v14M5 12h14',
  trash: 'M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13',
  x: 'M6 6l12 12M18 6L6 18',
  play: 'M8 5.5l10 6.5-10 6.5z',
  download: 'M12 4v11M7 11l5 5 5-5M5 20h14',
  crown: 'M4 18h16M5 18L3.5 8l5 4L12 5l3.5 7 5-4L19 18',
  file: 'M7 3h7l4 4v14H7zM14 3v4h4',
  link: 'M10 14a4 4 0 005.7 0l3-3A4 4 0 0013 5.3l-1 1M14 10a4 4 0 00-5.7 0l-3 3A4 4 0 0011 18.7l1-1',
  logout: 'M10 4H5v16h5M15 8l4 4-4 4M19 12H9',
  alert: 'M12 8v5M12 16.5v.5M12 3l9.5 17h-19z',
  clock: 'M12 7v5l3 2M12 3a9 9 0 100 18 9 9 0 000-18z',
  pencil: 'M4 20l1-4L16 5l3 3L8 19zM14 7l3 3',
  flag: 'M5 21V4M5 4h13l-2.5 4L18 12H5',
  chart: 'M4 20V10M10 20V4M16 20v-7M21 20H3',
} as const

defineProps<{ name: keyof typeof PATHS }>()
</script>

<template>
  <svg
    class="icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.6"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="PATHS[name]" />
  </svg>
</template>
