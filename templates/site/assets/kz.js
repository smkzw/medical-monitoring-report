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
/* 阈值档位：kz-tier.js 已按所选 T_base 载入该档的分析结果（window.KZV），覆盖默认档的对应数据（检验风险、专项核查、质疑、潜在 PD 等） */
(()=>{const V=window.KZV,Z=window.KZ;if(!V||!Z)return;const k=Object.keys(V)[0],v=V[k]||{};
  Object.keys(v).forEach(x=>{if(x==='meta')Object.assign(Z.meta||(Z.meta={}),v.meta);
    else if(x==='X'){if(window.KZX)Object.assign(KZX,v.X)}                                  /* 按编号索引的质疑/潜在 PD 原文，随档位替换 */
    else if(x==='todo')Z.todo=v.todo.concat((Z.todo||[]).slice(v.todoBase||0));            /* 保留工作台追加的待办 */
    else if(x!=='todoBase')Z[x]=v[x]});K.tier=k})();
K.VIS=(((window.KZ||{}).cfg||{}).visits||{}).order||['V1','V2','D1','USV','ET'];
K.VUNS=(((window.KZ||{}).cfg||{}).visits||{}).unsched||['USV'];K.VET=(((window.KZ||{}).cfg||{}).visits||{}).early||['ET'];
K.isAgg=v=>!K.VUNS.includes(v)&&!K.VET.includes(v);
K.vi=v=>{const i=K.VIS.indexOf(v);return i<0?99:i};
K.days=(a,b)=>{if(!a||!b||a.length<10||b.length<10)return null;return Math.round((new Date(a)-new Date(b))/864e5)};
K.studyDay=(d,fd)=>{const x=K.days(d,fd);return x==null?'':(x>=0?'D'+(x+1):'D'+x)};
K.clin=c=>c===2?K.p('CS','red'):c===1?K.p('NCS','yel'):c===0?K.p('正常','grn'):'';
/* 钻取行「判定与关联」列（用户 2026-10-30 裁定：参与者资料页 CS 项点开必须有链接信息）。
 * r＝受试者资料文件检验行（既有 14 位＋尾部扩位 [归因码, 原文说明, 关联摘要]，mm_build.drill_fields）；
 * 归因码：AE/MH＝已关联回溯到真实记录；disease＝研究疾病；NA＝超范围未评价；''＋CS＝未关联（灰字）。
 * 关联对象按「AE 」/「病史 」前缀跳参与者资料页对应 tab（subjects.html#s=<sid>&t=ae|mh）。 */
K.judgeCell=(r,sid)=>{const code=r[14]||'',txt=r[15]||'',sum=r[16]||'';
 const pill=r[7]===2?K.p('CS','red'):r[7]===1?K.p('NCS','yel'):r[7]===0?K.p('正常','grn'):K.p('ND','line','未评价/未查');
 const attr=code==='AE'?K.p('AE 关联','grn'):code==='MH'?K.p('病史关联','org'):code==='disease'?K.p('研究疾病','blu'):
  code==='NA'?K.p('未评价','yel'):r[7]===2?'<span class="faint">未关联</span>':'';
 const links=(sum||'').split('、').filter(Boolean).map(s=>{const ae=s.startsWith('AE ');
  return `<a class="p click ${ae?'grn':'org'}" href="subjects.html#s=${encodeURIComponent(sid||'')}&t=${ae?'ae':'mh'}" title="查看对应${ae?'AE':'病史'}记录">${K.esc(s)}</a>`}).join(' ');
 return `<div class="flex wrap" style="gap:3px;align-items:center">${pill}${attr}</div>${links?`<div style="margin-top:2px">${links}</div>`:''}${txt?`<div class="xs muted" style="margin-top:2px">${K.esc(txt)}</div>`:''}`};
K.PRI={4:['优先核实','red'],3:['需核实','org'],2:['结合临床','yel'],1:['筛查提示','']};
K.pri=n=>K.p(K.PRI[n]?.[0]||'—',K.PRI[n]?.[1]||'');
K.RISK={CSX:['CS·未关联AE/MH','solid-red','判CS但未关联AE或病史：漏报AE风险最高'],MH:['CS·仅关联MH·较基线加重','org','判CS且仅关联既往病史，系统判定给药后较基线加重，未见对应AE：请评估是否需记录AE'],MHU:['CS·仅关联MH·无法判断加重','yel','判CS并已关联病史，但基线缺失或为描述性结果，系统无法判断是否加重：请结合原始记录判断'],MHL:['已关联MH','grn','判CS并已关联既往病史，较基线未明显加重（病史延续），或加重已记录为AE：不作为风险'],NCS2:['NCS·≥2级','yel','数值落入'+((window.KZ||{}).cfg||{}).ctcaeVersion+'≥2级但判NCS'],NA2:['未评价·≥2级','yel','数值达≥2级，表单有临床意义字段但研究者未评价'],G2NF:['≥2级·表单无临床意义评价','yel','数值达≥2级，该表单没有临床意义字段（如体重）：请评估是否需记录AE'],AE:['已关联AE','grn','已有对应AE记录'],NA:['超范围·未评价','yel','给药后超出参考范围但未见研究者临床意义评价'],DIS:['CS·研究疾病表现','grn','研究者归因研究疾病，或属方案/IB 列出的研究疾病表现，且给药后未较基线进一步加重：不作为风险'],DISW:['CS·研究疾病·加重','org','研究者归因研究疾病，但给药后较基线加重：按AE定义评估'],NCS:['NCS','','异常无临床意义'],CSI:['CS·判定不一致','yel','同一受试者相近结果一次判NCS、一次判CS：发判定一致性query，不按潜在AE漏记'],REL:['较基线显著变化','yel','给药后超出参考范围且较基线同向明显变化（阈值见下方选择）；只统计未关联AE/病史的，已关联的单独标注'],'MHX-T':['疑似病史漏记·首剂前','org','首次给药前已明显超出参考范围（或达≥2级），研究者判NCS或未评价，且病史未记录（阈值见下方选择）']};
K.risk=r=>K.p(K.RISK[r]?.[0]||r,K.RISK[r]?.[1]||'',K.RISK[r]?.[2]);
/* ---- 双阈值（T_dev/T_base，PR-4）：状态读取 + REL 即时重分类 + 变更监听 ----
 * 档位来源：用户所选（localStorage，按研究编号）＞ 系统层 KZS.thresholds（工作台项目设置）＞ cfg.thresholds（构建配置，默认 30%/30%）。
 * 切换即保存并重新载入页面：T_base 按档位载入构建期结果（kz-tier.js），T_dev 与 REL/MHX-T 逐点在载入时按阈值过滤（K.applyThr），全报告同一口径。
 * per_metric 为覆盖（直接替换所选值）；metricThreshold 为收紧（有效值=min(所选,收紧值)，构建折叠进 cfg.metricTight）。 */
