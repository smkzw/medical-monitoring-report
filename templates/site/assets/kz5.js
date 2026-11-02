/* V5 公共模块（用户 2026-10-31 晚）：处置状态、研究层面容忍限度（QTL）与 KRI、角色、行动项、通用抽屉、跨上传趋势。
 * 在 kz.js 之后载入（全部页面）。数据：KZ.kri / KZ.cred / KZ.ops（构建），KZS.sigstate / history / timeliness（工作台系统层，可无）。 */
(function(){
const K=window.K,D=()=>window.KZ||{},Z=()=>window.KZS||{};
const study=()=>((K.cfg().study||{}).code||'');
const LS={get:(k,d)=>{try{const v=localStorage.getItem(k);return v==null?d:JSON.parse(v)}catch(e){return d}},set:(k,v)=>{try{localStorage.setItem(k,JSON.stringify(v))}catch(e){}}};

/* ---------- 处置状态（跨上传记住：键与工作台 riskdiff / K.dkey 同写法；处置后加重自动重新打开） ----------
 * 存储：本浏览器 localStorage ← 合并 → KZS.sigstate（工作台 state.db，构建时带入）；写入时若工作台层提供 window.KZSIG_SYNC 则同步到服务端。 */
K.SIGST={open:['待处理',''],doing:['处理中','blu'],done:['已处理','grn'],fp:['核实无问题','line'],hold:['暂缓','yel']};
K.SIGR={done:['已发质疑','数据已更正','已录入方案偏离','已与中心沟通','其他'],fp:['医学上合理','规则误报','数据无误','重复','其他'],hold:['等待数据更新','等待中心回复','其他']};
const LR={CSX:6,DISW:5,MH:5,NCS2:4,NA2:4,G2NF:4,NA:3,MHU:3,CSI:2,'MHX-T':2,REL:1};
K.sigKey={lab:g=>'lab|'+g.sid+'|'+g.test,oth:o=>{const q=String(o.qkey||'');return /^oth\|/.test(q)?q:'oth|'+q},pd:p=>'pd|'+p.rule+'|'+p.sid+'|'+(p.visit||p.date||''),
  ent:e=>'ent|'+e.sid+'|'+e.test+'|'+(e.visit||'')+'|'+(e.date||''),vis:v=>'vis|'+v.sid+'|'+v.v,ctr:x=>'ctr|'+x.site+'|'+x.k,
  kri:x=>'kri|'+x.site+'|'+x.k,qtl:x=>'qtl|'+x.k,cred:x=>'cred|'+x.site+'|'+x.k,fresh:x=>'fresh|'+x.site};
K.sigRank={lab:g=>(LR[g.risk]||0)*10+(g.mg||0),pd:p=>({'重要':3,'待判定':2,'一般':1}[p.grade]||0),oth:o=>o.pr||0};
const rankOf=(kind,x)=>(K.sigRank[kind]||(()=>0))(x);
K._sigLS='kz.sig:'+study();
K.sigAll=()=>{if(K._sigM)return K._sigM;const a=Z().sigstate||{},b=LS.get(K._sigLS,{}),m={...a};
  Object.entries(b).forEach(([k,v])=>{if(!m[k]||String(v.at||'')>=String(m[k].at||''))m[k]=v});
  /* V5 修复波：oth 处置键曾双前缀（oth|oth|…），归一后按单前缀读旧状态（剥第一个 oth| 即得单前缀别名，处置记录不丢） */
  Object.keys(m).forEach(k=>{if(k.startsWith('oth|oth|')){const nk=k.slice(4);if(!m[nk]||String(m[k].at||'')>=String(m[nk].at||''))m[nk]=m[k]}});
  return K._sigM=m};
K.sigGet=(kind,x)=>{const k=K.sigKey[kind](x),r=K.sigAll()[k];if(!r||r.s==='open')return {s:'open',k};
  if((r.s==='done'||r.s==='fp')&&r.rk!=null&&rankOf(kind,x)>r.rk)return {...r,s:'open',s0:r.s,k,re:true};return {...r,k}};
K.sigSet=(kind,x,s,r='',n='')=>{const k=K.sigKey[kind](x),rec={s,r,n,at:new Date().toISOString().slice(0,16).replace('T',' '),rk:rankOf(kind,x),by:Z().user||''};
  const b=LS.get(K._sigLS,{});b[k]=rec;LS.set(K._sigLS,b);K.sigAll()[k]=rec;
  if(window.KZSIG_SYNC)try{window.KZSIG_SYNC(k,rec)}catch(e){}
  document.dispatchEvent(new CustomEvent('kz-sig',{detail:{k,rec}}));return rec};
K.sigPill=(kind,x)=>{const g=K.sigGet(kind,x);if(g.re)return K.p('处置后加重','red',`曾标「${(K.SIGST[g.s0]||[''])[0]}」，之后加重，已重新打开`);
  if(g.s==='open')return '';const t=K.SIGST[g.s];return K.p(t[0],t[1],[g.r,g.n,g.at].filter(Boolean).join(' · '))};
/* 抽屉顶部的处置控件 */
K.sigCtl=(el,kind,x)=>{if(!el)return;const draw=()=>{const g=K.sigGet(kind,x),cur=g.s,rs=K.SIGR[cur]||[];
   el.innerHTML=`<div class="sigc"><span class="xs muted">处置</span>${Object.entries(K.SIGST).map(([k,[l]])=>`<button class="${k===cur?'on':''}" data-s="${k}">${l}</button>`).join('')}
    <select class="s"${rs.length?'':' style="display:none"'}>${rs.map(r=>`<option${r===g.r?' selected':''}>${r}</option>`).join('')}</select>
    <input class="s" placeholder="备注（可选）" value="${K.esc(g.n||'')}"><span class="xs faint">${g.re?'曾处置，之后加重，已重新打开':g.at?K.esc(g.at)+(g.by?' · '+K.esc(g.by):''):'跨上传保留；加重会自动重新打开'}</span></div>`;
   const sel=el.querySelector('select'),inp=el.querySelector('input');
   el.querySelectorAll('button').forEach(b=>b.onclick=()=>{const s=b.dataset.s,o=K.SIGR[s]||[];K.sigSet(kind,x,s,o.length?(o.includes(sel.value)?sel.value:o[0]):'',inp.value.trim());draw()});
   sel.onchange=()=>{K.sigSet(kind,x,cur,sel.value,inp.value.trim());draw()};
   inp.onchange=()=>{K.sigSet(kind,x,cur==='open'?'doing':cur,rs.length?sel.value:'',inp.value.trim());draw()}};
  draw()};
/* 列表上的「隐藏已处理」开关；返回过滤函数 f(kind, x) */
K.sigBar=(el,onChange)=>{if(!el)return ()=>true;let on=LS.get('kz.sighide',false);
  el.insertAdjacentHTML('beforeend',`<label class="chip" style="margin-left:6px"><input type="checkbox"${on?' checked':''}> 隐藏已处理/核实无问题</label>`);
  el.lastElementChild.querySelector('input').onchange=e=>{on=e.target.checked;LS.set('kz.sighide',on);onChange()};
  return (kind,x)=>{if(!on)return true;const s=K.sigGet(kind,x).s;return !(s==='done'||s==='fp')}};

/* ---------- 研究层面容忍限度（QTL）与 KRI：默认档＋严格/宽松可选，所选档位存本浏览器（按研究），全报告联动 ---------- */
K.kri=()=>D().kri||null;
K.QTLN={strict:'严格',std:'标准',loose:'宽松'};
K._qtlLS='kz.qtl:'+study();
K.qtlTier=()=>{const k=K.kri();return LS.get(K._qtlLS,null)||Z().qtlTier||(k&&k.tierDefault)||'std'};
K.setQtl=t=>{if(t===K.qtlTier())return;LS.set(K._qtlLS,t);location.reload()};
K.kriDef=k=>((K.kri()||{}).defs||[]).find(d=>d.k===k);
K.kriScale=u=>u==='%'?100:u==='/100人月'?100*30.4375:u==='/千条'?1000:1;
K.kriV=(k,nd)=>{const d=K.kriDef(k);if(!d||!nd||nd[0]==null||!nd[1])return null;return nd[0]/nd[1]*K.kriScale(d.u)};
K.kriFmt=(k,v)=>{const d=K.kriDef(k)||{};if(v==null)return '—';const s=d.u==='天'?String(Math.round(v)):v>=100?v.toFixed(0):v>=10?v.toFixed(1):v.toFixed(2).replace(/0$/,'');return s+(d.u==='%'?'%':d.u==='天'?' 天':'')};
K.qtlLim=k=>{const d=K.kriDef(k);if(!d||!d.qtl)return null;return d.qtl[{strict:0,std:1,loose:2}[K.qtlTier()]??1]};
K.qtlState=(k,nd)=>{const v=K.kriV(k,nd),lim=K.qtlLim(k);if(v==null||lim==null)return {v,lim,st:''};return {v,lim,st:v>lim?'exceed':lim>0&&v>lim*.8?'warn':'ok'}};
K.QTLC={exceed:['超出限度','solid-red'],warn:['接近限度','org'],ok:['限度内','grn']};
K.qtlRows=()=>{const k=K.kri();if(!k)return [];return k.defs.filter(d=>d.qtl).map(d=>({...d,nd:k.study[d.k],na:(k.na||{})[d.k],...((k.na||{})[d.k]?{v:null,lim:K.qtlLim(d.k),st:''}:K.qtlState(d.k,k.study[d.k]))}))};
K.qtlBar=el=>{const k=K.kri();if(!el||!k)return;el.innerHTML=`<span class="xs muted">容忍限度档位</span><span class="seg" id="kz-qtl"></span><span class="xs faint" style="margin-left:6px">切换后总览、临床监察、中心画像、行动项按所选档位重算</span>`;
  K.seg(el.querySelector('#kz-qtl'),k.tiers,K.qtlTier(),v=>K.setQtl(v))};
K.qtlTiles=el=>{const rows=K.qtlRows();if(!el)return;if(!rows.length){el.innerHTML='<div class="empty">本构建没有 KRI 数据</div>';return}
  el.innerHTML=`<div class="qtl">${rows.map(r=>`<a class="qt ${r.st||'na'}" href="monitor.html#tab=kri" title="${K.esc(r.note)}"><div class="l">${K.esc(r.l)}</div>
   <div class="v">${r.na?'—':K.kriFmt(r.k,r.v)}</div><div class="s">${r.na?`<span class="faint">${K.esc(r.na)}</span>`:`限度 ≤${r.lim}${r.u==='%'?'%':''} · ${r.nd?r.nd[0]+'/'+r.nd[1]:''}${(((D().ops||{}).kriPending)||{})[r.k]?` <span class="faint">另 ${D().ops.kriPending[r.k]} 例待核实未计入</span>`:''} ${r.st?K.p(K.QTLC[r.st][0],K.QTLC[r.st][1]):''}`}</div></a>`).join('')}</div>`};
/* 中心 KRI 单元：研究层面限度（有限度的指标，分母 ≥5 才判超限）＋同列中心间的观察/期望（BH） */
K.kriSite=(site,k)=>((K.kri()||{}).sites||{})[site]?.[k]||null;

/* ---------- 角色（行动项取材与排序、总览首屏强调） ---------- */
K.ROLES=[['mm','医学监察'],['cra','临床监察'],['pm','项目经理'],['all','全部']];
K._roleLS='kz.role:'+study();K.role=()=>LS.get(K._roleLS,'mm');K.setRole=r=>LS.set(K._roleLS,r);

/* ---------- 数据可信度：中心层面的提示（只说「建议核对」） ---------- */
K.credFlags=(site,v)=>{const f=[];if(!v)return f;
  if(v.dig&&v.dig[3]!=null&&v.dig[3]<.05)f.push({k:'dig',l:'血压/心率末位数字偏好',why:`末位为 0 或 5 的占 ${(v.dig[1]/v.dig[0]*100).toFixed(0)}%（${v.dig[1]}/${v.dig[0]}，随机约 20%）`});
  if(v.flat&&v.flat[3]!=null&&v.flat[3]<.10&&v.flat[1]>=2)f.push({k:'flat',l:'多次访视数值完全相同',why:`${v.flat[1]}/${v.flat[0]} 组（受试者×指标，≥4 次）结果完全相同`});
  if(v.shift&&v.shift[1]>=2)f.push({k:'shift',l:'基线生命体征均值偏离',why:v.shift[2].slice(0,3).map(x=>`${x[0]} 中心 ${x[3]} / 整体 ${x[4]}（z=${x[1]}）`).join('；')});
  if(v.dup&&v.dup[0])f.push({k:'dup',l:'同日多名受试者生命体征完全相同',why:`${v.dup[0]} 组`});return f};

/* ---------- 通用抽屉 ---------- */
const sigBox=()=>'<div class="sigbox"></div>';
K.showLabG=g=>{const b=K.drawer(`${g.sid} · ${K.esc(g.test)}`,`${sigBox()}<div class="flex wrap mb">${K.risk(g.risk)}${K.grade(g.mg)}${g.ctq?K.p('关键数据','solid-red',g.ctq):''}${g.grp?K.p(g.grp,'line'):''}${g.cat?K.p(g.cat,'line'):''}${K.ctxTags(g.ctx)}${(g.q||[]).map(K.qPill).join('')}</div>${(g.ctx||[]).length?`<div class="small muted mb" style="line-height:1.7">${g.ctx.map(c=>'· '+K.esc(c)).join('<br>')}</div>`:''}<div id="sp"></div>`);
  K.sigCtl(b.querySelector('.sigbox'),'lab',g);K.seriesPanel(b.querySelector('#sp'),{sid:g.sid,tests:[g.test],hl:(g.pts||[]).map(p=>[p[7],p[8]])})};
K.showOth=r=>{const b=K.drawer(`${r.sid} · ${K.esc(r.cat)}`,`${sigBox()}<div class="flex wrap mb">${K.pri(r.pr)}${r.ctq?K.p('关键数据','solid-red',r.ctq):''}${r.v?K.p(r.v,'blu'):''}${K.p(K.loc(r.sh,r.row),'sq')}${(r.q||[]).map(K.qPill).join('')}</div><div class="box">${K.hlNum(r.sum)}</div><div class="mt">${(r.ctx||[]).map(c=>`<div class="note">· ${K.esc(c)}</div>`).join('')}</div><div id="sp"></div>`);
  K.sigCtl(b.querySelector('.sigbox'),'oth',r);K.seriesPanel(b.querySelector('#sp'),{sid:r.sid,tests:[r.test],hl:[[r.sh,r.row]]})};
K.showEnt=r=>{const b=K.drawer(`${r.sid} · ${K.esc(r.test)}`,`${sigBox()}<div class="box org small mb">${K.esc(r.visit)} ${K.esc(r.raw)} ${K.esc(r.unit)}：${K.esc(r.why)}</div><div class="note small mb">只作数据质量提示，请 CRA 核对源数据；不发医学质疑。</div><div id="sp"></div>`,K.p(K.loc(r.sh,r.row),'sq'));
  K.sigCtl(b.querySelector('.sigbox'),'ent',r);K.seriesPanel(b.querySelector('#sp'),{sid:r.sid,tests:[r.test],hl:[[r.sh,r.row]],ae:false})};
K.showVis=v=>{const b=K.drawer(`${v.sid} · ${K.esc(v.v)} 访视`,`${sigBox()}<div class="box small">方案窗 ${K.esc(v.lo)} ~ ${K.esc(v.hi)}，截至数据截止未见该访视记录${(D().ops||{}).stage==='daily'?'（日常监查阶段：可能只是尚未录入，请先与中心确认）':''}。</div>
  <div class="vis-raw"></div><div class="mt"><a class="small" href="subjects.html#s=${v.sid}&t=raw">原始数据 ›</a>　<a class="small" href="subjects.html#s=${v.sid}">参与者资料 ›</a>　<a class="small" href="timeline.html#s=${v.sid}">时间线 ›</a></div>`);K.sigCtl(b.querySelector('.sigbox'),'vis',v);
  /* V6：该受试者的访视记录原行（核对是否其实做了、只是访视名写法不同） */
  K.rawIdx().then(I=>{if(!I)return;const vs=Object.keys(I.sheets).filter(k=>I.sheets[k].domain==='visits');K.raw(v.sid).then(R=>{if(!R)return;const ev=[];vs.forEach(k=>(R[k]||[]).forEach(r=>ev.push([k,r[0]])));
    if(ev.length)K.rawBox(b.querySelector('.vis-raw'),v.sid,ev,{ctx:0,title:'本受试者访视记录（原始）'})})})};
K.showSite=(kind,x,title,html)=>{const b=K.drawer(title,`${sigBox()}${html}<div class="mt"><a class="small" href="center.html#c=${x.site||''}">中心画像 ›</a></div>`);K.sigCtl(b.querySelector('.sigbox'),kind,x)};

/* ---------- 行动项：把各页的风险项汇成一张「今天先处理什么」的清单 ----------
 * 分值＝类别基础分 ×1.3（本次新增/较上次加重）×1.4（关键数据）×1.2（处置后加重）；角色决定取材（item.roles）。 */
K.actions=()=>{if(K._act)return K._act;const Dd=D(),O=Dd.ops||{},out=[];
  const add=o=>{const g=K.sigGet(o.kind,o.x);o.sig=g;o.key=g.k;let sc=o.base;const tags=[];
    const dk={lab:'lab',oth:'oth',pd:'pd'}[o.kind],ds=dk?K.dst(dk,o.x):'';
    if(ds==='new'||ds==='worse'){sc*=1.3;tags.push([ds==='new'?'本次新增':'较上次加重','red'])}
    if(o.x&&o.x.ctq){sc*=1.4;tags.push(['关键数据','solid-red',o.x.ctq])}
    if(g.re){sc*=1.2;tags.push(['处置后加重','red'])}
    o.score=Math.round(sc);o.tags=tags;out.push(o)};
  const LB={CSX:[90,'CS 未关联 AE/病史'],DISW:[70,'研究疾病·较基线加重'],MH:[70,'仅关联病史·较基线加重'],NCS2:[55,'≥2 级判 NCS'],NA2:[55,'≥2 级未评价'],G2NF:[50,'≥2 级·无评价字段'],
    NA:[35,'超范围未评价'],MHU:[35,'仅关联病史·无法判断加重'],CSI:[30,'判定不一致'],'MHX-T':[25,'疑似病史漏记·首剂前']};
  K.lab.forEach(g=>{const b=g.risk==='REL'?(K.relRisk(g)?[30,'较基线显著变化·未关联']:null):LB[g.risk];if(!b)return;
    add({kind:'lab',x:g,base:b[0]+(g.mg||0)*3,roles:['mm'],sid:g.sid,site:g.site,title:`${g.test} · ${b[1]}`,why:(g.ctx||[])[0]||'',tag:['检验','org'],open:()=>K.showLabG(g)})});
  const shift=new Set(['范围内明显变化','持续变化趋势']);
  /* V6（PM 审阅 2026-11-02）：旧版这里跳过带 pdId 的信号、下面又跳过带 sig 的潜在 PD → 同一件事两头都丢（RUX 232 条、含重要 40 条）。
     改为保留信号这一条，并把潜在 PD 分级并入它的分值与标签。 */
  const PDB={'重要':60,'待判定':28,'一般':14},pdOf=Object.fromEntries(((Dd.pd||{}).potential||[]).map(p=>[p.id,p]));
  Dd.others.forEach(o=>{const p=o.pdId&&pdOf[o.pdId];if(!p&&o.pr<3&&!shift.has(o.cat))return;
    add({kind:'oth',x:o,base:Math.max(o.cat==='范围内明显变化'?32:shift.has(o.cat)?22:o.pr*12,p?PDB[p.grade]||14:0),roles:p?(/^SAFE/.test(p.rule)?['mm','cra']:['mm','cra']):['mm'],sid:o.sid,site:o.site,title:o.cat+(p?` · 潜在PD（${p.grade}）`:''),why:o.sum,tag:[shift.has(o.cat)?'变化预警':p?'方案偏离':'专项',shift.has(o.cat)?'yel':p&&p.grade==='重要'?'red':'line'],open:()=>K.showOth(o)})});
  const addedLab=new Set(out.filter(o=>o.kind==='lab').map(o=>o.x));
  ((Dd.pd||{}).potential||[]).forEach(p=>{if(p.sig&&(p.sig[0]==='oth'?(Dd.others[p.sig[1]]||{}).pdId===p.id:addedLab.has(Dd.labrows[p.sig[1]])))return;   /* 信号已列（同一件事）才跳过 */
    add({kind:'pd',x:p,base:{'重要':60,'待判定':28,'一般':14}[p.grade]||14,roles:/^SAFE/.test(p.rule)?['mm','cra']:['cra'],sid:p.sid,site:p.site,title:p.title,why:p.fact,tag:['方案偏离',p.grade==='重要'?'red':'line'],open:()=>K.showPD(p.id)})});
  (O.entry||[]).forEach(e=>add({kind:'ent',x:e,base:35,roles:['cra'],sid:e.sid,site:e.site,title:`${e.test} 疑似录入错误`,why:`${e.visit} ${e.raw} ${e.unit}：${e.why}`,tag:['数据质量','yel'],open:()=>K.showEnt(e)}));
  (O.due||[]).filter(d=>d[6]==='overdue').forEach(d=>{const v={sid:d[0],site:d[1],v:d[2],lo:d[3],hi:d[4]},late=K.days(O.cutoff,d[4])||0;
    add({kind:'vis',x:v,base:O.stage==='daily'?(late>14?20:8):25,roles:['cra'],sid:v.sid,site:v.site,title:`${v.v} 访视逾期未见记录`,why:`方案窗 ${v.lo} ~ ${v.hi}，已过窗 ${late} 天${O.stage==='daily'?'（日常监查：可能尚未录入）':''}`,tag:['访视','blu'],open:()=>K.showVis(v)})});
  const CR=K.centerRisk();
  CR.centers.forEach(c=>{CR.cats.forEach(([k,grp,l,,desc])=>{const x=(CR.cell[k]||{})[c.site];if(!x||!K.qlt(x.qu,.10))return;const t={site:c.site,k};
      add({kind:'ctr',x:t,base:K.qlt(x.qu,.05)?48:36,roles:grp==='检验'||grp==='AE'?['mm','pm']:['cra','pm'],sid:'',site:c.site,title:`中心 ${c.site}「${l}」偏高`,why:`${desc}：观察 ${x.o}，按${CR.unit}推算期望 ${x.e.toFixed(1)}`,tag:['中心','org'],
        open:()=>K.showSite('ctr',t,`${c.site} ${K.esc(K.center(c.site))} · ${l}偏高`,`<div class="box small">${K.esc(desc)}：观察 ${x.o}，期望 ${x.e.toFixed(1)}（${K.qTip(x)}）。</div><div class="mt"><a class="small" href="safety.html#tab=ov">中心总览热力图 ›</a></div>`)})});
    const x=(CR.cell.ae||{})[c.site];if(x&&K.qlt(x.ql,.10)){const t={site:c.site,k:'ae-low'};
      add({kind:'ctr',x:t,base:40,roles:['mm','cra','pm'],sid:'',site:c.site,title:`中心 ${c.site} AE 报告偏少`,why:`TEAE 观察 ${x.o}，按${CR.unit}推算期望 ${x.e.toFixed(1)}：可能漏报`,tag:['中心','blu'],
        open:()=>K.showSite('ctr',t,`${c.site} ${K.esc(K.center(c.site))} · AE 报告偏少`,`<div class="box small">TEAE 观察 ${x.o}，期望 ${x.e.toFixed(1)}（${K.qTip(x)}），建议核对该中心是否漏报 AE。</div>`)})}});
  K.qtlRows().forEach(r=>{if(r.st!=='exceed'&&r.st!=='warn')return;
    add({kind:'qtl',x:{k:r.k},base:r.st==='exceed'?85:45,roles:['pm','cra','mm'],sid:'',site:'',title:`研究层面「${r.l}」${r.st==='exceed'?'超出':'接近'}容忍限度`,why:`当前 ${K.kriFmt(r.k,r.v)}（${r.nd[0]}/${r.nd[1]}），限度 ≤${r.lim}%（${K.QTLN[K.qtlTier()]}档）`,tag:['容忍限度',r.st==='exceed'?'solid-red':'org'],open:()=>location.href='monitor.html#tab=kri'})});
  const KR=K.kri();if(KR)Object.entries(KR.sites).forEach(([site,v])=>KR.defs.filter(d=>d.qtl).forEach(d=>{const nd=v[d.k];if(!nd||nd[1]<5||(KR.na||{})[d.k])return;const s=K.qtlState(d.k,nd);if(s.st!=='exceed')return;
    add({kind:'kri',x:{site,k:d.k},base:38,roles:['pm','cra'],sid:'',site,title:`中心 ${site}「${d.l}」超出研究层面限度`,why:`${K.kriFmt(d.k,s.v)}（${nd[0]}/${nd[1]}），限度 ≤${s.lim}%`,tag:['KRI','org'],open:()=>location.href='center.html#c='+site})}));
  if(Dd.cred)Object.entries(Dd.cred.sites).forEach(([site,v])=>K.credFlags(site,v).forEach(f=>{const t={site,k:f.k};
    add({kind:'cred',x:t,base:32,roles:['cra'],sid:'',site,title:`中心 ${site} ${f.l}`,why:f.why,tag:['可信度','yel'],open:()=>K.showSite('cred',t,`${site} ${K.esc(K.center(site))} · ${f.l}`,`<div class="box small">${K.esc(f.why)}</div><div class="note small mt">${K.esc(Dd.cred.note||'')}</div><div class="mt"><a class="small" href="monitor.html#tab=cred">数据可信度 ›</a></div>`)})}));
  Object.entries(O.fresh||{}).forEach(([site,f])=>{if(!(f[2]&&f[1]!=null&&f[1]>30))return;const t={site};
    add({kind:'fresh',x:t,base:f[1]>60?42:30,roles:['cra','pm'],sid:'',site,title:`中心 ${site} ${f[1]} 天无新数据`,why:`最近一条记录 ${f[0]}，仍有 ${f[2]} 例在研`,tag:['新鲜度','yel'],
      open:()=>K.showSite('fresh',t,`${site} ${K.esc(K.center(site))} · 数据新鲜度`,`<div class="box small">最近一条记录 ${K.esc(f[0])}，距数据截止 ${f[1]} 天，仍有 ${f[2]} 例在研：请确认是否有数据未录入。</div>`)})});
  /* V6：同受试者×同日期×同类别×同表单的信号合并为一条（中心页 59 项待办里 MCH/MCHC/MCV/HCT 逐项拆行），展开见明细与原始行 */
  return K._act=(K.groupSig?K.groupSig(out):out).sort((a,b)=>b.score-a.score)};
K.actFor=role=>K.actions().filter(a=>role==='all'||a.roles.includes(role));
document.addEventListener('kz-sig',()=>{K._act=null});

/* ---------- 跨上传趋势（工作台按快照谱系汇总；单次构建为空） ---------- */
K.hist=()=>Z().history||[];
K.spark=(el,vals,o={})=>K.chart(el,{grid:{left:2,right:2,top:6,bottom:2},xAxis:{type:'category',show:false,data:vals.map((_,i)=>i)},yAxis:{type:'value',show:false,scale:true},
  tooltip:{trigger:'axis',formatter:p=>(o.lab?o.lab(p[0].dataIndex):'')+' '+(o.fmt?o.fmt(p[0].value):p[0].value)},
  series:[{type:'line',data:vals,symbol:'circle',symbolSize:4,connectNulls:true,lineStyle:{color:o.c||'#FF9900',width:1.6},itemStyle:{color:o.c||'#FF9900'}}]});
})();
