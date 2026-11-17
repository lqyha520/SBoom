import { freshJourney } from './challenge-journey'
import { computed,onBeforeUnmount,onMounted,ref,watch,type Ref } from 'vue'
import { gameKey } from './catalog'
import { writeGameSave } from './game-storage'
import { GAME_PAUSE_EVENT, revealGameHint } from './game-activity'
import { finishExperience,newExperience,restoreExperience,type ExperienceDifficulty,type ExperienceId,type ExperienceSave } from './experience-games'
export function useExperience<I extends ExperienceId>(props:{storageKey?:string},id:I) {
  const key=computed(()=>props.storageKey || gameKey(id))
  const read=()=>{try{return restoreExperience(localStorage.getItem(key.value),id)}catch{return null}}
  const save=ref(read() || newExperience(id)) as Ref<ExperienceSave<I>>
  const feedback=ref(''),saveError=ref(false),history:ExperienceSave<I>[]=[]
  const canUndo=ref(false),resetOpen=ref(false),targetDifficulty=ref<ExperienceDifficulty>('starter')
  let stopActivity=()=>{}
  let pauseActivity: (()=>void) | undefined
  function pause(){(pauseActivity || stopActivity)()}
  function visibility(){if(document.hidden)pause()}
  onMounted(()=>{window.addEventListener(GAME_PAUSE_EVENT,pause);window.addEventListener('blur',pause);document.addEventListener('visibilitychange',visibility)})
  function act<T>(operation:()=>T):T {
    const previous=JSON.parse(JSON.stringify(save.value)) as ExperienceSave<I>,result=operation()
    if(result!==false && result!==null && result!==undefined){history.push(previous);if(history.length>20)history.shift();canUndo.value=true;finishExperience(save.value)}
    return result
  }
  function undo(){stopActivity();const previous=history.pop();if(!previous)return;const rounds=save.value.rounds,best={...save.value.best},journey=save.value.journey;save.value=previous;save.value.journey=journey;save.value.rounds=rounds;save.value.best=best;canUndo.value=!!history.length;feedback.value='已撤回一步，可以换个办法。'}
  function requestReset(difficulty=save.value.difficulty){stopActivity();targetDifficulty.value=difficulty;if(save.value.round.finished && difficulty===save.value.difficulty){reset();return}resetOpen.value=true}
  function reset(){stopActivity();const {rounds,best}=save.value,gallery=save.value.round.kind==='creative-studio'?save.value.round.gallery:undefined;const previous=save.value.round,journey=save.value.journey || freshJourney(),retry=!previous.finished && targetDifficulty.value===save.value.difficulty;save.value=newExperience(id,targetDifficulty.value,Math.random,journey,retry?previous:undefined);if(gallery && save.value.round.kind==='creative-studio')save.value.round.gallery=gallery;save.value.rounds=rounds;save.value.best=best;history.length=0;canUndo.value=false;feedback.value='';resetOpen.value=false}
  function hint(text:string){pause();save.value.round.hints++;feedback.value=text;void revealGameHint()}
  watch(save,value=>{try{writeGameSave(key.value,value);saveError.value=false}catch{saveError.value=true}},{deep:true,immediate:true,flush:'post'})
  watch(key,()=>{stopActivity();save.value=read() || newExperience(id);history.length=0;canUndo.value=false;feedback.value=''})
  onBeforeUnmount(()=>{stopActivity();window.removeEventListener(GAME_PAUSE_EVENT,pause);window.removeEventListener('blur',pause);document.removeEventListener('visibilitychange',visibility)})
  const frame=computed(()=>({gameId:id,difficulty:save.value.difficulty,rounds:save.value.round.kind==='creative-studio'?save.value.round.gallery.length:save.value.rounds,finished:save.value.round.finished,feedback:feedback.value,saveError:saveError.value,canUndo:canUndo.value,resetOpen:resetOpen.value,targetDifficulty:targetDifficulty.value,stage:save.value.round.stage || 1}))
  return {save,feedback,saveError,canUndo,resetOpen,targetDifficulty,frame,act,undo,requestReset,reset,hint,onStop:(callback:()=>void)=>{stopActivity=callback},onPause:(callback:()=>void)=>{pauseActivity=callback}}
}
export type ExperienceSession<I extends ExperienceId=ExperienceId>=ReturnType<typeof useExperience<I>>