/* 表单代码 → 中文表单名（「edc:LBCH」→「血生化（LBCH）」） */
/* 指标正则 → 可读名（研究依据页不露正则）：去域前缀、否定前瞻、可选后缀，取含中文的备选 */
K.rxl=s=>{s=String(s||'').replace(/\(\?![^()]*(?:\([^()]*\)[^()]*)*\)/g,'').replace(/\([^()]*\)\?/g,'').replace(/\^?\\w\+:|\^?[a-z]+:|\.\*|\\b|[\^$]|\(\?:/g,'');
  const n=[...new Set(s.split(/[|()]/).map(x=>x.replace(/[\\?*+\[\]{}]/g,'').trim()).filter(x=>/[\u4e00-\u9fff]/.test(x)))];return n.slice(0,3).join('、')||[...new Set(s.split(/[|()]/).map(x=>x.replace(/[\\^$.*?+\[\]{}]/g,'').trim()).filter(Boolean))].slice(0,3).join('/')};
K.OPL={'<':'＜','<=':'≤','>':'＞','>=':'≥','==':'＝',re:'阳性'};
/* ---- 较上次（工作台多次上传：KZS.delta 记录级、KZS.riskdiff 风险项级）；键与工作台 lifecycle/riskdiff.py 同一写法 ---- */
K.RD=()=>{const R=(window.KZS||{}).riskdiff;return R&&R.basis==='prev_build'?R:null};
K.dkey={lab:g=>g.sid+'|'+g.test,oth:o=>o.qkey,ae:a=>a.sid+'|'+(a.n!=null&&a.n!==''?a.n:a.t+'|'+a.s),pd:p=>p.rule+'|'+p.sid+'|'+(p.visit||p.date||'')};
K.dst=(kind,x)=>{const R=K.RD();return R&&R[kind]?(R[kind][K.dkey[kind](x)]||''):''};
K.DPL={new:['本次新增','red'],worse:['较上次加重','red'],milder:['较上次减轻','grn']};
K.dpill=(kind,x)=>{const p=K.DPL[K.dst(kind,x)];return p?K.p(p[0],p[1]):''};
/* 「只看本次新增/加重」开关＋已解决查看；返回过滤函数 */
K.chgBar=(el,kind,onChange,label)=>{const R=K.RD();if(!R||!el)return ()=>true;let on=false;const res=((R.resolved||{})[kind]||[]);
  el.innerHTML=`<label class="chip"><input type="checkbox"> 只看本次新增/加重</label>${res.length?`<a class="small" href="javascript:void 0" style="margin-left:8px">较上次已解决 ${res.length} 条 ›</a>`:''}`;
  el.querySelector('input').onchange=e=>{on=e.target.checked;onChange()};
  const a=el.querySelector('a');if(a)a.onclick=()=>K.drawer(`较上次已解决 · ${label||''}`,`<div class="note small mb">上次有、本次不再出现（数据更正、已补关联或记录删除等）；原因请结合源数据确认。</div><table class="t"><tbody>${res.map(x=>`<tr><td style="width:90px">${K.sid(x.sid)}</td><td class="small">${K.esc(x.sum)}</td></tr>`).join('')}</tbody></table>`);
  return x=>!on||['new','worse'].includes(K.dst(kind,x))};
/* 总览「较上次」卡：数据变化（记录级）＋风险变化（风险项级）；无上一次时不显示 */
K.deltaCard=()=>{const S=window.KZS||{},DL=S.delta,R=K.RD();if(!DL)return '';
  const c=DL.counts||{},L=DL.labels||{},sum=k=>Object.values(c).reduce((a,v)=>a+(v[k]||0),0);
  const doms=['visits','ae','findings','exposure','cm','mh','efficacy','sample'].filter(d=>c[d]&&(c[d].new||c[d].changed||c[d].deleted));
  const nsub=Object.keys(DL.subjects||{}).length;
  const rk=[['lab','检验异常','safety.html#tab=lab'],['oth','专项核查','safety.html#tab=oth'],['ae','AE','safety.html#tab=ae'],['pd','潜在 PD','deviations.html']];
  const rc=R?rk.map(([k,n,h])=>{const x=(R.counts||{})[k]||{};return `<a class="drow" href="${h}"><span class="dn">${n}</span>${x.new?K.p('新增 '+x.new,'red'):''}${x.worse?K.p('加重 '+x.worse,'red'):''}${x.milder?K.p('减轻 '+x.milder,'grn'):''}${x.resolved?K.p('已解决 '+x.resolved,'grn'):''}${!(x.new||x.worse||x.milder||x.resolved)?'<span class="xs faint">无变化</span>':''}</a>`}).join(''):'';
  const aeN=(DL.aeNew||[]).slice(0,6).map(a=>`<div class="small">${K.sid(a.sid)} ${K.esc(a.label)}${a.grade?' '+K.esc(a.grade):''}</div>`).join('');
  return `<div class="card mt"><div class="hd"><h2>较上次</h2><span class="sub">对比上次上传（${K.esc(DL.prevCutoff||'—')}）· 本次为${DL.exportType==='delta'?'差异导出，已合并到上次数据':'全量导出'}</span></div>
  ${DL.warning?`<div class="box red small mb">${K.esc(DL.warning)}</div>`:''}
  <div class="grid g2"><div><div class="xs muted mb">数据变化 · 涉及 ${nsub} 名受试者 · 新增 ${sum('new')}、修改 ${sum('changed')}、删除 ${sum('deleted')} 条记录</div>
   <table class="t"><tbody>${doms.map(d=>`<tr><td style="width:96px">${K.esc(L[d]||d)}</td><td>${c[d].new?K.p('新增 '+c[d].new,'blu'):''}${c[d].changed?K.p('修改 '+c[d].changed,'org'):''}${c[d].deleted?K.p('删除 '+c[d].deleted,'line'):''}</td></tr>`).join('')||'<tr><td class="empty">无记录变化</td></tr>'}</tbody></table>
   ${aeN?`<div class="xs muted mt">新增 AE${(DL.aeNew||[]).length>6?'（前 6 条）':''}</div>${aeN}`:''}${(DL.aeWorse||[]).length?`<div class="xs muted mt">等级升高或转为 SAE 的 AE ${(DL.aeWorse||[]).length} 条</div>`:''}
   <div class="mt"><a class="small" href="subjects.html">本次有新数据的受试者 ›</a></div></div>
   <div><div class="xs muted mb">风险变化（各页可勾选「只看本次新增/加重」）</div>${rc||'<div class="small muted">本次与上次之间没有可比的风险数据</div>'}</div></div></div>`};
K.shName=sh=>{const s=String(sh||'').replace(/^[^:]*:/,''),n=((C0().sheetNames)||{})[s];return n?`${n}（${s}）`:s};
K.loc=(sh,row)=>`${K.shName(sh)}${row!=null&&row!==''?' 第'+row+'行':''}`;
/* ---- 知识层状态（study analysis.knowledge 经构建透出为 KZ.knowledge；键缺失＝旧构建，不渲染）----
 * degraded＝MedDRA 不可用（字典缺失或 AE 器官归类 0 条）：AE 未按器官系统归类、临床意义关联合理性未预判。
 * 文案三页共用一处：研究依据页「知识层状态」卡／总览顶部警示条／query 页头提示。 */
K.knCard=kn=>!kn?'':kn.degraded
 ?`<div class="c1"><div class="t">知识层状态<span class="sp"></span>${K.p('降级','red')}</div><div class="v" style="color:var(--risk)">MedDRA 字典不可用：AE 未按器官系统归类、临床意义关联合理性未预判——请检查授权字典配置后重建</div></div>`
 :`<div class="c1"><div class="t">知识层状态<span class="sp"></span>${K.p('可用','grn')}</div><div class="v">MedDRA ${K.esc(kn.meddra_version_note||kn.meddra_version||'版本未记录')} · AE 器官归类 ${kn.ae_soc||0} 条 · 关联预判 ${(kn.implausible||0)+(kn.plausible||0)+(kn.unknown||0)} 行</div></div>`;
K.knBar=kn=>kn&&kn.degraded?`<div class="box red" style="margin-bottom:10px">⚠ MedDRA 不可用（知识层降级，报告仍生成）：AE 未按器官系统归类、临床意义关联合理性未预判——请检查授权字典配置后重建（研究依据页「知识层状态」有详情）</div>`:'';
K.knHint=kn=>kn&&kn.degraded?`<div class="box red mt small">⚠ MedDRA 不可用（知识层降级，报告仍生成）：关联类核对未含知识层预判，字典恢复后重建即自动补齐。</div>`:'';
/* ---- 术语一致性按 PT 归并（安全页 AE tab）：以 MedDRA 首选术语（PT）为归并单位，
 * 只列「同一 PT 下 ≥2 个不同原文术语」的桶；pt 覆盖率 <20%（含全空/无 AE）→ 降级，不按原文术语陈列冒充判定。 ---- */
K.ptCons=aes=>{const L=aes||[];const wp=L.filter(a=>a.pt).length;
 if(!L.length||wp/L.length<0.2)return{deg:true,rows:[]};
 const b={};L.forEach(a=>{if(!a.pt)return;const t=b[a.pt]=b[a.pt]||{};t[a.t]=(t[a.t]||0)+1});
 const rows=Object.entries(b).map(([pt,t])=>[pt,Object.entries(t).sort((x,y)=>y[1]-x[1]||x[0].localeCompare(y[0]))]).filter(r=>r[1].length>=2).sort((x,y)=>y[1].length-x[1].length);
 return{deg:false,rows}};
K.thrKey='kz.thr:'+((C0().study||{}).code||'');
/* 存储 {dev,base,src}：src=user 用户在本浏览器自选（最高优先）；src=project 工作台项目阈值的本地副本（供页面脚本前载入档位用，项目设置变了会更新） */
K._thrSel=(()=>{try{return JSON.parse(localStorage.getItem(K.thrKey)||'null')}catch(e){return null}})();
K.thr=()=>{const c=(C0().thresholds)||{},S=window.KZS,u=K._thrSel,src=(u&&u.src==='user')?u:(S&&S.thresholds)?S.thresholds:(u||{}),sel={...c,...src};
  return {dev:sel.dev??c.dev??.3,base:sel.base??c.base??.3,per_metric:sel.per_metric??c.per_metric??{}}};
K.thrOf=mid=>{const t=K.thr(),pm=(t.per_metric||{})[mid]||{},ti=((C0().metricTight)||{})[mid]||{};
  const d=pm.dev??t.dev,b=pm.base??t.base;
  return {dev:ti.dev!=null?Math.min(d,ti.dev):d,base:ti.base!=null?Math.min(b,ti.base):b,ov:pm.dev!=null||pm.base!=null,tight:ti.dev!=null||ti.base!=null}};
K.relOn=g=>!!g&&g.risk==='REL'&&!g.off;
K.relRisk=g=>K.relOn(g)&&(g.bind||'none')==='none';   /* 只有未关联 AE/病史的才算需关注 */
K.relBind=g=>({AE:['已关联AE','grn'],MH:['已关联病史','grn'],DIS:['研究疾病相关','grn']}[g.bind]||({NCS:['未关联·判NCS','yel'],NA:['未关联·未评价','yel'],N:['未关联·判正常','yel'],CS:['未关联·判CS','red']}[g.judg]||['未关联','yel']));
K.thrBar=(el)=>{if(!el)return;const t=K.thr(),o=[['0.2','20%'],['0.3','30%'],['0.5','50%']];
  el.innerHTML='<span class="xs muted">阈值：偏离参考范围 ≥</span><span class="seg" id="kz-tdev"></span><span class="xs muted">且较基线变化 ≥</span><span class="seg" id="kz-tbase"></span><span class="xs faint" style="margin-left:8px">切换后整份报告按所选阈值重算（各页列表、计数、质疑、潜在 PD）</span>';
  K.seg(el.querySelector('#kz-tdev'),o,String(t.dev),v=>K.setThr({dev:+v}));K.seg(el.querySelector('#kz-tbase'),o,String(t.base),v=>K.setThr({base:+v}))};                 /* 当前所选阈值下该 REL 候选是否构成风险项 */
K.mhxOn=g=>!!g&&g.risk==='MHX-T'&&!g.off;   /* M13：偏离≥T_dev、≥2 级或定性异常（K.applyThr 已逐点过滤） */
/* 切换阈值：保存后重新载入页面（档位数据在页面脚本之前载入，全部页面从同一口径重新渲染）；与当前相同则不动 */
K._thrSave=(th,src)=>{K._thrSel={dev:th.dev,base:th.base,src};try{localStorage.setItem(K.thrKey,JSON.stringify(K._thrSel))}catch(e){}};
K.setThr=sel=>{const cur=K._thrApplied||K.thr(),nx={...K.thr(),...sel};if(nx.dev===cur.dev&&nx.base===cur.base)return cur;
  K._thrSave(nx,'user');
  if(window.KZS)KZS.thresholds={...KZS.thresholds,...K._thrSel};location.reload();return nx};
/* 工作台系统层载入后告知项目阈值：用户未自选过、且与本页渲染所用阈值不同时，存为项目副本并重新载入（档位数据须在页面脚本前载入） */
K.thrInit=th=>{if(!th||(K._thrSel&&K._thrSel.src==='user'))return;const a=K._thrApplied||{},nx={dev:th.dev??a.dev,base:th.base??a.base};
  if(nx.dev===a.dev&&nx.base===a.base)return;K._thrSave(nx,'project');location.reload()};
/* 当前阈值下的检验风险视图：REL/MHX-T 只保留达到所选阈值的异常点，全部点都不达标的整行不进入任何页面（g.off）。
 * 各页列表与计数统一用 K.lab（按下标引用 KZ.labrows 的地方不受影响）。定性结果与 ≥2 级的首剂前异常不受偏离比例阈值限制。 */
K.applyThr=()=>{K._thrApplied=(({dev,base})=>({dev,base}))(K.thr());const L=(window.KZ||{}).labrows||[];L.forEach(g=>{if(g.risk!=='REL'&&g.risk!=='MHX-T')return;g._pts=g._pts||g.pts;const t=K.thrOf(g.mid||('lab:'+g.test));
    g.pts=g._pts.filter(p=>g.risk==='REL'?(p[10]!=null&&p[6]!=null&&p[10]>=t.dev&&Math.abs(p[6])>=t.base*100):(p[10]==null||p[10]>=t.dev||(p[4]!=null&&p[4]>=2)));
    g.off=!g.pts.length;if(!g.off)g.mg=Math.max(0,...g.pts.map(p=>p[4]||0))});
  K.lab=L.filter(g=>!g.off)};
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
/* mm4：「方案偏离」进入主导航；「审阅要点」降为总览底部折叠区（methods.html 仍可直达） */
K.PAGES=[['index.html','总览'],['study.html','研究依据'],['subjects.html','参与者资料'],['timeline.html','时间线'],['safety.html','AE/MH风险'],['deviations.html','方案偏离'],['efficacy.html','有效性趋势'],['objective.html','检验检查趋势'],['queries.html','医学质疑']];
K.header=()=>{
  const cur=location.pathname.split('/').pop()||'index.html';const m=D().meta,c=C0(),st=c.study||{},br=c.brand||{};
  document.title=(document.title.split(' · ')[0]||'')+' · '+(st.short||st.code||'医学监察');
  const h=document.createElement('header');h.className='top';
  h.innerHTML=`<div class="bar"><img class="logo" src="${br.logo||'assets/logo_bot.svg'}" alt="${K.esc(br.org||'康哲药业')}"><div class="ttl"><b>${K.esc(st.title||'医学监察报告')}</b><span>${K.esc(st.subtitle||'')}</span></div>
  <nav>${K.PAGES.map(([u,t])=>`<a href="${u}" class="${u===cur?'on':''}">${t}</a>`).join('')}</nav>
  <div class="meta">${(c.headerTags||[['数据截止 '+(m.cutoff||''),'line']]).map(t=>K.p(t[0],t[1]||'line')).join('')}${c.dataStage?K.p({daily:'日常监查·数据录入中',prelock:'锁库前·全量数据',cfdi:'锁库后·核查前'}[c.dataStage]||'','line'):''}${c.blind&&c.blind.on?K.p(c.blind.tag||'盲态','blu'):''}</div></div><div class="ribbon"></div>`;
  document.body.prepend(h);
  const f=document.createElement('div');f.className='foot';const ft=c.footer||{};f.innerHTML=`<span>${K.esc(ft.left||'产品中心-医学部')}</span><span>${K.esc(ft.right||((m.sources||[]).length?'数据来源：'+m.sources.join(' · '):'数据截止 '+(m.cutoff||'')))}</span>`;document.body.append(f);
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
    return `${cap?`<div class="cap">${K.p(K.shName(sh),'sq')} 第 ${rs.map(r=>r.row).join(', ')} 行</div>`:''}<div class="listing tw"><table><thead><tr><th>行</th>${keys.map(k=>`<th>${K.esc(k)}</th>`).join('')}</tr></thead><tbody>${rs.map(r=>`<tr><td class="faint">${r.row}</td>${keys.map(k=>`<td class="${r.hl.includes(k)?'on':''}" title="${K.esc(r.f[k]||'')}">${K.esc(r.f[k]??'')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`}).join('');
};
K.hlNum=t=>K.esc(t).replace(/(\d+(?:\.\d+)?(?:\s?(?:g\/L|mmol\/L|U\/L|ms|mmHg|g\/cm²|kg|%|×10\^9\/L|umol\/L|IU\/L)))/g,'<span class="num-hl">$1</span>').replace(/(20\d\d-\d\d-\d\d)/g,'<span class="num-hl">$1</span>');
K.qById=id=>D().queries.find(q=>q.id===id);
K.qPill=id=>`<span class="p org sq click mono" data-q="${id}">${id}</span>`;
K.showQ=id=>{const q=K.qById(id);if(!q)return;const cro=D().cro.filter(c=>c[2]===q.sid);
  K.drawer(`${q.id} · ${q.cat}`,`<div class="flex wrap mb">${K.sid(q.sid)}${K.p(K.center(q.site),'line')}${K.p(K.loc(q.sh,q.row),'sq')}${K.p(q.v,'blu')}${q.test?K.p(q.test,''):''}${K.p(q.cro,q.cro==='冲突澄清'?'red':q.cro==='未见同问'?'grn':'yel')}</div>
  <div class="box org" style="font-size:13px;line-height:1.7">${K.hlNum(q.text)}</div>
  <div class="sec-t"><h2>证据记录</h2><span class="muted small">${q.ev.length} 行 · ${K.esc((C0().query||{}).note||'已写入交付表格对应记录行的首列')}</span></div><div class="ex-rows muted">载入中…</div>
  <div class="sec-t"><h2>本例 ${K.esc((C0().query||{}).extLabel||'CRO 既往意见')}</h2><span class="muted small">${cro.length} 条</span></div>${cro.length?`<table class="t"><tbody>${cro.map(c=>`<tr><td class="nowrap">${K.p(c[0],'sq')} ${c[1]}</td><td>${K.p(c[3],'blu')}</td><td>${K.esc(c[4])}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">无</div>'}`);
  const box=document.querySelector('.dr .ex-rows');const X=window.KZX;const ex=X&&Object.values(X.ex).find(e=>e.q===id);
  if(ex){box.innerHTML=K.listing(ex.rows);box.classList.remove('muted')}else{box.innerHTML=`<table class="t"><tbody>${q.ev.map(e=>`<tr><td>${K.p(K.shName(e[0]),'sq')}</td><td>行 ${e[1]}</td><td>${K.p(e[2],'blu')}</td><td>${K.esc(e[3])}</td></tr>`).join('')}</tbody></table>`}
};
document.addEventListener('click',e=>{const q=e.target.closest('[data-q]');if(q){e.preventDefault();K.showQ(q.dataset.q)}});
K.CTX=((((window.KZ||{}).cfg||{}).taxonomy||{}).ctx||[['^提醒：同期另有可能对应的 AE','提醒：同期AE未关联','yel'],['^(IB|类效应|方案列明风险)','IB/类效应风险','red'],['^已关联病史「','已关联病史','grn'],['^已关联AE：','已关联AE','grn'],['^未关联AE/病史，研究者判定NCS','未关联·判NCS','yel'],['无CTCAE条目|不能仅凭数值','无CTCAE数值条目',''],['症状/处置型','需结合症状/处置',''],['单位|换算','单位待核','org'],['基线.*(回退|替代)|替代基线|改用首次','替代基线','blu'],['研究疾病表现.*未进一步加重|研究者归因：研究疾病$','研究疾病表现·未加重','grn'],['研究疾病表现.*进一步加重','疾病表现·较基线加重','org'],['可能为研究疾病表现','可能为疾病表现','']]).map(([re,l,c])=>[new RegExp(re),l,c]);
K.ctxTags=arr=>{const out=[];(arr||[]).forEach(t=>{const m=K.CTX.find(([re])=>re.test(t));if(m&&!out.some(o=>o[0]===m[1]))out.push([m[1],m[2],t])});return out.map(([l,c,t])=>K.p(l,c,t)).join('')};
/* 声明了系统层（cfg.ext.sys）时等它载入后再渲染：页面要用到 KZS（较上次、阈值等）；最多等 4 秒，载入失败也照常渲染 */
K.init=fn=>document.addEventListener('DOMContentLoaded',()=>{const go=()=>{K.header();fn()};K._sys?K._sys.then(go):go()});
/* SoA 完成度矩阵（访视流程表 × 实际完成）：mm4 起位于「方案偏离」执行层面；研究依据页只陈述方案本身 */
K.soaView=el=>{
const ST=(window.KZ||{}).study||{},X=window.KZX||{};const COND=new Set(ST.soaCond||[]);const SX=ST.soaExclude?new RegExp(ST.soaExclude):null;
const soa=(X.soa||[]).filter(r=>!SX||!SX.test(r.sheet));const cols=X.soacols;
const vn=v=>{const r=soa.find(r=>r.cells[v]);return r?r.cells[v][0]:''};
const cell=(r,v,ri)=>{const c=r.cells[v];if(!c)return '<td class="h faint">·</td>';const [n,done,no,miss,,,ex]=c;
 if(ex)return `<td class="h"><span class="p click" data-c="${ri}|${v}" title="非计划访视记录">+${done}</span></td>`;
 const cond=COND.has(r.name);let t;
 if(miss)t=K.p('缺 '+miss,'red click');else if(no)t=K.p((cond?'否 ':'否 ')+no,(cond?'line':'yel')+' click');else t=K.p('✓','grn');
 return `<td class="h" data-c="${ri}|${v}" style="cursor:${miss||no?'pointer':'default'};padding:3px 4px" title="完成 ${done}/${n}">${t}</td>`};
el.innerHTML=`<div class="tw"><table class="t heat"><thead><tr><th>项目</th>${cols.map(v=>`<th class="h" style="text-align:center">${v}<div class="xs faint" style="font-weight:400">n=${vn(v)}</div></th>`).join('')}</tr></thead><tbody>${soa.map((r,ri)=>`<tr><td class="nowrap" style="padding:3px 8px" title="${r.sheet}">${K.esc(r.name)} ${COND.has(r.name)?K.p('条件','line'):''}</td>${cols.map(v=>cell(r,v,ri)).join('')}</tr>`).join('')}</tbody></table></div>`;
el.onclick=e=>{const td=e.target.closest('[data-c]');if(!td)return;const [ri,v]=td.dataset.c.split('|');const r=soa[+ri],c=r.cells[v];if(!c||(!c[3]&&!c[2]&&!c[6]))return;
 K.drawer(`${r.name} · ${v}`,`<div class="flex wrap mb">${K.p('访视人数 '+c[0],'line')}${K.p('完成 '+c[1],'grn')}${c[3]?K.p('无记录 '+c[3],'red'):''}${c[2]?K.p('记录“否” '+c[2],'yel'):''}${COND.has(r.name)?K.p('条件性项目','line'):''}</div>
 ${c[6]?`<div class="box small">${v} 不在流程表计划内，但有 ${c[1]} 例记录（计划外/补充检查）。</div>`:''}
 ${c[4].length?`<h3 class="mt">无记录</h3><div class="flex wrap mt">${c[4].map(s=>K.sid(s)).join(' ')}</div>`:''}
 ${c[5].length?`<h3 class="mt">记录“未做”</h3><div class="flex wrap mt">${c[5].map(s=>K.sid(s)).join(' ')}</div>`:''}
 <div class="note mt">名单来自「${K.esc(K.shName(r.sheet))}」的“是否进行”记录与访视记录比对；${COND.has(r.name)?'条件性项目的“否”可能为允许豁免，结合原因字段判断，不直接发质疑。':'计划项无记录时先核对访视是否实际发生、是否已录入，再决定是否质疑。'}</div>`,K.p(K.shName(r.sheet),'sq'))};};
/* ---- 方案偏离（mm4）：分级/类别标签、详情抽屉（总览、方案偏离、AE/MH 风险共用）---- */
K.PDG={'重要':'solid-red','待判定':'yel','一般':'line'};
K.pdGrade=g=>K.p(g||'—',K.PDG[g]||'line',g==='重要'?'可能显著影响受试者权益/安全/福祉，或关键数据完整性/准确性/可靠性（ICH E3 Q&A R1；E6(R3)）':g==='待判定'?'需结合原因、源文件或医学判断确定分级':'不满足重要偏离标准');
K.PDS={'已记录':'grn','未见记录':'org','无 PD 记录可比对':'line'};
K.pdStatus=s=>s?K.p(s,K.PDS[s]||'line',s==='未见记录'?'方案偏离记录表中未见同受试者、同类别、时间相近的记录':s==='已记录'?'方案偏离记录表已有对应记录':'未提供方案偏离记录表'):'';
K.PDA={'发 query':'blu','CRA 核实':'brn','录入 PD':'red'};
K.pdAct=a=>a?K.p(a,K.PDA[a]||'line'):'';
K.pdTax=()=>Object.fromEntries((((window.KZ||{}).pd||{}).taxonomy||[]).map(t=>[t[0],t]));
K.pdCat=c=>{const t=K.pdTax()[c];return t?K.p(t[1],t[2]==='执行'?'blu':t[2]==='科学'?'org':'line',t[3]):K.p(c||'—','line')};
K.pdBy=id=>{const P=(window.KZ||{}).pd||{};return (P.potential||[]).find(x=>x.id===id)||(P.confirmed||[]).find(x=>x.id===id)};
K.pdPill=id=>id?`<span class="p sq mono click red" data-pd="${id}" title="潜在方案偏离，点击查看">潜在PD</span>`:'';
K.PDACT={'发 query':'数据层面可澄清：经 EDC query 请研究者核实或更正；核实属实后录入 PD log。','CRA 核实':'需源文件或现场核实，数据本身不足以确认：交 CRA 核实；属实则录入 PD log 并按分级报告。','录入 PD':'数据已足以确认偏离事实：请 CRA 与研究者确认后录入 PD log；重要偏离按方案与伦理要求报告。'};
K.showPD=id=>{const it=K.pdBy(id);if(!it)return;const P=KZ.pd,X=window.KZX||{},conf=!it.rule;
  const rule=(P.rules||[]).find(r=>r.id===it.rule)||{};const m=conf?null:(P.confirmed||[]).find(c=>c.id===it.matched);
  const sig=it.sig?(it.sig[0]==='oth'?KZ.others[it.sig[1]]:KZ.labrows[it.sig[1]]):null;
  const ev=(X.pdex||{})[it.id];
  const refs=[...new Set(((sig&&sig.ctx)||[]).concat(it.ctx||[]).join(' ').match(/R-[A-Z]+-\d+/g)||[])];
  const related=conf?(P.potential||[]).filter(x=>x.matched===it.id):[];
  K.drawer(`${it.id} · ${K.esc(conf?(it.rawCat||'已记录方案偏离'):it.title)}`,`
  <div class="flex wrap mb">${K.sid(it.sid)}${K.p(K.center(it.site),'line')}${it.visit?K.p(it.visit,'blu'):''}${it.date?K.p(it.date,'line'):''}${K.pdGrade(it.grade)}${conf?(it.rawGrade?K.p('原文：'+it.rawGrade,'line'):''):K.pdStatus(it.status)}${conf?'':K.pdAct(it.action)}</div>
  <div class="box ${it.grade==='重要'?'red':'org'}" style="font-size:13px;line-height:1.7">${K.hlNum(conf?it.desc:it.fact)}</div>
  ${conf?'':`<div class="sec-t"><h2>分级与依据</h2></div><div class="flex small" style="align-items:flex-start;line-height:1.7">${K.pdGrade(it.grade)}<span>${K.esc(it.why)}</span></div>
  <div class="xs muted mt" style="line-height:1.7">重要偏离：可能显著影响受试者权益、安全或福祉，或显著影响关键数据的完整性、准确性、可靠性（ICH E3 Q&A R1；ICH E6(R3)）。潜在 PD 由数据推断，核实属实前不计入 PD 率。</div>`}
  <div class="sec-t"><h2>源数据</h2><span class="muted small">${ev?ev.length+' 行':'未取得原始行'}</span></div>${ev?K.listing(ev):(it.src||[]).length?`<table class="t"><tbody>${it.src.map(s=>`<tr><td>${K.p(K.shName(s[0]),'sq')}</td><td>行 ${s[1]??'—'}</td><td>${K.esc(s[2]||'')}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">按方案访视计划推断，无对应原始记录</div>'}
  ${conf?`<div class="sec-t"><h2>归类</h2></div><div class="kv"><dt>统一分类</dt><dd>${K.pdCat(it.cat)} ${K.p(it.layer||'—','line')}</dd><dt>原文类别</dt><dd>${K.esc(it.rawCat||'—')} ${K.esc(it.sub||'')}</dd><dt>数据比对</dt><dd>${related.length?related.map(r=>`<span class="p sq mono click line" data-pd="${r.id}">${r.id}</span> ${K.esc(r.title)}`).join('<br>'):'<span class="muted">需现场/源文件核查（数据核查不覆盖）</span>'}</dd></div>`
  :`<div class="sec-t"><h2>判定依据</h2>${refs.map(r=>K.rp(r)).join('')}</div><div class="kv"><dt>检查</dt><dd>${K.esc(rule.title||'')}</dd><dt>逻辑</dt><dd>${K.esc(rule.logic||'')}</dd><dt>所需数据</dt><dd>${K.esc(rule.data||'')}</dd></div>
  <div class="sec-t"><h2>与已记录 PD 比对</h2></div>${m?`<div class="box grn small"><b>${m.id}</b> ${K.esc(m.date)} · ${K.esc(m.rawCat)}：${K.esc(m.desc)}${m.rawGrade?' （'+K.esc(m.rawGrade)+'）':''}</div>`:`<div class="box small">${it.status==='无 PD 记录可比对'?'未提供方案偏离记录表，无法比对。':'方案偏离记录表中未见同受试者、同类别、时间相近的记录。'}</div>`}
  ${sig?`<div class="sec-t"><h2>关联信号与质疑</h2></div><div class="flex wrap">${it.sig[0]==='lab'?`<a href="safety.html#tab=lab&risk=${sig.risk}">${K.risk(sig.risk)}</a>`:`<a href="safety.html#tab=oth&cat=${encodeURIComponent(sig.cat)}">${K.p(sig.cat,'line')}</a>`}${(sig.q||[]).map(K.qPill).join('')}${K.ctxTags(sig.ctx)}</div>`:''}
  <div class="sec-t"><h2>处理建议</h2>${K.pdAct(it.action)}</div><div class="small" style="line-height:1.7">${K.esc(K.PDACT[it.action]||'')}</div>${it.tip?`<div class="note small mt" style="line-height:1.7">${K.esc(it.tip)}</div>`:''}`}
  <div class="mt"><a class="small" href="timeline.html#s=${it.sid}">查看 ${it.sid} 时间线 ›</a>　<a class="small" href="deviations.html#id=${it.id}">在方案偏离页定位 ›</a></div>`,conf?K.pdCat(it.cat):`${K.pdCat(it.cat)}${K.p(it.layer+'层面','line')}`)};
document.addEventListener('click',e=>{const a=e.target.closest('[data-pd]');if(a){e.preventDefault();K.showPD(a.dataset.pd)}});
K.applyThr();
})();
K.DOM=(((window.KZ||{}).cfg||{}).taxonomy||{}).domains||[];
K.domOf=cat=>{const d=K.DOM.find(d=>d[1].includes(cat));return d?d[0]:'其他'};
K.IBC=Object.assign({'IB已识别风险':'red','IB潜在风险':'org','方案AESI':'solid-red','类效应·预期':'blu','疾病相关':'','同类常见':''},(((window.KZ||{}).cfg||{}).taxonomy||{}).ibColors||{});
K.ibTags=cat=>((window.KZ.ibtag||{})[cat]||[]).map(t=>K.p(t,K.IBC[t]||'')).join('');
/* protocol/IB rule pills + drawer */
K.SRC=Object.assign({protocol_soa:['方案 SoA','blu'],protocol_appendix:['方案附录','blu'],sap:['SAP','grn'],ib:['IB','red'],user_confirmed:['用户确认','grn'],protocol_operative:['方案原文','org'],protocol_footnote:['方案脚注','blu'],protocol_amendment_history:['修订史',''],user_confirmed_monitoring:['项目确认','grn'],ib_classification:['IB 风险分类','red'],ib_text:['IB 原文','red'],class_effect_cited:['同类药物（IB引用）','brn']},(((window.KZ||{}).cfg||{}).taxonomy||{}).sources||{});
K.ruleBy=id=>(window.KZ.rules||[]).find(r=>r.id===id);
K.rp=(id,c='')=>`<span class="p sq click ${c||'line'}" data-r="${id}" title="${K.esc((K.ruleBy(id)||{}).st||'')}">原文</span>`;   /* 不显示内部规则编号，点开看原文 */
K.showRule=id=>{const r=K.ruleBy(id);if(!r)return;const un=(window.KZ.unres||[]).find(u=>u.startsWith(id+' '));
  K.drawer(`${K.esc(r.dom||'规则')} · 原文依据`,`<div class="box org" style="font-size:13px;line-height:1.75">${K.hlNum(r.st)}</div>${un?`<div class="box red mt small"><b>口径待确认：</b>${K.esc(un)}</div>`:''}
  <div class="sec-t"><h2>原文定位</h2><span class="muted small">${r.src.length} 处</span></div><table class="t"><tbody>${r.src.map(s=>`<tr><td class="nowrap">${K.p((K.SRC[s[2]]||[s[2]])[0],(K.SRC[s[2]]||[0,''])[1])}</td><td class="nowrap xs muted">${K.esc(s[0])}</td><td>${K.esc(s[1])}</td></tr>`).join('')}</tbody></table>`,K.p(r.dom,'line'))};
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
  const sys = [].concat(ex.sys || []);
  let done = null;
  if (sys.length) window.K._sys = new Promise(res => { done = res; setTimeout(res, 4000); });
  [].concat(sys, ex.js || []).forEach((s, i) => { const t = document.createElement('script'); t.src = s; t.async = false;
    if (done && i === sys.length - 1) t.onload = t.onerror = () => done();
    head.appendChild(t); });
})();
