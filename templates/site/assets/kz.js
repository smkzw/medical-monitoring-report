/* KZ core: shared helpers for all pages */
(function(){
const K=window.K={};
const D=()=>window.KZ;
K.esc=s=>s==null?'':String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
K.p=(t,c='',tip)=>`<span class="p ${c}"${tip?` title="${K.esc(tip)}"`:''}>${t}</span>`;
K.fmt=(v,d)=>{if(v==null||v===''||isNaN(v))return '—';const n=+v;if(d!=null)return n.toFixed(d);return Math.abs(n)>=100?n.toFixed(0):Math.abs(n)>=10?(+n.toFixed(1)).toString():(+n.toFixed(2)).toString();};
K.rng=(lo,hi)=>lo!=null&&hi!=null?`${K.fmt(lo)}–${K.fmt(hi)}`:hi!=null?`≤${K.fmt(hi)}`:lo!=null?`≥${K.fmt(lo)}`:'—';
K.pct=v=>v==null||isNaN(v)?'—':(v>0?'+':'')+(+v).toFixed(1)+'%';
K.sid=(id,extra='')=>`<a class="sid" href="subjects.html#s=${id}${extra}">${id}</a>`;
const C0=()=>(window.KZ&&window.KZ.cfg)||{};
K.cfg=()=>C0();
K.VIS=(((window.KZ||{}).cfg||{}).visits||{}).order||['V1','V2','D1','USV','ET'];
K.VUNS=(((window.KZ||{}).cfg||{}).visits||{}).unsched||['USV'];K.VET=(((window.KZ||{}).cfg||{}).visits||{}).early||['ET'];
K.isAgg=v=>!K.VUNS.includes(v)&&!K.VET.includes(v);
K.vi=v=>{const i=K.VIS.indexOf(v);return i<0?99:i};
K.days=(a,b)=>{if(!a||!b||a.length<10||b.length<10)return null;return Math.round((new Date(a)-new Date(b))/864e5)};
K.studyDay=(d,fd)=>{const x=K.days(d,fd);return x==null?'':(x>=0?'D'+(x+1):'D'+x)};
K.clin=c=>c===2?K.p('CS','red'):c===1?K.p('NCS','yel'):c===0?K.p('正常','grn'):'';
K.PRI={4:['优先核实','red'],3:['需核实','org'],2:['结合临床','yel'],1:['筛查提示','']};
K.pri=n=>K.p(K.PRI[n]?.[0]||'—',K.PRI[n]?.[1]||'');
K.RISK={CSX:['CS·未关联AE/MH','solid-red','判CS但未关联AE或病史：漏报AE风险最高'],MH:['CS·仅关联MH','org','判CS且仅关联既往病史：需判断是否给药后加重'],NCS2:['NCS·≥2级','yel','数值落入'+((window.KZ||{}).cfg||{}).ctcaeVersion+'≥2级但判NCS'],NA2:['未评价·≥2级','yel','数值达≥2级但未见研究者临床意义评价'],AE:['已关联AE','grn','已有对应AE记录'],NCS:['NCS','','异常无临床意义'],REL:['较基线显著变化','yel','给药后超出参考范围且偏离≥T_dev、同向较基线变化≥T_base（双阈值，按当前所选档位即时重分类）']};
K.risk=r=>K.p(K.RISK[r]?.[0]||r,K.RISK[r]?.[1]||'',K.RISK[r]?.[2]);
/* ---- 双阈值（T_dev/T_base，PR-4）：状态读取 + REL 即时重分类 + 变更监听 ----
 * 档位来源：系统层 KZS.thresholds（选择器写入）＞ cfg.thresholds（构建配置，默认 30%/30%）。
 * per_metric 为覆盖（直接替换所选值）；metricThreshold 为收紧（有效值=min(所选,收紧值)，构建折叠进 cfg.metricTight）。 */
K._thrSel=null;
K.thr=()=>{const c=(C0().thresholds)||{},S=window.KZS,src=(S&&S.thresholds)?S.thresholds:(K._thrSel||{}),sel={...c,...src};
  return {dev:sel.dev??c.dev??.3,base:sel.base??c.base??.3,per_metric:sel.per_metric??c.per_metric??{}}};
K.thrOf=mid=>{const t=K.thr(),pm=(t.per_metric||{})[mid]||{},ti=((C0().metricTight)||{})[mid]||{};
  const d=pm.dev??t.dev,b=pm.base??t.base;
  return {dev:ti.dev!=null?Math.min(d,ti.dev):d,base:ti.base!=null?Math.min(b,ti.base):b,ov:pm.dev!=null||pm.base!=null,tight:ti.dev!=null||ti.base!=null}};
K.relPts=g=>{if(!g||g.risk!=='REL')return [];const t=K.thrOf(g.mid||('lab:'+g.test));
  return (g.pts||[]).filter(p=>p[10]!=null&&p[6]!=null&&p[10]>=t.dev&&Math.abs(p[6])>=t.base*100)};
K.relOn=g=>K.relPts(g).length>0;                 /* 当前所选阈值下该 REL 候选是否构成风险项 */
K._thrFns=[];
K.onThr=fn=>{K._thrFns.push(fn)};
K.setThr=sel=>{if(window.KZS)KZS.thresholds={...KZS.thresholds,...sel};else K._thrSel={...(K._thrSel||{}),...sel};
  K._thrFns.forEach(f=>{try{f(K.thr())}catch(e){console.error('thr listener',e)}});return K.thr()};
K.grade=g=>g==null?'':K.p('G'+g,g>=3?'solid-red':g>=2?'red':'yel');
K.hash=()=>Object.fromEntries(location.hash.replace(/^#/,'').split('&').filter(Boolean).map(x=>x.split('=').map(decodeURIComponent)));
K.setHash=o=>{const h=Object.entries(o).filter(([k,v])=>v!=null&&v!=='').map(([k,v])=>k+'='+encodeURIComponent(v)).join('&');history.replaceState(null,'','#'+h)};
K.center=site=>(D().centers.find(c=>c.site===site)||{}).name||site;
K.SUBF=['id','site','status','rand','fd','age','bmi','nae','maxg','sae','aesi','rel','nmh','ncm','nq','ncro','icf','lo','strat','ld','grp'];
K.subs=()=>{if(K._subs)return K._subs;K._subs=D().subs.map(a=>Object.fromEntries(K.SUBF.map((k,i)=>[k,a[i]])));K._subsBy=Object.fromEntries(K._subs.map(s=>[s.id,s]));return K._subs};
K.subBy=id=>{K.subs();return K._subsBy[id]};
K.STC=Object.assign({'完成试验':'grn','已入组':'blu','治疗结束':'brn','提前退出':'red','筛选失败':'','筛选中':'yel'},(((window.KZ||{}).cfg||{}).statusColors)||{});
K.status=s=>K.p(s,K.STC[s]??'');
/* header */
K.PAGES=[['index.html','总览'],['study.html','研究依据'],['subjects.html','参与者资料'],['timeline.html','时间线'],['safety.html','AE/MH风险'],['efficacy.html','有效性趋势'],['objective.html','检验检查趋势'],['queries.html','医学质疑'],['methods.html','审阅要点']];
K.header=()=>{
  const cur=location.pathname.split('/').pop()||'index.html';const m=D().meta,c=C0(),st=c.study||{},br=c.brand||{};
  document.title=(document.title.split(' · ')[0]||'')+' · '+(st.short||st.code||'医学监察');
  const h=document.createElement('header');h.className='top';
  h.innerHTML=`<div class="bar"><img class="logo" src="${br.logo||'assets/logo_bot.svg'}" alt="${K.esc(br.org||'康哲药业')}"><div class="ttl"><b>${K.esc(st.title||'医学监察报告')}</b><span>${K.esc(st.subtitle||'')}</span></div>
  <nav>${K.PAGES.map(([u,t])=>`<a href="${u}" class="${u===cur?'on':''}">${t}</a>`).join('')}</nav>
  <div class="meta">${(c.headerTags||[['数据截止 '+(m.cutoff||''),'line']]).map(t=>K.p(t[0],t[1]||'line')).join('')}${c.blind&&c.blind.on?K.p(c.blind.tag||'盲态','blu'):''}</div></div><div class="ribbon"></div>`;
  document.body.prepend(h);
  const f=document.createElement('div');f.className='foot';const ft=c.footer||{};f.innerHTML=`<span>${K.esc(ft.left||'产品中心-医学部')}</span><span>${K.esc(ft.right||('数据源：'+(m.sources||[]).join(' · ')))}</span>`;document.body.append(f);
  const mk=document.createElement('div');mk.className='dr-mask';const dr=document.createElement('aside');dr.className='dr';dr.innerHTML='<div class="dh"><h2></h2><span class="dsub"></span><button class="x" title="关闭">×</button></div><div class="db"></div>';
  document.body.append(mk,dr);mk.onclick=K.close;dr.querySelector('.x').onclick=K.close;document.addEventListener('keydown',e=>{if(e.key==='Escape')K.close()});
};
K.drawer=(title,html,sub='')=>{const dr=document.querySelector('.dr');dr.querySelector('h2').innerHTML=title;dr.querySelector('.dsub').innerHTML=sub;const b=dr.querySelector('.db');b.innerHTML=html;b.scrollTop=0;dr.classList.add('on');document.querySelector('.dr-mask').classList.add('on');return b};
K.close=()=>{document.querySelector('.dr')?.classList.remove('on');document.querySelector('.dr-mask')?.classList.remove('on')};
/* subject loader */
K._cache={};K._wait={};
window.KZ_SUB=d=>{K._cache[d.id]=d;(K._wait[d.id]||[]).forEach(f=>f(d));delete K._wait[d.id]};
K.sub=id=>new Promise(res=>{if(K._cache[id])return res(K._cache[id]);(K._wait[id]=K._wait[id]||[]).push(res);if(K._wait[id].length>1)return;const s=document.createElement('script');s.src='data/s/'+id+'.js';s.onerror=()=>res(null);document.head.append(s)});
/* table */
K.table=(el,cfg)=>{
  const st={sort:cfg.sort||null,dir:cfg.dir||-1,page:0};const ps=cfg.pageSize||60;
  function draw(){
    let rows=cfg.rows.slice();
    if(st.sort){const c=cfg.cols.find(c=>c.k===st.sort);const fn=c.s||(r=>r[c.k]);rows.sort((a,b)=>{const x=fn(a),y=fn(b);if(x==null&&y==null)return 0;if(x==null)return 1;if(y==null)return -1;return (x>y?1:x<y?-1:0)*st.dir})}
    const n=rows.length,pages=Math.max(1,Math.ceil(n/ps));if(st.page>=pages)st.page=0;const view=cfg.noPage?rows:rows.slice(st.page*ps,st.page*ps+ps);
    let grpPrev=null;
    const body=view.map((r,i)=>{let g='';if(cfg.group){const gv=cfg.group(r);if(gv!==grpPrev){grpPrev=gv;g=`<tr class="grp"><td colspan="${cfg.cols.length}">${cfg.groupHead?cfg.groupHead(gv,r):gv}</td></tr>`}}
      return g+`<tr class="${cfg.onRow?'click':''}" data-i="${cfg.rows.indexOf(r)}">${cfg.cols.map(c=>`<td class="${c.cls||''}"${c.w?` style="width:${c.w}"`:''}>${c.f?c.f(r):K.esc(r[c.k])}</td>`).join('')}</tr>`}).join('');
    el.innerHTML=`<div class="tw ${cfg.max===false?'':'max'}"${cfg.h?` style="max-height:${cfg.h}"`:''}><table class="t ${cfg.cls||''}"><thead><tr>${cfg.cols.map(c=>`<th class="${c.ns?'':'s'} ${c.cls||''}" data-k="${c.k}"${c.tip?` title="${K.esc(c.tip)}"`:''}>${c.t}${st.sort===c.k?`<span class="ar">${st.dir>0?'▲':'▼'}</span>`:''}</th>`).join('')}</tr></thead><tbody>${body||`<tr><td colspan="${cfg.cols.length}" class="empty">无匹配记录</td></tr>`}</tbody></table></div>`+
      (cfg.noPage||pages<=1?`<div class="pager">${n} 行</div>`:`<div class="pager">${n} 行 · 第 ${st.page+1}/${pages} 页 <button data-p="-1" ${st.page?'':'disabled'}>‹</button><button data-p="1" ${st.page<pages-1?'':'disabled'}>›</button></div>`);
    el.querySelectorAll('th.s').forEach(th=>th.onclick=()=>{const k=th.dataset.k;if(st.sort===k)st.dir*=-1;else{st.sort=k;st.dir=-1}draw()});
    el.querySelectorAll('.pager button').forEach(b=>b.onclick=()=>{st.page+=+b.dataset.p;draw()});
    if(cfg.onRow)el.querySelectorAll('tbody tr[data-i]').forEach(tr=>tr.onclick=e=>{if(e.target.closest('a'))return;cfg.onRow(cfg.rows[+tr.dataset.i],e)});
    cfg.after&&cfg.after(el);
  }
  draw();return {set(rows){cfg.rows=rows;st.page=0;draw()},draw};
};
/* chips filter: opts [[value,label,count]] multi=false */
K.chips=(el,opts,onChange,{multi=false,all='全部',value=null}={})=>{
  let sel=multi?new Set(value||[]):value;
  function draw(){el.innerHTML=(all?`<span class="chip ${(multi?sel.size===0:sel==null)?'on':''}" data-v="">${all}</span>`:'')+opts.map(([v,l,n])=>`<span class="chip ${(multi?sel.has(v):sel===v)?'on':''}" data-v="${K.esc(v)}">${l}${n!=null?` <b>${n}</b>`:''}</span>`).join('');
    el.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{const v=c.dataset.v;if(multi){if(!v)sel.clear();else sel.has(v)?sel.delete(v):sel.add(v)}else sel=v===''?null:(sel===v&&all?null:v);draw();onChange(multi?[...sel]:sel)})}
  draw();return {get:()=>multi?[...sel]:sel,set(v){sel=multi?new Set(v):v;draw()}};
};
K.seg=(el,opts,val,onChange)=>{function draw(){el.innerHTML=opts.map(([v,l])=>`<button class="${v===val?'on':''}" data-v="${v}">${l}</button>`).join('');el.querySelectorAll('button').forEach(b=>b.onclick=()=>{val=b.dataset.v;draw();onChange(val)})}draw();return{get:()=>val}};
K.tabs=(el,opts,val,onChange)=>{function draw(){el.innerHTML=opts.map(([v,l,n])=>`<button class="${v===val?'on':''}" data-v="${v}">${l}${n!=null?`<span class="n">${n}</span>`:''}</button>`).join('');el.querySelectorAll('button').forEach(b=>b.onclick=()=>{val=b.dataset.v;draw();onChange(val)})}draw();onChange(val);return{set(v){val=v;draw();onChange(v)}}};
/* charts */
K.COL=['#FF9900','#407AAA','#587B3B','#A85F34','#8B0000','#FFCC00','#8E6CB8','#3BA3A0','#7F7F7F'];
K.chart=(el,opt)=>{if(typeof el==='string')el=document.querySelector(el);let c=echarts.getInstanceByDom(el);if(!c){c=echarts.init(el,null,{renderer:'canvas'});new ResizeObserver(()=>c.resize()).observe(el)}
  opt=Object.assign({color:K.COL,textStyle:{fontFamily:'Microsoft YaHei, PingFang SC, Noto Sans CJK SC, Arial',fontSize:11},animationDuration:300},opt);c.setOption(opt,true);return c};
K.axis={axisLine:{onZero:false,lineStyle:{color:'#C9CCD1'}},axisTick:{show:false},axisLabel:{color:'#64676B'},splitLine:{lineStyle:{color:'#F0F1F4'}}};
K.q=(arr,p)=>{if(!arr.length)return null;const a=arr.slice().sort((x,y)=>x-y);const i=(a.length-1)*p,lo=Math.floor(i),hi=Math.ceil(i);return a[lo]+(a[hi]-a[lo])*(i-lo)};
K.median=a=>K.q(a,.5);
/* EDC-like listing render: rows [{sh,row,f,hl}] */
K.listing=(rows,{cols=null,cap=true}={})=>{
  const bySheet={};rows.forEach(r=>(bySheet[r.sh]=bySheet[r.sh]||[]).push(r));
  return Object.entries(bySheet).map(([sh,rs])=>{
    let keys=cols||[...new Set(rs.flatMap(r=>Object.keys(r.f)))];
    const hk=new Set(rs.flatMap(r=>r.hl));
    if(!cols&&keys.length>14){const keep=new Set(['受试者编号','表单集名称',...hk]);const imp=keys.filter(k=>keep.has(k)||/日期|结果|名称|项目|评价|严重|关系|AESI|SAE|单位|下限|上限|值|体积|压|QTc|心率|持续|剂量/.test(k));keys=[...new Set([...keys.filter(k=>keep.has(k)),...imp])].slice(0,18)}
    return `${cap?`<div class="cap">${K.p(sh,'sq mono')} 行 ${rs.map(r=>r.row).join(', ')}</div>`:''}<div class="listing tw"><table><thead><tr><th>行</th>${keys.map(k=>`<th>${K.esc(k)}</th>`).join('')}</tr></thead><tbody>${rs.map(r=>`<tr><td class="faint">${r.row}</td>${keys.map(k=>`<td class="${r.hl.includes(k)?'on':''}" title="${K.esc(r.f[k]||'')}">${K.esc(r.f[k]??'')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`}).join('');
};
K.hlNum=t=>K.esc(t).replace(/(\d+(?:\.\d+)?(?:\s?(?:g\/L|mmol\/L|U\/L|ms|mmHg|g\/cm²|kg|%|×10\^9\/L|umol\/L|IU\/L)))/g,'<span class="num-hl">$1</span>').replace(/(20\d\d-\d\d-\d\d)/g,'<span class="num-hl">$1</span>');
K.qById=id=>D().queries.find(q=>q.id===id);
K.qPill=id=>`<span class="p org sq click mono" data-q="${id}">${id}</span>`;
K.showQ=id=>{const q=K.qById(id);if(!q)return;const cro=D().cro.filter(c=>c[2]===q.sid);
  K.drawer(`${q.id} · ${q.cat}`,`<div class="flex wrap mb">${K.sid(q.sid)}${K.p(K.center(q.site),'line')}${K.p(q.sh+' 行'+q.row,'sq mono')}${K.p(q.v,'blu')}${q.test?K.p(q.test,''):''}${K.p(q.cro,q.cro==='冲突澄清'?'red':q.cro==='未见同问'?'grn':'yel')}</div>
  <div class="box org" style="font-size:13px;line-height:1.7">${K.hlNum(q.text)}</div>
  <div class="sec-t"><h2>证据记录</h2><span class="muted small">${q.ev.length} 行 · ${K.esc((C0().query||{}).note||'写入 clean listing 首列「申办方MM query」')}</span></div><div class="ex-rows muted">载入中…</div>
  <div class="sec-t"><h2>本例 ${K.esc((C0().query||{}).extLabel||'CRO 既往意见')}</h2><span class="muted small">${cro.length} 条</span></div>${cro.length?`<table class="t"><tbody>${cro.map(c=>`<tr><td class="nowrap">${K.p(c[0],'sq')} ${c[1]}</td><td>${K.p(c[3],'blu')}</td><td>${K.esc(c[4])}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">无</div>'}`);
  const box=document.querySelector('.dr .ex-rows');const X=window.KZX;const ex=X&&Object.values(X.ex).find(e=>e.q===id);
  if(ex){box.innerHTML=K.listing(ex.rows);box.classList.remove('muted')}else{box.innerHTML=`<table class="t"><tbody>${q.ev.map(e=>`<tr><td>${K.p(e[0],'sq mono')}</td><td>行 ${e[1]}</td><td>${K.p(e[2],'blu')}</td><td>${K.esc(e[3])}</td></tr>`).join('')}</tbody></table>`}
};
document.addEventListener('click',e=>{const q=e.target.closest('[data-q]');if(q){e.preventDefault();K.showQ(q.dataset.q)}});
K.CTX=((((window.KZ||{}).cfg||{}).taxonomy||{}).ctx||[['无CTCAE条目|不能仅凭数值','无CTCAE数值条目',''],['症状/处置型','需结合症状/处置',''],['单位|换算','单位待核','org'],['基线.*(回退|替代)|替代基线|改用首次','替代基线','blu']]).map(([re,l,c])=>[new RegExp(re),l,c]);
K.ctxTags=arr=>{const out=[];(arr||[]).forEach(t=>{const m=K.CTX.find(([re])=>re.test(t));if(m&&!out.some(o=>o[0]===m[1]))out.push([m[1],m[2],t])});return out.map(([l,c,t])=>K.p(l,c,t)).join('')};
K.init=fn=>document.addEventListener('DOMContentLoaded',()=>{K.header();fn()});
})();
K.DOM=(((window.KZ||{}).cfg||{}).taxonomy||{}).domains||[];
K.domOf=cat=>{const d=K.DOM.find(d=>d[1].includes(cat));return d?d[0]:'其他'};
K.IBC=Object.assign({'IB已识别风险':'red','IB潜在风险':'org','方案AESI':'solid-red','类效应·预期':'blu','疾病相关':'','同类常见':''},(((window.KZ||{}).cfg||{}).taxonomy||{}).ibColors||{});
K.ibTags=cat=>((window.KZ.ibtag||{})[cat]||[]).map(t=>K.p(t,K.IBC[t]||'')).join('');
/* protocol/IB rule pills + drawer */
K.SRC=Object.assign({protocol_operative:['方案原文','org'],protocol_footnote:['方案脚注','blu'],protocol_amendment_history:['修订史',''],user_confirmed_monitoring:['项目确认','grn'],ib_classification:['IB 风险分类','red'],ib_text:['IB 原文','red'],class_effect_cited:['同类药物（IB引用）','brn']},(((window.KZ||{}).cfg||{}).taxonomy||{}).sources||{});
K.ruleBy=id=>(window.KZ.rules||[]).find(r=>r.id===id);
K.rp=(id,c='')=>`<span class="p sq mono click ${c||'line'}" data-r="${id}" title="${K.esc((K.ruleBy(id)||{}).st||'')}">${id}</span>`;
K.showRule=id=>{const r=K.ruleBy(id);if(!r)return;const un=(window.KZ.unres||[]).find(u=>u.startsWith(id+' '));
  K.drawer(`${r.id} · 方案/IB 依据`,`<div class="box org" style="font-size:13px;line-height:1.75">${K.hlNum(r.st)}</div>${un?`<div class="box red mt small"><b>口径待确认：</b>${K.esc(un)}</div>`:''}
  <div class="sec-t"><h2>原文定位</h2><span class="muted small">${r.src.length} 处</span></div><table class="t"><tbody>${r.src.map(s=>`<tr><td class="nowrap">${K.p((K.SRC[s[2]]||[s[2]])[0],(K.SRC[s[2]]||[0,''])[1])}</td><td class="nowrap mono xs muted">${K.esc(s[0])}</td><td>${K.esc(s[1])}</td></tr>`).join('')}</tbody></table>`,K.p(r.dom,'line'))};
document.addEventListener('click',e=>{const r=e.target.closest('[data-r]');if(r){e.preventDefault();K.showRule(r.dataset.r)}});
/* ---- 中心偏离（漏斗图）---- */
K.mean=a=>a.length?a.reduce((s,x)=>s+x,0)/a.length:null;
K.sd=a=>{if(a.length<2)return null;const m=K.mean(a);return Math.sqrt(a.reduce((s,x)=>s+(x-m)*(x-m),0)/(a.length-1))};
K.FL={red:['明显偏离','#8B0000'],org:['需关注','#E67E00'],'':['范围内','#9A9DA3']};
/* groups:[{site,v:[数值]}] → 中心均值与整体均值 ± 2/3·SD/√n 比较；n<2 不判 */
K.funnel=groups=>{const all=groups.flatMap(g=>g.v),mu=K.mean(all),sd=K.sd(all)||0;
  const rows=groups.filter(g=>g.v.length).map(g=>{const n=g.v.length,m=K.mean(g.v),se=sd/Math.sqrt(n),z=se?(m-mu)/se:0;return {site:g.site,n,m,z,flag:n<2?'':Math.abs(z)>3?'red':Math.abs(z)>2?'org':''}});
  return {mu,sd,N:all.length,rows,se:n=>sd/Math.sqrt(n),kind:'m'}};
/* groups:[{site,x,n}] → 中心比例与整体比例 ± 2/3·√(p(1−p)/n) 比较 */
K.funnelP=groups=>{const X=groups.reduce((s,g)=>s+g.x,0),N=groups.reduce((s,g)=>s+g.n,0),p=N?X/N:0;
  const rows=groups.filter(g=>g.n).map(g=>{const m=g.x/g.n,se=Math.sqrt(p*(1-p)/g.n),z=se?(m-p)/se:0;return {site:g.site,n:g.n,x:g.x,m,z,flag:g.n<2?'':Math.abs(z)>3?'red':Math.abs(z)>2?'org':''}});
  return {mu:p,N,rows,se:n=>Math.sqrt(p*(1-p)/n),kind:'p'}};
K.funnelChart=(el,F,o={})=>{const fm=o.fmt||(v=>K.fmt(v)),hc=o.hc||'',maxN=Math.max(2,...F.rows.map(r=>r.n))+1,ns=[];for(let n=1;n<=maxN;n+=Math.max(.25,maxN/80))ns.push(n);
  const lo=o.kind==='p'?0:-Infinity,hi=o.kind==='p'?1:Infinity,cl=v=>Math.min(hi,Math.max(lo,v));
  const lim=(k,s)=>ns.map(n=>[n,cl(F.mu+s*k*F.se(n))]);
  const ms=F.rows.map(r=>r.m).concat([F.mu]),y0=Math.min(...ms),y1=Math.max(...ms),yp=(y1-y0)*.25||Math.abs(F.mu)*.1||1,st=Math.pow(10,Math.floor(Math.log10((y1-y0+2*yp)/4)))/2,yr=[Math.floor((y0-yp)/st)*st,Math.ceil((y1+yp)/st)*st].map(x=>+x.toPrecision(6));
  const L=(name,data,c,t)=>({type:'line',name,data,symbol:'none',silent:true,lineStyle:{color:c,width:1,type:t},z:1});
  const c=K.chart(el,{grid:{left:o.left||48,right:16,top:18,bottom:34},
   tooltip:{trigger:'item',formatter:p=>{const r=p.data&&p.data.r;if(!r)return '';return `<b>中心 ${r.site}</b>${o.names&&o.names[r.site]?' '+K.esc(o.names[r.site]):''}<br>n=${r.n}${r.x!=null?'（'+r.x+' 例）':''} · ${o.kind==='p'?'比例':'均值'} ${fm(r.m)}<br>整体 ${fm(F.mu)} · z=${r.z.toFixed(1)}<br>${K.FL[r.flag][0]}${r.n<2?'（n<2 不判）':''}`}},
   xAxis:{type:'value',name:o.xName||'中心受试者数 n',nameLocation:'middle',nameGap:20,nameTextStyle:{color:'#64676B',fontSize:10},min:0,max:Math.ceil(maxN),minInterval:1,...K.axis},
   yAxis:{type:'value',scale:true,...K.axis,axisLabel:{color:'#64676B',formatter:v=>o.kind==='p'?Math.round(v*100)+'%':K.fmt(v)},min:o.ymin!=null?o.ymin:yr[0],max:o.ymax!=null?o.ymax:yr[1]},
   series:[L('整体',[[0,F.mu],[maxN,F.mu]],'#64676B','solid'),L('+2SE',lim(2,1),'#F2B567','dashed'),L('−2SE',lim(2,-1),'#F2B567','dashed'),L('+3SE',lim(3,1),'#B88A8A','dotted'),L('−3SE',lim(3,-1),'#B88A8A','dotted'),
    {type:'scatter',z:5,data:F.rows.map(r=>{const s=r.site===hc;return {value:[r.n,o.ymax!=null?Math.min(r.m,o.ymax):r.m],r,symbolSize:s?13:8,
      itemStyle:{color:K.FL[r.flag][1],opacity:hc&&!s?.55:.9,borderColor:s?'#0F1115':'#fff',borderWidth:s?2:1},
      label:{show:s||!!r.flag||r.n>=3,position:'right',formatter:r.site,fontSize:s?11:9,fontWeight:s?700:400,color:s?'#0F1115':'#9A9DA3'}}})}]});
  c.off('click');if(o.onPick)c.on('click',p=>{if(p.data&&p.data.r)o.onPick(p.data.r.site)});return c};
K.flagPill=r=>r&&r.flag?K.p(K.FL[r.flag][0],r.flag):'';
/* ---- 连续变量按访视：中位线 + IQR 带 + 个体散点；选中中心加粗，整体淡化 ---- */
K.jit=s=>{let h=0;for(const ch of String(s))h=(h*31+ch.charCodeAt(0))%997;return (h/997-.5)*.5};
K.distLine=(el,o)=>{const V=o.V,YR=o.yr||null,clip=o.clip,fm=o.fmt||(v=>K.fmt(v));
  const st=a=>{const x=a.map(p=>p.v);return x.length?{n:x.length,q1:K.q(x,.25),md:K.q(x,.5),q3:K.q(x,.75)}:null};
  const cy=v=>{v=clip!=null?Math.min(v,clip):v;return K.ycl(YR,v)};
  const SA=o.all.map(st),SS=o.sel?o.sel.map(st):null,on=!!o.sel;
  const band=(S,fill,z)=>({type:'custom',silent:true,z,data:(()=>{const i=S.findIndex(x=>x);return i<0?[]:[[i,cy(S[i].md)]]})(),renderItem:(p,api)=>{const ix=S.map((s,i)=>s?i:null).filter(i=>i!=null);if(ix.length<2)return;
     const pts=ix.map(i=>api.coord([i,cy(S[i].q3)])).concat(ix.slice().reverse().map(i=>api.coord([i,cy(S[i].q1)])));return {type:'polygon',shape:{points:pts},style:{fill}}}});
  const med=(S,name,c,w,z,dash)=>({type:'line',name,z,data:S.map((s,i)=>s?{value:[i,cy(s.md)],st:s,lab:name}:null).filter(Boolean),symbol:'circle',symbolSize:w>2?7:5,lineStyle:{color:c,width:w,type:dash||'solid'},itemStyle:{color:c}});
  const pts=(A,c,sz,op,z)=>({type:'scatter',z,data:A.flatMap((a,i)=>a.map(p=>({value:[i+K.jit(p.sid),cy(p.v)],sid:p.sid,raw:p.v,vis:V[i],...K.ysym(YR,p.v)}))),symbolSize:sz,itemStyle:{color:c,opacity:op}});
  const ser=[band(SA,on?'rgba(201,204,209,.28)':'rgba(255,153,0,.13)',1),pts(o.all,on?'#C9CCD1':'#F6C27E',on?3:4,on?.35:.6,2),med(SA,o.allName||'整体',on?'#9A9DA3':'#E67E00',on?1.5:2.5,3,on?'dashed':'solid')];
  if(on)ser.push(band(SS,'rgba(255,153,0,.16)',4),pts(o.sel,'#E67E00',6,.85,5),med(SS,o.selName||'所选中心','#FF9900',3,6));
  if(o.extra)ser.push(...o.extra);
  if(o.ml&&o.ml.length)ser[2].markLine={symbol:'none',silent:true,lineStyle:{color:'#9A9DA3',type:'dashed'},label:{fontSize:10,color:'#64676B',position:'insideEndTop'},data:o.ml};
  const c=K.chart(el,{grid:{left:o.left||46,right:18,top:on?28:16,bottom:34},legend:on?{top:0,right:0,itemWidth:14,itemHeight:6,textStyle:{fontSize:10,color:'#64676B'},data:[o.selName||'所选中心',o.allName||'整体']}:undefined,
   tooltip:{trigger:'item',formatter:p=>{if(p.data&&p.data.st){const s=p.data.st;return `<b>${p.data.lab}</b> · ${V[p.data.value[0]]}<br>n=${s.n} · 中位 ${fm(s.md)}<br>Q1–Q3 ${fm(s.q1)} – ${fm(s.q3)}`}if(p.data&&p.data.sid)return `${p.data.sid} · ${p.data.vis} ${fm(p.data.raw)}${p.data.raw!==p.data.value[1]?'（超出显示范围，标于边缘）':''}`;return ''}},
   xAxis:[{type:'value',min:-.5,max:V.length-.5,show:false},{type:'category',data:V.map((v,i)=>v+'\nn='+(on?(SS[i]?SS[i].n:0)+'/':'')+(SA[i]?SA[i].n:0)),position:'bottom',...K.axis,axisLabel:{color:'#64676B',fontSize:10,interval:0}}],
   yAxis:{type:'value',scale:true,max:clip!=null?clip:o.ymax,min:o.ymin,...K.axis,...K.ybOpt(YR)},series:ser});
  c.off('click');if(o.onClick)c.on('click',p=>{if(p.data&&p.data.sid)o.onClick(p.data.sid)});return c};
/* KPI：所选中心值 + 淡色整体值 */
K.kpiCS=(label,cv,ov,o={})=>`<div class="kpi${o.sel?' sel':''}${o.cls?' '+o.cls:''}"><div class="l">${label}</div><div class="v">${cv}<small>${o.unit||''}</small></div>${o.sel?`<div class="ov">整体 ${ov}${o.ou?' · '+o.ou:''}</div>`:o.note?`<div class="ov">${o.note}</div>`:''}${o.flag?`<div class="s">${o.flag}</div>`:''}</div>`;

/* Y 轴：按主体数据范围（Q1−3·IQR ~ Q3+3·IQR）定位，远端异常值用轴断裂（多区间）压缩显示 */
K.yb=(vals,refs=[])=>{const a=vals.filter(v=>v!=null&&isFinite(v)).sort((x,y)=>x-y),R={breaks:[],hi:null,lo:null};if(a.length<5)return R;
  const q1=K.q(a,.25),q3=K.q(a,.75);let iq=q3-q1;if(!iq)iq=(K.q(a,.95)-K.q(a,.05))||Math.abs(q3)*.1||1;
  let lo=Math.max(a[0],q1-2*iq),hi=Math.min(a[a.length-1],q3+2*iq);
  refs.forEach(r=>{if(r!=null&&isFinite(r)&&r>=lo-iq&&r<=hi+iq){lo=Math.min(lo,r);hi=Math.max(hi,r)}});
  const span=hi-lo||1,pad=span*.04,st=Math.pow(10,Math.floor(Math.log10(span/5)));
  const nice=(x,up)=>+((up?Math.ceil(x/st):Math.floor(x/st))*st).toPrecision(6);
  // 向外逐点扩展：大间隔处断轴（≤3 处），额外可见范围累计 > 1×主体范围后截顶（以三角标记显示，悬停看原值）
  const side=(vs,dir)=>{let prev=dir>0?hi:lo,extra=0,nb=0;for(const v of vs){const g=Math.abs(v-prev);
      if(g>span*.35){if(nb>=3)return prev;const s0=dir>0?nice(prev+pad,1):nice(v+pad,1),e0=dir>0?nice(v-pad,0):nice(prev-pad,0);if(e0-s0>span*.2){R.breaks.push({start:s0,end:e0,gap:'4%'});nb++}else extra+=g}
      else extra+=g;if(extra>span)return dir>0?Math.max(prev,hi):Math.min(prev,lo);prev=v}return null};
  const up=a.concat(refs.filter(r=>r!=null&&isFinite(r)&&r>hi)).filter(v=>v>hi).sort((x,y)=>x-y);const dn=a.filter(v=>v<lo).sort((x,y)=>y-x);
  const ch=side(up,1);if(ch!=null)R.hi=nice(ch+pad,1);const cl=side(dn,-1);if(cl!=null)R.lo=nice(cl-pad,0);
  R.breaks=R.breaks.filter(b=>(R.hi==null||b.end<R.hi)&&(R.lo==null||b.start>R.lo));
  R.nClip=a.filter(v=>(R.hi!=null&&v>R.hi)||(R.lo!=null&&v<R.lo)).length;R.on=R.breaks.length>0||R.nClip>0;return R};
K.ycl=(R,v)=>v==null||!R?v:R.hi!=null&&v>R.hi?R.hi:R.lo!=null&&v<R.lo?R.lo:v;
K.ysym=(R,v)=>!R||v==null?{}:R.hi!=null&&v>R.hi?{symbol:'triangle',symbolSize:9}:R.lo!=null&&v<R.lo?{symbol:'triangle',symbolRotate:180,symbolSize:9}:{};
K.ybOpt=R=>{if(!R)return {};const br=R.breaks||[],o={};if(R.hi!=null)o.max=R.hi;if(R.lo!=null)o.min=R.lo;if(!br.length)return o;
  const keep=new Set([Math.min(...br.map(b=>b.start)),Math.max(...br.map(b=>b.end))]);
  return {...o,breaks:br,breakLabelLayout:{moveOverlap:'auto'},breakArea:{show:true,itemStyle:{color:'#fff',borderColor:'#C9CCD1',borderWidth:1,borderType:[3,3],opacity:1},zigzagAmplitude:3,expandOnClick:true},axisLabel:{color:'#64676B',formatter:(v,i,ex)=>ex&&ex.break&&!keep.has(v)?'':K.fmt(v)}}};

/* Extension hooks: a host system (e.g. the kz workbench) may ship extra layers alongside a built report —
 * a system layer `data/sys.js` (window.KZS) and optional assets. Everything is DECLARED AT BUILD TIME via
 * study.json `cfg.ext = {sys:"data/sys.js", js:["assets/ext/…"], css:["assets/ext/…"]}`; nothing is probed
 * at runtime (fetch/HEAD does not work on file:// and missing-resource loads log console errors), so a
 * standalone skill build without cfg.ext behaves exactly as before. See references/ext-hooks.md. */
(function(){
  const ex = ((window.KZ || {}).cfg || {}).ext;
  if (!ex) return;
  const head = document.head;
  (ex.css || []).forEach(h => { const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; head.appendChild(l); });
  [].concat(ex.sys || [], ex.js || []).forEach(s => { const t = document.createElement('script'); t.src = s; t.async = false; head.appendChild(t); });
})();
