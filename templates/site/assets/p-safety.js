K.init(()=>{
const D=KZ,app=document.getElementById('app'),H=K.hash();
const lab=D.labrows,oth=D.others,aes=D.aes;
app.innerHTML=`<div class="flex mb"><h1 style="font-size:18px">AE / MH 漏报风险</h1><span class="muted small">检验异常与AE/MH关联 · 方案阈值专项 · AE记录 · 同中心判定一致性</span><span class="sp"></span>${(K.cfg().blind||{}).on?K.p((K.cfg().blind||{}).tag||'盲态合并，不分组','blu'):''}</div>
<div class="tabs" id="tabs"></div><div id="pane"></div>`;
const pane=document.getElementById('pane');
const tabs=[['lab','检验异常 → AE/MH',lab.length],['oth','专项核查',oth.length],['ae','AE 记录',aes.length],['cons','同中心判定一致性',D.cons.length],['ctr','中心对比',D.centers.filter(c=>c.dosed).length]];
const R={lab:tabLab,oth:tabOth,ae:tabAE,cons:tabCons,ctr:tabCtr};
const sel=(id,opts,v)=>`<select class="s" id="${id}">${opts.map(([a,b])=>`<option value="${K.esc(a)}" ${a===v?'selected':''}>${b}</option>`).join('')}</select>`;
const centerOpts=[['','全部中心'],...D.centers.filter(c=>c.dosed).map(c=>[c.site,c.site+' '+c.name])];
K.tabs(document.getElementById('tabs'),tabs,H.tab||'lab',v=>{K.setHash({...(v===(H.tab||'lab')?H:{}),tab:v});R[v]()});
/* ---------- lab */
function tabLab(){
  const st={risk:H.risk||null,cat:'',grp:'',site:H.c||'',q:''};
  pane.innerHTML=`<div class="grid g4 mb">${['CSX','MH','NCS2','NA2','AE','REL'].filter(k=>k!=='NA2'||lab.some(g=>g.risk==='NA2')).filter(k=>k!=='REL'||lab.some(g=>g.risk==='REL')).map(k=>`<div class="box ${k==='CSX'?'red':k==='MH'?'org':''}" ${k==='REL'?'id="kz-rel-box"':''}><div class="flex">${K.risk(k)}<span class="sp"></span><b style="font-size:18px;color:var(--ink)" ${k==='REL'?'id="kz-rel-n"':''}>${k==='REL'?lab.filter(g=>g.risk==='REL'&&K.relOn(g)).length:lab.filter(g=>g.risk===k).length}</b>${k==='REL'?`<small class="muted">/${lab.filter(g=>g.risk==='REL').length}</small>`:''}</div><div class="xs muted mt" style="margin-top:3px">${K.RISK[k][2]}</div></div>`).join('')}</div>
  <div class="card"><div class="tbar"><div class="chips" id="rk"></div><span class="sp"></span>${sel('cat',[['','全部来源'],['治疗后新发/加重检验异常','治疗后新发/加重（'+(K.cfg().ctcaeVersion||'分级')+'/参考范围）'],['较基线显著变化且超出参考范围','较基线显著变化（双阈值 REL）']],'')}${sel('site',centerOpts,st.site)}<input class="s" id="q" placeholder="受试者 / 指标"></div>
  <div class="tbar"><div class="chips" id="grp"></div></div><div id="tb"></div>
  <div class="legend mt"><span class="vchip cs">CS</span>异常有临床意义 <span class="vchip ncs">NCS</span>异常无临床意义 <span class="vchip n">值</span>正常/未评价 · 基线：按方案基线定义（${K.esc(((K.cfg().baseline||{}).labLabel)||'见检验检查趋势页各指标')}），缺失时按规则回退 · G=${K.esc(K.cfg().ctcaeVersion||'方案分级标准')} 数值分级（仅数值条目）</div></div>`;
  const groups=[...new Set(lab.map(g=>g.grp))];
  const rk=K.chips(document.getElementById('rk'),Object.keys(K.RISK).map(k=>[k,K.RISK[k][0],k==='REL'?lab.filter(g=>g.risk==='REL'&&K.relOn(g)).length:lab.filter(g=>g.risk===k).length]).filter(x=>x[2]||!lab.some(g=>g.risk===x[0])),v=>{st.risk=v;draw()},{value:st.risk});
  K.onThr(()=>{rk.set(st.risk);draw();const b=document.getElementById('kz-rel-n');if(b)b.textContent=lab.filter(g=>g.risk==='REL'&&K.relOn(g)).length});
  K.chips(document.getElementById('grp'),groups.map(g=>[g,g,lab.filter(x=>x.grp===g).length]),v=>{st.grp=v||'';draw()},{all:'全部分组'});
  document.getElementById('cat').onchange=e=>{st.cat=e.target.value;draw()};document.getElementById('site').onchange=e=>{st.site=e.target.value;draw()};document.getElementById('q').oninput=e=>{st.q=e.target.value.trim();draw()};
  const order={CSX:0,MH:1,NCS2:2,AE:3,NCS:4,REL:5};
  const tb=K.table(document.getElementById('tb'),{rows:[],h:'640px',pageSize:80,cols:[
    {k:'risk',t:'风险',s:r=>-order[r.risk],f:r=>K.risk(r.risk)},
    {k:'sid',t:'受试者',f:r=>K.sid(r.sid)+` <span class="xs faint">${r.site}</span>`},
    {k:'test',t:'指标',f:r=>{if(r.risk!=='REL')return `<b style="color:var(--ink)">${K.esc(r.test)}</b>`;const t=K.thrOf(r.mid||('lab:'+r.test));return `<b style="color:var(--ink)">${K.esc(r.test)}</b> ${K.p('偏离≥'+Math.round(t.dev*100)+'% Δ≥'+Math.round(t.base*100)+'%','line sq','双阈值 T_dev/T_base'+(t.ov?'（per_metric 覆盖）':'')+(t.tight?'（项目收紧后有效值）':''))}`}},
    {k:'base',t:'基线',ns:1,f:r=>r.base?`<span class="vchip ${r.base[3]===2?'cs':r.base[3]===1?'ncs':'n'}"><i>${r.base[0]}</i>${K.esc(r.base[1]??'—')}</span>`:'—'},
    {k:'pts',t:'给药后异常点',ns:1,f:r=>r.pts.map(p=>`<span class="vchip ${p[5]===2?'cs':p[5]===1?'ncs':'n'}" title="${K.esc(p[1]+' · '+p[7]+' 行'+p[8]+(p[6]!=null?' · Δ'+K.pct(p[6]):'')+(p[10]!=null?' · 偏离'+Math.round(p[10]*100)+'%':'')+(p[9]?' · '+p[9]:''))}"><i>${p[0]}</i>${K.esc(p[2])}${p[4]!=null?`<i>G${p[4]}</i>`:''}${p[10]!=null?`<i>${Math.round(p[10]*100)}%</i>`:''}</span>`).join('')},
    {k:'mg',t:'最高',s:r=>r.mg??-1,f:r=>K.grade(r.mg)},
    {k:'rel',t:'已关联',ns:1,f:r=>r.rel.map(x=>K.p((x[0]==='AE'?'AE ':'MH ')+K.esc(x[1]),x[0]==='AE'?'grn':'org')).join(' ')},
    {k:'ctx',t:'背景',ns:1,f:r=>K.ctxTags(r.ctx)+(r.cro?K.p(((K.cfg().query||{}).extShort||'外部')+'已覆盖','line'):'')},
    {k:'q',t:'质疑',s:r=>r.q.length,f:r=>r.q.map(K.qPill).join('')}],onRow:showLab,sort:'risk',dir:-1});
  /* REL 候选：满足当前所选阈值才进默认风险列表（计入 KPI/box）；未满足候选不隐藏——box 显示 n/候选 m，
     逐点偏离%/Δ% 在满足行与检验检查趋势页明细可见（03 §5「显示」行） */
  function draw(){const q=st.q.toLowerCase();tb.set(lab.filter(g=>((g.risk==='REL'&&!K.relOn(g))?false:(!st.risk||g.risk===st.risk))&&(!st.cat||g.cat===st.cat)&&(!st.grp||g.grp===st.grp)&&(!st.site||g.site===st.site)&&(!q||g.sid.includes(q)||g.test.toLowerCase().includes(q))))}
  draw();
}
async function showLab(g){
  const b=K.drawer(`${g.sid} · ${K.esc(g.test)}`,`<div class="flex wrap mb">${K.risk(g.risk)}${K.grade(g.mg)}${K.p(g.grp,'line')}${K.p(g.cat,'line')}${K.ctxTags(g.ctx)}<span class="sp"></span><a href="subjects.html#s=${g.sid}&t=lab">参与者资料 ›</a> <a href="timeline.html#s=${g.sid}">时间线 ›</a></div><div id="lc" class="chart"></div><div id="lt"></div><div id="lr"></div>`);
  const s=await K.sub(g.sid);if(!s)return;const ser=s.labs[g.test]||[];
  const pts=ser.filter(r=>r[2]!=null);const lo=pts.find(r=>r[5]!=null)?.[5],hi=pts.find(r=>r[6]!=null)?.[6];
  K.chart(b.querySelector('#lc'),{grid:{left:44,right:16,top:20,bottom:28},tooltip:{trigger:'axis'},xAxis:{type:'time',...K.axis},yAxis:{type:'value',scale:true,...K.axis},
    series:[{type:'line',data:pts.map(r=>({value:[r[0],r[2]],itemStyle:{color:r[7]===2?'#8B0000':r[7]===1?'#E8C300':'#407AAA'},symbolSize:r[7]>0?9:6})),lineStyle:{color:'#9DB7D3'},
      markArea:lo!=null&&hi!=null?{silent:true,itemStyle:{color:'rgba(88,123,59,.07)'},data:[[{yAxis:lo},{yAxis:hi}]]}:undefined,
      markLine:{symbol:'none',silent:true,data:[s.fd?{xAxis:s.fd,label:{formatter:'D1',color:'#B86400'},lineStyle:{color:'#FF9900',type:'dashed'}}:null,s.ld?{xAxis:s.ld,label:{formatter:'末次给药',color:'#64676B'},lineStyle:{color:'#C9CCD1',type:'dashed'}}:null].filter(Boolean)}}]});
  b.querySelector('#lt').innerHTML=`<table class="t mt"><thead><tr><th>访视</th><th>日期</th><th>结果</th><th>参考范围</th><th>判定</th><th>说明/关联</th><th>来源</th></tr></thead><tbody>${ser.map(r=>`<tr><td>${K.p(r[1],'blu')}</td><td class="nowrap">${r[0]} <span class="xs faint">${K.studyDay(r[0],s.fd)}</span></td><td class="num"><b>${K.esc(r[3])}</b> <span class="xs muted">${K.esc(r[4])}</span></td><td class="nowrap">${K.rng(r[5],r[6])}</td><td>${K.clin(r[7])}</td><td class="small">${K.esc(r[8])}</td><td class="xs faint">${r[9]} ${r[10]}</td></tr>`).join('')}</tbody></table>`;
  const ae=s.ae.map(a=>`<tr><td>${K.p('AE','grn')}</td><td>${K.esc(a.t)}</td><td class="nowrap">${a.s}${a.e?' → '+a.e:' → 持续'}</td><td>${K.p(a.g,a.g>='2'?'red':'yel')}</td><td>${K.esc(a.rel)}</td></tr>`).join('');
  const mh=s.mh.map(a=>`<tr><td>${K.p('MH','org')}</td><td>${K.esc(a.t)}</td><td class="nowrap">${a.s}</td><td>${a.ong==='是'?K.p('持续','line'):''}</td><td></td></tr>`).join('');
  b.querySelector('#lr').innerHTML=`<div class="sec-t"><h2>本例 AE / MH</h2></div><table class="t"><tbody>${ae+mh||'<tr><td class="empty">无</td></tr>'}</tbody></table>`;
}
/* ---------- others */
function tabOth(){
  const cats=[...new Set(oth.map(o=>o.cat))];const st={cat:H.cat||null,dom:null,site:'',q:''};
  pane.innerHTML=`<div class="card"><div class="tbar"><div class="chips" id="dm"></div><span class="sp"></span>${sel('site',centerOpts,'')}<input class="s" id="q" placeholder="受试者 / 关键词"></div><div class="tbar"><div class="chips" id="ct"></div></div><div id="tb"></div></div>`;
  K.chips(document.getElementById('dm'),K.DOM.map(d=>[d[0],d[0],oth.filter(o=>d[1].includes(o.cat)).length]).filter(x=>x[2]),v=>{st.dom=v;st.cat=null;cc();draw()},{all:'全部领域'});
  let ctc;function cc(){const list=cats.filter(c=>!st.dom||K.domOf(c)===st.dom);ctc=K.chips(document.getElementById('ct'),list.map(c=>[c,c,oth.filter(o=>o.cat===c).length]),v=>{st.cat=v;draw()},{all:'全部类别',value:st.cat})}cc();
  document.getElementById('site').onchange=e=>{st.site=e.target.value;draw()};document.getElementById('q').oninput=e=>{st.q=e.target.value.trim();draw()};
  const ord=c=>{const i=K.DOM.findIndex(d=>d[1].includes(c));return i*100+(K.DOM[i]?.[1].indexOf(c)||0)};
  const tb=K.table(document.getElementById('tb'),{rows:[],h:'680px',pageSize:200,group:r=>r.cat,groupHead:(g)=>{const n=oth.filter(o=>o.cat===g);const d=K.DOM.find(d=>d[1].includes(g));return `${K.p(d?d[0]:'其他',d?d[2]:'')} ${g} <span class="muted small">${n.length} 条 · 质疑 ${D.queries.filter(q=>q.cat===g).length}</span>`},
    cols:[{k:'pr',t:'优先级',f:r=>K.pri(r.pr)},{k:'sid',t:'受试者',f:r=>K.sid(r.sid)},{k:'v',t:'访视',f:r=>`${K.p(r.v||'—','blu')} <span class="xs faint">${r.d||''}</span>`},
      {k:'sum',t:'信号',ns:1,f:r=>`<span>${K.hlNum(r.sum)}</span>`},{k:'rel',t:'已关联',ns:1,f:r=>r.rel.slice(0,3).map(x=>K.p(x[0]+' '+K.esc(x[1]),x[0]==='AE'?'grn':'org')).join(' ')},
      {k:'ctx',t:'背景',ns:1,f:r=>K.ctxTags(r.ctx)+(r.cro?K.p(((K.cfg().query||{}).extShort||'外部')+'已覆盖','line'):'')},{k:'q',t:'质疑',f:r=>r.q.map(K.qPill).join('')||(r.cro?'':'<span class="faint xs">未发</span>')}],
    onRow:r=>{if(r.q.length)K.showQ(r.q[0]);else K.drawer(`${r.sid} · ${r.cat}`,`<div class="box">${K.hlNum(r.sum)}</div><div class="mt">${(r.ctx||[]).map(c=>`<div class="note">· ${K.esc(c)}</div>`).join('')}</div><div class="mt">${K.p(r.sh+' 行'+r.row,'sq mono')} <a href="subjects.html#s=${r.sid}">参与者资料 ›</a></div>`)}});
  function draw(){const q=st.q;tb.set(oth.filter(o=>(!st.dom||K.domOf(o.cat)===st.dom)&&(!st.cat||o.cat===st.cat)&&(!st.site||o.site===st.site)&&(!q||o.sid.includes(q)||o.sum.includes(q))).sort((a,b)=>ord(a.cat)-ord(b.cat)||b.pr-a.pr||a.sid.localeCompare(b.sid)))}
  draw();
}
/* ---------- AE */
function tabAE(){
  const st={c:H.c||null,g:'',rel:'',aesi:H.aesi==='1',pre:false,site:''};
  const cats=D.aecat.filter(c=>aes.some(a=>a.c===c));
  /* synonyms */
  const syn=cats.map(c=>{const t={};aes.filter(a=>a.c===c).forEach(a=>t[a.t]=(t[a.t]||0)+1);return [c,Object.entries(t).sort((a,b)=>b[1]-a[1])]}).filter(x=>x[1].length>2&&x[0]!=='其他');
  pane.innerHTML=`<div class="grid g21 mb"><div class="card"><div class="hd"><h2>术语一致性</h2><span class="sub">同一临床概念使用的不同AE术语（跨受试者/中心），影响汇总与预期性判断</span></div>
   <table class="t"><tbody>${syn.map(([c,t])=>`<tr><td class="nowrap" style="width:140px"><b style="color:var(--ink)">${c}</b><div>${K.ibTags(c)}</div></td><td>${t.map(([n,k])=>`<span class="vchip n">${K.esc(n)}<i>×${k}</i></span>`).join('')}</td></tr>`).join('')}</tbody></table></div>
   <div class="card"><div class="hd"><h2>AE 结构</h2><span class="sub">给药后，${aes.filter(a=>!a.pre).length} 例次</span></div><div id="aep" class="chart" style="height:250px"></div></div></div>
   <div class="card"><div class="tbar"><div class="chips" id="cc"></div></div><div class="tbar">${sel('g',[['','全部等级'],['1级','1级'],['2级','2级'],['3级','3级']],'')}${sel('rel',[['','全部相关性'],['rel','相关（可能/很可能/肯定）'],['unrel','无关/可能无关']],'')}${sel('site',centerOpts,'')}<label class="chip"><input type="checkbox" id="aesi" ${st.aesi?'checked':''}> AESI</label><label class="chip"><input type="checkbox" id="pre"> 首剂前</label><span class="sp"></span><span class="note">首剂前仅收集研究流程相关AE（三类，非TEAE）</span></div><div id="tb"></div></div>`;
  const grp=['1级','2级','3级'].map(g=>aes.filter(a=>!a.pre&&a.g===g).length);const rel=x=>/可能有关|很可能有关|肯定有关/.test(x)&&!/无关/.test(x);
  K.chart('#aep',{tooltip:{},series:[{type:'pie',radius:['38%','62%'],center:['28%','50%'],label:{formatter:'{b}\n{c}',fontSize:11},data:[{name:'1级',value:grp[0],itemStyle:{color:'#FFCC80'}},{name:'2级',value:grp[1],itemStyle:{color:'#E67E00'}},{name:'3级',value:grp[2],itemStyle:{color:'#8B0000'}}]},
    {type:'pie',radius:['38%','62%'],center:['74%','50%'],label:{formatter:'{b}\n{c}',fontSize:11},data:[{name:'相关',value:aes.filter(a=>!a.pre&&rel(a.rel)).length,itemStyle:{color:'#407AAA'}},{name:'无关/可能无关',value:aes.filter(a=>!a.pre&&!rel(a.rel)).length,itemStyle:{color:'#C9D7E6'}}]}],
    title:[{text:'严重程度',left:'28%',top:'47%',textAlign:'center',textStyle:{fontSize:11,color:'#64676B',fontWeight:400}},{text:'相关性',left:'74%',top:'47%',textAlign:'center',textStyle:{fontSize:11,color:'#64676B',fontWeight:400}}]});
  K.chips(document.getElementById('cc'),cats.map(c=>[c,c,aes.filter(a=>a.c===c).length]),v=>{st.c=v;draw()},{all:'全部类别',value:st.c});
  ['g','rel','site'].forEach(k=>document.getElementById(k).onchange=e=>{st[k]=e.target.value;draw()});document.getElementById('aesi').onchange=e=>{st.aesi=e.target.checked;draw()};document.getElementById('pre').onchange=e=>{st.pre=e.target.checked;draw()};
  const tb=K.table(document.getElementById('tb'),{rows:[],h:'600px',pageSize:100,sort:'s',dir:1,cols:[
   {k:'sid',t:'受试者',f:r=>K.sid(r.sid)},{k:'t',t:'AE 术语',f:r=>`<b style="color:var(--ink)">${K.esc(r.t)}</b> ${K.p(r.c,'line')}`},{k:'ib',t:'IB/类效应',ns:1,f:r=>K.ibTags(r.c)},
   {k:'s',t:'开始 → 结束',f:r=>`<span class="nowrap">${r.s} <span class="xs faint">${K.studyDay(r.s,r.fd)}</span></span><br><span class="xs muted">${r.e||'持续'}</span>`},
   {k:'g',t:'等级',f:r=>K.p(r.g,r.g==='3级'?'solid-red':r.g==='2级'?'red':'yel')+((r.chg||[]).length?' '+K.p('变更→'+r.chg.join('→'),'line'):'')},
   {k:'rel',t:'相关性',f:r=>K.p(r.rel,rel(r.rel)?'blu':'')},
   {k:'flags',t:'标记',ns:1,f:r=>[r.pre?K.p('首剂前','brn'):'',r.aesi?K.p('AESI','solid-red'):'',r.sae?K.p('SAE','solid-red'):'',r.dili?K.p('DILI','red'):'',r.wd?K.p('退出治疗','red'):''].join('')},
   {k:'act',t:'措施',f:r=>`<span class="small">${K.esc(r.act)}</span>`},{k:'out',t:'转归',f:r=>K.p(r.out.split('/')[0],/痊愈|好转/.test(r.out)?'grn':'line')},{k:'cm',t:'合并用药',f:r=>r.cm==='是'?K.p('是','org'):'<span class="faint">否</span>'}]});
  function draw(){tb.set(aes.filter(a=>(!st.c||a.c===st.c)&&(!st.g||a.g===st.g)&&(!st.rel||(st.rel==='rel'?rel(a.rel):!rel(a.rel)))&&(!st.aesi||a.aesi)&&(!st.pre||a.pre)&&(!st.site||a.site===st.site)))}
  draw();
}
/* ---------- consistency */
function tabCons(){
  const C=D.cons;const st={st:null,t:null,site:''};const sc={'需核实':'red','已有问题覆盖':'line','保留提示':'yel','有解释':'grn'};
  pane.innerHTML=`<div class="card"><div class="hd"><h2>同中心判定一致性</h2><span class="sub">同中心 · 同指标/单位/参考范围 · 同异常方向与给药阶段 · 结果相同或相差≤5%，但 CS/NCS 或 AE 处理不同</span></div>
  <div class="tbar"><div class="chips" id="ss"></div><span class="sp"></span>${sel('site',[['','全部中心'],...[...new Set(C.map(c=>c.site))].sort().map(s=>[s,s+' '+K.center(s)])],'')}</div><div class="tbar"><div class="chips" id="tt"></div></div><div id="tb"></div></div>`;
  K.chips(document.getElementById('ss'),Object.keys(sc).map(k=>[k,k,C.filter(c=>c.st===k).length]),v=>{st.st=v;draw()});
  const tests=Object.entries(C.reduce((a,c)=>{a[c.test]=(a[c.test]||0)+1;return a},{})).sort((a,b)=>b[1]-a[1]);
  K.chips(document.getElementById('tt'),tests.map(([t,n])=>[t,t,n]),v=>{st.t=v;draw()},{all:'全部指标'});document.getElementById('site').onchange=e=>{st.site=e.target.value;draw()};
  const side=(x,sid)=>`${K.sid(sid)} ${K.p(x[0]||'—','blu')} <b>${K.esc(x[2]??'')}</b> <span class="xs muted">${K.esc(x[3]??'')}</span> ${x[4]==='异常有临床意义'?K.p('CS','red'):x[4]==='异常无临床意义'?K.p('NCS','yel'):K.p(x[4]||'—','line')}`;
  const tb=K.table(document.getElementById('tb'),{rows:[],h:'640px',pageSize:100,cols:[{k:'st',t:'状态',f:r=>K.p(r.st,sc[r.st])},{k:'site',t:'中心',f:r=>K.p(r.site,'sq mono')},{k:'test',t:'指标/事件',f:r=>`<b style="color:var(--ink)">${K.esc(r.test)}</b>`},
    {k:'a',t:'本例',ns:1,f:r=>side(r.av,r.a)},{k:'b',t:'同中心对照',ns:1,f:r=>side(r.bv,r.b)},{k:'why',t:'判读',ns:1,f:r=>`<div class="clamp2 small" style="max-width:460px">${K.esc(r.why)}</div>`}],
    onRow:r=>K.drawer(`${r.id} · ${K.esc(r.test)}`,`<div class="flex wrap mb">${K.p(r.st,sc[r.st])}${K.p(r.site+' '+K.center(r.site),'line')}</div><div class="grid g2"><div class="box"><div class="xs muted">本例</div>${side(r.av,r.a)}<div class="xs faint mt">${r.av[1]||''} · ${r.av[5]||''} · ${r.av[6]} 行${r.av[7]}</div></div><div class="box"><div class="xs muted">同中心对照</div>${side(r.bv,r.b)}<div class="xs faint mt">${r.bv[1]||''} · ${r.bv[5]||''} · ${r.bv[6]} 行${r.bv[7]}</div></div></div><div class="box org mt">${K.esc(r.diff)}</div><div class="mt" style="line-height:1.7">${K.esc(r.why)}</div>`)});
  function draw(){tb.set(C.filter(c=>(!st.st||c.st===st.st)&&(!st.t||c.test===st.t)&&(!st.site||c.site===st.site)).sort((a,b)=>Object.keys(sc).indexOf(a.st)-Object.keys(sc).indexOf(b.st)))}
  draw();
}
/* ---------- centers */
function tabCtr(){
  const C=D.centers.filter(c=>c.dosed);
  pane.innerHTML=`<div class="grid g2"><div class="card"><div class="hd"><h2>AE 报告密度 × 检验异常负荷</h2><span class="sub">气泡=给药例数；右下象限（异常多、AE少）优先关注漏报</span></div><div id="sc" class="chart lg"></div></div>
  <div class="card"><div class="hd"><h2>给药后检验异常的判定构成</h2><span class="sub">每中心「受试者×指标」行：CS未关联 / CS仅MH / 已关联AE / NCS</span></div><div id="st" class="chart lg"></div></div></div>
  <div class="note mt">判读：AE/例 低于全体中位数且 CS未关联或 CS仅MH 行偏多，提示该中心可能以病史或「复查」替代AE记录；NCS 占比显著高于全体时，结合同中心判定一致性页核对判定尺度。跨中心差异只作提示，不以多数中心的判定作为医学标准。</div>`;
  const med=K.median(C.map(c=>c.ae/c.dosed)),medL=K.median(C.map(c=>c.labrows/c.dosed));
  K.chart('#sc',{grid:{left:50,right:20,top:20,bottom:40},tooltip:{formatter:p=>{const c=p.data.c;return `<b>${c.site} ${c.name}</b><br>给药 ${c.dosed} · AE ${c.ae}（${(c.ae/c.dosed).toFixed(1)}/例）<br>异常行 ${c.labrows}（${(c.labrows/c.dosed).toFixed(1)}/例）<br>CS未关联 ${c.csx} · CS仅MH ${c.mhx}`}},
   xAxis:{name:'检验异常行 / 给药例',nameLocation:'middle',nameGap:26,...K.axis},yAxis:{name:'AE 例次 / 给药例',...K.axis},
   series:[{type:'scatter',data:C.map(c=>({value:[c.labrows/c.dosed,c.ae/c.dosed],c,symbolSize:8+Math.sqrt(c.dosed)*6,itemStyle:{color:c.csx?'#8B0000':c.mhx?'#FF9900':'#407AAA',opacity:.75}})),label:{show:true,formatter:p=>p.data.c.site,fontSize:10,color:'#404040'},
     markLine:{symbol:'none',silent:true,lineStyle:{color:'#C9CCD1',type:'dashed'},label:{color:'#9A9DA3',fontSize:10},data:[{xAxis:medL,label:{formatter:'中位'}},{yAxis:med,label:{formatter:'中位'}}]}}]}).on('click',p=>location.href='subjects.html#c='+p.data.c.site);
  const S2=C.slice().sort((a,b)=>(b.csx+b.mhx)-(a.csx+a.mhx)||b.labrows-a.labrows);
  const cnt=(site,r)=>lab.filter(g=>g.site===site&&g.risk===r).length;
  K.chart('#st',{grid:{left:40,right:16,top:28,bottom:40},legend:{top:0,itemWidth:10,itemHeight:10,textStyle:{fontSize:11}},tooltip:{trigger:'axis',axisPointer:{type:'shadow'}},xAxis:{type:'category',data:S2.map(c=>c.site),...K.axis,axisLabel:{fontSize:10,interval:0,rotate:60}},yAxis:{type:'value',...K.axis},
   series:[['CSX','CS未关联','#8B0000'],['MH','CS仅MH','#FF9900'],['NCS2','NCS≥2级','#E8C300'],['AE','已关联AE','#587B3B'],['NCS','NCS','#D5D8DD']].map(([k,n,c])=>({type:'bar',stack:'a',name:n,data:S2.map(x=>cnt(x.site,k)),itemStyle:{color:c},barWidth:10}))}).on('click',p=>{location.hash='tab=lab&c='+S2[p.dataIndex].site;location.reload()});
}
});
