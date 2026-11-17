<script setup lang="ts">
import { computed,onBeforeUnmount,ref } from 'vue'
import ExploreFrame from './ExploreFrame.vue'
import { useExperience } from './use-experience'
import { catchAnimals,catchFood,catchSpeeds } from './animal-catch'
import { seededRandom } from './challenge-journey'
const props=defineProps<{storageKey?:string}>()
const {save,frame,feedback,resetOpen,act,undo,requestReset,reset,hint,onStop,onPause}=useExperience(props,'animal-catch')
const round=computed(()=>save.value.round),animal=computed(()=>catchAnimals[round.value.animal]),speed=computed(()=>catchSpeeds.find(item=>item.id===round.value.speed)!),field=ref<HTMLElement|null>(null)
const teamLabel=computed(()=>round.value.team?.map(index=>catchAnimals[index].icon).join(' → '))
const basket=ref(50),playing=ref(false),startedOnce=ref(false),drops=ref<Array<{id:number;food:number;x:number;age:number}>>([])
let animation=0,last=0,elapsed=0,serial=0,held=0
const rules=['看清动物喜欢的食物，移动篮子接住它；其他食物让它落下就好。','手机可以直接在游戏区滑动，也可以点左右按钮；电脑可在游戏区使用左右方向键。','可以调慢速度、暂停，再回来继续。接够目标数量就完成，不会因漏接而结束游戏。']
function pause(){held=0;playing.value=false;cancelAnimationFrame(animation)}
function clear(){pause();drops.value=[];elapsed=0;serial=0;startedOnce.value=false}
onStop(clear)
onPause(pause)
function spawn(){const random=seededRandom((round.value.seed || 0)+serial*7919+round.value.caught*101),target=serial===0 || random()<.65,other=catchAnimals.map((_,index)=>index).filter(index=>index!==round.value.animal);drops.value.push({id:serial,food:target?round.value.animal:other[Math.floor(random()*other.length)],x:serial===0?50:14+random()*72,age:0});serial++}
function start(){if(round.value.finished || playing.value)return;playing.value=true;startedOnce.value=true;last=performance.now();if(!drops.value.length)spawn();field.value?.focus()
  function tick(now:number){if(!playing.value)return;const delta=Math.max(0,Math.min(now-last,100));last=now;basket.value=Math.max(10,Math.min(90,basket.value+held*delta*.055));elapsed+=delta;if(elapsed>=speed.value.interval){elapsed-=speed.value.interval;spawn()}
    for(const drop of drops.value)drop.age+=delta
    const landed=drops.value.filter(drop=>drop.age>=speed.value.duration);drops.value=drops.value.filter(drop=>drop.age<speed.value.duration)
    for(const drop of landed){const previous=round.value.animal,result=act(()=>catchFood(round.value,drop.food,Math.abs(drop.x-basket.value)<=10));if(result==='good')feedback.value='接到'+catchAnimals[previous].foodName+'啦！';else if(result==='wrong')feedback.value='这是其他动物的食物，留意'+animal.value.foodName+'。';if(round.value.animal!==previous){drops.value=[];elapsed=0;feedback.value='下一位伙伴是'+animal.value.name+'，现在要接'+animal.value.foodName+'！';break}if(round.value.finished){clear();return}}
    animation=requestAnimationFrame(tick)
  }animation=requestAnimationFrame(tick)
}
function hold(direction:number,event:PointerEvent){event.preventDefault();held=direction;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);shift(direction)}
function shift(direction:number){basket.value=Math.max(10,Math.min(90,basket.value+direction*12))}
function pointer(event:PointerEvent){event.preventDefault();const box=field.value!.getBoundingClientRect();basket.value=Math.max(10,Math.min(90,(event.clientX-box.left)/box.width*100));if(event.type==='pointerdown'){field.value!.setPointerCapture(event.pointerId);field.value!.focus()}}
function movePointer(event:PointerEvent){if(event.buttons || event.pointerType==='touch')pointer(event)}
function keyboard(event:KeyboardEvent){if(event.key==='ArrowLeft' || event.key==='ArrowRight'){event.preventDefault();shift(event.key==='ArrowLeft'?-1:1)}}
onBeforeUnmount(clear)
</script>
<template>
  <ExploreFrame v-bind="frame" :progress="`接到 ${round.caught} / ${round.goal} 份食物`" :rules="rules" @difficulty="requestReset" @undo="undo" @restart="requestReset()" @reset="reset" @cancel="resetOpen=false" @hint="hint('先把速度调到“慢慢接”，把篮子移到 '+animal.foodName+' 的正下方，等它落下来。')">
    <div class="catch-intro"><span>{{ animal.icon }}</span><div><h2>今天帮{{ animal.name }}接{{ animal.foodName }}</h2><p>喜欢的食物是 {{ animal.food }}，其他食物不用接。</p><p v-if="round.team">本关伙伴：{{ teamLabel }} · 连续接对 {{ round.streak || 0 }} 份</p></div></div>
    <div class="explore-toolbar"><select v-model="round.speed" aria-label="接食物速度" :disabled="round.finished" @change="clear"><option v-for="item in catchSpeeds" :key="item.id" :value="item.id">{{ item.name }}</option></select><button v-if="playing" @click="pause">暂停游戏</button><button v-else :disabled="round.finished" @click="start">{{ startedOnce || round.moves?'继续接食物':'开始接食物' }}</button><span class="explore-chip">已接到 {{ round.caught }} 份</span></div>
    <div ref="field" class="catch-field" tabindex="0" role="group" aria-label="接食物游戏区" @keydown="keyboard" @pointerdown="pointer" @pointermove="movePointer"><span class="catch-cloud cloud-one">☁</span><span class="catch-cloud cloud-two">☁</span><span v-for="drop in drops" :key="drop.id" class="falling-food" :data-food="drop.food" :data-drop="drop.id" :style="{left:drop.x+'%',top:4+drop.age/speed.duration*79+'%'}">{{ catchAnimals[drop.food].food }}</span><div class="catch-basket" :style="{left:basket+'%'}"><span>🧺</span><small>{{ animal.food }}</small></div><div v-if="!playing && !round.finished" class="catch-paused"><strong>{{ startedOnce || round.moves?'休息一下，随时继续。':'移动篮子，准备开始。' }}</strong><span>点击上面的开始按钮</span></div></div>
    <div class="catch-buttons"><button aria-label="篮子向左" @pointerdown="hold(-1,$event)" @pointerup="held=0" @pointercancel="held=0" @lostpointercapture="held=0" @click="!$event.detail && shift(-1)">←</button><span>拖动篮子 · 按住方向按钮</span><button aria-label="篮子向右" @pointerdown="hold(1,$event)" @pointerup="held=0" @pointercancel="held=0" @lostpointercapture="held=0" @click="!$event.detail && shift(1)">→</button></div>
    <p class="explore-caption">不用着急，漏接后可以接着玩；暂停时，食物也会停下来。</p>
  </ExploreFrame>
