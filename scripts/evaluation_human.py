"""生成离线人工盲评表；题目来自固定评测，未评分保持 null。"""
import json
from pathlib import Path

from evaluate_generation import ratings_template

FORM = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>试题人工盲评</title>
<style>body{max-width:980px;margin:32px auto;font:16px/1.7 system-ui;color:#172b3a;padding:0 20px}header{position:sticky;top:0;background:#fff;padding:12px 0;border-bottom:1px solid #ccc}article{padding:18px 0;border-bottom:1px solid #ddd}pre{white-space:pre-wrap;background:#f4f7fa;padding:14px}textarea{display:block;width:95%;min-height:70px;margin-top:10px}button,select{font:inherit;padding:8px}small{color:#586b77}</style>
<header><b>待人工评分</b> · <span id="progress"></span> <button id="download">下载评分 JSON</button>
<div><small>核对题目、答案、解析、知识点与年级；未评分不视为正确。评错须写依据。下载后用 evaluation_gate.py --ratings 导入。页面不展示模型复核结论。</small></div></header><main></main>
<script type="application/json" id="data">PAYLOAD</script><script>
const data=JSON.parse(document.querySelector('#data').textContent), rows=data.rounds.flatMap(r=>r.questions);
const main=document.querySelector('main');
function progress(){document.querySelector('#progress').textContent=`已评分 ${rows.filter(x=>x.correct!==null).length} / ${rows.length}`}
// 固定打乱顺序，避免按模型返回顺序评分；不改变样本键与轮次对应关系。
[...rows].sort((a,b)=>a.key.localeCompare(b.key)).forEach((q,i)=>{
 const article=document.createElement('article'), title=document.createElement('b'),pre=document.createElement('pre');
 title.textContent=`题目 ${i+1}`;pre.textContent='教学要求：'+JSON.stringify(q.requirements)+'\\n\\n'+(q.passage?'阅读正文：'+q.passage+'\\n\\n':'')+JSON.stringify(q.question,null,2);
 const choice=document.createElement('select');[['','待评分'],['true','正确'],['false','有错误']].forEach(([v,t])=>{const o=new Option(t,v);choice.add(o)});
 const reason=document.createElement('textarea');reason.placeholder='评分依据（有错误时必填）';
 choice.onchange=()=>{q.correct=choice.value===''?null:choice.value==='true';progress()};reason.oninput=()=>q.reason=reason.value;
 article.append(title,pre,choice,reason);main.append(article);
});
document.querySelector('#download').onclick=()=>{
 if(rows.some(q=>q.correct===false&&!q.reason.trim())){alert('请为错误题填写核对依据');return}
 data.status=rows.every(q=>q.correct!==null)?'reviewed':'pending_human_review';
 const a=document.createElement('a'),url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
 a.href=url;a.download='human-ratings.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};progress();</script></html>'''


def write_form(run: dict, path: Path):
    value = json.dumps(ratings_template(run), ensure_ascii=False).replace('<', '\\u003c')
    path.write_text(FORM.replace('PAYLOAD', value), encoding='utf-8', newline='\n')
