K.init(()=>{
const CF=K.cfg(),SD=CF.study||{},QC=CF.query||{};const D=KZ,app=document.getElementById('app'),S=K.subs(),m=D.meta;
const dosed=S.filter(s=>s.fd);const ae=dosed.reduce((a,s)=>a+s.nae,0);
const allAE=[];/* from subs only counts; AE detail per category built from labrows? use counts in core subs */
const st=m.status;
const lab=K.lab,oth=D.others;
const rc=k=>lab.filter(g=>g.risk===k).length;
const aesiSubs=S.filter(s=>s.aesi>0).length;
/* mm4：方案偏离（KZ.pd）——入排/用药/访视类专项信号归入方案偏离，医学风险分层只保留医学判断类 */
const PD=D.pd,POT=(PD||{}).potential||[],CONF=(PD||{}).confirmed||[],pdImp=POT.filter(x=>x.grade==='重要').length,pdMiss=POT.filter(x=>x.status==='未见记录').length;
const pdCats=new Set(PD?oth.filter(o=>o.pd&&o.pd!=='SAFE-03'&&o.pd!=='SAFE-02').map(o=>o.cat):[]);
const kpiPD=PD?`<a class="kpi risk" href="deviations.html" style="text-decoration:none;color:inherit"><div class="l">方案偏离（潜在 / 已记录）</div><div class="v">${POT.length}<small>/ ${CONF.length} 条</small></div><div class="s">${K.p('重要 '+pdImp,'solid-red')}${K.p('未见记录 '+pdMiss,'org')}${K.p('已记录 '+CONF.length,'grn')}</div></a>`
 :`<div class="kpi"><div class="l">专项核查信号</div><div class="v">${oth.length}<small>条</small></div><div class="s">${K.p('优先核实 '+oth.filter(o=>o.pr===4).length,'red')}${K.p('需核实 '+oth.filter(o=>o.pr===3).length,'org')}</div></div>`;
/* mm5 首屏「先看这里」：最需要处理的几件事（大数字＋一句含义＋直达）；用户 2026-10-31：打开后不清楚看哪里、哪些数字是重点 */
const CR=K.centerRisk(),hotC=CR.centers.map(c=>[c,CR.hot(c.site)]).filter(x=>x[1].length>=2).sort((a,b)=>b[1].length-a[1].length);
const RD=K.RD(),rdn=RD?Object.values(RD.counts||{}).reduce((a,x)=>a+(x.new||0)+(x.worse||0),0):0;
const focus=[
  [rc('CSX'),'CS 未关联 AE/病史','判 CS 却没有关联 AE 或病史：漏记 AE 风险最高','safety.html#tab=lab&risk=CSX','solid-red'],
  [rc('MH')+rc('DISW'),'CS 较基线加重','只关联病史或归因研究疾病，但较基线明显加重','safety.html#tab=lab&risk=MH','org'],
  ...(PD?[[pdImp,'重要潜在方案偏离','可能影响受试者安全或关键数据，待 CRA 核实','deviations.html','red']]:[]),
  [hotC.length,'需关注中心','≥2 类风险高于按入组人数推算的期望','safety.html#tab=ov','org'],
  ...(RD?[[rdn,'本次新增/加重','与上次上传相比新出现或加重的风险项','safety.html#tab=lab','red']]:[]),
  [((D.ops||{}).entry||[]).length,'疑似录入错误','小数点/单位疑似录错，先核对源数据','monitor.html#tab=ent','yel'],
  [D.queries.length,'待发医学质疑',`其中与 CRO 意见冲突 ${D.queries.filter(q=>q.cro==='冲突澄清').length} 条`,'queries.html','grn']].slice(0,6);
const guide=[['安全性概况','全试验/中心/受试者的 AE、病史、用药、检验与有效性概况','profile.html'],['AE/MH风险','中心总览热力图、检验异常与 AE/病史关联','safety.html'],['方案偏离','已记录与潜在方案偏离','deviations.html'],
  ['临床监察','入组进度、访视执行、给药依从、数据质量','monitor.html'],['医学质疑','可直接发给中心的质疑','queries.html'],['参与者资料','单个受试者的全部数据与概况','subjects.html']];
app.innerHTML=`
<div class="card mb" style="padding:12px 14px"><div class="hd" style="margin-bottom:8px"><h2>先看这里</h2><span class="sub">点击直达明细；条目点开可看该受试者该指标的全程数据</span></div>
 <div class="grid" style="grid-template-columns:repeat(${focus.length},1fr);gap:10px">${focus.map(([n,l,s,h,c])=>`<a class="box" href="${h}" style="text-decoration:none;color:inherit;display:block"><div class="flex"><span class="p ${n?c:'line'}">${l}</span></div><div style="font-size:26px;font-weight:700;color:var(--ink);margin:4px 0 2px">${n}</div><div class="xs muted" style="line-height:1.5">${s}</div></a>`).join('')}</div>
 <div class="flex wrap mt xs muted" style="gap:14px">${guide.map(([n,s,h])=>`<a href="${h}" title="${K.esc(s)}"><b style="color:var(--ink)">${n}</b> <span class="faint">${s}</span></a>`).join('')}</div></div>
<div class="kpis">
 <div class="kpi"><div class="l">筛选 / 随机并给药</div><div class="v">${m.n}<small>/ ${m.dosed} 例</small></div><div class="s">${Object.entries(st).map(([k,v])=>K.p(k+' '+v,K.STC[k]??'')).join('')}</div></div>
 <div class="kpi blu"><div class="l">中心（有给药 / 全部）</div><div class="v">${D.centers.filter(c=>c.dosed).length}<small>/ ${D.centers.length}</small></div><div class="s">${(SD.tags||[]).map(t=>Array.isArray(t)?K.p(K.esc(t[0]),t[1]||'line'):K.p(K.esc(t),'line')).join('')}</div></div>
 <div class="kpi"><div class="l">不良事件（给药者）</div><div class="v">${ae}<small>例次 · ${dosed.filter(s=>s.nae).length} 例</small></div><div class="s">${K.p('SAE '+S.reduce((a,s)=>a+s.sae,0),'grn')}${K.p('AESI '+S.reduce((a,s)=>a+s.aesi,0)+' 例次/'+aesiSubs+' 例','red')}${K.p('≥2级 '+S.filter(s=>s.maxg>=2).length+' 例','org')}</div></div>
 <div class="kpi risk"><div class="l">检验异常 → 需核对 AE/病史</div><div class="v">${['CSX','DISW','MH','MHU','NCS2','NA2','G2NF','NA'].reduce((a,k)=>a+rc(k),0)}<small>受试者×指标</small></div><div class="s">${['CSX','DISW','MH','MHU','NCS2','NA2','G2NF','NA'].filter(k=>rc(k)).map(k=>`<a href="safety.html#tab=lab&risk=${k}">${K.p(K.RISK[k][0]+' '+rc(k),K.RISK[k][1])}</a>`).join('')}${lab.some(g=>g.risk==='REL')?`<a href="safety.html#tab=lab&risk=REL" id="kz-rel-kpi">${K.p('较基线显著变化·未关联 '+lab.filter(g=>g.risk==='REL'&&K.relRisk(g)).length+'（已关联 '+lab.filter(g=>g.risk==='REL'&&K.relOn(g)&&!K.relRisk(g)).length+'）',K.RISK.REL[1])}</a>`:''}${lab.some(g=>g.risk==='MHX-T')?` <a href="safety.html#tab=lab&risk=MHX-T" id="kz-mhxt-kpi">${K.p('疑似病史漏记·首剂前 '+lab.filter(g=>g.risk==='MHX-T').length,K.RISK['MHX-T'][1])}</a>`:''}</div></div>
 ${kpiPD}
 <div class="kpi grn"><div class="l">申办方医学质疑${QC.label?'（'+K.esc(QC.label)+'）':''}</div><div class="v">${D.queries.length}<small>条</small></div><div class="s">${D.cro.length?K.p((QC.extShort||'外部质疑')+' '+D.cro.length+' 条已查重','line'):''}${K.p('冲突澄清 '+D.queries.filter(q=>q.cro==='冲突澄清').length,'red')}</div></div>
</div>
<div class="grid g12 mt">
 <div class="card"><div class="hd"><h2>医学风险分层</h2><span class="sub">点击进入明细${pdCats.size?' · 入排/用药/访视类信号见方案偏离':''}</span><span class="sp"></span><span class="legend"><span><i class="dot red"></i> 优先核实</span><span><i class="dot org"></i> 需核实</span><span><i class="dot yel"></i> 结合临床/提示</span><span>${K.p('Q','org sq')} 已发质疑</span></span></div><div id="dom"></div></div>
 ${PD?`<div class="card"><div class="hd"><h2>方案偏离</h2><span class="sub">潜在 PD 按分级堆叠 · 右侧为已记录数</span><span class="sp"></span><span class="legend"><span><i class="dot red"></i> 重要</span><span><i class="dot yel"></i> 待判定</span><span><i class="dot"></i> 一般</span></span><a class="small" href="deviations.html" style="margin-left:8px">进入 ›</a></div><div id="pdo"></div></div>`:''}
</div>
<div class="grid g12 mt">
 <div class="card"><div class="hd"><h2>AE 谱 × IB / 类效应</h2><span class="sub">${(CF.blind||{}).on?'盲态合并 · ':''}给药后 · 点击条形进入明细</span></div><div id="aech" class="chart" style="height:300px"></div></div>
 <div class="card"><div class="hd"><h2>AESI 记录</h2><span class="sub">研究者标记为 AESI 的不良事件</span><span class="sp"></span><a class="small" href="safety.html#tab=ae&aesi=1">全部 ›</a></div><div id="aesi"></div></div>
</div>
<div class="grid g21 mt">
 <div class="card"><div class="hd"><h2>需关注中心</h2><span class="sub">风险高于按本中心给药人数推算的期望（超出随机波动）的类别</span><span class="sp"></span><a class="small" href="safety.html#tab=ov">中心总览热力图 ›</a></div><div id="ctr"></div></div>
 <div class="card"><div class="hd"><h2>入组进度</h2><span class="sub">首次给药累计</span></div><div id="enr" class="chart sm"></div>
  <div class="hd mt"><h2>主要待办</h2></div><div id="todo"></div></div>
</div>
<details class="fold" id="mfold"><summary>审阅要点与方法学（关注字段 · 判读路径 · 异常界定 · 实例 · 规则${PD?'，含方案偏离审阅要点':''}）</summary><div class="fold-b" id="mbody"></div></details>`;
/* domains */
const qset=new Set(D.queries.map(q=>q.cat));
const rows=K.DOM.map(([name,cats,c])=>{const items=cats.filter(cat=>!pdCats.has(cat)).map(cat=>{const o=oth.filter(x=>x.cat===cat);return {cat,n:o.length,p4:o.filter(x=>x.pr===4).length,p3:o.filter(x=>x.pr===3).length,q:D.queries.filter(q=>q.cat===cat).length}}).filter(x=>x.n);return {name,c,items}}).filter(r=>r.items.length);
rows.splice(1,0,{name:'检验异常 → AE/MH',c:'org',lab:true});
const maxN=Math.max(...oth.reduce((a,o)=>{a[o.cat]=(a[o.cat]||0)+1;return a},{}).constructor===Object?Object.values(oth.reduce((a,o)=>{a[o.cat]=(a[o.cat]||0)+1;return a},{})):[1]);
const bar=(n,max,col)=>`<div class="bar-in" style="flex:1"><i style="width:${Math.max(3,n/max*100)}%;background:${col}"></i></div>`;
const blk=r=>{if(r.lab)return `<div class="dblk"><div class="dh">${K.p(r.name,'org')}<span class="xs muted">${lab.length} 行 / ${lab.reduce((a,g)=>a+g.pts.length,0)} 点</span></div>${['CSX','DISW','MH','MHU','NCS2','NA2','G2NF','NA','CSI','DIS','AE','MHL','NCS'].filter(k=>rc(k)).map(k=>`<a class="drow" href="safety.html#tab=lab&risk=${k}"><span class="dn">${K.risk(k)}</span>${bar(rc(k),lab.length,k==='CSX'?'#8B0000':k==='MH'?'#FF9900':k==='NCS2'?'#E8C300':k==='AE'?'#587B3B':'#C9CCD1')}<b>${rc(k)}</b><span class="dq">${(()=>{const n=lab.filter(g=>g.risk===k&&g.q.length).length;return n?K.p('Q'+n,'org sq'):''})()}</span></a>`).join('')}</div>`;
 return `<div class="dblk"><div class="dh">${K.p(r.name,r.c)}<span class="xs muted">${r.items.reduce((a,i)=>a+i.n,0)} 条</span></div>${r.items.map(it=>`<a class="drow" href="safety.html#tab=oth&cat=${encodeURIComponent(it.cat)}"><span class="dn">${it.cat}</span>${bar(it.n,maxN,it.p4?'#8B0000':it.p3?'#FF9900':'#E8C300')}<b>${it.n}</b><span class="dq">${it.q?K.p('Q'+it.q,'org sq'):''}</span></a>`).join('')}</div>`};
document.getElementById('dom').innerHTML=`<div class="dgrid">${rows.map(blk).join('')}</div>`;
const aesiL=D.aes.filter(a=>a.aesi);
K.table(document.getElementById('aesi'),{rows:aesiL,sort:'s',dir:1,h:'260px',cols:[{k:'sid',t:'受试者',f:r=>K.sid(r.sid)},{k:'t',t:'AE术语',f:r=>K.esc(r.t)},{k:'s',t:'开始',f:r=>`<span class="nowrap">${r.s}</span> <span class="xs faint">${K.studyDay(r.s,r.fd)}</span>`},{k:'g',t:'等级',f:r=>K.p(r.g,r.g>='2'?'red':'yel')},{k:'rel',t:'相关性',f:r=>K.p(r.rel,/有关/.test(r.rel)&&!/无关/.test(r.rel)?'org':'')},{k:'out',t:'转归',f:r=>K.p(r.out.split('/')[0],'line')}]});
/* 方案偏离概览（执行 / 科学两层，按类别） */
if(PD){const TX=K.pdTax(),G=[['重要','#8B0000'],['待判定','#E8C300'],['一般','#C9CCD1']];const mx=Math.max(1,...Object.values(POT.reduce((a,x)=>{a[x.cat]=(a[x.cat]||0)+1;return a},{})));
 const blkP=lay=>{const cs=(PD.taxonomy||[]).filter(t=>t[2]===lay).map(t=>t[0]).filter(c=>POT.some(x=>x.cat===c)||CONF.some(x=>x.cat===c));const n=POT.filter(x=>(TX[x.cat]||[])[2]===lay).length;
  return `<div class="dblk"><div class="dh">${K.p(lay+'层面',lay==='执行'?'blu':'org')}<span class="xs muted">潜在 ${n} 条</span></div>${cs.map(c=>{const ps=POT.filter(x=>x.cat===c),cf=CONF.filter(x=>x.cat===c).length;
   return `<a class="drow" href="deviations.html#tab=${lay==='执行'?'exe':'sci'}&cat=${c}"><span class="dn">${K.esc((TX[c]||[])[1]||c)}</span><div class="bar-in" style="flex:1;display:flex">${G.map(([g,col])=>{const k=ps.filter(x=>x.grade===g).length;return k?`<i style="width:${k/mx*100}%;background:${col}"></i>`:''}).join('')}</div><b>${ps.length}</b><span class="dq">${cf?K.p(cf,'grn sq'):''}</span></a>`}).join('')||'<div class="xs faint" style="padding:4px">无</div>'}</div>`};
 document.getElementById('pdo').innerHTML=`<div class="dgrid">${blkP('执行')}${blkP('科学')}</div><div class="flex wrap mt xs muted" style="gap:10px"><span>已记录 PD <b style="color:var(--ink)">${CONF.length}</b></span><span>潜在未见记录 <b style="color:var(--brand-d)">${pdMiss}</b></span><span>涉及受试者 <b style="color:var(--ink)">${new Set(POT.map(x=>x.sid)).size}</b></span>${PD.hasListing?'':'<span>未提供方案偏离记录表</span>'}<span class="sp"></span><a href="deviations.html#tab=rules">已执行检查 ${(PD.rules||[]).filter(r=>r.state==='ran').length}/${(PD.rules||[]).length} 项 ›</a></div>
 ${(()=>{const top=POT.filter(x=>x.grade==='重要').slice(0,6);return top.length?`<div class="hd mt" style="margin-bottom:4px"><h3>重要潜在 PD</h3><span class="xs muted">待核实，前 ${top.length} 条</span></div><table class="t"><tbody>${top.map(x=>`<tr class="click" data-pd="${x.id}"><td style="width:62px">${K.sid(x.sid)}</td><td style="width:92px">${K.pdCat(x.cat)}</td><td class="small">${K.esc(x.title)}<span class="xs faint"> · ${K.esc(x.date||x.visit||'')}</span></td><td style="width:70px">${K.pdStatus(x.status)}</td></tr>`).join('')}</tbody></table>`:''})()}`}
/* AE chart: need AE categories -> from per-subject not in core; compute from labrows? use D.aesum */
const cats=Object.assign({},D.aesum);let order=Object.keys(cats).sort((a,b)=>cats[a].n-cats[b].n);
if(order.length>12){/* mm4：类别过多（未编码原文术语）时只画前 12 类，其余合并为「其他」 */const rest=order.slice(0,order.length-12);
 cats['其他（'+rest.length+' 类）']=rest.reduce((a,k)=>({n:a.n+cats[k].n,s:a.s+cats[k].s,g2:a.g2+cats[k].g2,rel:a.rel+cats[k].rel,aesi:a.aesi+cats[k].aesi,terms:a.terms.concat(cats[k].terms)}),{n:0,s:0,g2:0,rel:0,aesi:0,terms:[]});
 order=['其他（'+rest.length+' 类）'].concat(order.slice(-12))}
K.chart('#aech',{grid:{left:120,right:120,top:6,bottom:20},tooltip:{trigger:'axis',axisPointer:{type:'shadow'},formatter:p=>{const c=cats[p[0].name];return `<b>${p[0].name}</b><br>${c.n} 例次 / ${c.s} 例<br>≥2级 ${c.g2} · 相关 ${c.rel} · AESI ${c.aesi}<br>${(D.ibtag[p[0].name]||[]).join(' · ')}<br><span style="color:#999">术语 ${c.terms.length} 种：${c.terms.slice(0,6).join('、')}</span>`}},
 xAxis:{type:'value',...K.axis},yAxis:{type:'category',data:order,...K.axis,axisLabel:{color:'#404040',fontSize:11}},
 series:[{type:'bar',stack:'a',name:'1级',data:order.map(k=>cats[k].n-cats[k].g2),itemStyle:{color:'#FFCC80'},barWidth:12},{type:'bar',stack:'a',name:'≥2级',data:order.map(k=>({value:cats[k].g2,itemStyle:{color:'#E67E00'}})),label:{show:true,position:'right',formatter:p=>{const c=cats[p.name];const t=(D.ibtag[p.name]||[])[0];return c.n+(t?'  '+t:'')},color:'#64676B',fontSize:10.5}}]}).on('click',p=>location.href='safety.html#tab=ae&c='+encodeURIComponent(p.name));
/* centers */
document.getElementById('ctr').innerHTML=hotC.length?`<table class="t"><thead><tr><th>中心</th><th class="num">给药</th><th>偏高的风险类别</th></tr></thead><tbody>${hotC.slice(0,8).map(([c,h])=>`<tr class="click" onclick="location.href='profile.html#c=${c.site}'"><td class="nowrap">${K.p(c.site,'sq mono')} ${K.esc(c.name.length>14?c.name.slice(0,14)+'…':c.name)}</td><td class="num">${c.dosed}</td><td>${h.map(x=>K.p(x,'org')).join('')}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">没有中心在 2 类及以上风险中明显偏高</div>';
/* enrollment */
const fds=dosed.map(s=>s.fd).sort();const pts=fds.map((d,i)=>[d,i+1]);
K.chart('#enr',{grid:{left:36,right:12,top:10,bottom:24},tooltip:{trigger:'axis'},xAxis:{type:'time',...K.axis},yAxis:{type:'value',...K.axis,max:SD.planned?Math.ceil(SD.planned*1.08):null},series:[{type:'line',step:'end',data:pts,symbol:'none',lineStyle:{color:'#FF9900',width:2},areaStyle:{color:'rgba(255,153,0,.12)'},markLine:SD.planned?{symbol:'none',data:[{yAxis:SD.planned,label:{formatter:'计划'+SD.planned,color:'#64676B'},lineStyle:{color:'#C9CCD1',type:'dashed'}}]}:undefined}]});
/* todo: KZ.todo=[[tag,cls,text,href]] from engine; fallback generic */
const todo=(D.todo&&D.todo.length?D.todo:[
 ['CS·未关联','solid-red',`${rc('CSX')} 行判CS但未关联AE/MH`,'safety.html#tab=lab&risk=CSX'],
 ['AESI','red',`${S.reduce((a,s)=>a+s.aesi,0)} 例次 AESI`,'safety.html#tab=ae&aesi=1'],
 ['优先核实','org',`${oth.filter(o=>o.pr===4).length} 条专项信号优先核实`,'safety.html#tab=oth'],
 ['一致性','grn',`同中心判定对照 ${D.cons.length} 组：需核实 ${D.cons.filter(c=>c.st==='需核实').length}`,'safety.html#tab=cons'],
 ['质疑','org',`${D.queries.length} 条医学质疑已写入交付表格`,'queries.html']]).map(t=>[K.p(t[0],t[1]),t[2],t[3]]);
document.getElementById('todo').innerHTML=`<table class="t"><tbody>${todo.map(t=>`<tr class="click" onclick="location.href='${t[2]}'"><td style="width:90px">${t[0]}</td><td>${t[1]}</td><td class="faint">›</td></tr>`).join('')}</tbody></table>`;
/* 审阅要点：折叠区首次展开时渲染（与 methods.html 同一渲染器） */
const mf=document.getElementById('mfold');if(mf)mf.addEventListener('toggle',()=>{if(mf.open&&!mf.dataset.done&&K.renderMethods){mf.dataset.done=1;K.renderMethods(document.getElementById('mbody'),{embed:true})}});
{const go=['monitor.html','safety.html#tab=ov','profile.html',null,null,'queries.html'];app.querySelectorAll('.kpis>.kpi').forEach((k,i)=>{if(go[i]&&k.tagName!=='A'){k.classList.add('click');k.title='点击查看明细';k.onclick=e=>{if(!e.target.closest('a'))location.href=go[i]}}});
 const kp=app.querySelector('.kpis'),dc=K.deltaCard(),kn=K.knBar(D.knowledge);if(dc&&kp)kp.insertAdjacentHTML('afterend',dc);if(kn&&kp)kp.insertAdjacentHTML('beforebegin',kn)/* mm4：知识层降级 → 顶部警示条 */}
});