</template>
<style scoped>
.catch-intro{display:flex;align-items:center;gap:17px;margin:0 0 23px}.catch-intro>span{font-size:47px}.catch-intro h2{font-size:19px;color:#70845e;font-weight:650}.catch-intro p{font-size:12px;color:#8c977e;margin-top:7px;line-height:1.8}.catch-field{position:relative;height:380px;background:linear-gradient(#e4f2f8 0%,#edf6f6 82%,#d4e4bd 82%);border:1px solid #d3e1cb;border-radius:17px;overflow:hidden;touch-action:none;user-select:none}.catch-field:focus-visible{outline-offset:3px}.catch-cloud{position:absolute;color:#fff;font-size:58px}.cloud-one{left:12%;top:4%}.cloud-two{right:9%;top:10%;font-size:42px}.falling-food{position:absolute;transform:translate(-50%,-50%);font-size:31px;pointer-events:none}.catch-basket{position:absolute;bottom:5px;transform:translateX(-50%);width:73px;height:66px;display:flex;align-items:center;justify-content:center;font-size:53px;pointer-events:none}.catch-basket small{position:absolute;top:17px;font-size:20px}.catch-paused{position:absolute;top:34%;left:12%;right:12%;padding:25px 10px;text-align:center;border:1px solid #d4e3cf;border-radius:15px;background:#fffdf0e8;color:#8b966f;pointer-events:none}.catch-paused strong{font-size:17px;display:block;font-weight:600}.catch-paused>span{display:block;font-size:11px;margin-top:11px}.catch-buttons{display:flex;align-items:center;gap:22px;justify-content:center;margin:20px 0}.catch-buttons button{display:grid;place-items:center;width:51px;height:43px;border:1px solid #d1dfc7;border-radius:10px;background:#fff;color:#809672;font-size:26px}.catch-buttons>span{font-size:11px;color:#8c9b7f}@media(max-width:560px){.catch-intro{gap:12px}.catch-intro>span{font-size:38px}.catch-intro h2{font-size:16px}.catch-intro p{font-size:11px}.catch-field{height:330px}.catch-paused strong{font-size:15px}.catch-buttons{gap:15px}.catch-buttons>span{font-size:10px}}
</style>
