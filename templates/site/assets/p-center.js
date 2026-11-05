/* 中心画像（V5，用户 2026-10-31 晚；临床监查空间子页）：一个中心的入组进度、KRI 对照整体与研究层面限度、风险类别、待办、
 * 方案偏离、访视、录入错误、数据可信度、数据新鲜度集中一页（#c=中心）。安全性细节链到安全性概览中心视图。 */
K.init(()=>{
const D=KZ,app=document.getElementById('app'),O=D.ops||{},KR=D.kri,CRD=D.cred,TL=(window.KZS||{}).timeliness;
const F=O.fields||[],SU=(O.subs||[]).map(a=>Object.fromEntries(F.map((k,i)=>[k,a[i]])));
const CS=D.centers.filter(c=>c.n).slice().sort((a,b)=>a.site.localeCompare(b.site));
app.innerHTML=`<div class="flex mb"><h1 style="font-size:18px">中心画像</h1><span class="muted small">入组进度 · KRI 对照整体与容忍限度 · 风险类别 · 本中心待办 · 方案偏离 · 访视 · 数据质量</span><span class="sp"></span>
 <select class="s" id="cs">${CS.map(c=>`<option value="${c.site}">${c.site} ${K.esc(c.name)}（给药 ${c.dosed}）</option>`).join('')}</select></div><div id="cp"></div>`;
const sel=document.getElementById('cs');
const go=()=>{const site=sel.value;K.setHash({c:site});draw(site)};
sel.value=(K.hash().c&&CS.some(c=>c.site===K.hash().c))?K.hash().c:(CS[0]||{}).site||'';
sel.onchange=go;window.addEventListener('hashchange',()=>{const c=K.hash().c;if(c&&c!==sel.value&&CS.some(x=>x.site===c)){sel.value=c;draw(c)}});

function draw(site){
  const el=document.getElementById('cp'),c=CS.find(x=>x.site===site);if(!c){el.innerHTML='<div class="card empty">无中心数据</div>';return}
  const ss=SU.filter(s=>s.site===site),ds=ss.filter(s=>s.fd),stc=k=>ss.filter(s=>s.status===k).length,fu=O.fu||{};
  const pm=ds.reduce((a,s)=>a+(fu[s.id]||0),0)/30.4375,fr=(O.fresh||{})[site];
  const POT=((D.pd||{}).potential||[]).filter(p=>p.site===site),due=(O.due||[]).filter(d=>d[1]===site),ent=(O.entry||[]).filter(e=>e.site===site),q=D.queries.filter(x=>x.site===site);
  const kpi=(l,v,s)=>`<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div><div class="s xs muted">${s}</div></div>`;
  const CR=K.centerRisk(),cats=CR.cats;
  const risks=K.riskFor('all',site);
  el.innerHTML=`<div class="kpis mb">
   ${kpi('筛选 / 给药',`${ss.length}<small>/ ${ds.length} 例</small>`,`筛败 ${stc('筛选失败')} · 在组 ${stc('已入组')} · 完成 ${stc('完成试验')} · 提前退出 ${stc('提前退出')}`)}
   ${kpi('随访人月',pm.toFixed(0),'首剂至研究结束或数据截止')}
   ${kpi('数据新鲜度',fr?`${fr[1]}<small>天</small>`:'—',fr?`最近记录 ${fr[0]} · 在研 ${fr[2]} 例`:'')}
   ${kpi('访视',`${due.length}<small>次应完成</small>`,`逾期 ${due.filter(d=>d[6]==='overdue').length} · 超窗 ${due.filter(d=>d[6]==='out').length} · 未来 14 天 ${(O.upcoming||[]).filter(u=>u[1]===site).length}`)}
   ${kpi('潜在方案偏离',`${POT.length}<small>条</small>`,`重要 ${POT.filter(p=>p.grade==='重要').length}`)}
   ${kpi('申办方质疑',`${q.length}<small>条</small>`,`疑似录入错误 ${ent.length}`)}</div>
  <div class="flex wrap mb small" style="gap:12px"><a href="profile.html#c=${site}">安全性概览 · 本中心 ›</a><a href="safety.html#tab=lab&c=${site}">本中心检验风险 ›</a><a href="deviations.html">方案偏离 ›</a><a href="subjects.html#c=${site}">本中心受试者 ›</a><a href="raw.html#c=${site}">本中心原始数据 ›</a></div>
  <div class="grid g12"><div class="card"><div class="hd"><h2>KRI</h2><span class="sub">本中心 · 研究整体 · 研究层面限度（${K.QTLN[K.qtlTier()]}档）</span><span class="sp"></span><a class="small" href="monitor.html#tab=kri">全部中心 ›</a></div><div id="ck"></div></div>
   <div class="card"><div class="hd"><h2>风险类别</h2><span class="sub">观察数与按${K.esc(CR.unit)}推算的期望；着色＝校正多重比较后偏高/偏少</span><span class="sp"></span><a class="small" href="safety.html#tab=ov">热力图 ›</a></div><div id="cr"></div></div></div>
  <div class="card mt"><div class="hd"><h2>本中心受试者风险构成</h2><span class="sub">每名已给药受试者的检验 CS 未关联、专项（需核实及以上）、质疑与 AE；点条形进入个例资料</span><span class="sp"></span><a class="small" href="raw.html#c=${site}">本中心原始数据 ›</a></div><div id="crs" class="chart"></div></div>
  <div class="card mt"><div class="hd"><h2>本中心风险排名</h2><span class="sub">${risks.length} 项（全部角色）· 点行查看证据与原始数据</span><span class="sp"></span><a class="small" href="index.html#rank">全部中心 ›</a></div><div id="ca"></div></div>
  <div class="grid g12 mt"><div class="card"><div class="hd"><h2>潜在方案偏离</h2><span class="sub">${POT.length} 条</span></div><div id="cpd"></div></div>
   <div class="card"><div class="hd"><h2>访视与录入</h2><span class="sub">逾期/超窗访视、疑似录入错误</span></div><div id="cv"></div></div></div>
  <div class="card mt"><div class="hd"><h2>数据质量</h2><span class="sub">数据可信度（建议核对，不作结论）${TL?' · 录入及时性（按上传谱系推算上限）':''}</span></div><div id="cq"></div></div>`;
  /* KRI */
  if(KR){const sv=KR.sites[site]||{};document.getElementById('ck').innerHTML=`<table class="t"><thead><tr><th>指标</th><th class="num">本中心</th><th class="num">整体</th><th class="num">限度</th><th></th></tr></thead><tbody>${KR.defs.map(d=>{const nd=sv[d.k],v=K.kriV(d.k,nd),s=d.qtl&&nd&&nd[1]>=5?K.qtlState(d.k,nd):{},na=(KR.na||{})[d.k];
    return `<tr><td class="small" title="${K.esc(d.note)}">${K.esc(d.l)} <span class="xs faint">${d.u}</span></td><td class="num"><b>${na||v==null?'—':K.kriFmt(d.k,v)}</b> <span class="xs faint">${nd&&nd[1]&&d.u!=='天'?nd[0]+'/'+nd[1]:''}</span></td><td class="num">${na?'—':K.kriFmt(d.k,K.kriV(d.k,KR.study[d.k]))}</td><td class="num">${d.qtl?'≤'+K.qtlLim(d.k)+'%':''}</td><td>${s.st?K.p(K.QTLC[s.st][0],K.QTLC[s.st][1]):d.qtl&&nd&&nd[1]<5&&nd[1]?'<span class="xs faint">n<5 不判</span>':''}</td></tr>`}).join('')}</tbody></table>`}
  else document.getElementById('ck').innerHTML='<div class="empty">本构建没有 KRI 数据</div>';
  /* 风险类别 */
  document.getElementById('cr').innerHTML=`<table class="t"><thead><tr><th>组</th><th>类别</th><th class="num">观察</th><th class="num">期望</th><th></th></tr></thead><tbody>${cats.map(([k,g,l,,desc])=>{const x=(CR.cell[k]||{})[site];if(!x)return '';
    return `<tr title="${K.esc(desc)}"><td class="xs muted">${g}</td><td class="small">${l}</td><td class="num" style="${K.qStyle(x.qu,x.ql)}">${x.o}</td><td class="num">${x.e.toFixed(1)}</td><td>${K.qlt(x.qu,.10)?K.p(K.qlt(x.qu,.05)?'明显偏高':'偏高','org'):K.qlt(x.ql,.10)?K.p('偏少','blu'):''}</td></tr>`}).join('')}</tbody></table>`;
  if(K.roster)K.roster(document.getElementById('crs'),ds.map(s=>s.id));
  /* 风险排名 */
  K.riskTable(document.getElementById('ca'),risks,{h:'420px'});
  /* 方案偏离 */
  K.table(document.getElementById('cpd'),{rows:POT,h:'320px',onRow:r=>K.showPD(r.id),cols:[{k:'grade',t:'分级',f:r=>K.pdGrade(r.grade)},{k:'sid',t:'受试者',f:r=>K.sid(r.sid)},{k:'title',t:'偏离',ns:1,f:r=>`<span class="small">${K.esc(r.title)}：${K.esc(String(r.fact||'').slice(0,70))}</span>`}]});
  /* 访视与录入 */
  const vr=due.filter(d=>d[6]!=='ok').map(d=>({sid:d[0],v:d[2],lo:d[3],hi:d[4],got:d[5],st:d[6],nd:d[11]}));
  document.getElementById('cv').innerHTML=`<div id="cvv"></div><div class="sec-t"><h2>疑似录入错误</h2><span class="muted small">${ent.length} 条</span></div><div id="cve"></div>`;
  K.table(document.getElementById('cvv'),{rows:vr,h:'200px',onRow:r=>{if(r.st==='overdue')K.showVis({sid:r.sid,site,v:r.v,lo:r.lo,hi:r.hi})},cols:[{k:'sid',t:'受试者',f:r=>K.sid(r.sid)},{k:'v',t:'访视',f:r=>K.p(r.v,'blu')},{k:'st',t:'情况',f:r=>(r.st==='overdue'?(r.nd?K.p('EDC 记为未进行','red'):K.p('逾期未见记录','org')):K.p('超窗','yel'))},{k:'lo',t:'方案窗',f:r=>`<span class="small nowrap">${r.lo} ~ ${r.hi}</span>`}]});
  K.table(document.getElementById('cve'),{rows:ent,h:'200px',onRow:r=>K.showEnt(r),cols:[{k:'sid',t:'受试者',f:r=>K.sid(r.sid)},{k:'test',t:'指标',f:r=>K.esc(r.test)},{k:'raw',t:'录入值',f:r=>`${K.esc(r.raw)} ${K.esc(r.unit)}`}]});
  /* 数据质量 */
  const cf=CRD?K.credFlags(site,CRD.sites[site]):[],tl=TL&&TL.sites?TL.sites[site]:null;
  document.getElementById('cq').innerHTML=`<div class="grid g2"><div><div class="xs muted mb">数据可信度</div>${cf.length?cf.map(f=>`<div class="box small mb">${K.p(f.l,'yel')} ${K.esc(f.why)}</div>`).join(''):'<div class="small muted">未见中心层面的异常模式</div>'}</div>
   <div><div class="xs muted mb">录入及时性</div>${tl?`<div class="kv"><dt>新增访视记录</dt><dd>${tl.n??'—'}</dd><dt>延迟中位数 / P90</dt><dd>${tl.med??'—'} / ${tl.p90??'—'} 天</dd><dt>修改/删除率</dt><dd>${tl.mod&&tl.mod[1]?(tl.mod[0]/tl.mod[1]*100).toFixed(1)+'%':'—'}</dd><dt>最近一次有新数据</dt><dd>${K.esc(tl.lastNew||'—')}</dd></div>`:'<div class="small muted">单次构建：在工作台多次上传后按上传谱系推算</div>'}</div></div>`;
}
if(sel.value)go();
});
