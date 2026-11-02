K.init(()=>{
const D=KZ,app=document.getElementById('app'),P=D.pd,H=K.hash();
if(!P){app.innerHTML='<div class="card empty">本报告未启用方案偏离分析</div>';return}
const POT=P.potential||[],CONF=P.confirmed||[],TAX=P.taxonomy||[],TX=K.pdTax(),RULES=P.rules||[];
const G=['重要','待判定','一般'],GC={'重要':'#8B0000','待判定':'#E8C300','一般':'#C9CCD1'};
const imp=a=>a.filter(x=>x.grade==='重要').length;
const exe=POT.filter(x=>x.layer==='执行'),sci=POT.filter(x=>x.layer!=='执行');
const subj=new Set(POT.map(x=>x.sid).concat(CONF.map(x=>x.sid))),sites=new Set(POT.map(x=>x.site).concat(CONF.map(x=>x.site)));
const ran=RULES.filter(r=>r.state==='ran').length;
app.innerHTML=`
<div class="flex mb"><h1 style="font-size:18px">方案偏离</h1><span class="muted small">已记录 PD（方案偏离记录表）· 潜在 PD（数据推断，待 CRA/研究者核实，不计入 PD 率）· 分级：重要 / 待判定 / 一般</span><span class="sp"></span>${(K.cfg().blind||{}).on?K.p('盲态','blu'):''}</div>
<div class="kpis">
 <div class="kpi risk"><div class="l">已记录 PD</div><div class="v">${CONF.length}<small>条</small></div><div class="s">${P.hasListing?K.p('重要 '+imp(CONF),'solid-red')+K.p('待判定 '+CONF.filter(x=>x.grade==='待判定').length,'yel')+K.p('一般 '+CONF.filter(x=>x.grade==='一般').length,'line'):K.p('未提供方案偏离记录表','line')}</div></div>
 <div class="kpi"><div class="l">潜在 PD · 执行层面</div><div class="v">${exe.length}<small>条</small></div><div class="s">${K.p('重要 '+imp(exe),'solid-red')}${K.p('待判定 '+exe.filter(x=>x.grade==='待判定').length,'yel')}</div></div>
 <div class="kpi"><div class="l">潜在 PD · 科学层面</div><div class="v">${sci.length}<small>条</small></div><div class="s">${K.p('重要 '+imp(sci),'solid-red')}${K.p('待判定 '+sci.filter(x=>x.grade==='待判定').length,'yel')}</div></div>
 <div class="kpi"><div class="l">潜在 PD 未见记录</div><div class="v">${P.hasListing===false?'—':POT.filter(x=>x.status==='未见记录').length}<small>/ ${POT.length}</small></div><div class="s">${K.p('已记录 '+POT.filter(x=>x.status==='已记录').length,'grn')}${P.hasListing?'':K.p('无方案偏离记录表可比对','line')}</div></div>
 <div class="kpi blu"><div class="l">涉及受试者 / 中心</div><div class="v">${subj.size}<small>例 · ${sites.size} 个中心</small></div><div class="s">${K.p('数据截止 '+(P.cutoff||D.meta.cutoff||''),'line')}</div></div>
 <div class="kpi grn"><div class="l">检查覆盖</div><div class="v">${ran}<small>/ ${RULES.length} 项已执行</small></div><div class="s">${K.p('未执行 '+RULES.filter(r=>r.state!=='ran').length,'line')}${K.p('需源文件核查 '+(P.notDetectable||[]).length+' 类','brn')}</div></div>
</div>
<div class="grid g12 mt">
 <div class="card"><div class="hd"><h2>类别 × 分级</h2><span class="sub">潜在 PD 按分级堆叠；点击行筛选下方清单</span><span class="sp"></span><span class="legend">${G.map(g=>`<span><i class="dot" style="background:${GC[g]}"></i> ${g}</span>`).join('')}</span></div><div id="mx"></div></div>
 <div class="card"><div class="hd"><h2>中心分布</h2><span class="sub">潜在 PD 每例受试者条数；颜色越深越偏高</span></div><div id="st"></div></div>
</div>
<div class="tabs mt" id="tabs"></div><div id="pane"></div>`;
/* ---------- 类别 × 分级矩阵 ---------- */
const cats=TAX.map(t=>t[0]).filter(c=>POT.some(x=>x.cat===c)||CONF.some(x=>x.cat===c));
const mxRows=cats.map(c=>{const p=POT.filter(x=>x.cat===c),f=CONF.filter(x=>x.cat===c);return {c,p,f,n:p.length,g:G.map(g=>p.filter(x=>x.grade===g).length),miss:p.filter(x=>x.status==='未见记录').length}});
const mxMax=Math.max(1,...mxRows.map(r=>r.n));
const F={tab:H.tab||'exe',cat:H.cat||null,g:[],st:null,site:'',s:''};
function drawMx(){app.querySelector('#mx').innerHTML=`<div class="tw"><table class="t pdm"><thead><tr><th>类别</th><th class="c">已记录</th><th>潜在（重要/待判定/一般）</th><th class="c">潜在</th><th class="c">未见记录</th></tr></thead><tbody>${mxRows.map(r=>{const t=TX[r.c]||[];return `<tr class="click ${F.cat===r.c?'on':''}" data-c="${r.c}"><td class="nowrap">${K.pdCat(r.c)} <span class="lay">${t[2]||''}${t[2]&&t[2]!=='—'?'层面':''}</span></td><td class="c">${r.f.length?`<b>${r.f.length}</b>${imp(r.f)?' '+K.p('重 '+imp(r.f),'red'):''}`:'<span class="faint">·</span>'}</td>
 <td><div class="bar2" style="width:${Math.max(18,r.n/mxMax*100)}%">${G.map((g,i)=>r.g[i]?`<i style="width:${r.g[i]/Math.max(1,r.n)*100}%;background:${GC[g]}" title="${g} ${r.g[i]}"></i>`:'').join('')}</div></td>
 <td class="c">${r.n?`<b>${r.n}</b>`:'<span class="faint">·</span>'}</td><td class="c">${r.miss?K.p(r.miss,'org'):'<span class="faint">·</span>'}</td></tr>`}).join('')||'<tr><td colspan="5" class="empty">无方案偏离</td></tr>'}</tbody></table></div>`;
 app.querySelectorAll('#mx tr[data-c]').forEach(tr=>tr.onclick=()=>{const c=tr.dataset.c;F.cat=F.cat===c?null:c;const lay=(TX[c]||[])[2];if(F.cat&&F.tab!=='conf')F.tab=lay==='执行'?'exe':'sci';drawMx();tabs.set(F.tab)})}
drawMx();
/* ---------- 中心分布 ---------- */
const dosedBy={};K.subs().filter(s=>s.fd).forEach(s=>dosedBy[s.site]=(dosedBy[s.site]||0)+1);
const st=[...sites].sort().map(s=>{const p=POT.filter(x=>x.site===s),f=CONF.filter(x=>x.site===s);const cc={};p.forEach(x=>cc[x.cat]=(cc[x.cat]||0)+1);return {site:s,name:K.center(s),n:dosedBy[s]||0,pot:p.length,rate:dosedBy[s]?p.length/dosedBy[s]:null,imp:imp(p),conf:f.length,top:Object.entries(cc).sort((a,b)=>b[1]-a[1]).slice(0,3)}});
const rmax=Math.max(.01,...st.map(r=>r.rate||0));
K.table(app.querySelector('#st'),{rows:st,sort:'rate',h:'300px',noPage:true,onRow:r=>{F.site=F.site===r.site?'':r.site;drawPane()},cols:[
 {k:'site',t:'中心',f:r=>`<span class="nowrap">${K.p(r.site,'sq mono')} ${K.esc(r.name.length>10?r.name.slice(0,10)+'…':r.name)}</span>`},{k:'n',t:'给药',cls:'num'},
 {k:'pot',t:'潜在',cls:'num'},{k:'rate',t:'每例',cls:'num',f:r=>r.rate==null?'—':`<span style="background:rgba(139,0,0,${(r.rate/rmax*.45).toFixed(2)});padding:1px 6px;border-radius:4px;color:${r.rate/rmax>.6?'#fff':'inherit'}">${r.rate.toFixed(2)}</span>`,tip:'潜在 PD 条数 / 给药受试者数'},
 {k:'imp',t:'重要',cls:'num',f:r=>r.imp?K.p(r.imp,'solid-red'):'·'},{k:'conf',t:'已记录',cls:'num',f:r=>r.conf||'·'},
 {k:'top',t:'主要类别',ns:1,f:r=>r.top.map(([c,n])=>`<span class="xs muted">${K.esc((TX[c]||[])[1]||c)} ${n}</span>`).join(' · ')}]});
/* ---------- 清单 ---------- */
const pane=app.querySelector('#pane');
function potList(rows,title){
 pane.innerHTML=`<div class="tbar"><div class="chips" id="fg"></div><div class="chips" id="fs"></div><span class="sp"></span><select class="s" id="fc"><option value="">全部类别</option>${cats.filter(c=>rows.some(x=>x.cat===c)).map(c=>`<option value="${c}" ${F.cat===c?'selected':''}>${K.esc((TX[c]||[])[1]||c)}</option>`).join('')}</select><select class="s" id="fsi"><option value="">全部中心</option>${[...sites].sort().map(s=>`<option value="${s}" ${F.site===s?'selected':''}>${s} ${K.esc(K.center(s))}</option>`).join('')}</select><input class="s" id="fq" placeholder="受试者 / 事实关键词" value="${K.esc(F.s)}"></div><div class="tbar" id="chg-pd"></div><div id="tb"></div>
 <div class="note mt xs muted">${title} · 潜在 PD 由数据推断，待核实：「发 query」= 数据层面可澄清；「CRA 核实」= 需源文件；「录入 PD」= 数据已足以确认。确认属实后录入方案偏离记录，按分级报告伦理与申办方（GCP 2026 第二十三条）。</div>`;
 K.chips(pane.querySelector('#fg'),G.map(g=>[g,g,rows.filter(x=>x.grade===g).length]),v=>{F.g=v;draw()},{multi:true,value:F.g,all:'全部分级'});
 K.chips(pane.querySelector('#fs'),['未见记录','已记录'].map(s=>[s,s,rows.filter(x=>x.status===s).length]).filter(x=>x[2]),v=>{F.st=v;draw()},{all:'全部比对',value:F.st});
 pane.querySelector('#fc').onchange=e=>{F.cat=e.target.value||null;drawMx();draw()};pane.querySelector('#fsi').onchange=e=>{F.site=e.target.value;draw()};pane.querySelector('#fq').oninput=e=>{F.s=e.target.value.trim();draw()};
 const tb=K.table(pane.querySelector('#tb'),{rows:[],pageSize:40,onRow:r=>{K.setHash({tab:F.tab,id:r.id});K.showPD(r.id)},cols:[
  {k:'grade',t:'分级',f:r=>K.pdGrade(r.grade)+K.dpill('pd',r)+(r.ctq?K.p('关键','solid-red',r.ctq):'')+K.sigPill('pd',r),s:r=>G.indexOf(r.grade),w:'84px'},{k:'cat',t:'类别',f:r=>K.pdCat(r.cat),w:'118px'},
  {k:'sid',t:'受试者',f:r=>`${K.sid(r.sid)} <span class="xs faint">${r.site}</span>`,w:'90px'},{k:'date',t:'访视 / 日期',f:r=>`${r.visit?K.p(r.visit,'blu'):''}<div class="xs muted nowrap">${r.date||''}</div>`,w:'96px'},
  {k:'fact',t:'偏离事实（数据推断）',ns:1,f:r=>`<b class="small" style="color:var(--ink)">${K.esc(r.title)}</b><div class="small" style="margin-top:2px;line-height:1.6">${K.hlNum(r.fact)}</div>`},
  {k:'status',t:'比对',f:r=>`${K.pdStatus(r.status)}${r.matched?`<div class="xs mono faint" style="margin-top:2px">${r.matched}</div>`:''}`,w:'84px'},
  {k:'action',t:'处理',f:r=>K.pdAct(r.action),w:'76px'},
  {k:'sig',t:'关联',ns:1,f:r=>{const s=r.sig?(r.sig[0]==='oth'?D.others[r.sig[1]]:D.labrows[r.sig[1]]):null;return s?(s.q||[]).map(K.qPill).join('')||`<span class="xs faint">${r.sig[0]==='lab'?'检验风险':'专项信号'}</span>`:''},w:'70px'}]});
 const cfP=K.chgBar(pane.querySelector('#chg-pd'),'pd',()=>draw(),'潜在 PD'),sgP=K.sigBar(pane.querySelector('#chg-pd'),()=>draw());
 document.addEventListener('kz-sig',()=>{if(pane.contains(tb&&pane.querySelector('#tb')))draw()});
 function draw(){const s=F.s.toLowerCase();tb.set(rows.filter(r=>cfP(r)&&sgP('pd',r)&&(!F.g.length||F.g.includes(r.grade))&&(!F.st||r.status===F.st)&&(!F.cat||r.cat===F.cat)&&(!F.site||r.site===F.site)&&(!s||(r.sid+r.fact+r.title).toLowerCase().includes(s))))}
 draw();
}
function confList(){
 pane.innerHTML=CONF.length?`<div id="tb"></div><div class="note mt xs muted">已记录 PD 来自方案偏离记录表；按类别归入统一分类（原文类别保留），严重程度原文映射为 重要/一般/待判定。「数据比对」列出数据推断出的同类潜在 PD；未命中多为需现场核查的偏离（知情同意文件、药物管理、伦理等）。</div>`:`<div class="card empty">${P.hasListing?'方案偏离记录表为空':'未提供方案偏离记录表：已记录 PD 不可用；潜在 PD 照常识别（状态标「无 PD 记录可比对」）'}</div>`;
 if(!CONF.length)return;
 K.table(pane.querySelector('#tb'),{rows:CONF.filter(r=>(!F.cat||r.cat===F.cat)&&(!F.site||r.site===F.site)),pageSize:40,onRow:r=>K.showPD(r.id),cols:[
  {k:'id',t:'编号',f:r=>K.p(r.id,'sq mono line'),w:'62px'},{k:'grade',t:'分级',f:r=>`${K.pdGrade(r.grade)}${r.rawGrade?`<div class="xs faint" style="margin-top:2px">${K.esc(r.rawGrade)}</div>`:''}`,s:r=>G.indexOf(r.grade),w:'84px'},
  {k:'cat',t:'类别',f:r=>`${K.pdCat(r.cat)}<div class="xs faint" style="margin-top:2px">${K.esc(r.rawCat)}</div>`,w:'110px'},{k:'sid',t:'受试者',f:r=>`${K.sid(r.sid)} <span class="xs faint">${r.site}</span>`,w:'90px'},
  {k:'date',t:'日期',f:r=>`<span class="nowrap xs">${r.date||'—'}</span>`,w:'86px'},{k:'desc',t:'偏离描述（原文）',ns:1,f:r=>`<span class="small">${K.esc(r.desc)}</span>${r.sub?` <span class="xs faint">${K.esc(r.sub)}</span>`:''}`},
  {k:'matched',t:'数据比对',ns:1,f:r=>r.matched.length?r.matched.map(x=>K.p(x,'sq mono grn')).join(''):'<span class="xs faint">数据未覆盖</span>',w:'110px'}]});
}
function soaPane(){pane.innerHTML=`<div class="card"><div class="hd"><h2>访视流程表 × 实际完成</h2><span class="sub">已给药受试者 · 点击单元格查看缺失名单（「缺」即评估缺失的潜在 PD 来源）</span><span class="sp"></span><span class="legend"><span>${K.p('✓','grn')} 全部完成</span><span>${K.p('缺','red')} 无记录</span><span>${K.p('否','yel')} 记录“未做”</span><span>${K.p('条件','line')} 条件性项目</span><span>${K.p('+n','')} 计划外</span></span></div><div id="soa"></div></div>`;K.soaView(pane.querySelector('#soa'))}
function rulesPane(){
 const stl={ran:['已执行','grn'],unconfigured:['未执行','line'],'no-data':['缺数据未执行','yel'],'stage-off':['日常监查阶段不判定','line']};
 const nd=P.notDetectable||[];
 pane.innerHTML=`<div id="rt"></div>
 <div class="grid g2 mt"><div class="card"><div class="hd"><h2>只能经源文件核查 / 外部系统确认</h2><span class="sub">数据表不含所需信息，不从数据推断</span></div>${nd.map(([c,t])=>`<div class="flex" style="align-items:flex-start;margin:5px 0">${K.pdCat(c)}<span class="small">${K.esc(t)}</span></div>`).join('')}</div>
 <div class="card"><div class="hd"><h2>分级口径</h2><span class="sub">依据与默认值</span></div>
  <div class="kv"><dt>${K.pdGrade('重要')}</dt><dd class="small">可能显著影响受试者权益、安全或福祉，或显著影响关键数据（主要/关键次要终点、关键安全评估、随机与盲态）的完整性、准确性、可靠性（ICH E3 Q&A R1；ICH E6(R3) §3.9.3）。</dd>
  <dt>${K.pdGrade('待判定')}</dt><dd class="small">需结合原因、源文件或医学判断：如禁用药是否影响疗效评价、潜在 AE 漏记是否属实、评估未做是否属方案允许情形。</dd>
  <dt>${K.pdGrade('一般')}</dt><dd class="small">不满足重要标准，如非关键访视小幅超窗、非关键评估缺失；同一中心同类反复发生时应升级审视（TransCelerate PDAP 阈值）。</dd>
  <dt>升级条件</dt><dd class="small">关键访视：${(P.critical.visits||[]).join('、')||'方案未指定'}；关键评估：${K.esc(K.rxl(P.critical.items)||'方案未指定')}；数值达 ≥3 级的潜在 AE 漏记；影响主要终点的禁用药类别。</dd>
  <dt>不算 PD</dt><dd class="small">按方案条件使用的补救治疗（属伴发事件，ICH E9(R1)）；与方案无关的 GCP 问题；录入错误更正后不再偏离。</dd></div></div></div>`;
 K.table(pane.querySelector('#rt'),{rows:RULES,noPage:true,max:false,cols:[
  {k:'cat',t:'类别',f:r=>K.pdCat(r.cat),w:'100px'},{k:'title',t:'检查',f:r=>`<b class="small" style="color:var(--ink)">${K.esc(r.title)}</b><div class="xs muted" style="margin-top:2px;line-height:1.6">${K.esc(r.logic)}</div>`},
  {k:'grade',t:'默认分级',f:r=>K.pdGrade(r.grade),w:'70px'},{k:'action',t:'处理',f:r=>K.pdAct(r.action),w:'76px'},{k:'data',t:'所需数据',f:r=>`<span class="xs">${K.esc(r.data)}</span>`,w:'150px'},
  {k:'state',t:'本次',f:r=>`${K.p((stl[r.state]||[r.state])[0],(stl[r.state]||['',''])[1])}${r.state==='ran'?`<div class="xs" style="margin-top:2px"><b>${r.n}</b> 条</div>`:''}${r.reason?`<div class="xs muted" style="margin-top:2px;line-height:1.5">${K.esc(r.reason)}</div>`:''}`,w:'170px'}]});
}
const tabs=K.tabs(app.querySelector('#tabs'),[['exe','潜在 PD · 执行层面',exe.length],['sci','潜在 PD · 科学层面',sci.length],['conf','已记录 PD',CONF.length],['soa','SoA 完成度',null],['rules','检查规则与覆盖',ran+'/'+RULES.length]],F.tab,v=>{F.tab=v;K.setHash({tab:v});drawPane()});
function drawPane(){F.tab==='exe'?potList(exe,'执行层面：访视、评估、给药、样本、知情、随机'):F.tab==='sci'?potList(sci,'科学层面：入组资格、合并用药、安全性记录与报告、退出与停药'):F.tab==='conf'?confList():F.tab==='soa'?soaPane():rulesPane()}
if(H.id)setTimeout(()=>K.showPD(H.id),60);
});
