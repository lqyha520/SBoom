import { freshExperience,integer,type ExperienceBase } from './experience-types'
export const artColors=['#38564d','#dc967e','#82aebe','#a394c2','#dbc172','#99b58d','#ffffff']
export const artBackgrounds=[{id:'paper',name:'米白画纸',color:'#fffdf3'},{id:'sky',name:'晴朗天空',color:'#edf6fc'},{id:'night',name:'星空画纸',color:'#34495e'}]
export const artStamps=[{id:'flower',name:'花朵',icon:'🌼'},{id:'tree',name:'树木',icon:'🌳'},{id:'star',name:'星星',icon:'⭐'},{id:'heart',name:'爱心',icon:'♥'},{id:'cloud',name:'云朵',icon:'☁'},{id:'mountain',name:'山峰',icon:'⛰'}]
export type ArtPoint=[number,number]
export type ArtMark={kind:'stroke';color:string;width:number;points:ArtPoint[]}|{kind:'stamp';color:string;size:number;stamp:string;x:number;y:number}
export interface ArtWork {title:string;background:string;marks:ArtMark[]}
export interface ArtRound extends ExperienceBase {kind:'creative-studio';title:string;background:string;marks:ArtMark[];revision:number;savedRevision:number;gallery:ArtWork[]}
export const artInspirations=['我的小世界','想象中的游乐园','住在云朵上的家','海底的奇妙朋友','一座未来城市','给森林设计小屋','会飞的交通工具','四季的颜色','一张生日邀请卡','夜空里的故事','和朋友一起野餐','给小动物设计花园']
export function newArt(stage=1):ArtRound {return {...freshExperience(),kind:'creative-studio',title:artInspirations[(stage-1)%artInspirations.length],background:'paper',marks:[],revision:0,savedRevision:-1,gallery:[]}}
export function addArt(round:ArtRound,mark:ArtMark):boolean {if(round.marks.length>=64 || !validMark(mark))return false;round.marks.push(mark);round.revision++;round.moves++;round.finished=false;return true}
export function setArtBackground(round:ArtRound,id:string):boolean {if(!artBackgrounds.some(item=>item.id===id) || round.background===id)return false;round.background=id;round.revision++;round.moves++;round.finished=false;return true}
export function eraseArt(round:ArtRound,x:number,y:number):boolean {
  if(!integer(x,0,600) || !integer(y,0,400))return false
  const index=[...round.marks].reverse().findIndex(mark=>mark.kind==='stamp' ? Math.hypot(mark.x-x,mark.y-y)<=mark.size*.65 : mark.points.some((point,index)=>{const next=mark.points[index+1]||point,dx=next[0]-point[0],dy=next[1]-point[1],t=Math.max(0,Math.min(1,((x-point[0])*dx+(y-point[1])*dy)/(dx*dx+dy*dy||1)));return Math.hypot(x-point[0]-t*dx,y-point[1]-t*dy)<=Math.max(12,mark.width) }))
  if(index<0)return false
  round.marks.splice(round.marks.length-1-index,1);round.revision++;round.moves++;round.finished=false;return true
}
export function saveArtwork(round:ArtRound):boolean {if(!round.marks.length || round.savedRevision===round.revision)return false;round.savedRevision=round.revision;round.gallery.unshift({title:round.title,background:round.background,marks:JSON.parse(JSON.stringify(round.marks))});round.gallery=round.gallery.slice(0,12);round.moves++;return true}
export function loadArtwork(round:ArtRound,index:number):boolean {const work=round.gallery[index];if(!work)return false;round.title=work.title;round.background=work.background;round.marks=JSON.parse(JSON.stringify(work.marks));round.revision++;round.finished=false;round.moves++;return true}
export const artPassed=(round:ArtRound)=>round.marks.length>0 && round.savedRevision===round.revision
export function validMark(mark:ArtMark):boolean {if(!mark || !artColors.includes(mark.color))return false;if(mark.kind==='stamp')return integer(mark.x,0,600) && integer(mark.y,0,400) && integer(mark.size,12,96) && artStamps.some(stamp=>stamp.id===mark.stamp);return mark.kind==='stroke' && integer(mark.width,2,24) && Array.isArray(mark.points) && mark.points.length>0 && mark.points.length<=128 && mark.points.every(point=>Array.isArray(point) && point.length===2 && integer(point[0],0,600) && integer(point[1],0,400))}
export function validArt(round:ArtRound):boolean {const validWork=(work:ArtWork)=>work && typeof work.title==='string' && work.title.length<=40 && artBackgrounds.some(item=>item.id===work.background) && Array.isArray(work.marks) && work.marks.length<=64 && work.marks.every(validMark);return validWork(round) && integer(round.revision) && integer(round.savedRevision,-1,round.revision) && Array.isArray(round.gallery) && round.gallery.length<=12 && round.gallery.every(validWork)}
