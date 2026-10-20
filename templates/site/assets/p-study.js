K.init(()=>{
const D=KZ,X=KZX,app=document.getElementById('app');
const qn=cats=>D.queries.filter(q=>cats.includes(q.cat)).length;
const qlink=(cats,lab)=>{const n=qn(cats);return n?`<a class="small" href="#" data-qc="${K.esc(cats.join('|'))}">${lab||'相关质疑'} ${n} 条 ›</a>`:`<span class="small faint">${lab||'相关质疑'} 0</span>`};
document.addEventListener('click',e=>{const a=e.target.closest('[data-qc]');if(!a)return;e.preventDefault();const cats=a.dataset.qc.split('|');const qs=D.queries.filter(q=>cats.includes(q.cat));
 K.drawer('相关医学质疑',`<table class="t"><tbody>${qs.map(q=>`<tr class="click" data-q="${q.id}"><td>${K.qPill(q.id)}</td><td>${K.sid(q.sid)}</td><td>${K.p(q.cat,'line')}<div class="small mt" style="margin-top:3px">${K.hlNum(q.text)}</div></td></tr>`).join('')}</tbody></table>`,qs.length+' 条')});
const R=(...ids)=>ids.map(i=>K.rp(i)).join('');
/* ---------- design (KZ.study, generated from protocol extraction) ---------- */
const ST=D.study||{},DS=ST.design||{},st=D.meta.status;
const pills=a=>(a||[]).map(x=>Array.isArray(x)?K.p(x[0],x[1]||'line'):K.p(x,'line')).join('');
const secHide=k=>(ST.hide||[]).includes(k);
app.innerHTML=`
<div class="card"><div class="hd"><h2>研究设计</h2><span class="sub">${K.esc(DS.sub||'')}</span><span class="sp"></span>${R(...(DS.refs||[]))}</div>
 <div class="flow">${(DS.flow||[]).map(f=>`<div class="st${f.hot?' hot':''}"><span class="n">${K.esc(f.n||'')}</span><b>${K.esc(f.b||'')}</b><span class="xs muted">${K.esc(f.x||'')}</span></div>`).join('')}</div>
 <div class="grid g3 mt" style="grid-template-columns:1.3fr 1fr 1.2fr">
  <div><div class="muted xs mb" style="margin-bottom:4px">${K.esc((DS.arms||{}).label||'组别')}</div>${pills((DS.arms||{}).items)}</div>
  <div><div class="muted xs" style="margin-bottom:4px">${K.esc((DS.baselines||{}).label||'规定基线')} ${R(...((DS.baselines||{}).refs||[]))}</div>${pills((DS.baselines||{}).items)}</div>
  <div><div class="muted xs" style="margin-bottom:4px">截至 ${K.esc(D.meta.cutoff)}</div>${K.p('筛选 '+D.meta.n,'line')}${K.p('给药 '+D.meta.dosed,'org')}${Object.entries(st).filter(([k])=>k!=='筛选失败').map(([k,v])=>K.p(k+' '+v,K.STC[k]??'')).join('')}${DS.planned?K.p('计划 '+DS.planned,'line'):''}</div>
 </div></div>

<div class="grid mt" style="grid-template-columns:1.55fr 1fr">
 <div class="card"><div class="hd"><h2>访视流程表 × 实际完成</h2><span class="sub">已给药受试者 · 点击单元格查看缺失名单</span><span class="sp"></span><span class="legend"><span>${K.p('✓','grn')} 全部完成</span><span>${K.p('缺','red')} 无记录</span><span>${K.p('否','yel')} 记录“未做”</span><span>${K.p('条件','line')} 条件性项目</span><span>${K.p('+n','')} 计划外</span></span></div><div id="soa"></div>
  ${ST.soaNote?`<div class="note mt">${K.esc(ST.soaNote)} ${R(...(ST.soaRefs||[]))}</div>`:''}</div>
 <div class="card"><div class="hd"><h2>口径确认状态</h2><span class="sub">方案文字不一致处的处理</span></div><div id="cons"></div></div>
</div>

<div class="sec-t"><h2>判定阈值</h2><span class="muted small">方案原文 → 监察判读；点击编号查看原文定位</span></div>
<div class="grid g4" id="thr"></div>

<div class="sec-t"><h2>IB 风险 × 本研究${(K.cfg().blind||{}).on?'盲态 ':''}AE</h2><span class="muted small">给药后 AE${(K.cfg().blind||{}).on?'，各组合并、不分组':''}；点击行进入 AE 明细</span></div>
<div class="card flush"><div id="ib"></div></div>

<div class="grid g2 mt">
 <div class="card"><div class="hd"><h2>禁用 / 限用药物</h2><span class="sp"></span>${R(...((ST.prohibited||{}).refs||[]))}</div><div id="pm"></div></div>
 <div class="card"><div class="hd"><h2>入排关键数值</h2><span class="sp"></span>${qlink(ST.eligCats||[],'入排/禁用药质疑')}</div><div id="ie"></div></div>
</div>

<div class="sec-t"><h2>方案 / IB 规则库</h2><span class="muted small" id="rn"></span><span class="sp"></span><input class="s" id="rs" placeholder="搜索 规则文字 / 编号"></div>
<div class="chips mb" id="rd"></div><div id="rules"></div>`;

/* ---------- SoA ---------- */
const COND=new Set(ST.soaCond||[]);const SX=ST.soaExclude?new RegExp(ST.soaExclude):null;
const soa=(X.soa||[]).filter(r=>!SX||!SX.test(r.sheet));const cols=X.soacols;
const vn=v=>{const r=soa.find(r=>r.cells[v]);return r?r.cells[v][0]:''};
const cell=(r,v,ri)=>{const c=r.cells[v];if(!c)return '<td class="h faint">·</td>';const [n,done,no,miss,,,ex]=c;
 if(ex)return `<td class="h"><span class="p click" data-c="${ri}|${v}" title="非计划访视记录">+${done}</span></td>`;
 const cond=COND.has(r.name);let t;
 if(miss)t=K.p('缺 '+miss,'red click');else if(no)t=K.p((cond?'否 ':'否 ')+no,(cond?'line':'yel')+' click');else t=K.p('✓','grn');
 return `<td class="h" data-c="${ri}|${v}" style="cursor:${miss||no?'pointer':'default'};padding:3px 4px" title="完成 ${done}/${n}">${t}</td>`};
app.querySelector('#soa').innerHTML=`<div class="tw"><table class="t heat"><thead><tr><th>项目</th>${cols.map(v=>`<th class="h" style="text-align:center">${v}<div class="xs faint" style="font-weight:400">n=${vn(v)}</div></th>`).join('')}</tr></thead><tbody>${soa.map((r,ri)=>`<tr><td class="nowrap" style="padding:3px 8px" title="${r.sheet}">${K.esc(r.name)} ${COND.has(r.name)?K.p('条件','line'):''}</td>${cols.map(v=>cell(r,v,ri)).join('')}</tr>`).join('')}</tbody></table></div>`;
app.querySelector('#soa').onclick=e=>{const td=e.target.closest('[data-c]');if(!td)return;const [ri,v]=td.dataset.c.split('|');const r=soa[+ri],c=r.cells[v];if(!c||(!c[3]&&!c[2]&&!c[6]))return;
 K.drawer(`${r.name} · ${v}`,`<div class="flex wrap mb">${K.p('访视人数 '+c[0],'line')}${K.p('完成 '+c[1],'grn')}${c[3]?K.p('无记录 '+c[3],'red'):''}${c[2]?K.p('记录“否” '+c[2],'yel'):''}${COND.has(r.name)?K.p('条件性项目','line'):''}</div>
 ${c[6]?`<div class="box small">${v} 不在流程表计划内，但有 ${c[1]} 例记录（计划外/补充检查）。</div>`:''}
 ${c[4].length?`<h3 class="mt">无记录</h3><div class="flex wrap mt">${c[4].map(s=>K.sid(s)).join(' ')}</div>`:''}
 ${c[5].length?`<h3 class="mt">记录“未做”</h3><div class="flex wrap mt">${c[5].map(s=>K.sid(s)).join(' ')}</div>`:''}
 <div class="note mt">名单来自 ${r.sheet} 页“是否进行”字段与访视页（SV）比对；${COND.has(r.name)?'条件性项目的“否”可能为允许豁免，结合原因字段判断，不直接发质疑。':'计划项无记录时先核对访视是否实际发生、是否已录入，再决定是否质疑。'}</div>`,K.p(r.sheet,'sq mono'))};

/* ---------- consensus ---------- */
const CS=ST.consensus||[];
app.querySelector('#cons').innerHTML=`<div class="tw"><table class="t"><thead><tr><th>口径</th><th>原文差异</th><th>本次采用</th></tr></thead><tbody>${CS.length?'':'<tr><td colspan=3 class="empty">无口径冲突</td></tr>'}${CS.map(c=>`<tr><td class="nowrap"><b class="small">${c[0]}</b>${c[4]?`<div>${K.rp(c[4])}</div>`:""}</td><td class="small muted">${c[1]}</td><td>${K.p(c[3]==='grn'?'已确认':c[3]==='blu'?'按原文':'待确认',c[3])}<div class="small" style="margin-top:2px">${c[2]}</div></td></tr>`).join('')}</tbody></table></div>`;

/* ---------- thresholds ---------- */
const L=(cond,c,out)=>`<div class="flex" style="align-items:flex-start;margin:3px 0"><span style="flex:0 0 46%">${K.p(cond,c)}</span><span class="small">${out}</span></div>`;
const TH=(ST.thresholds||[]).map(t=>[t.t,t.c||'org',(t.rows||[]).map(r=>L(r[0],r[1]||'line',r[2]||'')),t.note||'',t.refs||[],t.cats||[]]);
app.querySelector('#thr').innerHTML=TH.map(([t,c,ls,n,ids,cats])=>`<div class="card"><div class="hd"><i class="dot ${c}"></i><h3>${t}</h3><span class="sp"></span>${qlink(cats,'质疑')}</div>${ls.join('')}${n?`<div class="note mt">${n}</div>`:''}<div class="mt">${R(...ids)}</div></div>`).join('');

/* ---------- IB matrix ---------- */
const IBN=(ST.ib||{}).notes||{};
const am=D.aesum,rows=Object.entries(am).map(([k,v])=>({k,...v})).sort((a,b)=>(b.aesi-a.aesi)||((D.ibtag[b.k]?1:0)-(D.ibtag[a.k]?1:0))||b.n-a.n);
const mx=Math.max(1,...rows.map(r=>r.n||0));
rows.push(...(((ST.ib||{}).extra)||[]));
K.table(app.querySelector('#ib'),{rows,noPage:true,max:false,onRow:r=>{if(r.n)location.href='safety.html#tab=ae&cat='+encodeURIComponent(r.k)},
 cols:[{k:'k',t:'AE 类别 / IB 风险',f:r=>`<b>${K.esc(r.k)}</b>`,w:'150px'},{k:'tag',t:'定位',ns:1,f:r=>r.tag?(r.tag||[]).map(t=>K.p(t,/潜在/.test(t)?'org':'line')).join(''):K.ibTags(r.k)||'<span class="faint xs">未列入 IB 风险</span>',w:'200px'},
  {k:'n',t:'例次',cls:'num',f:r=>r.n==null?'<span class="faint">—</span>':`<div class="flex" style="justify-content:flex-end"><div class="bar-in" style="width:80px"><i style="width:${r.n/mx*100}%;background:${r.aesi?'#8B0000':D.ibtag[r.k]?'#FF9900':'#C9CCD1'}"></i></div><b>${r.n}</b></div>`},
  {k:'s',t:'例数',cls:'num',f:r=>r.n==null?'—':r.s},{k:'g2',t:'≥2级',cls:'num',f:r=>r.n==null?'—':r.g2?`<b style="color:var(--brand-d)">${r.g2}</b>`:'0'},{k:'rel',t:'研究者判相关',cls:'num',f:r=>r.n==null?'—':r.rel},{k:'aesi',t:'AESI',cls:'num',f:r=>r.n==null?'—':r.aesi?K.p(r.aesi,'solid-red'):'0'},
  {k:'x',t:'IB / 类效应要点',ns:1,f:r=>{const x=r.x||IBN[r.k];return x?`<span class="small">${x[0]}</span> ${K.rp(x[1])}`:`<span class="xs faint">${(r.terms||[]).slice(0,4).join('、')}</span>`}}]});

/* ---------- prohibited ---------- */
const PM=(ST.prohibited||{}).groups||[];
app.querySelector('#pm').innerHTML=PM.map(([t,c,a])=>`<div class="flex wrap" style="align-items:flex-start;margin:5px 0"><span class="small muted nowrap" style="width:132px;flex:0 0 132px">${t}</span><span>${a.map(x=>K.p(x,c)).join('')}</span></div>`).join('')+((ST.prohibited||{}).note?`<div class="box small mt">${K.esc(ST.prohibited.note)}</div>`:'')+(PM.length?'':'<div class="empty">方案未列禁用药</div>');
const IE=ST.eligibility||[];
app.querySelector('#ie').innerHTML=`<div class="grid g2" style="gap:4px 14px">${IE.map(([a,b,id])=>`<div class="flex" style="align-items:flex-start"><b class="small nowrap" style="width:62px;flex:0 0 62px">${a}</b><span class="small sp">${b}</span>${K.rp(id)}</div>`).join('')}</div>`;

/* ---------- rule library ---------- */
const G=(ST.ruleGroups||[['设计/盲法/人群','identity|design|blinding|population|analysis_set|monitoring'],['访视与日程','visit_window|schedule|baseline'],['入排与病史','inclusion|exclusion|history'],['合并用药','concomitant|prohibited|ddi|washout'],['避孕/妊娠','contraception|pregnancy'],['终点','endpoint'],['安全性判定','ae_|causality|reporting|expectedness|stopping|aesi|threshold|dili|vital|ecg'],['IB 风险','risk|expected_pharm|class_event|missing|blinded_agg']]).map(([a,b])=>[a,new RegExp(b)]);
const gOf=r=>(G.find(g=>g[1].test(r.id+" "+(r.dom||"")))||[r.dom||"其他"])[0];
const unr=new Set(D.unres.map(u=>u.split(' ')[0]));
const F={g:null,s:''};
const cnt={};D.rules.forEach(r=>cnt[gOf(r)]=(cnt[gOf(r)]||0)+1);
K.chips(app.querySelector('#rd'),[...G.map(g=>[g[0],g[0],cnt[g[0]]]),['__u','口径待确认',unr.size]],v=>{F.g=v;dr()});
const rt=K.table(app.querySelector('#rules'),{rows:[],pageSize:20,onRow:r=>K.showRule(r.id),cols:[{k:'id',t:'编号',f:r=>K.rp(r.id,unr.has(r.id)?'red':''),w:'84px'},{k:'g',t:'类别',f:r=>K.p(gOf(r),'line'),s:r=>gOf(r),w:'110px'},{k:'st',t:'规则（方案/IB 原文归纳）',f:r=>`<span class="small">${K.hlNum(r.st)}</span>`},{k:'src',t:'原文依据',ns:1,w:'190px',f:r=>[...new Set(r.src.map(s=>s[2]))].map(c=>K.p((K.SRC[c]||[c])[0],(K.SRC[c]||[0,''])[1])).join('')}]});
app.querySelector('#rs').oninput=e=>{F.s=e.target.value.trim();dr()};
function dr(){const s=F.s.toLowerCase();const rows=D.rules.filter(r=>(!F.g||(F.g==='__u'?unr.has(r.id):gOf(r)===F.g))&&(!s||(r.id+r.st).toLowerCase().includes(s)));app.querySelector('#rn').textContent=`${rows.length} / ${D.rules.length} 条`;rt.set(rows)}
dr();
const h=K.hash();if(h.r)K.showRule(h.r);
});
