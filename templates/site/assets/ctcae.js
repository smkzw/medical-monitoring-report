/* 数值毒性分级（CTCAE v5.0 / v6.0 / 自定义）——与 scripts/ctcae.py 同一套声明式规则。
   规则表由构建写入 data/grading.js：window.KZG = {label, items, map:{指标id:代码}, fac:{指标id:单位换算系数}}
   仅实现可凭数值直接分级的条目；需结合症状/干预/临床后果的级别不自动分级。 */
(function(){
const G=()=>(typeof window!=='undefined'&&window.KZG)||{items:{},map:{},fac:{}};
const X=(by,v,l,u,b)=>({val:v,xuln:u?v/u:null,xlln:l?v/l:null,xbase:b?v/b:null,chg:b!=null?v-b:null,pct:b?(v-b)/Math.abs(b)*100:null,duln:u!=null?v-u:null})[by];
const OK=(s,v,l,u,b)=>{const x=X(s.by||'val',v,l,u,b);let t=s.v;if(typeof t==='string')t={ULN:u,LLN:l,BASE:b}[t];if(x==null||x!==x||t==null)return false;
  const o=s.op||'>';const r=o==='>'?x>t:o==='>='?x>=t:o==='<'?x<t:x<=t;return r&&(s.and||[]).every(a=>OK(a,v,l,u,b))};
const code=id=>G().items[id]?id:(G().map||{})[id];
const CTC={label:()=>G().label||'CTCAE',has:id=>!!G().items[code(id)],terms:id=>(G().items[code(id)]||[]).map(c=>c.zh||c.term),
  grade(id,v,l,u,b,isBase){const cd=code(id),T=G().items[cd];if(!T||v==null)return null;const f=(G().fac||{})[id]??1;if(f==null)return null;
    v=v*f;l=l!=null?l*f:null;u=u!=null?u*f:null;b=isBase||b==null?null:b*f;let best={g:0,t:'',d:''};
    T.forEach(c=>{const d=c.dir||'H';const ab=b!=null&&((d==='H'&&u!=null&&b>u)||(d==='L'&&l!=null&&b<l));
      if(c.when==='baseAbnormal'&&!ab)return;if(c.when==='baseNormal'&&ab)return;
      const rel=c.steps.some(s=>['chg','pct'].includes(s.by));
      if(!c.absolute){if(d==='H'&&u!=null&&v<=u&&!ab&&!rel)return;if(d==='L'&&l!=null&&v>=l&&!rel&&!c.steps.some(s=>s.by==='xlln'))return}
      const g=Math.max(0,...c.steps.filter(s=>OK(s,v,l,u,b)).map(s=>s.g));if(g>best.g)best={g,t:c.zh||c.term,d}});return best}};
if(typeof window!=='undefined')window.CTC=CTC;if(typeof module!=='undefined')module.exports=CTC;
})();
