K.init(()=>{
const CF=K.cfg(),BL=CF.baseline||{},HL=CF.cmHighlight||null,QC=CF.query||{},EXL=QC.extLabel||'外部质疑',EXS=QC.extShort||'外部';const hlRe=HL?new RegExp(HL.re):null;
const D=KZ,app=document.getElementById('app'),H=K.hash();
const subs=K.subs();
const LR={},OT={},QS={};
D.labrows.forEach(g=>(LR[g.sid]=LR[g.sid]||[]).push(g));
D.others.forEach(g=>(OT[g.sid]=OT[g.sid]||[]).push(g));
D.queries.forEach(q=>(QS[q.sid]=QS[q.sid]||[]).push(q));
const score=s=>{const l=LR[s.id]||[];return {csx:l.filter(g=>g.risk==='CSX').length,mh:l.filter(g=>g.risk==='MH').length,n2:l.filter(g=>g.risk==='NCS2').length,ot:(OT[s.id]||[]).filter(o=>o.pr>=3&&o.risk!=='AE').length,q:(QS[s.id]||[]).length}};
subs.forEach(s=>s.sc=score(s));
app.innerHTML=`<div class="grid" style="grid-template-columns:270px 1fr;gap:14px;align-items:start">
 <div class="card" style="padding:8px 0 0;position:sticky;top:66px">
  <div style="padding:0 10px 6px;display:grid;grid-template-columns:90px 1fr;gap:6px"><input class="s" id="fq" placeholder="编号" style="width:100%;min-width:0"><select class="s" id="fc" style="width:100%;min-width:0"><option value="">全部中心</option>${D.centers.filter(c=>c.dosed).map(c=>`<option value="${c.site}">${c.site} ${K.esc(c.name)}</option>`).join('')}</select></div>
  <div style="padding:0 10px 6px" class="chips" id="fs"></div>
  <div style="padding:0 10px 6px" class="flex"><span class="xs muted">排序</span><div class="seg" id="fo"></div></div>
  <div class="subj-list" id="sl"></div></div>
 <div id="main"></div></div>`;
const st={q:'',c:H.c||'',s:'dosed',o:'risk'};
document.getElementById('fc').value=st.c;
K.chips(document.getElementById('fs'),[['dosed','已给药',subs.filter(s=>s.fd).length],['risk','有风险提示',subs.filter(s=>s.fd&&(s.sc.csx||s.sc.mh||s.sc.ot)).length],['q','有质疑',subs.filter(s=>s.nq).length],['sf','筛选失败',subs.filter(s=>s.status==='筛选失败').length]],v=>{st.s=v;list()},{all:'全部',value:'dosed'});
K.seg(document.getElementById('fo'),[['risk','风险'],['id','编号'],['ae','AE数']],'risk',v=>{st.o=v;list()});
document.getElementById('fq').oninput=e=>{st.q=e.target.value.trim();list()};
document.getElementById('fc').onchange=e=>{st.c=e.target.value;list()};
const rk=s=>s.sc.csx*100+s.sc.ot*20+s.sc.mh*10+s.sc.q*3+s.sc.n2;
let cur=H.s;
function list(){
  let r=subs.filter(s=>(!st.c||s.site===st.c)&&(!st.q||s.id.includes(st.q)));
  if(st.s==='dosed')r=r.filter(s=>s.fd);else if(st.s==='risk')r=r.filter(s=>s.fd&&(s.sc.csx||s.sc.mh||s.sc.ot));else if(st.s==='q')r=r.filter(s=>s.nq);else if(st.s==='sf')r=r.filter(s=>s.status==='筛选失败');
  r.sort(st.o==='risk'?(a,b)=>rk(b)-rk(a)||a.id.localeCompare(b.id):st.o==='ae'?(a,b)=>b.nae-a.nae||a.id.localeCompare(b.id):(a,b)=>a.id.localeCompare(b.id));
  const el=document.getElementById('sl');
  el.innerHTML=r.map(s=>`<div class="it ${s.id===cur?'on':''}" data-id="${s.id}"><b style="width:44px;color:var(--ink)">${s.id}</b><span class="dot ${K.STC[s.status]||''}" title="${s.status}"></span><span class="sp"></span>${s.sc.csx?`<span class="p solid-red sq" title="CS未关联AE/MH">${s.sc.csx}</span>`:''}${s.sc.ot?`<span class="p red sq" title="专项核查（需核实及以上）">${s.sc.ot}</span>`:''}${s.sc.mh?`<span class="p org sq" title="CS仅关联MH">${s.sc.mh}</span>`:''}${s.sc.q?`<span class="p line sq" title="质疑">Q${s.sc.q}</span>`:''}<span class="xs faint" style="width:30px;text-align:right">${s.nae?'AE'+s.nae:''}</span></div>`).join('')||'<div class="empty">无</div>';
  el.querySelectorAll('.it').forEach(it=>it.onclick=()=>show(it.dataset.id));
  if(!cur&&r.length)show(r[0].id);
}
list();
if(cur)show(cur);
/* ---------------- profile */
const SHEET=CF.labGroups||{};
const SHO=Object.keys(SHEET);
function baseIdx(rows,fd){ // lab baseline: cfg.baseline.lab visit, else last pre-dose valid
  if(BL.lab){const i=rows.findIndex(r=>r[1]===BL.lab&&r[2]!=null);if(i>=0)return i}
  let b=-1;rows.forEach((r,j)=>{if(fd&&r[0]&&r[0]<=fd&&(r[2]!=null||r[3]))b=j});return b;}
const bandCell=(td,test)=>{const B=(CF.cellBands||{})[test];if(!B)return;const n=parseFloat(td.textContent);if(isNaN(n))return;for(const [op,v,c] of B){if((op==='>='&&n>=v)||(op==='>'&&n>v)||(op==='<='&&n<=v)||(op==='<'&&n<v)){if(c==='cs')td.classList.add('cs');else td.style.background=c;break}}};
async function show(id){
  cur=id;document.querySelectorAll('#sl .it').forEach(x=>x.classList.toggle('on',x.dataset.id===id));
  K.setHash({s:id,c:st.c,t:H.t});
  const m=document.getElementById('main');m.innerHTML='<div class="card empty">载入中…</div>';
  const d=await K.sub(id);if(!d){m.innerHTML='<div class="card empty">无数据</div>';return}
  const s=K.subBy(id),sc=s.sc,lr=LR[id]||[],ot=OT[id]||[],qs=QS[id]||[];
  const cro=D.cro.filter(c=>c[2]===id);
  const v=Object.fromEntries(d.visits.map(x=>[x[0],x[2]]));
  const ecs=d.ec.filter(x=>x.s).map(x=>[x.s,x.e]);
  const lastDose=d.ld;
  const dur=d.fd&&lastDose?K.days(lastDose,d.fd)+1:null;
  const iron=hlRe?d.cm.filter(c=>hlRe.test(c.t)):[];
  const risks=[...lr.filter(g=>g.risk==='CSX').map(g=>[`CS未关联 · ${g.test}`,'solid-red',`lab:${g.test}`]),...ot.filter(o=>o.pr>=3&&o.risk!=='AE').map(o=>[`${o.cat}`,o.pr>=4?'red':'org',`oth:${D.others.indexOf(o)}`]),...lr.filter(g=>g.risk==='MH').map(g=>[`仅MH · ${g.test}`,'org',`lab:${g.test}`]),...lr.filter(g=>g.risk==='NCS2').map(g=>[`NCS≥2级 · ${g.test}`,'yel',`lab:${g.test}`])];
  m.innerHTML=`<div class="card mb" style="padding:12px 14px">
   <div class="flex wrap" style="gap:10px"><b style="font-size:22px;color:var(--ink)">${id}</b>${K.status(d.status)}${K.p(d.site+' '+d.center,'line')}${d.rand?K.p('随机号 '+d.rand,'mono sq'):''}${d.strat&&CF.strat?K.p(K.esc(CF.strat.label||'分层')+'：'+K.esc(d.strat),d.strat===CF.strat.flag?'red':''):''}<span class="sp"></span><a class="p click blu" href="timeline.html#s=${id}">时间线 →</a></div>
   <div class="grid mt" style="grid-template-columns:repeat(7,1fr);gap:8px;margin-top:10px">
    ${[['年龄 / BMI',`${d.age??'—'} 岁 · ${d.bmi??'—'}`],['知情同意',d.icf||'—'],['首剂 D1',d.fd||'—'],['末次给药',lastDose?`${lastDose} <span class="xs muted">${dur?dur+' 天':''}</span>`:'—'],['治疗结束',d.eot?`${d.eot.d}<div class="xs muted clamp2" title="${K.esc(d.eot.why)}">${K.esc(d.eot.why)}</div>`:'—'],['研究结束',d.eos?`${d.eos.d||'—'} ${K.p(d.eos.done==='是'?'完成':'提前退出',d.eos.done==='是'?'grn':'red')}${d.eos.why?`<div class="xs muted clamp2">${K.esc(d.eos.why)}</div>`:''}`:'—'],['末次观察',d.lo||'—']].map(([a,b])=>`<div><div class="xs muted">${a}</div><div style="color:var(--ink);font-size:13px">${b}</div></div>`).join('')}
   </div>
   <div class="flex wrap mt" style="margin-top:10px;gap:6px">${[['AE',d.ae.length,d.ae.some(a=>a.sae)?'SAE':''],['MH',d.mh.length],['合并用药',d.cm.length,iron.length?HL.label+iron.length:''],['检验异常行',lr.length],['专项核查',ot.length],['质疑',qs.length],[EXS+'意见',cro.length]].map(([a,b,c])=>`<span class="chip" style="cursor:default">${a} <b>${b}</b>${c?` <span class="xs" style="color:var(--risk)">${c}</span>`:''}</span>`).join('')}</div>
   ${risks.length?`<div class="flex wrap" style="margin-top:8px;gap:4px"><span class="xs muted" style="margin-right:4px">风险提示</span>${risks.map(([t,c,k])=>`<span class="p ${c} click" data-go="${k}">${K.esc(t)}</span>`).join('')}</div>`:''}
  </div>
  <div class="tabs" id="ptabs"></div><div id="pp"></div>`;
  const dayOf=x=>K.studyDay(x,d.fd);
  const dt=x=>x?`${x}${d.fd?` <span class="xs faint">${dayOf(x.slice(0,10))}</span>`:''}`:'';
  const T=[['ae','AE',d.ae.length],['mh','病史/手术',d.mh.length+d.sur.length],['cm','合并用药',d.cm.length],['lab','检验矩阵',Object.keys(d.labs).length],...(Object.keys(d.vs||{}).length||Object.keys(d.ecg||{}).length?[['vs',Object.keys(d.vs||{}).length?(Object.keys(d.ecg||{}).length?'生命体征/ECG':'生命体征'):'心电图',null]]:[]),...((d.ext||[]).length?[['img',CF.extTab||'专项检查',d.ext.length]]:[]),['eff','有效性',Object.values(d.eff||{}).reduce((a,x)=>a+x.length,0)],['q','质疑/'+EXS,qs.length+cro.length]];
  const pp=document.getElementById('pp');
  const R={ae:tAE,mh:tMH,cm:tCM,lab:tLab,vs:tVS,img:tImg,eff:tEff,q:tQ};
  let t0=H.t&&R[H.t]?H.t:'ae';H.t=null;
  const tb=K.tabs(document.getElementById('ptabs'),T,t0,x=>{K.setHash({s:id,c:st.c,t:x});R[x]()});
  m.querySelectorAll('[data-go]').forEach(e=>e.onclick=()=>{const [k,val]=e.dataset.go.split(':');if(k==='lab'){tb.set('lab');setTimeout(()=>labChart(val),50)}else{tb.set('ae');setTimeout(()=>{const o=D.others[+val];drawOt(o)},50)}});
  function drawOt(o){K.drawer(`${o.cat}`,`<div class="flex wrap mb">${K.sid(o.sid)}${K.pri(o.pr)}${K.p(o.v||'','blu')}${K.p(o.sh+' 行'+o.row,'sq mono')}</div><div class="box org">${K.hlNum(o.sum)}</div>${o.rel.length?`<div class="sec-t"><h2>已关联</h2></div>${o.rel.map(r=>K.p(r[0]+' '+r[1],'grn')).join(' ')}`:''}${o.q.length?`<div class="sec-t"><h2>质疑</h2></div>${o.q.map(K.qPill).join(' ')}`:''}${o.ctx.length?`<div class="sec-t"><h2>判读背景</h2></div><ul class="lst small muted">${o.ctx.map(c=>`<li>${K.esc(c)}</li>`).join('')}</ul>`:''}${o.cro?`<div class="sec-t"><h2>CRO</h2></div><div class="small">${K.esc(o.cro)}</div>`:''}`)}
  /* AE */
  function tAE(){
    const rel=a=>/很可能|肯定|^可能有关/.test(a.rel)?'org':'';
    pp.innerHTML=`${d.ae.length?'':`<div class="box ${lr.length?'red':''} mb small">本例无 AE 记录${d.fd?`；给药后检验异常 <b>${lr.length}</b> 行（CS未关联 <b>${sc.csx}</b>、仅MH <b>${sc.mh}</b>），见「检验矩阵」`:''}</div>`}<div class="card" ${d.ae.length?'':'style="display:none"'}><div id="aet"></div></div>${ot.length?`<div class="card mt"><div class="sec-t" style="margin-top:0"><h2>专项核查</h2><span class="muted small">${ot.length} 条 · 方案阈值 / 记录一致性</span></div><div id="ott"></div></div>`:''}`;
    K.table(document.getElementById('aet'),{rows:d.ae,noPage:true,max:false,sort:'s',dir:1,cols:[
      {k:'n',t:'#',f:a=>`<span class="faint">${a.n}</span>`},
      {k:'t',t:'AE 术语',f:a=>`<b>${K.esc(a.t)}</b> ${K.p(a.c,'line')}${a.sae?K.p('SAE','solid-red'):''}${a.aesi?K.p('AESI','red'):''}${a.dili?K.p('DILI','red'):''}`},
      {k:'ib',t:'IB/类效应',ns:1,f:a=>K.ibTags(a.c)},
      {k:'s',t:'开始 → 结束',f:a=>`${dt(a.s)}<div class="xs muted">${a.e?dt(a.e):'持续'}</div>`},
      {k:'g',t:'等级',f:a=>K.p(a.g,a.g[0]>=3?'solid-red':a.g[0]==='2'?'red':'yel')},
      {k:'rel',t:'相关性',f:a=>K.p(a.rel,rel(a))},{k:'act',t:'措施',f:a=>a.act==='剂量不变'?`<span class="muted">${a.act}</span>`:K.p(a.act,'org')},{k:'out',t:'转归',f:a=>K.p(a.out,/痊愈|恢复/.test(a.out)?'grn':'')},{k:'cm',t:'合并用药',f:a=>a.cm==='是'?K.p('是','org'):'<span class="faint">否</span>'},
      {k:'pre',t:'阶段',f:a=>d.fd&&a.s&&a.s.slice(0,10)<d.fd?K.p('首剂前','brn'):''},{k:'row',t:'AE行',f:a=>`<span class="faint mono">${a.row}</span>`}]});
    if(ot.length)K.table(document.getElementById('ott'),{rows:ot,noPage:true,max:false,sort:'pr',onRow:drawOt,cols:[{k:'pr',t:'优先级',f:o=>K.pri(o.pr)},{k:'cat',t:'类别',f:o=>K.p(o.cat,'line')},{k:'v',t:'访视',f:o=>K.p(o.v||'—','blu')+` <span class="xs faint">${o.d||''}</span>`},{k:'sum',t:'信号',f:o=>`<div class="clamp2">${K.hlNum(o.sum)}</div>`},{k:'rel',t:'已关联',f:o=>o.rel.map(r=>K.p(r[0]+' '+r[1],'grn')).join(' ')},{k:'q',t:'质疑',f:o=>o.q.map(K.qPill).join(' ')||(o.cro?K.p('CRO已覆盖',''):'')}]});
  }
  function tMH(){
    pp.innerHTML=`<div class="grid g21"><div class="card"><div class="sec-t" style="margin-top:0"><h2>既往/现病史</h2></div><div id="mht"></div></div><div class="card"><div class="sec-t" style="margin-top:0"><h2>手术史 / 操作</h2></div><div id="sut"></div></div></div>`;
    const mhLab=t=>lr.filter(g=>g.rel.some(r=>r[0]==='MH'&&r[1]===t));
    K.table(document.getElementById('mht'),{rows:d.mh,noPage:true,max:false,cols:[{k:'n',t:'#',f:a=>`<span class="faint">${a.n}</span>`},{k:'t',t:'病史',f:a=>`<b>${K.esc(a.t)}</b>`},{k:'s',t:'开始',f:a=>a.s},{k:'ong',t:'筛选期持续',f:a=>a.ong==='是'?K.p('持续','org'):a.e||'<span class="faint">否</span>'},{k:'lk',t:'关联检验异常',ns:1,f:a=>mhLab(a.t).map(g=>K.risk(g.risk)+' '+K.esc(g.test)).join('<br>')},{k:'cmx',t:'对应用药',ns:1,f:a=>d.cm.filter(c=>c.wk==='MH'&&c.why.includes(a.t)).map(c=>K.p(c.t,'')).join(' ')}]});
    K.table(document.getElementById('sut'),{rows:[...d.sur.map(x=>({...x,k:'手术'})),...d.pr.map(x=>({...x,d:x.s,k:'操作'}))],noPage:true,max:false,cols:[{k:'t',t:'名称',f:a=>`<b>${K.esc(a.t)}</b> ${K.p(a.k,'line')}`},{k:'d',t:'日期'},{k:'why',t:'原因',f:a=>K.esc(a.why)}]});
  }
  function tCM(){
    pp.innerHTML=`<div class="card"><div class="tbar"><span class="note">${HL&&HL.note?K.esc(HL.note):''}</span><span class="sp"></span>${K.p('首剂前','brn')}${K.p('治疗期','blu')}${HL?K.p(HL.label,'red'):''}</div><div id="cmt"></div></div>`;
    const ph=c=>!d.fd?'':(c.s&&c.s.slice(0,10)<d.fd?(c.ong||!c.e||c.e>=d.fd?'首剂前→持续':'首剂前'):'治疗期');
    K.table(document.getElementById('cmt'),{rows:d.cm,noPage:true,max:false,sort:'s',dir:1,cols:[{k:'n',t:'#',f:a=>`<span class="faint">${a.n}</span>`},{k:'t',t:'药物',f:a=>`<b>${K.esc(a.t)}</b> ${hlRe&&hlRe.test(a.t)?K.p(HL.label,'red'):''}`},{k:'ph',t:'阶段',s:a=>ph(a),f:a=>{const x=ph(a);return x?K.p(x,x==='治疗期'?'blu':'brn'):''}},{k:'s',t:'开始 → 结束',f:a=>`${dt(a.s)}<div class="xs muted">${a.ong?'持续':dt(a.e)}</div>`},{k:'dose',t:'剂量/频次',f:a=>`${K.esc(a.dose)} · ${K.esc(a.fq)} <span class="xs faint">${K.esc(a.rt)}</span>`},{k:'why',t:'用药原因',f:a=>a.why?`${K.p(a.wk||'其他',a.wk==='AE'?'org':a.wk==='MH'?'line':'')} ${K.esc(a.why)}`:'<span class="faint">—</span>'},...(HL&&HL.lab?[{k:'hb',t:'同期 '+K.esc(HL.labShort||HL.lab),ns:1,f:a=>{if(!hlRe.test(a.t))return '';const hb=d.labs[HL.lab]||[];const near=x=>{let b=null;hb.forEach(r=>{if(r[0]&&r[0]<=x)b=r});return b};const s0=a.s&&near(a.s.slice(0,10)),e0=a.e&&near(a.e.slice(0,10));const f=r=>r?`<span class="vchip ${r[2]!=null&&r[5]!=null&&r[2]<r[5]?'cs':'n'}"><i>${r[1]}</i>${r[3]}</span>`:'';return `${f(s0)}${e0&&e0!==s0?'→'+f(e0):''}`}}]:[]),{k:'row',t:'行',f:a=>`<span class="faint mono">${a.row}</span>`}]});
  }
  /* matrices */
  function cols(obj){const set=new Map();Object.values(obj).forEach(rows=>rows.forEach(r=>{const k=(r[0]||'')+'|'+(r[11]||'');if(!set.has(k))set.set(k,{d:r[0],v:r[1],tp:r[11]||''})}));return [...set.values()].sort((a,b)=>(a.d||'').localeCompare(b.d||'')||a.tp.localeCompare(b.tp))}
  function tn(t){const m=t.match(/^(.*?)（(.*)）$/);return m?`${K.esc(m[1])} <span class="faint xs">${K.esc(m[2])}</span>`:K.esc(t)}
  function mx(el,groups,obj,{abn=false,bfn=null}={}){
    const C=cols(obj);const fl=new Set(lr.map(g=>g.test));
    const hd=`<tr><th>项目</th><th class="xs">单位/范围</th>${C.map(c=>`<th class="v">${c.v}${c.tp?`<div class="xs faint">${K.esc(c.tp.replace(/给药后/,'后').replace(/给药前/,'前').replace(/±.*$/,''))}</div>`:''}<div class="xs faint" style="font-weight:400">${(c.d||'').slice(5)}</div></th>`).join('')}</tr>`;
    let body='';
    groups.forEach(([g,tests])=>{
      const show=tests.filter(t=>!abn||obj[t].some(r=>r[7]>0));if(!show.length)return;
      body+=`<tr class="grp"><td colspan="${C.length+2}">${g} <span class="faint">${show.length}</span></td></tr>`;
      show.forEach(t=>{const rows=obj[t];const bs=rows.some(r=>r.length>13)?new Set(rows.map((r,j)=>r[13]?j:-1).filter(j=>j>=0)):new Set([(bfn||baseIdx)(rows,d.fd)]);const u=rows.find(r=>r[4])||[];
        body+=`<tr class="click" data-t="${K.esc(t)}"><td class="tn">${tn(t)}${fl.has(t)?' '+K.risk((lr.find(g=>g.test===t)||{}).risk):''}</td><td class="xs faint nowrap">${K.esc(u[4]||'')}${u[5]!=null||u[6]!=null?` ${K.rng(u[5],u[6])}`:''}</td>${C.map(c=>{const r=rows.find(r=>r[0]===c.d&&(r[11]||'')===c.tp);if(!r)return '<td class="v faint">·</td>';const hi=r[2]!=null&&r[6]!=null&&r[2]>r[6],lo=r[2]!=null&&r[5]!=null&&r[2]<r[5];return `<td class="v ${r[7]===2?'cs':r[7]===1?'ncs':''} ${bs.has(rows.indexOf(r))?'base':''}" title="${K.esc(r[9]+' 行'+r[10]+(r[8]?' · '+r[8]:''))}">${K.esc(r[3]??'')}${hi?'<span class="ar">↑</span>':lo?'<span class="ar">↓</span>':''}</td>`}).join('')}</tr>`})});
    el.innerHTML=`<div class="tw max" style="max-height:640px"><table class="t mx"><thead>${hd}</thead><tbody>${body||`<tr><td class="empty" colspan="${C.length+2}">无</td></tr>`}</tbody></table></div>`;
    el.querySelectorAll('tr[data-t]').forEach(tr=>tr.onclick=()=>labChart(tr.dataset.t,obj));
  }
  function tLab(){
    pp.innerHTML=`<div class="card"><div class="tbar"><label class="chip"><input type="checkbox" id="abn"> 仅异常项目</label><span class="sp"></span><span class="vchip cs">CS</span><span class="vchip ncs">NCS</span><span class="xs muted">橙色下划线 = 方案定义基线（${K.esc(BL.labLabel||BL.lab||'按 baselineRules')}；缺失时按规则回退，多次均值时全部标记）· 点击行看趋势</span></div><div id="lm"></div></div>`;
    const by={};Object.entries(d.labs).forEach(([t,rows])=>{const sh=rows[0][9];(by[sh]=by[sh]||[]).push(t)});
    const groups=Object.keys(by).sort((a,b)=>SHO.indexOf(a)-SHO.indexOf(b)).map(sh=>[SHEET[sh]||sh,by[sh]]);
    const draw=()=>mx(document.getElementById('lm'),groups,d.labs,{abn:document.getElementById('abn').checked});
    document.getElementById('abn').onchange=draw;draw();
  }
  function tVS(){
    pp.innerHTML=`${Object.keys(d.ecg||{}).length?`<div class="card mb"><div class="sec-t" style="margin-top:0"><h2>心电图</h2><span class="muted small">${K.esc(CF.ecgNote||'')}</span></div><div id="em"></div></div>`:''}${Object.keys(d.vs||{}).length?`<div class="card"><div class="sec-t" style="margin-top:0"><h2>生命体征</h2><span class="muted small">${K.esc(CF.vsNote||'')}</span></div><div id="vm"></div></div>`:''}`;
    const vb=(vis,tp)=>rows=>{const i=vis?rows.findIndex(r=>r[1]===vis&&(!tp||new RegExp(tp).test(r[11]||''))):-1;return i>=0?i:baseIdx(rows,d.fd)};
    if(document.getElementById('em'))mx(document.getElementById('em'),[['ECG',Object.keys(d.ecg)]],d.ecg,{bfn:vb(BL.ecg,BL.ecgTpt)});
    if(document.getElementById('vm'))mx(document.getElementById('vm'),[['生命体征',Object.keys(d.vs||{})]],d.vs||{},{bfn:vb(BL.vs,BL.vsTpt)});
    document.querySelectorAll('#em tr[data-t] td.v,#vm tr[data-t] td.v').forEach(td=>bandCell(td,td.parentNode.dataset.t));
  }
  /* generic extension modules: d.ext=[{title,note,cols:[..],rows:[[cell|[v,cls]]],chart:{x:[..],series:[{name,data,axis,type}],axes:[name,name2]}}] */
  function tImg(){
    const E=d.ext||[];
    pp.innerHTML=`<div class="grid g2">${E.map((e,i)=>`<div class="card"><div class="sec-t" style="margin-top:0"><h2>${K.esc(e.title)}</h2><span class="muted small">${K.esc(e.note||'')}</span></div>${e.chart?`<div class="chart" id="exc${i}" style="height:190px"></div>`:''}<div id="ext${i}"></div></div>`).join('')}</div>`;
    const cell=c=>Array.isArray(c)?(c[1]?K.p(K.esc(c[0]),c[1]):K.esc(c[0])):K.esc(c??'');
    E.forEach((e,i)=>{
      document.getElementById('ext'+i).innerHTML=(e.rows||[]).length?`<table class="t"><thead><tr>${e.cols.map((c,j)=>`<th class="${j>=(e.numFrom??99)?'r':''}">${K.esc(c)}</th>`).join('')}</tr></thead><tbody>${e.rows.map(r=>`<tr>${r.map((c,j)=>`<td class="${j>=(e.numFrom??99)?'r':''}">${cell(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>`:'<div class="empty">无记录</div>';
      if(e.chart)K.chart('#exc'+i,{grid:{left:44,right:44,top:24,bottom:22},legend:{top:0,itemWidth:10,itemHeight:6,textStyle:{fontSize:10}},tooltip:{trigger:'axis'},xAxis:{type:'category',data:e.chart.x,...K.axis},yAxis:(e.chart.axes||['']).map((n,k)=>({type:'value',name:n,scale:true,...K.axis,...(k?{splitLine:{show:false}}:{})})),series:e.chart.series.map(x=>({name:x.name,type:x.type||'line',yAxisIndex:x.axis||0,data:x.data,symbolSize:6,connectNulls:true,...(x.type==='bar'?{barWidth:8,itemStyle:{color:'#DCE6F2'}}:{})}))});
    });
  }
  /* efficacy per subject: d.eff={metricId:[[visit,date,value,raw]]}; metric meta from KZ.eff.metrics */
  function tEff(){
    const M=((D.eff||{}).metrics||[]).filter(m=>(d.eff||{})[m.id]&&d.eff[m.id].length);
    const bl=CF.blind||{};
    pp.innerHTML=`<div class="tbar">${bl.on?K.p(bl.tag||'盲态 · 不分组','blu'):''}${(bl.hidden||[]).map(x=>K.p(K.esc(x)+' 按约定不展示','line')).join('')}</div>${M.length?`<div class="grid g2">${M.map((m,i)=>`<div class="card"><div class="sec-t" style="margin-top:0"><h2>${K.esc(m.label)}</h2><span class="muted small">${K.esc(m.unit||'')}</span></div><div class="chart" id="efc${i}" style="height:190px"></div></div>`).join('')}</div>`:'<div class="card empty">无有效性记录</div>'}
    <div class="flex wrap small mt">${((D.eff||{}).anomalies||[]).filter(x=>x.sid===id).map(x=>K.p(x.label||x.type,'red')).join(' ')}</div>`;
    M.forEach((m,i)=>{const r=d.eff[m.id];const ref=(m.refLines||[]).map(([y,l])=>({yAxis:y,label:{formatter:l,fontSize:10}}));
      K.chart('#efc'+i,{grid:{left:40,right:16,top:16,bottom:22},tooltip:{trigger:'axis'},xAxis:{type:'category',data:r.map(x=>x[0]+'\n'+(x[1]||'').slice(5)),...K.axis,axisLabel:{fontSize:10,color:'#64676B'}},yAxis:{type:'value',scale:true,...K.axis,...(m.min!=null?{min:m.min}:{}),...(m.max!=null?{max:m.max}:{})},series:[{type:m.kind==='ordinal'?'bar':'line',barWidth:10,data:r.map(x=>x[2]),symbolSize:7,lineStyle:{color:'#FF9900'},itemStyle:{color:'#FF9900'},markLine:ref.length?{symbol:'none',silent:true,lineStyle:{color:'#8B0000',type:'dashed'},data:ref}:undefined}]})});
  }
  function tQ(){
    pp.innerHTML=`<div class="card mb"><div class="sec-t" style="margin-top:0"><h2>申办方 MM 质疑</h2><span class="muted small">${qs.length} 条</span></div>${qs.length?qs.map(q=>`<div class="flex" style="align-items:flex-start;padding:7px 0;border-bottom:1px solid var(--line2);gap:8px">${K.qPill(q.id)}<div style="flex:1"><div class="flex wrap" style="gap:4px;margin-bottom:2px">${K.p(q.cat,'line')}${K.p(q.sh+' 行'+q.row,'sq mono')}${K.p(q.v,'blu')}${K.p(q.cro,q.cro==='冲突澄清'?'red':q.cro==='未见同问'?'grn':'yel')}</div><div class="small">${K.hlNum(q.text)}</div></div></div>`).join(''):'<div class="empty">无</div>'}</div>
    <div class="card"><div class="sec-t" style="margin-top:0"><h2>${K.esc(EXL)}</h2><span class="muted small">${cro.length} 条</span></div>${cro.length?`<table class="t"><tbody>${cro.map(c=>`<tr><td class="nowrap">${K.p(c[0],'sq')} <span class="faint">${c[1]}</span></td><td>${K.p(c[3]||'—','blu')}</td><td class="small">${K.esc(c[4])}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">无</div>'}</div>`;
  }
  function labChart(t,obj){
    obj=obj||(d.labs[t]?d.labs:d.vs[t]?d.vs:d.ecg);const rows=(obj[t]||[]).filter(r=>r[2]!=null);
    const g=lr.find(x=>x.test===t);
    const b=K.drawer(`${id} · ${K.esc(t)}`,`${g?`<div class="flex wrap mb">${K.risk(g.risk)}${g.rel.map(r=>K.p(r[0]+' '+r[1],r[0]==='AE'?'grn':'org')).join('')}${g.q.map(K.qPill).join('')}${K.ctxTags(g.ctx)}</div>`:''}<div class="chart" id="dc" style="height:260px"></div><table class="t mt"><thead><tr><th>访视</th><th>日期</th><th>时间点</th><th class="r">结果</th><th>范围</th><th>判定</th><th>说明</th><th>来源</th></tr></thead><tbody>${(obj[t]||[]).map(r=>`<tr><td>${K.p(r[1],'blu')}</td><td class="xs">${r[0]} <span class="faint">${dayOf(r[0])}</span></td><td class="xs">${K.esc(r[11]||'')}</td><td class="r"><b>${K.esc(r[3])}</b> <span class="xs faint">${K.esc(r[4])}</span></td><td class="xs faint">${K.rng(r[5],r[6])}</td><td>${K.clin(r[7])}</td><td class="xs">${K.esc(r[8])}</td><td class="xs faint mono">${r[9]} ${r[10]}</td></tr>`).join('')}</tbody></table>`);
    const lo=rows.find(r=>r[5]!=null)?.[5],hi=rows.find(r=>r[6]!=null)?.[6];
    const ml=[];if(lo!=null)ml.push({yAxis:lo,label:{formatter:'LLN '+lo}});if(hi!=null)ml.push({yAxis:hi,label:{formatter:'ULN '+hi}});
    ((CF.refLines||{})[t]||[]).forEach(([y,l])=>ml.push({yAxis:y,label:{formatter:l||String(y)}}));
    (CF.ulnMult||[]).forEach(([re,k])=>{if(new RegExp(re).test(t)&&hi)ml.push({yAxis:hi*k,label:{formatter:k+'×ULN'},lineStyle:{color:'#8B0000'}})});
    K.chart(b.querySelector('#dc'),{grid:{left:44,right:60,top:20,bottom:30},tooltip:{trigger:'axis'},xAxis:{type:'time',...K.axis},yAxis:{type:'value',scale:true,...K.axis},series:[{type:'line',data:rows.map(r=>({value:[r[0]+(r[12]?'T'+r[12]:''),r[2]],itemStyle:{color:r[7]===2?'#8B0000':r[7]===1?'#E8C300':'#FF9900'}})),symbolSize:8,lineStyle:{color:'#FF9900'},markLine:{symbol:'none',silent:true,lineStyle:{color:'#9A9DA3',type:'dashed'},label:{fontSize:10,position:'end'},data:ml},markArea:d.fd?{silent:true,itemStyle:{color:'rgba(64,122,170,.06)'},data:[[{xAxis:d.fd},{xAxis:lastDose||d.lo}]]}:undefined}]});
  }
}
});
