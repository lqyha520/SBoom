<script setup lang="ts">
import { ref } from 'vue'
import { artBackgrounds,type ArtMark } from './creative-studio'
defineProps<{marks:ArtMark[];background:string;preview?:ArtMark|null;title?:string}>()
const element=ref<SVGSVGElement|null>(null)
defineExpose({element})
const path=(points:Array<[number,number]>)=>points.map((point,index)=>(index?'L':'M')+point.join(' ')).join(' ')
</script>
<template>
  <svg ref="element" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 400" role="img" :aria-label="title || '创意画布'" class="art-picture">
    <rect width="600" height="400" :fill="artBackgrounds.find(item=>item.id===background)?.color" />
    <template v-for="(mark,index) in preview?[...marks,preview]:marks" :key="index"><g v-if="mark.kind==='stroke'"><path v-if="mark.points.length>1" :d="path(mark.points)" :stroke="mark.color" :stroke-width="mark.width" stroke-linecap="round" stroke-linejoin="round" fill="none" /><circle v-else :cx="mark.points[0][0]" :cy="mark.points[0][1]" :r="mark.width/2" :fill="mark.color" /></g><g v-else :transform="`translate(${mark.x-mark.size/2} ${mark.y-mark.size/2}) scale(${mark.size/100})`" :fill="mark.color"><template v-if="mark.stamp==='flower'"><circle v-for="n in 5" :key="n" :cx="50+23*Math.cos(n*Math.PI*2/5)" :cy="48+23*Math.sin(n*Math.PI*2/5)" r="20" /><circle cx="50" cy="48" r="15" fill="#e6c77f" /></template><template v-else-if="mark.stamp==='tree'"><rect x="44" y="49" width="12" height="44" rx="3" fill="#ad9171" /><path d="M50 4L12 58H31L13 78H87L69 58H88Z" /></template><path v-else-if="mark.stamp==='star'" d="M50 3L62 34L97 37L70 59L79 93L50 74L21 93L30 59L3 37L38 34Z" /><path v-else-if="mark.stamp==='heart'" d="M50 88L14 53C-10 28 25-7 50 23C75-7 110 28 86 53Z" /><template v-else-if="mark.stamp==='cloud'"><circle cx="29" cy="55" r="22" /><circle cx="51" cy="41" r="27" /><circle cx="75" cy="56" r="20" /><rect x="25" y="53" width="52" height="24" rx="10" /></template><template v-else><path d="M50 6L2 90H98Z" /><path d="M50 6L34 34L44 30L53 40L64 31Z" fill="#fff8" /></template></g></template>
  </svg>
</template>
<style scoped>.art-picture{width:100%;height:auto;aspect-ratio:1.5;display:block;overflow:hidden}</style>
