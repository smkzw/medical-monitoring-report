/* mm5 临床监察页（用户 2026-10-31：把医学监察工作台升级为监察工作台，加入临床监察内容；单独成页，不混入风险页）。
 * 数据：KZ.ops（mm_build.build_ops：受试者里程碑、访视、方案访视窗、给药依从摘要、知情版本、疑似录入错误）＋ KZ.pd / queries / cro / others。
 * listing 中没有 EDC 录入/核查时间戳，录入及时性与 SDV 进度不在本页。 */
K.init(()=>{
const D=KZ,app=document.getElementById('app'),H=K.hash(),O=D.ops||{subs:[],vis:{},win:{},ex:{},icf:{},entry:[],fields:[]};
const F=O.fields||[],SU=(O.subs||[]).map(a=>Object.fromEntries(F.map((k,i)=>[k,a[i]])));
const cut=O.cutoff||(D.meta||{}).cutoff||'',daily=O.stage==='daily';
const CN=Object.fromEntries(D.centers.map(c=>[c.site,c.name]));
const sites=[...new Set(SU.map(s=>s.site))].sort();
const addD=(d,n)=>{const x=new Date(d+'T00:00:00Z');x.setUTCDate(x.getUTCDate()+n);return x.toISOString().slice(0,10)};
const dd=(a,b)=>K.days(a,b);
const med=a=>a.length?K.median(a):null;
const by=(arr,f)=>arr.reduce((m,x)=>{const k=f(x);(m[k]=m[k]||[]).push(x);return m},{});
const PDP=((D.pd||{}).potential)||[];
const end=s=>[s.eos_d,s.eot_d].filter(d=>d&&d.length>=10).sort()[0]||'';
/* ---------- 访视推算：方案访视窗（目标日/窗）× 首剂日 → 截至数据截止应完成的访视 ---------- */
const W=O.win||{},WV=Object.keys(W);
const spec=v=>{const s=W[v];return Array.isArray(s)?{t:s[0],mi:s[1]||0,pl:s[2]||0}:{t:s.target,mi:s.minus||0,pl:s.plus||0}};
const visRows=[];SU.filter(s=>s.fd).forEach(s=>{const rec=Object.fromEntries((O.vis[s.id]||[]).map(x=>[x[0],x[1]]));const e=end(s);
  WV.forEach(v=>{const p=spec(v);if(p.t==null)return;const due=addD(s.fd,p.t-1+p.pl),lo=addD(s.fd,p.t-1-p.mi);const got=rec[v];
    if(!got&&(due>=cut||(e&&lo>e)))return;            // 未到期，或受试者已结束于该访视窗之前 → 不应完成
    const sd=got&&got.length>=10?dd(got,s.fd)+1:null;
    visRows.push({sid:s.id,site:s.site,v,lo,due,got:got||'',st:!got?'overdue':(sd<p.t-p.mi||sd>p.t+p.pl)?'out':'ok',sd,t:p.t,mi:p.mi,pl:p.pl})})});
const tabs=[['enr','入组与进度',SU.length],['vis','访视执行',visRows.filter(r=>r.st!=='ok').length],['dose','给药与知情'],['dq','退出与数据质量'],['ent','疑似录入错误',(O.entry||[]).length]];
app.innerHTML=`<div class="flex mb"><h1 style="font-size:18px">临床监察</h1><span class="muted small">入组与进度 · 访视执行 · 给药与知情 · 退出与数据质量 · 疑似录入错误（数据截止 ${K.esc(cut)}${daily?' · 日常监查，数据仍在录入':''}）</span></div>
<div class="tabs" id="tabs"></div><div id="pane"></div>`;
const pane=document.getElementById('pane');
const R={enr,vis,dose,dq,ent};
const cname=s=>`${K.p(s,'sq mono')} ${K.esc((CN[s]||'').length>12?CN[s].slice(0,12)+'…':CN[s]||'')}`;
const rateCell=(n,d,all)=>{if(!d)return '·';const z=K.oe(n,d,all).z;return `<span style="${K.oeStyle(z)};padding:1px 6px;border-radius:4px" title="本中心 ${(n/d*100).toFixed(0)}%，整体 ${(all*100).toFixed(0)}%">${n} <span class="xs muted">${(n/d*100).toFixed(0)}%</span></span>`};
/* ---------- 入组与进度 ---------- */
function enr(){
  const st=k=>SU.filter(s=>s.status===k).length,n=SU.length,dosed=SU.filter(s=>s.fd);
  const sfAll=st('筛选失败')/(n||1),wdAll=st('提前退出')/(dosed.length||1);
  const icf2fd=dosed.map(s=>s.icf&&dd(s.fd,s.icf)).filter(x=>x!=null&&x>=0);
  pane.innerHTML=`<div class="kpis mb">${[['知情 / 筛选',n+'<small>例</small>',SU.filter(s=>s.rescreen).length?'重复筛选 '+SU.filter(s=>s.rescreen).length+' 例':''],['筛选失败',st('筛选失败')+`<small>例 · ${(sfAll*100).toFixed(0)}%</small>`,''],
    ['随机 / 给药',SU.filter(s=>s.rand).length+'<small>/ '+dosed.length+' 例</small>',O.planned?'计划 '+O.planned+' 例 · 已完成 '+(dosed.length/O.planned*100).toFixed(0)+'%':''],
    ['完成 / 在组',st('完成试验')+'<small>/ '+st('已入组')+' 例</small>','治疗结束 '+st('治疗结束')+' 例'],['提前退出',st('提前退出')+`<small>例 · ${(wdAll*100).toFixed(0)}%</small>`,''],
    ['知情 → 首剂（中位）',(med(icf2fd)??'—')+'<small>天</small>',icf2fd.length?'范围 '+Math.min(...icf2fd)+'–'+Math.max(...icf2fd)+' 天':'']].map(([l,v,s])=>`<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div><div class="s xs muted">${s}</div></div>`).join('')}</div>
  <div class="grid g21"><div class="card"><div class="hd"><h2>各中心入组与进度</h2><span class="sub">比率着色：高于整体且超出随机波动</span></div><div style="overflow-x:auto"><table class="t heat"><thead><tr><th>中心</th><th class="num">筛选</th><th class="num">筛败</th><th class="num">随机</th><th class="num">给药</th><th class="num">完成</th><th class="num">在组</th><th class="num">治疗结束</th><th class="num">提前退出</th><th class="num">重复筛选</th><th class="num">知情→首剂</th><th>首例给药</th></tr></thead><tbody>
   ${sites.map(si=>{const ss=SU.filter(s=>s.site===si),ds=ss.filter(s=>s.fd),c=k=>ss.filter(s=>s.status===k).length,i2=ds.map(s=>s.icf&&dd(s.fd,s.icf)).filter(x=>x!=null&&x>=0);
     return `<tr class="click" data-site="${si}"><td class="nowrap">${cname(si)}</td><td class="num">${ss.length}</td><td class="num">${rateCell(c('筛选失败'),ss.length,sfAll)}</td><td class="num">${ss.filter(s=>s.rand).length}</td><td class="num"><b>${ds.length}</b></td><td class="num">${c('完成试验')||'·'}</td><td class="num">${c('已入组')||'·'}</td><td class="num">${c('治疗结束')||'·'}</td><td class="num">${ds.length?rateCell(c('提前退出'),ds.length,wdAll):'·'}</td><td class="num">${ss.filter(s=>s.rescreen).length||'·'}</td><td class="num">${med(i2)??'—'}</td><td class="nowrap small">${ds.map(s=>s.fd).sort()[0]||'—'}</td></tr>`}).join('')}</tbody></table></div></div>
   <div class="card"><div class="hd"><h2>累计入组</h2><span class="sub">首次给药累计${O.planned?' · 虚线为计划例数':''}</span></div><div class="chart" id="enrc" style="height:300px"></div><div class="hd mt"><h2>筛选失败原因</h2></div><div id="sfr"></div></div></div>`;
  const fds=dosed.map(s=>s.fd).sort();
  const series=[{type:'line',name:'全部',step:'end',data:fds.map((d,i)=>[d,i+1]),symbol:'none',lineStyle:{color:'#FF9900',width:2},areaStyle:{color:'rgba(255,153,0,.10)'},markLine:O.planned?{symbol:'none',data:[{yAxis:O.planned,label:{formatter:'计划 '+O.planned}}],lineStyle:{type:'dashed',color:'#C9CCD1'}}:undefined}];
  K.chart('#enrc',{grid:{left:36,right:12,top:12,bottom:24},tooltip:{trigger:'axis'},xAxis:{type:'time',...K.axis},yAxis:{type:'value',...K.axis},series});
  const why=by(SU.filter(s=>s.status==='筛选失败'),s=>(s.eos_why||s.eot_why||'未注明').slice(0,30));
  document.getElementById('sfr').innerHTML=`<table class="t"><tbody>${Object.entries(why).sort((a,b)=>b[1].length-a[1].length).map(([k,v])=>`<tr><td class="small">${K.esc(k)}</td><td class="num">${v.length}</td></tr>`).join('')||'<tr><td class="empty">无</td></tr>'}</tbody></table>`;
  pane.querySelectorAll('tr[data-site]').forEach(tr=>tr.onclick=()=>location.href='subjects.html#c='+tr.dataset.site);
}
/* ---------- 访视执行 ---------- */
function vis(){
  if(!WV.length){pane.innerHTML='<div class="card empty">方案访视窗未配置（研究依据页「访视窗」），无法推算应完成访视</div>';return}
  const g=by(visRows,r=>r.site),ovAll=visRows.filter(r=>r.st==='overdue').length/(visRows.length||1),outAll=visRows.filter(r=>r.st==='out').length/(visRows.filter(r=>r.got).length||1);
  pane.innerHTML=`<div class="note small mb">按方案访视窗（目标日 ± 窗）与每例首剂日推算截至数据截止应完成的访视；受试者已结束于访视窗之前的不计。${daily?'日常监查阶段数据仍在录入，「逾期未见记录」可能只是尚未录入，请先与中心确认。':''}</div>
  <div class="grid g12"><div class="card"><div class="hd"><h2>各中心访视执行</h2></div><table class="t heat"><thead><tr><th>中心</th><th class="num">应完成</th><th class="num">已完成</th><th class="num">逾期未见记录</th><th class="num">超窗</th></tr></thead><tbody>
   ${sites.filter(s=>g[s]).map(si=>{const r=g[si],ov=r.filter(x=>x.st==='overdue').length,got=r.filter(x=>x.got),out=r.filter(x=>x.st==='out').length;
     return `<tr><td class="nowrap">${cname(si)}</td><td class="num">${r.length}</td><td class="num">${got.length}</td><td class="num">${rateCell(ov,r.length,ovAll)}</td><td class="num">${rateCell(out,got.length,outAll)}</td></tr>`}).join('')}</tbody></table></div>
   <div class="card"><div class="hd"><h2>逾期未见记录 / 超窗明细</h2><span class="sub">${visRows.filter(r=>r.st!=='ok').length} 条</span></div><div id="vt"></div></div></div>`;
  K.table(document.getElementById('vt'),{rows:visRows.filter(r=>r.st!=='ok'),sort:'due',dir:1,h:'520px',cols:[{k:'sid',t:'受试者',f:r=>K.sid(r.sid)},{k:'site',t:'中心',f:r=>K.p(r.site,'sq mono')},{k:'v',t:'访视',f:r=>K.p(r.v,'blu')},
    {k:'st',t:'情况',f:r=>r.st==='overdue'?K.p(daily?'逾期未见记录（可能未录入）':'逾期未见记录','org'):K.p('超窗','yel')},{k:'due',t:'方案窗',f:r=>`<span class="nowrap small">${r.lo} ~ ${r.due}</span>`},{k:'got',t:'实际',f:r=>r.got?`${r.got} <span class="xs faint">D${r.sd}</span>`:'—'}]});
}
/* ---------- 给药依从与知情 ---------- */
function dose(){
  const ds=SU.filter(s=>s.fd),EX=O.ex||{},sumEx=(ss,k)=>ss.reduce((a,s)=>a+((EX[s.id]||{})[k]||0),0),nEx=ss=>sumEx(ss,'n');
  const icfLate=ds.filter(s=>s.icf&&s.first&&s.first<s.icf);
  const IV=O.icf||{},vers=[...new Set(Object.values(IV).flat().map(x=>x[0]).filter(Boolean))].sort();
  const lastV=vers[vers.length-1];const reNeed=ds.filter(s=>!end(s)||end(s)>=cut),reDone=reNeed.filter(s=>(IV[s.id]||[]).some(x=>x[0]===lastV));
  const samp=PDP.filter(x=>/样本/.test(x.title||''));
  const all={miss:sumEx(ds,'miss')/(nEx(ds)||1),pause:sumEx(ds,'pause')/(nEx(ds)||1),devi:sumEx(ds,'devi')/(nEx(ds)||1),fast:sumEx(ds,'fast')/(nEx(ds)||1)};
  pane.innerHTML=`<div class="kpis mb">${[['给药记录',nEx(ds)+'<small>条</small>',''],['漏服/0 剂量',sumEx(ds,'miss')+'<small>条</small>',''],['给药中断',sumEx(ds,'pause')+'<small>条</small>',''],['剂量偏离',sumEx(ds,'devi')+'<small>条</small>','实际与计划剂量不同'],['未按要求空腹',sumEx(ds,'fast')+'<small>条</small>',''],
    ['知情晚于首个研究程序',icfLate.length+'<small>例</small>','首个访视日期早于知情日期'],...(vers.length>1?[['最新版本再知情',reDone.length+'<small>/ '+reNeed.length+' 例</small>','版本 '+K.esc(lastV)+'（在研受试者）']]:[]),['样本采集超窗',samp.length+'<small>条</small>','潜在 PD']].map(([l,v,s])=>`<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div><div class="s xs muted">${s}</div></div>`).join('')}</div>
  <div class="card"><div class="hd"><h2>各中心给药依从与知情</h2><span class="sub">给药类为条数（占该中心给药记录%）；着色＝高于整体且超出随机波动</span></div><div style="overflow-x:auto"><table class="t heat"><thead><tr><th>中心</th><th class="num">给药</th><th class="num">给药记录</th><th class="num">漏服/0剂量</th><th class="num">中断</th><th class="num">剂量偏离</th><th class="num">未空腹</th><th class="num">知情晚于程序</th>${vers.length>1?'<th class="num">最新版再知情</th>':''}<th class="num">样本超窗</th></tr></thead><tbody>
   ${sites.map(si=>{const ss=ds.filter(s=>s.site===si);if(!ss.length)return '';const n=nEx(ss),rn=reNeed.filter(s=>s.site===si);
     return `<tr><td class="nowrap">${cname(si)}</td><td class="num">${ss.length}</td><td class="num">${n}</td>${['miss','pause','devi','fast'].map(k=>`<td class="num">${n?rateCell(sumEx(ss,k),n,all[k]):'·'}</td>`).join('')}<td class="num">${icfLate.filter(s=>s.site===si).length||'·'}</td>${vers.length>1?`<td class="num">${reDone.filter(s=>s.site===si).length}/${rn.length}</td>`:''}<td class="num">${samp.filter(x=>x.site===si).length||'·'}</td></tr>`}).join('')}</tbody></table></div>
   ${icfLate.length?`<div class="sec-t"><h2>知情晚于首个研究程序</h2></div><table class="t"><tbody>${icfLate.map(s=>`<tr><td>${K.sid(s.id)}</td><td>${cname(s.site)}</td><td class="small">首个访视 ${s.first} · 知情 ${s.icf}</td></tr>`).join('')}</tbody></table>`:''}</div>`;
}
/* ---------- 退出与数据质量 ---------- */
function dq(){
  const ds=SU.filter(s=>s.fd),wd=SU.filter(s=>s.status==='提前退出'||(s.eot_d&&s.status!=='完成试验'&&s.eot_why));
  const why=by(wd,s=>(s.eos_why||s.eot_why||'未注明').slice(0,30));
  const QS=by(D.queries,q=>q.site),SUB=Object.fromEntries(SU.map(s=>[s.id,s.site])),CRO=by(D.cro,c=>SUB[c[2]]||'');
  const oc=cat=>by(D.others.filter(o=>o.cat===cat),o=>o.site),date=oc('日期完整性核对'),rng=oc('参考范围缺失核对'),ENT=by(O.entry||[],e=>e.site);
  const qAll=D.queries.length/(ds.length||1);
  pane.innerHTML=`<div class="grid g12"><div class="card"><div class="hd"><h2>提前退出 / 终止治疗原因</h2><span class="sub">${wd.length} 例</span></div><table class="t"><tbody>${Object.entries(why).sort((a,b)=>b[1].length-a[1].length).map(([k,v])=>`<tr><td class="small">${K.esc(k)}</td><td class="num">${v.length}</td><td class="small">${v.slice(0,6).map(s=>K.sid(s.id)+(s.fd&&end(s)?` <span class="xs faint">D${dd(end(s),s.fd)+1}</span>`:'')).join('　')}</td></tr>`).join('')||'<tr><td class="empty">无</td></tr>'}</tbody></table></div>
   <div class="card"><div class="hd"><h2>各中心数据质量</h2><span class="sub">申办方质疑按给药人数校正着色</span></div><table class="t heat"><thead><tr><th>中心</th><th class="num">给药</th><th class="num">申办方质疑</th><th class="num">CRO 质疑</th><th class="num">日期完整性</th><th class="num">参考范围缺失</th><th class="num">疑似录入错误</th></tr></thead><tbody>
    ${sites.map(si=>{const n=ds.filter(s=>s.site===si).length;if(!n&&!(QS[si]||[]).length)return '';const q=(QS[si]||[]).length;
      return `<tr><td class="nowrap">${cname(si)}</td><td class="num">${n}</td><td class="num"><span style="${K.oeStyle(K.oe(q,n,qAll).z)};padding:1px 6px;border-radius:4px">${q||'·'}</span></td><td class="num">${(CRO[si]||[]).length||'·'}</td><td class="num">${(date[si]||[]).length||'·'}</td><td class="num">${(rng[si]||[]).length||'·'}</td><td class="num">${(ENT[si]||[]).length||'·'}</td></tr>`}).join('')}</tbody></table></div></div>`;
}
/* ---------- 疑似录入错误 ---------- */
function ent(){
  const E=O.entry||[];
  pane.innerHTML=`<div class="note small mb">同一受试者同一指标，某次结果为本人其余结果的约 10 的整数次幂倍（疑似小数点错位）或 ≥20 倍且为孤立尖峰（前后两次都正常范围波动），或单位与本人其余记录不同。只作数据质量提示（请 CRA 核对源数据），不发医学质疑；若该点同时进了医学风险层，风险行已标注「可能为录入错误，请先核对源数据」。</div>
  <div class="card"><div id="et"></div></div>`;
  K.table(document.getElementById('et'),{rows:E,sort:'site',dir:1,h:'620px',onRow:r=>{const b=K.drawer(`${r.sid} · ${K.esc(r.test)}`,`<div class="box org small mb">${K.esc(r.visit)} ${K.esc(r.raw)} ${K.esc(r.unit)}：${K.esc(r.why)}</div><div id="sp"></div>`);K.seriesPanel(b.querySelector('#sp'),{sid:r.sid,tests:[r.test],hl:[[r.sh,r.row]],ae:false})},
    cols:[{k:'sid',t:'受试者',f:r=>K.sid(r.sid)},{k:'site',t:'中心',f:r=>cname(r.site)},{k:'test',t:'指标',f:r=>`<b>${K.esc(r.test)}</b>`},{k:'visit',t:'访视',f:r=>K.p(r.visit,'blu')+` <span class="xs faint">${K.esc(r.date)}</span>`},
      {k:'raw',t:'录入值',f:r=>`<b>${K.esc(r.raw)}</b> <span class="xs muted">${K.esc(r.unit)}</span>`},{k:'why',t:'判断',f:r=>`<span class="small">${K.esc(r.why)}</span>`},{k:'row',t:'来源',f:r=>`<span class="xs faint">${K.esc(K.loc(r.sh,r.row))}</span>`}]});
}
K.tabs(document.getElementById('tabs'),tabs,H.tab&&R[H.tab]?H.tab:'enr',v=>{K.setHash({tab:v});R[v]()});   /* 放在末尾：tabs 会立即渲染默认页签，所用的函数与常量须已定义 */
});
