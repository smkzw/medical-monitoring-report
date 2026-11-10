/* 临床监查·监查概况（mm5 建页；V5 用户 2026-10-31 晚：KRI 与研究层面容忍限度、录入及时性、数据可信度、前瞻视图）。
 * 数据：KZ.ops（受试者里程碑、访视推算 due/upcoming、随访人日、新鲜度、给药依从、知情、疑似录入错误）、KZ.kri、KZ.cred，
 * 工作台系统层 KZS.timeliness / history（多次上传才有）。listing 没有录入/核查时间戳：录入及时性由工作台按快照谱系推算上限。 */
K.init(()=>{
const D=KZ,app=document.getElementById('app'),H=K.hash(),O=D.ops||{subs:[],vis:{},win:{},ex:{},icf:{},entry:[],fields:[]};
const F=O.fields||[],SU=(O.subs||[]).map(a=>Object.fromEntries(F.map((k,i)=>[k,a[i]])));
const cut=O.cutoff||(D.meta||{}).cutoff||'',daily=O.stage==='daily';
const CN=Object.fromEntries(D.centers.map(c=>[c.site,c.name]));
const sites=[...new Set(SU.map(s=>s.site))].sort();
const addD=(d,n)=>{const x=new Date(d+'T00:00:00Z');x.setUTCDate(x.getUTCDate()+Math.round(n));return x.toISOString().slice(0,10)};
const dd=(a,b)=>K.days(a,b),med=a=>a.length?K.median(a):null;
const by=(arr,f)=>arr.reduce((m,x)=>{const k=f(x);(m[k]=m[k]||[]).push(x);return m},{});
const PDP=((D.pd||{}).potential)||[];
const end=s=>[s.eos_d,s.eot_d].filter(d=>d&&d.length>=10).sort()[0]||'';
/* 访视推算在后端（ops.due）：[sid, site, 访视, 窗起, 窗止, 实际, 状态, 研究日, 目标日, −窗, +窗] */
const visRows=(O.due||[]).map(d=>({sid:d[0],site:d[1],v:d[2],lo:d[3],due:d[4],got:d[5],st:d[6],sd:d[7],t:d[8],mi:d[9],pl:d[10],nd:d[11]}));
const UP=(O.upcoming||[]).map(u=>({sid:u[0],site:u[1],v:u[2],lo:u[3],hi:u[4],tg:u[5]}));
const KR=D.kri,CRD=D.cred,TL=(window.KZS||{}).timeliness;
const tabs=[['enr','入组与进度',SU.length],['vis','访视执行',visRows.filter(r=>r.st!=='ok').length],['dose','给药与知情'],['dq','退出与数据质量'],
  ['kri','KRI 与容忍限度',KR?K.qtlRows().filter(r=>r.st==='exceed').length||null:null],['time','录入及时性'],['cred','数据可信度',CRD?Object.entries(CRD.sites).filter(([s,v])=>K.credFlags(s,v).length).length||null:null],['ent','疑似录入错误',(O.entry||[]).length]];
app.innerHTML=`<div class="flex mb"><h1 style="font-size:18px">临床监查</h1>${daily?'<span class="muted small">日常监查，数据仍在录入</span>':''}<span class="sp"></span><span id="qtlbar"></span></div>
<div class="tabs" id="tabs"></div><div id="pane"></div>`;
const pane=document.getElementById('pane');
const R={enr,vis,dose,dq,kri,time,cred,ent};
const cname=s=>`${K.p(s,'sq mono')} ${K.esc((CN[s]||'').length>12?CN[s].slice(0,12)+'…':CN[s]||'')}`;
/* 一列各中心比率着色：期望＝整体率×分母，泊松上尾、按列 Benjamini–Hochberg 校正（与风险页热力图同口径） */
/* per=true：分子是计数、分母是人数（质疑数/给药人数）——显示「每例 x.x」而不是百分比（MY008 运营复审：「142 592%」无意义） */
const colCells=(rows,all,per)=>{const f=K.colFlags(rows,all),fm=x=>per?`每例 ${x.toFixed(1)}`:`${(x*100).toFixed(0)}%`;return rows.map(([n,d],i)=>d?`<span style="${(f[i]||{}).style||''};padding:1px 6px;border-radius:4px" title="本中心 ${fm(n/d)}，整体 ${fm(all)} · ${K.esc(K.qTip(f[i]))}">${n} <span class="xs muted">${fm(n/d)}</span></span>`:'·')};
/* ---------- 入组与进度（含入组预测） ---------- */
function enr(){
  const st=k=>SU.filter(s=>s.status===k).length,n=SU.length,dosed=SU.filter(s=>s.fd);
  const sfAll=st('筛选失败')/(n||1),wdAll=st('提前退出')/(dosed.length||1);
  const icf2fd=dosed.map(s=>s.icf&&dd(s.fd,s.icf)).filter(x=>x!=null&&x>=0);
  const fds=dosed.map(s=>s.fd).sort(),n90=cut?fds.filter(d=>dd(cut,d)>=0&&dd(cut,d)<90).length:0,pl=O.planned;
  const proj=pl&&cut&&dosed.length<pl&&n90>=3?addD(cut,(pl-dosed.length)/(n90/90)):null;
  pane.innerHTML=`<div class="kpis mb">${[['知情 / 筛选',n+'<small>例</small>',SU.filter(s=>s.rescreen).length?'重复筛选 '+SU.filter(s=>s.rescreen).length+' 例':''],['筛选失败',st('筛选失败')+`<small>例 · ${(sfAll*100).toFixed(0)}%</small>`,''],
    ['随机 / 给药',SU.filter(s=>s.rand).length+'<small>/ '+dosed.length+' 例</small>',pl?'计划 '+pl+' 例 · 已完成 '+(dosed.length/pl*100).toFixed(0)+'%':''],
    ['入组预测',pl?(dosed.length>=pl?'已达成':proj||'—'):'—',pl?(dosed.length>=pl?'已达计划例数':proj?`近 90 天给药 ${n90} 例（${(n90/90*30).toFixed(1)} 例/月）外推`:'近 90 天给药不足 3 例，无法外推'):'方案未给计划例数'],
    ['完成 / 在组',st('完成试验')+'<small>/ '+st('已入组')+' 例</small>','提前终止治疗（随访中） '+st('提前终止治疗')+' 例'],['提前退出',st('提前退出')+`<small>例 · ${(wdAll*100).toFixed(0)}%</small>`,''],
    ['知情 → 首剂（中位）',(med(icf2fd)??'—')+'<small>天</small>',icf2fd.length?'范围 '+Math.min(...icf2fd)+'–'+Math.max(...icf2fd)+' 天':'']].map(([l,v,s])=>`<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div><div class="s xs muted">${s}</div></div>`).join('')}</div>
  <div class="grid g21"><div class="card"><div class="hd"><h2>各中心入组与进度</h2><span class="sub">比率着色：高于整体且校正多重比较后仍显著；点行进入中心画像</span></div><div style="overflow-x:auto"><table class="t heat"><thead><tr><th>中心</th><th class="num">筛选</th><th class="num">筛败</th><th class="num">随机</th><th class="num">给药</th><th class="num">完成</th><th class="num">在组</th><th class="num">治疗结束</th><th class="num">提前退出</th><th class="num">重复筛选</th><th class="num">知情→首剂</th><th>首例给药</th><th>最近给药</th></tr></thead><tbody id="enrb"></tbody></table></div></div>
   <div class="card"><div class="hd"><h2>累计入组</h2><span class="sub">首次给药累计${pl?' · 灰线为计划例数':''}${proj?' · 虚线为预测':''}</span></div><div class="chart" id="enrc" style="height:300px"></div><div class="hd mt"><h2>筛选失败原因</h2></div><div id="sfr"></div></div></div>`;
  const rows=sites.map(si=>{const ss=SU.filter(s=>s.site===si),ds=ss.filter(s=>s.fd);return {si,ss,ds}});
  const sfC=colCells(rows.map(r=>[r.ss.filter(s=>s.status==='筛选失败').length,r.ss.length]),sfAll),wdC=colCells(rows.map(r=>[r.ss.filter(s=>s.status==='提前退出').length,r.ds.length]),wdAll);
  document.getElementById('enrb').innerHTML=rows.map(({si,ss,ds},i)=>{const c=k=>ss.filter(s=>s.status===k).length,i2=ds.map(s=>s.icf&&dd(s.fd,s.icf)).filter(x=>x!=null&&x>=0),fd=ds.map(s=>s.fd).sort();
     return `<tr class="click" data-site="${si}"><td class="nowrap">${cname(si)}</td><td class="num">${ss.length}</td><td class="num">${sfC[i]}</td><td class="num">${ss.filter(s=>s.rand).length}</td><td class="num"><b>${ds.length}</b></td><td class="num">${c('完成试验')||'·'}</td><td class="num">${c('已入组')||'·'}</td><td class="num">${(c('治疗结束')+c('提前终止治疗'))||'·'}</td><td class="num">${ds.length?wdC[i]:'·'}</td><td class="num">${ss.filter(s=>s.rescreen).length||'·'}</td><td class="num">${med(i2)??'—'}</td><td class="nowrap small">${fd[0]||'—'}</td><td class="nowrap small">${fd[fd.length-1]||'—'}</td></tr>`}).join('');
  const series=[{type:'line',name:'全部',step:'end',data:fds.map((d,i)=>[d,i+1]),symbol:'none',lineStyle:{color:'#FF9900',width:2},areaStyle:{color:'rgba(255,153,0,.10)'},markLine:pl?{symbol:'none',data:[{yAxis:pl,label:{formatter:'计划 '+pl}}],lineStyle:{type:'dashed',color:'#C9CCD1'}}:undefined}];
  if(proj)series.push({type:'line',name:'预测',data:[[cut,dosed.length],[proj,pl]],symbol:'none',lineStyle:{color:'#FF9900',type:'dashed',width:1.5}});
  K.chart('#enrc',{grid:{left:36,right:12,top:12,bottom:24},tooltip:{trigger:'axis'},xAxis:{type:'time',...K.axis},yAxis:{type:'value',...K.axis},series});
  /* 筛败原因：EDC 多选分隔符「$」、重复前缀「入选标准 入选标准5」清洗；编号配上标准原文（审阅 2026-11-11） */
const CRI=((D.study||{}).criteria||[]),criTxt=(k,n)=>{const c=CRI.find(c=>c.no===(k==='入选'?'I':'E')+n);return c?`${k}标准 ${n}：${String(c.text).replace(/^[\s\d.、]+/,'').slice(0,18)}${String(c.text).length>18?'…':''}`:`${k}标准 ${n}`};
const sfClean=t=>String(t||'未注明').split(/\s*\$\s*|；|;/).map(x=>x.replace(/^(入选|排除)标准\s+(?=(入选|排除)标准)/,'').trim()).filter(Boolean)
  .map(x=>{const m=x.match(/^(入选|排除)标准\s*(\d+)$/);return m?criTxt(m[1],m[2]):x.slice(0,30)}).filter((x,i,a)=>a.indexOf(x)===i).join('、');
const why=by(SU.filter(s=>s.status==='筛选失败'),s=>sfClean(s.sf_why||s.eos_why||s.eot_why));   /* V6：入排标准页不满足的标准优先 */
  document.getElementById('sfr').innerHTML=`<table class="t"><tbody>${Object.entries(why).sort((a,b)=>b[1].length-a[1].length).map(([k,v])=>`<tr><td class="small">${K.esc(k)}</td><td class="num">${v.length}</td></tr>`).join('')||'<tr><td class="empty">无</td></tr>'}</tbody></table>`;
  pane.querySelectorAll('tr[data-site]').forEach(tr=>tr.onclick=()=>location.href='center.html#c='+tr.dataset.site);
}
/* ---------- 访视执行（含未来 14 天应到访视、末例末次访视预测） ---------- */
function vis(){
  const W=O.win||{},WV=Object.keys(W);
  if(!WV.length){pane.innerHTML='<div class="card empty">方案访视窗未配置（研究依据页「访视窗」），无法推算应完成访视</div>';return}
  const g=by(visRows,r=>r.site),ovAll=visRows.filter(r=>r.st==='overdue').length/(visRows.length||1),outAll=visRows.filter(r=>r.st==='out').length/(visRows.filter(r=>r.got).length||1);
  const tmax=Math.max(...WV.map(v=>{const s=W[v];return Array.isArray(s)?s[0]:s.target}).filter(x=>x!=null));
  const ongo=SU.filter(s=>s.fd&&!end(s)&&!['完成试验','提前退出','筛选失败'].includes(s.status)).map(s=>[s,addD(s.fd,tmax-1)]).sort((a,b)=>a[1]<b[1]?1:-1);
  const sv=sites.filter(s=>g[s]);
  const ovC=colCells(sv.map(si=>[g[si].filter(x=>x.st==='overdue').length,g[si].length]),ovAll),ouC=colCells(sv.map(si=>[g[si].filter(x=>x.st==='out').length,g[si].filter(x=>x.got).length]),outAll);
  pane.innerHTML=`<div class="note small mb">按方案访视窗（目标日 ± 窗，首剂为锚点）推算截至数据截止应完成的访视；受试者已结束于访视窗之前的不计。${daily?'日常监查阶段数据仍在录入，「逾期未见记录」可能只是尚未录入，请先与中心确认。':''}${(()=>{const al=Object.entries(O.visitAlias||{}),um=O.visitUnmapped||[];return (al.length?`<br>方案访视与数据访视代码写法不同，已按访视日落在方案窗内的比例对齐：${al.map(([a,b])=>`${K.esc(a)}→${K.esc(b)}`).join('、')}。`:'')+(um.length?`<br><b>未映射</b>：${um.map(K.esc).join('、')} 在数据中找不到对应访视代码，未推算逾期（请在研究依据页核对访视窗命名）。`:'')+((O.visitArm||[]).length?`<br>组别专属访视：${O.visitArm.map(K.esc).join('、')}——数据中只见于部分组别，其余组不推算逾期。`:'')})()}</div>
  <div class="grid g12"><div class="card"><div class="hd"><h2>各中心访视执行</h2><span class="sub">着色：校正多重比较后仍偏高</span></div><table class="t heat"><thead><tr><th>中心</th><th class="num">应完成</th><th class="num">已完成</th><th class="num">逾期未见记录</th><th class="num">超窗</th><th class="num">未来 14 天</th></tr></thead><tbody>
   ${sv.map((si,i)=>{const r=g[si];return `<tr class="click" data-site="${si}"><td class="nowrap">${cname(si)}</td><td class="num">${r.length}</td><td class="num">${r.filter(x=>x.got).length}</td><td class="num">${ovC[i]}</td><td class="num">${ouC[i]}</td><td class="num">${UP.filter(u=>u.site===si).length||'·'}</td></tr>`}).join('')}</tbody></table>
   <div class="sec-t"><h2>前瞻</h2></div><div class="kv"><dt>未来 14 天应到访视</dt><dd>${UP.length} 次（${new Set(UP.map(u=>u.site)).size} 个中心）</dd>
    <dt>在研受试者最后一次计划访视</dt><dd>${ongo.length?`最晚约 <b>${ongo[0][1]}</b>（${K.sid(ongo[0][0].id)}，按 ${tmax} 天的最后访视目标日）`:'无在研受试者'}</dd>
    ${O.planned&&SU.filter(s=>s.fd).length<O.planned?`<dt>尚未入组</dt><dd>${O.planned-SU.filter(s=>s.fd).length} 例：末例末次访视 ≈ 末例入组日 + ${tmax} 天（入组预测见「入组与进度」）</dd>`:''}</div></div>
   <div class="card"><div class="hd"><h2>逾期未见记录 / 超窗明细</h2><span class="sub">${visRows.filter(r=>r.st!=='ok').length} 条 · 点逾期行查看本受试者访视原始记录</span></div><div id="vt"></div>
    <div class="hd mt"><h2>未来 14 天应到访视</h2><span class="sub">${UP.length} 次</span></div><div id="ut"></div></div></div>`;
  const rowsV=()=>visRows.filter(r=>r.st!=='ok');
  const tb=K.table(document.getElementById('vt'),{rows:rowsV(),sort:'due',dir:1,h:'420px',onRow:r=>{if(r.st==='overdue')K.showVis({sid:r.sid,site:r.site,v:r.v,lo:r.lo,hi:r.due})},cols:[{k:'sid',t:'受试者',f:r=>K.sid(r.sid)},{k:'site',t:'中心',f:r=>K.p(r.site,'sq mono')},{k:'v',t:'访视',f:r=>K.p(r.v,'blu')},
    {k:'st',t:'情况',f:r=>(r.st==='overdue'?(r.nd?K.p('EDC 记为未进行','red'):K.p(daily?'逾期未见记录（可能未录入）':'逾期未见记录','org')):K.p('超窗','yel'))},{k:'due',t:'方案窗',f:r=>`<span class="nowrap small">${r.lo} ~ ${r.due}</span>`},{k:'got',t:'实际',f:r=>r.got?`${r.got} <span class="xs faint">D${r.sd}</span>`:'—'}]});
  K.table(document.getElementById('ut'),{rows:UP,sort:'tg',dir:1,h:'260px',cols:[{k:'sid',t:'受试者',f:r=>K.sid(r.sid)},{k:'site',t:'中心',f:r=>K.p(r.site,'sq mono')},{k:'v',t:'访视',f:r=>K.p(r.v,'blu')},{k:'tg',t:'目标日',f:r=>`<span class="nowrap small">${r.tg}</span>`},{k:'lo',t:'方案窗',f:r=>`<span class="nowrap small">${r.lo} ~ ${r.hi}</span>`}]});
  pane.querySelectorAll('tr[data-site]').forEach(tr=>tr.onclick=()=>location.href='center.html#c='+tr.dataset.site);
}
/* ---------- 给药依从与知情 ---------- */
function dose(){
  const ds=SU.filter(s=>s.fd),EX=O.ex||{},sumEx=(ss,k)=>ss.reduce((a,s)=>a+((EX[s.id]||{})[k]||0),0),nEx=ss=>sumEx(ss,'n');
  const icfLate=ds.filter(s=>s.icf&&s.first&&s.first<s.icf);
  const IV=O.icf||{},vers=[...new Set(Object.values(IV).flat().map(x=>x[0]).filter(Boolean))].sort();
  const lastV=vers[vers.length-1];const reNeed=ds.filter(s=>!end(s)||end(s)>=cut),reDone=reNeed.filter(s=>(IV[s.id]||[]).some(x=>x[0]===lastV));
  const samp=PDP.filter(x=>/样本/.test(x.title||''));
  const all={miss:sumEx(ds,'miss')/(nEx(ds)||1),pause:sumEx(ds,'pause')/(nEx(ds)||1),devi:sumEx(ds,'devi')/(nEx(ds)||1),fast:sumEx(ds,'fast')/(nEx(ds)||1)};
  const ss_=sites.map(si=>ds.filter(s=>s.site===si)).filter(x=>x.length);
  const col=Object.fromEntries(['miss','pause','devi','fast'].map(k=>[k,colCells(ss_.map(ss=>[sumEx(ss,k),nEx(ss)]),all[k])]));
  pane.innerHTML=`<div class="kpis mb">${[['给药记录',nEx(ds)+'<small>条</small>',''],['漏服/0 剂量',sumEx(ds,'miss')+'<small>条</small>',''],['给药中断',sumEx(ds,'pause')+'<small>条</small>',''],['剂量偏离',sumEx(ds,'devi')+'<small>条</small>','实际与计划剂量不同'],['未按要求空腹',sumEx(ds,'fast')+'<small>条</small>',''],
    ['知情晚于首个研究程序',icfLate.length+'<small>例</small>','首个访视日期早于知情日期'],...(vers.length>1?[['最新版本再知情',reDone.length+'<small>/ '+reNeed.length+' 例</small>','版本 '+K.esc(lastV)+'（在研受试者）']]:[]),['样本采集超窗',samp.length+'<small>条</small>','潜在 PD']].map(([l,v,s])=>`<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div><div class="s xs muted">${s}</div></div>`).join('')}</div>
  <div class="card"><div class="hd"><h2>各中心给药依从与知情</h2><span class="sub">给药类为条数（占该中心给药记录%）；着色＝高于整体且校正多重比较后仍显著</span></div><div style="overflow-x:auto"><table class="t heat"><thead><tr><th>中心</th><th class="num">给药</th><th class="num">给药记录</th><th class="num">漏服/0剂量</th><th class="num">中断</th><th class="num">剂量偏离</th><th class="num">未空腹</th><th class="num">知情晚于程序</th>${vers.length>1?'<th class="num">最新版再知情</th>':''}<th class="num">样本超窗</th></tr></thead><tbody>
   ${ss_.map((ss,i)=>{const si=ss[0].site,n=nEx(ss),rn=reNeed.filter(s=>s.site===si);
     return `<tr><td class="nowrap">${cname(si)}</td><td class="num">${ss.length}</td><td class="num">${n}</td>${['miss','pause','devi','fast'].map(k=>`<td class="num">${n?col[k][i]:'·'}</td>`).join('')}<td class="num">${icfLate.filter(s=>s.site===si).length||'·'}</td>${vers.length>1?`<td class="num">${reDone.filter(s=>s.site===si).length}/${rn.length}</td>`:''}<td class="num">${samp.filter(x=>x.site===si).length||'·'}</td></tr>`}).join('')}</tbody></table></div>
   ${icfLate.length?`<div class="sec-t"><h2>知情晚于首个研究程序</h2></div><table class="t"><tbody>${icfLate.map(s=>`<tr><td>${K.sid(s.id)}</td><td>${cname(s.site)}</td><td class="small">首个访视 ${s.first} · 知情 ${s.icf}</td></tr>`).join('')}</tbody></table>`:''}</div>`;
}
/* ---------- 退出与数据质量 ---------- */
function dq(){
  const ds=SU.filter(s=>s.fd),wd=SU.filter(s=>s.status==='提前退出'||(s.eot_d&&s.status!=='完成试验'&&s.eot_why));
  const why=by(wd,s=>(s.eos_why||s.eot_why||'未注明').slice(0,30));
  const QS=by(D.queries,q=>q.site),SUB=Object.fromEntries(SU.map(s=>[s.id,s.site])),CRO=by(D.cro,c=>SUB[c[2]]||'');
  const oc=cat=>by(D.others.filter(o=>o.cat===cat),o=>o.site),date=oc('日期完整性核对'),rng=oc('参考范围缺失核对'),ENT=by(O.entry||[],e=>e.site);
  const qAll=D.queries.length/(ds.length||1),FR=O.fresh||{};
  const sq=sites.filter(si=>ds.some(s=>s.site===si)||(QS[si]||[]).length),qC=colCells(sq.map(si=>[(QS[si]||[]).length,ds.filter(s=>s.site===si).length]),qAll,true);
  pane.innerHTML=`<div class="grid g12"><div class="card"><div class="hd"><h2>提前退出 / 终止治疗原因</h2><span class="sub">${wd.length} 例</span></div><table class="t"><tbody>${Object.entries(why).sort((a,b)=>b[1].length-a[1].length).map(([k,v])=>`<tr><td class="small">${K.esc(k)}</td><td class="num">${v.length}</td><td class="small">${v.slice(0,6).map(s=>K.sid(s.id)+(s.fd&&end(s)?` <span class="xs faint">D${dd(end(s),s.fd)+1}</span>`:'')).join('　')}</td></tr>`).join('')||'<tr><td class="empty">无</td></tr>'}</tbody></table></div>
   <div class="card"><div class="hd"><h2>各中心数据质量</h2><span class="sub">申办方质疑按给药人数校正着色 · 数据新鲜度＝数据截止 − 最近一条记录</span></div><div style="overflow-x:auto"><table class="t heat"><thead><tr><th>中心</th><th class="num">给药</th><th class="num">申办方质疑</th><th class="num">CRO 质疑</th><th class="num">日期完整性</th><th class="num">参考范围缺失</th><th class="num">疑似录入错误</th><th class="num">最近记录</th></tr></thead><tbody>
    ${sq.map((si,i)=>{const n=ds.filter(s=>s.site===si).length,f=FR[si];
      return `<tr class="click" data-site="${si}"><td class="nowrap">${cname(si)}</td><td class="num">${n}</td><td class="num">${(QS[si]||[]).length?qC[i]:'·'}</td><td class="num">${(CRO[si]||[]).length||'·'}</td><td class="num">${(date[si]||[]).length||'·'}</td><td class="num">${(rng[si]||[]).length||'·'}</td><td class="num">${(ENT[si]||[]).length||'·'}</td><td class="num nowrap">${f?`${f[0]} ${f[2]&&f[1]>30?K.p(f[1]+' 天','yel'):`<span class="xs faint">${f[1]} 天</span>`}`:'—'}</td></tr>`}).join('')}</tbody></table></div></div></div>`;
  pane.querySelectorAll('tr[data-site]').forEach(tr=>tr.onclick=()=>location.href='center.html#c='+tr.dataset.site);
}
/* ---------- KRI 与研究层面容忍限度 ---------- */
function kri(){
  if(!KR){pane.innerHTML='<div class="card empty">本期数据不足以计算关键风险指标</div>';return}
  const defs=KR.defs,st=KR.study,HS=K.hist();
  /* 列内对照：期望＝研究层面率×分母，按不利方向取尾概率，按列 BH 校正 */
  const colF=d=>{const rows=sites.map(si=>(KR.sites[si]||{})[d.k]||[null,0]),all=st[d.k]&&st[d.k][1]?st[d.k][0]/st[d.k][1]:0;
    if(d.u==='天')return rows.map(([v])=>v!=null&&v>30?'background:rgba(232,195,0,.22)':'');
    const x=rows.map(([n,dn])=>n!=null&&dn?K.oe(n,dn,all):null),pu=K.bh(x.map(o=>o&&d.dir!=='low'?o.pu:null)),pl=K.bh(x.map(o=>o&&d.dir!=='high'?o.pl:null));
    return x.map((o,i)=>o?K.qStyle(pu[i],pl[i]):'')};
  const flags=Object.fromEntries(defs.map(d=>[d.k,colF(d)]));
  pane.innerHTML=`<div class="card"><div class="hd"><h2>研究层面容忍限度</h2><span class="sub">关键质量因素的研究层面指标（ICH E6(R3) §3.10.1.3：申办方预设可接受范围）；默认档为经验值，需研究团队确认</span></div><div id="qtl"></div></div>
   <div class="card mt"><div class="hd"><h2>各中心 KRI</h2><span class="sub">红框＝超出研究层面限度（分母 ≥5）；底色＝与其他中心相比偏高（橙）或偏低（蓝），校正多重比较；点中心进入画像</span></div>
    <div style="overflow-x:auto"><table class="t heat"><thead><tr><th>中心</th>${defs.map(d=>`<th class="h" title="${K.esc(d.note)}">${K.esc(d.l)}<div class="xs faint" style="font-weight:400">${d.u}${d.qtl?' · 限 '+K.qtlLim(d.k):''}</div></th>`).join('')}</tr></thead><tbody>
    <tr class="pin" style="background:#FAFAFB"><td><b>研究整体</b></td>${defs.map(d=>`<td class="num"><b>${(KR.na||{})[d.k]?'—':K.kriFmt(d.k,K.kriV(d.k,st[d.k]))}</b></td>`).join('')}</tr>
    ${sites.map((si,i)=>`<tr class="click" data-site="${si}"><td class="nowrap">${cname(si)}</td>${defs.map(d=>{const nd=(KR.sites[si]||{})[d.k],v=K.kriV(d.k,nd),q=d.qtl&&nd&&nd[1]>=5?K.qtlState(d.k,nd):{};
      return `<td class="num" style="${flags[d.k][i]}${q.st==='exceed'?';outline:2px solid #8B0000;outline-offset:-2px':''}" title="${nd?K.esc(nd[0]+' / '+nd[1]):''}">${(KR.na||{})[d.k]||v==null?'<span class="faint">·</span>':K.kriFmt(d.k,v)}</td>`}).join('')}</tr>`).join('')}</tbody></table></div>
    ${Object.keys(KR.na||{}).length?`<div class="xs muted mt">未计算：${Object.entries(KR.na).map(([k,v])=>`${K.esc((K.kriDef(k)||{}).l||k)}（${K.esc(v)}）`).join('；')}</div>`:''}
    ${KR.pem&&KR.pem.items&&KR.pem.items.length?`<div class="xs muted mt">主要终点缺失：关键访视 ${K.esc(KR.pem.visits.join('、'))}，关键评估按数据中的「${K.esc(KR.pem.items.join('、'))}」判定</div>`:''}</div>
   <div class="card mt" id="kh"></div>`;
  K.qtlTiles(document.getElementById('qtl'));
  const kh=document.getElementById('kh');
  if(HS.length>=2){const q=defs.filter(d=>d.qtl&&!(KR.na||{})[d.k]);kh.innerHTML=`<div class="hd"><h2>跨上传趋势</h2><span class="sub">研究层面数值随上传变化（${HS.length} 次）· 虚线为当前档位限度</span></div><div class="grid g4">${q.map((d,i)=>`<div><div class="xs muted">${K.esc(d.l)}</div><div id="kt${i}" style="height:90px"></div></div>`).join('')}</div>`;
    q.forEach((d,i)=>K.chart(document.getElementById('kt'+i),{grid:{left:30,right:6,top:8,bottom:18},tooltip:{trigger:'axis'},xAxis:{type:'category',data:HS.map(h=>(h.cutoff||'').slice(5)),...K.axis},yAxis:{type:'value',...K.axis},
      series:[{type:'line',data:HS.map(h=>{const nd=(h.kri||{})[d.k];return nd&&nd[1]?+(K.kriV(d.k,nd)).toFixed(2):null}),connectNulls:true,lineStyle:{color:'#FF9900'},itemStyle:{color:'#FF9900'},markLine:{symbol:'none',silent:true,data:[{yAxis:K.qtlLim(d.k)}],lineStyle:{color:'#8B0000',type:'dashed'},label:{show:false}}}]}))}
  else kh.innerHTML='<div class="hd"><h2>跨上传趋势</h2></div><div class="empty">首次数据：后续每次上传新数据后，这里显示各指标随时间的变化</div>';
  pane.querySelectorAll('tr[data-site]').forEach(tr=>tr.onclick=()=>location.href='center.html#c='+tr.dataset.site);
}
/* ---------- 录入及时性（工作台按快照谱系推算） ---------- */
function time(){
  if(!TL||!TL.sites){pane.innerHTML=`<div class="card"><div class="hd"><h2>录入及时性</h2></div><div class="note">暂无录入时间信息：多次上传数据后，这里显示各中心的录入延迟和记录修改比例。</div></div>`;return}
  const S=TL.sites;
  pane.innerHTML=`<div class="note small mb">录入延迟按记录首次出现的上传批次估算（为上限）；修改率＝被修改或删除的记录占比。共 ${TL.snaps||'—'} 次上传。</div>
  <div class="card"><table class="t heat"><thead><tr><th>中心</th><th class="num">新增访视记录</th><th class="num">延迟中位数（天）</th><th class="num">P90（天）</th><th class="num">>14 天占比</th><th class="num">修改/删除率</th><th>最近一次有新数据</th></tr></thead><tbody>
   ${Object.keys(S).sort().map(si=>{const x=S[si];return `<tr class="click" data-site="${si}"><td class="nowrap">${cname(si)}</td><td class="num">${x.n??'—'}</td><td class="num" style="${x.med>14?'background:rgba(230,126,0,.30)':''}">${x.med??'—'}</td><td class="num">${x.p90??'—'}</td><td class="num">${x.n?(x.gt14/x.n*100).toFixed(0)+'%':'—'}</td><td class="num">${x.mod&&x.mod[1]?(x.mod[0]/x.mod[1]*100).toFixed(1)+'%':'—'}</td><td class="nowrap small">${K.esc(x.lastNew||'—')}</td></tr>`}).join('')}</tbody></table></div>`;
  pane.querySelectorAll('tr[data-site]').forEach(tr=>tr.onclick=()=>location.href='center.html#c='+tr.dataset.site);
}
/* ---------- 数据可信度（中心层面，建议核对） ---------- */
function cred(){
  if(!CRD){pane.innerHTML='<div class="card empty">本构建没有数据可信度数据</div>';return}
  const S=CRD.sites,pc=x=>x==null?'—':x<.001?'<0.001':x.toFixed(3);
  pane.innerHTML=`<div class="note small mb">${K.esc(CRD.note||'')}。末位数字：血压/心率整数结果末位为 0 或 5 的占比（随机约 20%，全研究 ${CRD.digAll[1]}/${CRD.digAll[0]}）；完全相同：同一受试者同一生命体征 ≥4 次结果完全相同；基线偏离：各中心基线生命体征均值与整体相比（按指标检验并校正）；同日相同：同一中心同一天多名受试者血压与心率完全相同。</div>
  <div class="card"><table class="t heat"><thead><tr><th>中心</th><th class="num">末位 0/5 占比</th><th class="num">q</th><th class="num">≥4 次完全相同</th><th class="num">q</th><th class="num">基线偏离指标</th><th>偏离最大的指标</th><th class="num">同日相同</th><th>提示</th></tr></thead><tbody>
   ${Object.keys(S).sort().map(si=>{const v=S[si],f=K.credFlags(si,v);return `<tr class="click" data-site="${si}"><td class="nowrap">${cname(si)}</td>
     <td class="num" style="${v.dig[3]!=null&&v.dig[3]<.05?'background:rgba(230,126,0,.30)':''}">${v.dig[0]?(v.dig[1]/v.dig[0]*100).toFixed(0)+'% <span class="xs faint">'+v.dig[1]+'/'+v.dig[0]+'</span>':'—'}</td><td class="num xs">${pc(v.dig[3])}</td>
     <td class="num" style="${v.flat[3]!=null&&v.flat[3]<.10&&v.flat[1]>=2?'background:rgba(230,126,0,.30)':''}">${v.flat[1]}/${v.flat[0]}</td><td class="num xs">${pc(v.flat[3])}</td>
     <td class="num" style="${v.shift[1]>=2?'background:rgba(230,126,0,.30)':''}">${v.shift[1]}/${v.shift[0]}</td><td class="small">${v.shift[2].slice(0,2).map(x=>`${K.esc(x[0])} ${x[3]}（整体 ${x[4]}）`).join('；')}</td>
     <td class="num">${v.dup[0]||'·'}</td><td>${f.map(x=>K.p(x.l,'yel')).join('')}</td></tr>`}).join('')}</tbody></table></div>
  <div class="grid g12 mt"><div class="card"><div class="hd"><h2>≥4 次完全相同</h2><span class="sub">${CRD.flat.length} 组</span></div><div id="cf"></div></div><div class="card"><div class="hd"><h2>同日多名受试者生命体征完全相同</h2><span class="sub">${CRD.dup.length} 组</span></div><div id="cd"></div></div></div>`;
  K.table(document.getElementById('cf'),{rows:CRD.flat.map(r=>({sid:r[0],site:r[1],t:r[2],v:r[3],n:r[4]})),h:'320px',cols:[{k:'sid',t:'受试者',f:r=>K.sid(r.sid)},{k:'site',t:'中心',f:r=>K.p(r.site,'sq mono')},{k:'t',t:'指标'},{k:'v',t:'结果'},{k:'n',t:'次数',cls:'num'}]});
  K.table(document.getElementById('cd'),{rows:CRD.dup.map(r=>({site:r[0],d:r[1],s:r[2],v:r[3]})),h:'320px',cols:[{k:'site',t:'中心',f:r=>K.p(r.site,'sq mono')},{k:'d',t:'日期'},{k:'s',t:'受试者',ns:1,f:r=>r.s.map(x=>K.sid(x)).join(' ')},{k:'v',t:'收缩压/舒张压/心率'}]});
  pane.querySelectorAll('tr[data-site]').forEach(tr=>tr.onclick=()=>{const si=tr.dataset.site,f=K.credFlags(si,S[si]);if(!f.length)return location.href='center.html#c='+si;
    const b=K.drawer(`${si} ${K.esc(CN[si]||'')} · 数据可信度`,`${f.map((x,i)=>`<div class="sec-t"><h2>${K.esc(x.l)}</h2></div><div class="box small">${K.esc(x.why)}</div>`).join('')}<div class="note small mt">${K.esc(CRD.note||'')}</div><div class="mt"><a class="small" href="center.html#c=${si}">中心画像 ›</a></div>`);});
}
/* ---------- 疑似录入错误 ---------- */
function ent(){
  const E=O.entry||[];
  pane.innerHTML=`<div class="note small mb">同一受试者同一指标，某次结果为本人其余结果的约 10 的整数次幂倍（疑似小数点错位）或 ≥20 倍且为孤立尖峰（前后两次都正常范围波动），或单位与本人其余记录不同。只作数据质量提示（请 CRA 核对源数据），不发医学质疑；若该点同时进了医学风险层，风险行已标注「可能为录入错误，请先核对源数据」。</div>
  <div class="card"><div id="et"></div></div>`;
  K.table(document.getElementById('et'),{rows:E,sort:'site',dir:1,h:'620px',onRow:r=>K.showEnt(r),
    cols:[{k:'sid',t:'受试者',f:r=>K.sid(r.sid)},{k:'site',t:'中心',f:r=>cname(r.site)},{k:'test',t:'指标',f:r=>`<b>${K.esc(r.test)}</b>${r.ctq?K.p('关键','solid-red',r.ctq):''}`},{k:'visit',t:'访视',f:r=>K.p(r.visit,'blu')+` <span class="xs faint">${K.esc(r.date)}</span>`},
      {k:'raw',t:'录入值',f:r=>`<b>${K.esc(r.raw)}</b> <span class="xs muted">${K.esc(r.unit)}</span>`},{k:'why',t:'判断',f:r=>`<span class="small">${K.esc(r.why)}</span>`},{k:'row',t:'来源',f:r=>`<span class="xs faint">${K.esc(K.loc(r.sh,r.row))}</span>`}]});
}
K.qtlBar(document.getElementById('qtlbar'));
K.tabs(document.getElementById('tabs'),tabs,H.tab&&R[H.tab]?H.tab:'enr',v=>{K.setHash({tab:v});R[v]()});   /* 放在末尾：tabs 会立即渲染默认页签，所用的函数与常量须已定义 */
});
