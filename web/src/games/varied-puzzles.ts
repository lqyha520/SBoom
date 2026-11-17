import { randomInt, type Rng } from './random'

const neighboring = (a: number, b: number, size: number) => Math.abs(a%size-b%size)+Math.abs(Math.floor(a/size)-Math.floor(b/size))===1
/** 反咬变换保留整条可走路线，改变蛇形路线的转弯、分支位置和端口。 */
export function variedPipeRoute(size: number, rng: Rng): number[] {
  let route = Array.from({length:size*size},(_,index)=>Math.floor(index/size)*size+(Math.floor(index/size)%2?size-1-index%size:index%size))
  let accepted = [...route]
  const boundary = (cell:number)=>cell%size===0 || cell%size===size-1 || cell<size || cell>=size*(size-1)
  for(let turn=0;turn<size*size*24;turn++) {
    if(rng()<.5)route.reverse()
    const choices=route.flatMap((cell,index)=>index>1 && neighboring(route[0],cell,size)?[index]:[])
    if(choices.length){const index=choices[randomInt(rng,0,choices.length-1)];route=[...route.slice(0,index).reverse(),...route.slice(index)]}
    if(boundary(route[0]) && boundary(route.at(-1)!))accepted=[...route]
  }
  return accepted
}

const motifs = [
  {name:'小房子',rows:['00100','01110','11111','10101','11111']},
  {name:'小帆船',rows:['00100','00110','00111','11111','01110']},
  {name:'小鱼',rows:['00010','01111','11110','01111','00010']},
  {name:'小雨伞',rows:['00100','01110','11111','00100','01100']},
  {name:'小花朵',rows:['01010','11111','01110','00100','01100']},
  {name:'小茶杯',rows:['00000','11110','10101','11110','01100']},
  {name:'小火箭',rows:['00100','01110','01110','11111','01010']},
  {name:'小蝴蝶',rows:['11011','11111','01110','11011','10001']},
  {name:'小皇冠',rows:['10101','11111','01110','01110','00000']},
  {name:'小铃铛',rows:['00100','01110','01110','11111','00100']},
  {name:'小蘑菇',rows:['01110','11111','11111','00100','00100']},
  {name:'小旗子',rows:['11110','10110','11110','10000','10000']},
  {name:'小钥匙',rows:['01100','10100','01111','00010','00000']},
  {name:'小雪人',rows:['00100','01110','00100','01110','11111']},
  {name:'小猫咪',rows:['10001','11011','11111','01110','00100']},
  {name:'小树苗',rows:['00100','01110','00100','01110','00100']},
  {name:'小山峰',rows:['00100','01110','11011','10001','11111']},
  {name:'小台阶',rows:['00001','00011','00111','01111','11111']},
  {name:'小箭头',rows:['00100','01110','11111','00100','00100']},
  {name:'小菱形',rows:['00100','01010','10001','01010','00100']},
  {name:'小窗户',rows:['11111','10101','11111','10101','11111']},
  {name:'小梯子',rows:['10001','11111','10001','11111','10001']},
  {name:'小拱门',rows:['01110','11011','10001','10001','10001']},
  {name:'小十字',rows:['01110','01110','11111','01110','01110']},
  {name:'小风车',rows:['11001','01101','00100','10110','10011']},
  {name:'小爱心',rows:['01010','11111','11111','01110','00100']},
  {name:'小闪电',rows:['00111','00110','01110','01100','11000']},
  {name:'小环形',rows:['01110','11011','10001','11011','01110']},
  {name:'小城墙',rows:['10101','11111','11111','11011','11011']},
  {name:'小树叶',rows:['00011','00111','01110','11100','10000']},
]
export function variedPicture(size:number,stage:number,rng:Rng):number[] {
  const motif=motifs[(stage-1)%motifs.length], offsetY=randomInt(rng,0,size-5),offsetX=randomInt(rng,0,size-5)
  const cells=Array(size*size).fill(0)
  for(let y=0;y<5;y++)for(let x=0;x<5;x++)cells[(y+offsetY)*size+x+offsetX]=Number(motif.rows[y][x])
  return cells
}
export const pictureName=(stage:number)=>motifs[(stage-1)%motifs.length].name

export function variedStroke(size:number,rank:number,stage:number,rng:Rng):Array<[number,number]> {
  const key=(a:number,b:number)=>[a,b].sort((a,b)=>a-b).join('-')
  for(let attempt=0;attempt<200;attempt++) {
    const edges=new Map<string,[number,number]>()
    const toggle=(a:number,b:number)=>{const id=key(a,b);if(edges.has(id))edges.delete(id);else edges.set(id,[a,b])}
    const cycles=rank===0?randomInt(rng,1,3):randomInt(rng,2,Math.min(6,3+Math.floor(stage/3)))
    for(let cycle=0;cycle<cycles;cycle++) {
      const x=randomInt(rng,0,size-2),y=randomInt(rng,0,size-2),right=randomInt(rng,x+1,size-1),bottom=randomInt(rng,y+1,size-1)
      const path:number[]=[]
      for(let col=x;col<right;col++)path.push(y*size+col)
      for(let row=y;row<bottom;row++)path.push(row*size+right)
      for(let col=right;col>x;col--)path.push(bottom*size+col)
      for(let row=bottom;row>y;row--)path.push(row*size+x)
      path.forEach((node,index)=>toggle(node,path[(index+1)%path.length]))
    }
    if(edges.size && rng()<.6){let node=[...edges.values()][0][0];for(let length=0;length<randomInt(rng,1,3);length++){const choices=Array.from({length:size*size},(_,index)=>index).filter(next=>neighboring(node,next,size));const next=choices[randomInt(rng,0,choices.length-1)];toggle(node,next);node=next}}
    const result=[...edges.values()],nodes=[...new Set(result.flat())],degrees=nodes.map(node=>result.filter(edge=>edge.includes(node)).length),minimum=[6,9,15][rank]
    if(result.length<minimum || result.length>24 || ![0,2].includes(degrees.filter(degree=>degree%2).length))continue
    const reached=new Set([nodes[0]]),queue=[nodes[0]]
    for(const node of queue)for(const [a,b] of result){const next=a===node?b:b===node?a:-1;if(next>=0 && !reached.has(next)){reached.add(next);queue.push(next)}}
    if(reached.size===nodes.length)return result
  }
  // 可解的保底路线；常规生成都会得到新的拓扑。
  const path=Array.from({length:size*size},(_,index)=>Math.floor(index/size)*size+(Math.floor(index/size)%2?size-1-index%size:index%size))
  return path.slice(1).map((node,index)=>[path[index],node])
}

export function hanoiDistance(cells:number[]):number {
  const target='2'.repeat(cells.length),queue=[{cells,steps:0}],seen=new Set([cells.join('')])
  for(const node of queue){if(node.cells.join('')===target)return node.steps;for(let from=0;from<3;from++)for(let to=0;to<3;to++){const disk=node.cells.indexOf(from),other=node.cells.indexOf(to);if(from===to || disk<0 || other>=0 && disk>other)continue;const next=[...node.cells];next[disk]=to;const key=next.join('');if(!seen.has(key)){seen.add(key);queue.push({cells:next,steps:node.steps+1})}}}
  return 1
}
