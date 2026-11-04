K.init(()=>{
const D=KZ,X=KZX,app=document.getElementById('app');
const qn=cats=>D.queries.filter(q=>cats.includes(q.cat)).length;
const qlink=(cats,lab)=>{const n=qn(cats);return n?`<a class="small" href="#" data-qc="${K.esc(cats.join('|'))}">${lab||'相关质疑'} ${n} 条 ›</a>`:`<span class="small faint">${lab||'相关质疑'} 0</span>`};
document.addEventListener('click',e=>{const a=e.target.closest('[data-qc]');if(!a)return;e.preventDefault();const cats=a.dataset.qc.split('|');const qs=D.queries.filter(q=>cats.includes(q.cat));
 K.drawer('相关医学质疑',`<table class="t"><tbody>${qs.map(q=>`<tr class="click" data-q="${q.id}"><td>${K.qPill(q.id)}</td><td>${K.sid(q.sid)}</td><td>${K.p(K.catN(q.cat),'line')}<div class="small mt" style="margin-top:3px">${K.hlNum(q.text)}</div></td></tr>`).join('')}</tbody></table>`,qs.length+' 条')});
const R=(...ids)=>ids.map(i=>K.rp(i)).join('');
/* ---------- design (KZ.study, generated from protocol extraction) ---------- */
const ST=D.study||{},DS=ST.design||{},st=D.meta.status;
const pills=a=>(a||[]).map(x=>Array.isArray(x)?K.p(x[0],x[1]||'line'):K.p(x,'line')).join('');
const secHide=k=>(ST.hide||[]).includes(k);
app.innerHTML=`<div class="flex mb"><h1 style="font-size:18px">研究依据</h1><span class="muted small">本报告每一条判断依据什么：研究概况 → 关键口径 → 按监查领域的规则 → 方案/IB 原文规则库（数据结果见各分析页）</span></div>

<div class="card"><div class="hd"><h2>研究设计</h2><span class="sub">${K.esc(DS.sub||'')}</span><span class="sp"></span>${R(...(DS.refs||[]))}</div>
 <div class="flow">${(DS.flow||[]).map(f=>`<div class="st${f.hot?' hot':''}"><span class="n">${K.esc(f.n||'')}</span><b>${K.esc(f.b||'')}</b><span class="xs muted">${K.esc(f.x||'')}</span></div>`).join('')}</div>
 <div class="grid g3 mt" style="grid-template-columns:${[(DS.arms||{}).items,(DS.baselines||{}).items].filter(a=>(a||[]).length).map(()=>'1.2fr ').join('')}1.2fr">
  ${((DS.arms||{}).items||[]).length?`<div><div class="muted xs mb" style="margin-bottom:4px">${K.esc((DS.arms||{}).label||'组别')}</div>${pills((DS.arms||{}).items)}</div>`:''}
  ${((DS.baselines||{}).items||[]).length?`<div><div class="muted xs" style="margin-bottom:4px">${K.esc((DS.baselines||{}).label||'规定基线')} ${R(...((DS.baselines||{}).refs||[]))}</div>${pills((DS.baselines||{}).items)}</div>`:''}
  <div><div class="muted xs" style="margin-bottom:4px">截至 ${K.esc(D.meta.cutoff)}</div>${K.p('筛选 '+D.meta.n,'line')}${K.p('给药 '+D.meta.dosed,'org')}${Object.entries(st).filter(([k])=>k!=='筛选失败').map(([k,v])=>K.p(k+' '+v,K.STC[k]??'')).join('')}${DS.planned?K.p('计划 '+DS.planned,'line'):''}</div>
 </div></div>

${(DS.facts||[]).length||(ST.endpoints||[]).length?`<div class="card mt"><div class="grid g2" style="gap:6px 24px">${(DS.facts||[]).length?`<div><div class="muted xs" style="margin-bottom:4px">研究要素</div><div class="kv">${DS.facts.map(f=>`<dt>${K.esc(f[0])}</dt><dd>${K.esc(f[1])} ${f[2]?K.rp(f[2]):''}</dd>`).join('')}</div></div>`:''}
 ${(ST.endpoints||[]).length?`<div><div class="muted xs" style="margin-bottom:4px">终点</div>${ST.endpoints.map(e=>`<div class="flex" style="align-items:flex-start;margin:3px 0">${K.p(e[0],/主要|primary/i.test(e[0])?'org':'line')}<span class="small">${K.esc(e[1])}</span>${e[2]?K.rp(e[2]):''}</div>`).join('')}</div>`:''}</div></div>`:''}
<div class="sec-t"><h2>关键口径</h2><span class="muted small">全报告共用的定义与采用口径；状态：方案规定（有原文）/ 口径裁定 / 待确认 / 项目配置（已配置、规则库未引原文）/ 默认采用（方案未规定）</span></div>
<div class="cal" id="cal"></div>
<div class="sec-t"><h2>监查规则</h2><span class="muted small">按监查领域：方案/IB 原文 → 用数据核对什么 → 结果在哪一页</span></div>
<div class="tabs" id="rtab"></div><div id="rpane"></div>
<div class="sec-t"><h2>方案 / IB 规则库</h2><span class="muted small" id="rn"></span><span class="sp"></span><input class="s" id="rs" placeholder="搜索 规则文字"></div>
<div class="chips mb" id="rd"></div><div id="rules"></div>
<div class="card mt" id="sysnote"><div class="hd"><h2>系统提示</h2><span class="sub">构建与审阅过程中需要人处理的事项（映射、词表、AI 审阅、CS 解释待确认等），不属于数据风险</span></div><div id="todo"></div></div>`;
/* V6（用户审阅 RUX 裁定 2）：系统提示从总览移到研究依据页底部；工作台系统层（kz-sys.js）向 #todo 追加 CS 解释待确认等行 */
{const T=(D.todo||[]);document.getElementById('todo').innerHTML=T.length?`<table class="t"><tbody>${T.map(t=>`<tr class="click" onclick="location.href='${t[3]}'"><td style="width:90px">${K.p(t[0],t[1])}</td><td>${t[2]}</td><td class="faint">›</td></tr>`).join('')}</tbody></table>`:'<table class="t"><tbody></tbody></table><div class="empty small">无</div>'}
/* ---------- 关键口径 ---------- */
const CST={'方案规定':'grn','口径裁定':'org','待确认':'red','项目配置':'blu','默认采用':'line'};
/* mm4：知识层状态卡置顶（KZ.knowledge＝study analysis.knowledge；绿＝可用，红＝MedDRA 不可用降级；无键＝旧构建不显示） */
app.querySelector('#cal').innerHTML=K.knCard(D.knowledge)+((ST.calibers||[]).map(c=>`<div class="c1"><div class="t">${K.esc(c[0])}<span class="sp"></span>${K.p(c[2],CST[c[2]]||'line')}${c[3]?K.rp(c[3]):''}</div><div class="v">${K.esc(c[1])}</div>${c[4]?`<div class="s">${K.esc(c[4])}</div>`:''}</div>`).join('')||'<div class="empty">未生成关键口径</div>')
  +(((D.bind||{}).notes||[]).length?`<div class="c1"><div class="t">规则指标重绑<span class="sp"></span>${K.p('系统对齐','yel')}</div><div class="v small">${D.bind.notes.map(K.esc).join('<br>')}</div><div class="s">方案编译出的指标写法在数据中零命中时，按括注缩写/域别名自动对齐；请核对是否为同一指标</div></div>`:'');
/* ---------- 监查规则（按领域）---------- */
/* ---------- thresholds ---------- */
const L=(cond,c,out)=>`<div class="flex" style="align-items:flex-start;margin:3px 0"><span style="flex:0 0 46%">${K.p(cond,c)}</span><span class="small">${out}</span></div>`;
const TH=(ST.thresholds||[]).map(t=>[t.t,t.c||'org',(t.rows||[]).map(r=>L(r[0],r[1]||'line',r[2]||'')),t.note||'',t.refs||[],t.cats||[]]);
const thrHTML=TH.map(([t,c,ls,n,ids,cats])=>`<div class="card"><div class="hd"><i class="dot ${c}"></i><h3>${t}</h3><span class="sp"></span>${qlink(cats,'质疑')}</div>${ls.join('')}${n?`<div class="note mt">${n}</div>`:''}<div class="mt">${R(...ids)}</div></div>`).join('');

const B=D.basis||{},PDC=B.pd||{},POT=((D.pd||{}).potential)||[];
const pdN=re=>POT.filter(x=>re.test(x.rule)).length;
const go=(href,lab,n)=>`<a class="small" href="${href}">${lab}${n!=null?' '+n+' 条':''} ›</a>`;
const ANC={fd:'首剂（D1=第 1 天）',rand:'随机',icf:'知情同意',ld:'末次给药'};
const pane=app.querySelector('#rpane');
const IE=ST.criteria||[],IEold=ST.eligibility||[],EL=(B.eligibility||[]).concat((B.eligibilitySubject||[]).map(e=>({...e,metric:'人口学:'+e.field})));
const WO=(B.washout||[]).map(w=>({...w,label:w.name,op:'洗脱',v:w.days+' 天'}));
const coded=txt=>EL.concat(WO).find(e=>txt&&(String(e.text||e.name||'').includes(String(txt).slice(0,8))||String(txt).includes(String(e.text||e.name||'~~').slice(0,8))||(e.name&&String(txt).includes(String(e.name).slice(0,4)))));
const views={
 elig:()=>`<div class="card"><div class="hd"><h2>入选 / 排除标准</h2><span class="sub">可核查性：数据核查（系统逐受试者判定入组前末次有效值）/ 需研究者判断或源文件</span><span class="sp"></span>${go('deviations.html#tab=sci&cat=ELIG','入组资格潜在 PD',pdN(/^ELIG/))}</div>
  <div class="tw"><table class="t"><thead><tr><th style="width:70px">编号</th><th>标准（原文）</th><th style="width:180px">能否用数据核对</th><th style="width:70px">依据</th></tr></thead><tbody>${(IE.length?IE.map(c=>[c.no,c.text,c.check,c.rule,c.kind]):IEold.map(e=>[e[0],e[1],coded(e[1])?'data':'judgment',e[2],''])).map(([no,tx,ck,rid,kind])=>{const e=coded(tx);return `<tr><td class="nowrap">${K.p(no||'—',kind==='exclusion'?'red':kind==='inclusion'?'grn':'line')}</td><td class="small">${K.esc(tx)}</td><td>${ck==='data'||e?K.p('数据核查','grn')+(e?`<div class="xs muted" style="margin-top:2px">${K.esc(e.label||K.rxl(e.metric))} ${K.esc(K.OPL[e.op]||e.op||'')}${e.op==='re'?'即不符':' '+K.esc(e.v??'')}${e.on==='uln'?'×ULN':''}${e.pick&&e.pick!=='last'?' · '+(e.pick==='any'?'任一测量':'首次测量'):''}</div>`:''):ck==='partial'?K.p('部分可核查','yel'):K.p('需研究者判断 / 源文件','line')}</td><td>${rid?K.rp(rid):''}</td></tr>`}).join('')||'<tr><td colspan="4" class="empty">方案入排标准未导入</td></tr>'}</tbody></table></div>
  <div class="note mt xs muted">判定值：方案允许复查时取入组前末次有效测量；只核查筛选期（首剂访视之前的计划访视及计划外复查）记录，一位受试者一条标准只产生一条信号。</div></div>`,
 cm:()=>{const PM=(ST.prohibited||{}).groups||[];return `<div class="grid g2"><div class="card"><div class="hd"><h2>禁用 / 限用药物</h2><span class="sp"></span>${R(...((ST.prohibited||{}).refs||[]))}${go('deviations.html#tab=sci&cat=CM','合并用药潜在 PD',pdN(/^CM/))}</div>
  ${PM.map(([t,c,a])=>`<div class="flex wrap" style="align-items:flex-start;margin:5px 0"><span class="small muted nowrap" style="width:132px;flex:0 0 132px">${t}</span><span>${a.map(x=>K.p(x,c)).join('')}</span></div>`).join('')}
  ${(B.prohibited||[]).length?`<table class="t mt"><thead><tr><th>类别</th><th>禁用期</th><th>分级</th></tr></thead><tbody>${B.prohibited.map(p=>`<tr><td class="small">${K.esc(p.name)}</td><td class="small">${p.daysBefore?'首剂前 '+p.daysBefore+' 天至':'治疗期'}${p.daysAfter?'末次给药后 '+p.daysAfter+' 天':'末次给药'}</td><td>${p.important?K.pdGrade('重要'):K.pdGrade('待判定')}</td></tr>`).join('')}</tbody></table>`:''}
  ${(ST.prohibited||{}).note?`<div class="box small mt">${K.esc(ST.prohibited.note)}</div>`:''}${PM.length||(B.prohibited||[]).length?'':'<div class="empty">方案未列禁用药</div>'}</div>
  <div class="card"><div class="hd"><h2>洗脱期 · 补救治疗 · 方案要求的合并治疗</h2></div>
  ${(B.washout||[]).length?`<table class="t"><thead><tr><th>入组前须停用</th><th class="num">天数</th><th>锚点</th></tr></thead><tbody>${B.washout.map(w=>`<tr><td class="small">${K.esc(w.name)}</td><td class="num">${w.days}</td><td class="small">${ANC[w.ref]||w.ref||'—'}</td></tr>`).join('')}</tbody></table>`:'<div class="small muted">方案未规定洗脱期</div>'}
  <div class="kv mt"><dt>补救治疗</dt><dd class="small">${PDC.rescue?`${K.esc(PDC.rescue.name||K.rxl(PDC.rescue.re))}：自第 ${PDC.rescue.earliestDay||'—'} 天起可用${PDC.rescue.stopRequired?'，使用后须永久停用研究药物':''}（按方案条件使用不算方案偏离，属伴发事件）`:'方案未规定'}</dd>
  <dt>方案要求合并治疗</dt><dd class="small">${(B.cmProtocolRequired||[]).map(x=>K.esc(typeof x==='string'?x:x.name)).join('、')||'—'}</dd></div></div></div>`},
 exec:()=>{const W=B.visitWindows||{};const rows=Object.entries(W).map(([v,s])=>Array.isArray(s)?{v,t:s[0],mi:s[1],pl:s[2],a:'fd'}:{v,t:s.target,mi:s.minus||0,pl:s.plus||0,a:s.anchor||'fd'});
  const ex=[['给药',[PDC.dosing&&PDC.dosing.route?'途径 '+(PDC.dosing.routeLabel||PDC.dosing.route):'',PDC.dosing&&PDC.dosing.freq?'频次 '+PDC.dosing.freq:'',PDC.fasting?'空腹服药':''].filter(Boolean).join('；')],
   ['依从性',PDC.compliance?`${PDC.compliance.lo}%–${PDC.compliance.hi}%（每日 ${PDC.compliance.perDay} 单位；累计 ≥${PDC.compliance.minDays||14} 天才评估）`:''],
   ['样本时点',PDC.sample?`给药前样本须早于当次给药${PDC.sample.windowMin?`；给药后样本 ±${typeof PDC.sample.windowMin==='object'?PDC.sample.windowMin.default:PDC.sample.windowMin} 分钟`:''}`:''],
   ['访视内顺序',(PDC.order||[]).map(o=>o.label||(o.before+' 先于 '+(o.after||'给药'))).join('；')],
   ['知情同意',(PDC.icfVersions||[]).map(v=>`${v.ver} 版 ${v.effective} 生效${v.reconsent?'，在研受试者须再签':''}`).join('；')||'签署先于任何研究程序'],
   ['关键访视 / 评估',[(PDC.criticalVisits||[]).join('、'),PDC.criticalItems||''].filter(Boolean).join('；')]].filter(r=>r[1]);
  return `<div class="grid g2"><div class="card"><div class="hd"><h2>访视窗</h2><span class="sub">超窗与缺失访视在方案偏离页</span><span class="sp"></span>${go('deviations.html#tab=soa','SoA 完成度（访视级）',null)}${go('deviations.html#tab=exe&cat=VIS','访视潜在 PD',pdN(/^VIS/))}</div>
  ${rows.length?`<table class="t"><thead><tr><th>访视</th><th class="num">目标日</th><th class="num">窗口</th><th>锚点</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${K.p(r.v,'blu')}</td><td class="num">${r.a==='fd'?'D'+r.t:'+'+r.t}</td><td class="num">−${r.mi} / +${r.pl}</td><td class="small">${ANC[r.a]||'前一访视 '+r.a}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">方案中未找到访视窗</div>'}</div>
  <div class="card"><div class="hd"><h2>执行要求</h2><span class="sub">执行层面潜在偏离按这些参数判定</span><span class="sp"></span>${go('deviations.html#tab=rules','检查规则与覆盖')}</div>
  ${ex.length?`<div class="kv">${ex.map(r=>`<dt>${r[0]}</dt><dd class="small">${K.esc(r[1])}</dd>`).join('')}</div>`:'<div class="empty">方案中未找到给药与依从性等执行要求</div>'}
  ${ST.soaNote?`<div class="note mt">${K.esc(ST.soaNote)} ${R(...(ST.soaRefs||[]))}</div>`:''}</div></div>`},
 safe:()=>`<div class="grid g4">${thrHTML}</div>
  <div class="grid g2 mt"><div class="card"><div class="hd"><h2>AESI 定义</h2><span class="sp"></span>${go('safety.html#tab=ae&aesi=1','AESI 记录')}</div>${(B.aesi||[]).map(a=>`<div class="flex" style="align-items:flex-start;margin:4px 0">${K.p(a.id||'AESI','red')}<span class="small"><b>${K.esc(a.name||'')}</b> ${K.esc(a.terms||'')}${a.minGrade?' · ≥'+a.minGrade+' 级':''}</span></div>`).join('')}${(B.thresholdRules||[]).filter(r=>r.aesi).map(r=>`<div class="flex" style="margin:4px 0">${K.p('阈值型','red')}<span class="small">${K.esc(r.label||K.rxl(r.metric))}</span></div>`).join('')}${(B.comboRules||[]).map(r=>`<div class="flex" style="margin:4px 0">${K.p('组合','red')}<span class="small">${K.esc(r.name||r.id)}</span></div>`).join('')||''}${(B.aesi||[]).length||(B.comboRules||[]).length?'':'<div class="small muted">方案未定义术语型 AESI</div>'}</div>
  <div class="card"><div class="hd"><h2>报告时限 · 停药阈值</h2></div><div class="kv">${(B.reportRules||[]).map(r=>`<dt>${K.esc(r.flag==='serious'?'SAE':r.flag==='aesi'?'AESI':r.flag)}</dt><dd class="small">${K.esc(r.label||'获知后 '+r.days+' 天内')}</dd>`).join('')}${(B.thresholdRules||[]).filter(r=>r.stop).map(r=>`<dt>停药</dt><dd class="small">${K.esc(r.label||'')} ${K.esc(r.note||'')}</dd>`).join('')}</div>${(B.reportRules||[]).length?'':'<div class="small muted">方案未规定报告时限</div>'}</div></div>`,
 risk:()=>{const IBN=(ST.ib||{}).notes||{};const IND=B.indicationBackground||[];return `<div class="grid g2"><div class="card"><div class="hd"><h2>产品风险（IB / 类效应）</h2><span class="sub">AE 预期性标签来源；AE 实际分布见总览与 AE/MH 风险</span></div>
  ${Object.entries(IBN).map(([k,v])=>`<div class="flex" style="align-items:flex-start;margin:5px 0"><b class="small" style="width:110px;flex:0 0 110px">${K.esc(k)}</b><span class="small">${K.ibTags(k)} ${K.esc(v[0])}${v[1]?`<div class="xs muted" style="margin-top:2px">${/^R-/.test(v[1])?K.rp(v[1]):'出处：'+K.esc(v[1])}</div>`:''}</span></div>`).join('')||'<div class="small muted">未提供研究者手册（IB），也未从方案中识别到产品风险</div>'}</div>
  <div class="card"><div class="hd"><h2>研究疾病的常见检查表现</h2><span class="sub">用于判断 CS 异常能否由研究疾病解释；给药后较基线加重仍须评估 AE</span></div>
  ${IND.length?`<table class="t"><tbody>${IND.map(([re,n])=>`<tr><td class="small nowrap">${K.esc(String(n||'').split('：')[0].replace(/（医学常识）/,'')||K.rxl(re))}</td><td class="small">${K.esc(n||'研究疾病常见表现')}</td></tr>`).join('')}</tbody></table>`:'<div class="small muted">方案/IB 未列出研究疾病的常见检查表现：归因研究疾病的 CS 只按研究者填写的原因或备注判断</div>'}</div></div>`}};
const tabs=[['elig','入组资格'],['cm','合并用药'],['exec','访视与执行'],['safe','安全性判定'],['risk','产品与适应症风险']];
K.tabs(app.querySelector('#rtab'),tabs,K.hash().rt||'elig',v=>{pane.innerHTML=views[v]()});
/* ---------- rule library ---------- */
/* 按规则类别（中文）归组：旧版按英文目标名匹配，规则编号改为缩写后全部落空 */
const G=(ST.ruleGroups||[['IB/产品风险','IB|产品风险|类效应|潜在风险'],['设计/盲法/人群','设计|盲|人群|分析集'],['访视与基线','访视|基线|日程|SoA'],['入排','入排|入选|排除'],['合并用药','禁用|限用|洗脱|合并用药|补救'],['避孕/妊娠','避孕|妊娠'],['终点与有效性','终点|有效性'],['安全性判定','分级|AE|AESI|SAE|阈值|停药|报告|安全|疾病进展']]).map(([a,b])=>[a,new RegExp(b)]);
const gOf=r=>(G.find(g=>g[1].test(r.dom||""))||[r.dom||"其他"])[0];
const unr=new Set(D.unres.map(u=>u.split(' ')[0]));
const F={g:null,s:''};
const cnt={};D.rules.forEach(r=>cnt[gOf(r)]=(cnt[gOf(r)]||0)+1);
K.chips(app.querySelector('#rd'),[...[...new Set(D.rules.map(gOf))].map(g=>[g,g,cnt[g]]),...(unr.size?[['__u','口径待确认',unr.size]]:[])],v=>{F.g=v;dr()});
const rt=K.table(app.querySelector('#rules'),{rows:[],pageSize:20,onRow:r=>K.showRule(r.id),cols:[{k:'g',t:'类别',f:r=>K.p(gOf(r),unr.has(r.id)?'red':'line'),s:r=>gOf(r),w:'110px'},{k:'st',t:'规则（方案/IB 原文归纳）',f:r=>`<span class="small">${K.hlNum(r.st)}</span>`},{k:'src',t:'原文依据',ns:1,w:'230px',f:r=>r.src.length?[...new Set(r.src.map(s=>s[2]))].map(c=>K.p((K.SRC[c]||[c])[0],(K.SRC[c]||[0,''])[1])).join('')+`<div class="xs muted" style="margin-top:2px">${K.esc(r.src[0][0]||'')}</div>`:'<span class="xs faint">未保存原文片段</span>'}]});
app.querySelector('#rs').oninput=e=>{F.s=e.target.value.trim();dr()};
function dr(){const s=F.s.toLowerCase();const rows=D.rules.filter(r=>(!F.g||(F.g==='__u'?unr.has(r.id):gOf(r)===F.g))&&(!s||(r.dom+r.st).toLowerCase().includes(s)));app.querySelector('#rn').textContent=`${rows.length} / ${D.rules.length} 条`;rt.set(rows)}
dr();
const h=K.hash();if(h.r)K.showRule(h.r);
});
