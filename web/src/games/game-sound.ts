/** 用浏览器合成短音，不下载音频，也不上传麦克风数据。 */
export function gameSound() {
  let context:AudioContext|undefined
  const nodes=new Set<AudioScheduledSourceNode>()
  async function ready(){try{context ||= new AudioContext();if(context.state==='suspended')await context.resume();return context}catch{return null}}
  function note(instrument:number){if(!context || context.state!=='running')return;const start=context.currentTime,gain=context.createGain();gain.gain.setValueAtTime(.0001,start);gain.gain.exponentialRampToValueAtTime(.23,start+.005);gain.gain.exponentialRampToValueAtTime(.0001,start+.28);gain.connect(context.destination)
    let source:AudioScheduledSourceNode
    if(instrument===1){const buffer=context.createBuffer(1,Math.floor(context.sampleRate*.18),context.sampleRate),data=buffer.getChannelData(0);for(let i=0;i<data.length;i++)data[i]=(Math.random()*2-1)*(1-i/data.length);const noise=context.createBufferSource();noise.buffer=buffer;noise.connect(gain);source=noise}
    else {const oscillator=context.createOscillator();oscillator.type=instrument===2?'triangle':'sine';oscillator.frequency.setValueAtTime([150,0,523.25,1046.5][instrument]||440,start);if(instrument===0)oscillator.frequency.exponentialRampToValueAtTime(45,start+.17);oscillator.connect(gain);source=oscillator}
    nodes.add(source);source.onended=()=>{nodes.delete(source);gain.disconnect();source.disconnect()};source.start(start);source.stop(start+.3)
  }
  function stop(){for(const source of nodes){try{source.stop()}catch{/* 短音可能已结束。 */}}nodes.clear()}
  function dispose(){stop();void context?.close();context=undefined}
  return {ready,note,stop,dispose}
}
