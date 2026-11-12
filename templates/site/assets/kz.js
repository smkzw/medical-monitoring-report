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
/* V6 R10：工作台回写的 AI 来源质疑（CSB/医学审阅，KZ.qx，不随档位）按 qkey 并入质疑列表——报告与质疑工作簿同一口径 */
(()=>{const Z=window.KZ;if(!Z||!Array.isArray(Z.qx)||!Array.isArray(Z.queries))return;const s=new Set(Z.queries.map(q=>q.qkey));
  Z.qx.forEach(q=>{if(!s.has(q.qkey)){Z.queries.push(q);s.add(q.qkey)}})})();
K.VIS=(((window.KZ||{}).cfg||{}).visits||{}).order||['V1','V2','D1','USV','ET'];
K.VUNS=(((window.KZ||{}).cfg||{}).visits||{}).unsched||['USV'];K.VET=(((window.KZ||{}).cfg||{}).visits||{}).early||['ET'];
K.isAgg=v=>!K.VUNS.includes(v)&&!K.VET.includes(v);
K.vi=v=>{const i=K.VIS.indexOf(v);return i<0?99:i};
K.days=(a,b)=>{if(!a||!b||a.length<10||b.length<10)return null;return Math.round((new Date(a)-new Date(b))/864e5)};
/* V6（用户审阅 RUX 第 19 条）：检验时间字段只接受时:分（此前「页面最近修改时间」被映射成采样时间，拼出非法时间戳，抽屉图整张空白） */
K.dd=(a,b)=>{const x=Date.parse(String(a).slice(0,10)),y=Date.parse(String(b).slice(0,10));return isNaN(x)||isNaN(y)?'?':Math.round((y-x)/864e5)};   /* 两日期相差天数（b−a） */
K.hhmm=t=>/^\d{1,2}:\d{2}(:\d{2})?$/.test(String(t||'').trim());
K.dt=(d,t)=>{d=String(d||'').slice(0,10);return K.hhmm(t)?d+'T'+String(t).trim().replace(/^(\d):/,'0$1:'):d};
K.studyDay=(d,fd)=>{const x=K.days(d,fd);return x==null?'':(x>=0?'D'+(x+1):'D'+x)};
K.clin=c=>c===2?K.p('CS','red'):c===1?K.p('NCS','yel'):c===0?K.p('正常','grn'):'';
/* 钻取行「判定与关联」列（用户 2026-10-30 裁定：参与者资料页 CS 项点开必须有链接信息）。
 * r＝参与者资料文件检验行（既有 14 位＋尾部扩位 [归因码, 原文说明, 关联摘要]，mm_build.drill_fields）；
 * 归因码：AE/MH＝已关联回溯到真实记录；disease＝研究疾病；NA＝超范围未评价；''＋CS＝未关联（灰字）。
 * 关联对象按「AE 」/「病史 」前缀跳参与者资料页对应 tab（subjects.html#s=<sid>&t=ae|mh）。 */
K.judgeCell=(r,sid)=>{const code=r[14]||'',txt=r[15]||'',sum=r[16]||'';
 const pill=r[7]===2?K.p('CS','red'):r[7]===1?K.p('NCS','yel'):r[7]===0?K.p('正常','grn'):K.p('ND','line','未评价/未查');
 const attr=code==='AE'?K.p('AE 关联','grn'):code==='MH'?K.p('病史关联','org'):code==='disease'?K.p('研究疾病','blu'):
  code==='NA'?K.p('未评价','yel'):r[7]===2?'<span class="faint">未关联</span>':'';
 const links=(sum||'').split('；').filter(Boolean).map(s=>{const ae=s.startsWith('AE ');
  return `<a class="p click ${ae?'grn':'org'}" href="subjects.html#s=${encodeURIComponent(sid||'')}&t=${ae?'ae':'mh'}" title="查看对应${ae?'AE':'病史'}记录">${K.esc(s)}</a>`}).join(' ');
 return `<div class="flex wrap" style="gap:3px;align-items:center">${pill}${attr}</div>${links?`<div style="margin-top:2px">${links}</div>`:''}${txt?`<div class="xs muted" style="margin-top:2px">${K.esc(txt)}</div>`:''}`};
K.PRI={4:['优先核实','red'],3:['需核实','org'],2:['结合临床','yel'],1:['筛查提示','']};
K.pri=n=>K.p(K.PRI[n]?.[0]||'—',K.PRI[n]?.[1]||'');
K.RISK={HXU:['有临床意义·已归因既往情况·病史未记录','org','说明已写明与既往手术/病史/生理状态相关，但病史与手术史中未见记录：请补充病史（不按漏报 AE 处理）'],CSX:['有临床意义·未关联AE/病史','solid-red','判为有临床意义但未关联AE或病史：漏报AE风险最高'],MH:['有临床意义·仅关联病史·加重','org','判为有临床意义且仅关联既往病史，系统判定给药后较基线加重，未见对应AE：请评估是否需记录AE'],MHU:['有临床意义·仅关联病史·无法判断加重','yel','判为有临床意义并已关联病史，但基线缺失或为描述性结果，系统无法判断是否加重：请结合原始记录判断'],MHL:['已关联MH','grn','判为有临床意义并已关联既往病史，较基线未明显加重（病史延续），或加重已记录为AE：不作为风险'],NCS2:['无临床意义·≥2级','yel','数值落入'+((window.KZ||{}).cfg||{}).ctcaeVersion+'≥2级但判为无临床意义'],NA2:['未评价·≥2级','yel','数值达≥2级，表单有临床意义字段但研究者未评价'],G2NF:['≥2级·表单无临床意义评价','yel','数值达≥2级，该表单没有临床意义字段（如体重）：请评估是否需记录AE'],AE:['已关联AE','grn','已有对应AE记录'],NA:['超范围·未评价','yel','给药后超出参考范围但未见研究者临床意义评价'],DIS:['研究疾病表现','grn','研究者归因研究疾病，或属方案/IB 列出的研究疾病表现，且给药后未较基线进一步加重：不作为风险'],DISW:['研究疾病表现·加重','org','研究者归因研究疾病，但给药后较基线加重：按AE定义评估'],ENT:['疑似录入错误·超出生理范围','yel','数值超出生理可能范围（如平均红细胞容积 26.5 fl）：请中心核对录入，不按 AE 追问'],PART:['复合定义单项达标','line','方案该事件为复合定义（需同时满足其他条件），仅单项达标：只作提示'],DISL:['研究疾病指标波动','line','研究者归因研究疾病，按疾病不利方向较基线变化明显，但未达3级、分级未上升：列清单供医学人员查看，不发质疑'],NCS:['无临床意义','','异常无临床意义'],CSI:['临床意义判定不一致','yel','同一参与者相近结果一次判为无临床意义、一次判为有临床意义：发判定一致性query，不按潜在AE漏记'],REL:['较基线显著变化','yel','给药后超出参考范围且较基线同向明显变化（阈值见下方选择）；只统计未关联AE/病史的，已关联的单独标注'],'MHX-T':['疑似病史漏记·首剂前','org','首次给药前已明显超出参考范围（或达≥2级），研究者判为无临床意义或未评价，且病史未记录（阈值见下方选择）']};
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
  <div class="grid g2"><div><div class="xs muted mb">数据变化 · 涉及 ${nsub} 名参与者 · 新增 ${sum('new')}、修改 ${sum('changed')}、删除 ${sum('deleted')} 条记录</div>
   <table class="t"><tbody>${doms.map(d=>`<tr><td style="width:96px">${K.esc(L[d]||d)}</td><td>${c[d].new?K.p('新增 '+c[d].new,'blu'):''}${c[d].changed?K.p('修改 '+c[d].changed,'org'):''}${c[d].deleted?K.p('删除 '+c[d].deleted,'line'):''}</td></tr>`).join('')||'<tr><td class="empty">无记录变化</td></tr>'}</tbody></table>
   ${aeN?`<div class="xs muted mt">新增 AE${(DL.aeNew||[]).length>6?'（前 6 条）':''}</div>${aeN}`:''}${(DL.aeWorse||[]).length?`<div class="xs muted mt">等级升高或转为 SAE 的 AE ${(DL.aeWorse||[]).length} 条</div>`:''}
   <div class="mt"><a class="small" href="subjects.html">本次有新数据的参与者 ›</a></div></div>
   <div><div class="xs muted mb">风险变化（各页可勾选「只看本次新增/加重」）</div>${rc||'<div class="small muted">本次与上次之间没有可比的风险数据</div>'}</div></div></div>`};
K.shCN=sh=>{const s=String(sh||'').replace(/^[^:]*:/,'');return ((C0().sheetNames)||{})[s]||s};   /* 只要中文表单名（有中文名时不带数据集代码） */
K.shName=sh=>{const s=String(sh||'').replace(/^[^:]*:/,''),n=((C0().sheetNames)||{})[s];return n?`${n}（${s}）`:s};
K.loc=(sh,row)=>`${K.shName(sh)}${row!=null&&row!==''?' 第'+row+'行':''}`;
/* ---- 知识层状态（study analysis.knowledge 经构建透出为 KZ.knowledge；键缺失＝旧构建，不渲染）----
 * degraded＝MedDRA 不可用（字典缺失或 AE 器官归类 0 条）：AE 未按器官系统归类、临床意义关联合理性未预判。
 * 文案三页共用一处：研究依据页「知识层状态」卡／总览顶部警示条／query 页头提示。 */
K.knCard=kn=>!kn?'':kn.degraded
 ?`<div class="c1"><div class="t">知识层状态<span class="sp"></span>${K.p('降级','red')}</div><div class="v" style="color:var(--risk)">MedDRA 字典不可用：AE 未按器官系统归类、临床意义关联合理性未预判——请检查授权字典配置后重建</div></div>`
 :`<div class="c1"><div class="t">知识层状态<span class="sp"></span>${K.p('可用','grn')}</div><div class="v">MedDRA ${K.esc(kn.meddra_version_note||kn.meddra_version||'版本未记录')} · AE 器官归类 ${kn.ae_soc||0} 条 · 关联预判 ${(kn.implausible||0)+(kn.plausible||0)+(kn.unknown||0)} 行</div></div>`;
K.knBar=kn=>kn&&kn.degraded?`<div class="box red" style="margin-bottom:10px">⚠ 医学术语词典暂不可用：不良事件未按器官系统归类，检验异常与 AE/病史的对应关系未预判。请联系管理员恢复词典后重新生成报告。</div>`:'';
K.knHint=kn=>kn&&kn.degraded?`<div class="box red mt small">⚠ 医学术语词典暂不可用：本页关联类核对不完整，词典恢复后重新生成即可补齐。</div>`:'';
/* ---- 术语一致性按 PT 归并（安全页 AE tab）：以 MedDRA 首选术语（PT）为归并单位，
 * 只列「同一 PT 下 ≥2 个不同原文术语」的桶；pt 覆盖率 <20%（含全空/无 AE）→ 降级，不按原文术语陈列冒充判定。 ---- */
K.ptCons=aes=>{const L=aes||[];const wp=L.filter(a=>a.pt).length;
 if(!L.length||wp/L.length<0.2)return{deg:true,rows:[]};
 const b={};L.forEach(a=>{if(!a.pt)return;const t=b[a.pt]=b[a.pt]||{};t[a.t]=(t[a.t]||0)+1});
 const rows=Object.entries(b).map(([pt,t])=>[pt,Object.entries(t).sort((x,y)=>y[1]-x[1]||x[0].localeCompare(y[0]))]).filter(r=>r[1].length>=2).sort((x,y)=>y[1].length-x[1].length);
 return{deg:false,rows}};
/* F5（V6 RUX）：研究编号缺失时键回退项目 id／报告路径——不退化成全局键（跨项目/跨页互相改写档位）；
 * 与 kz-tier.js 的档位载入键同一表达式（两处必须一致）。 */
K.thrKey='kz.thr:'+((C0().study||{}).code||((window.KZS||{}).project||{}).id||(typeof location!=='undefined'?location.pathname.replace(/\/[^\/]*$/,'').replace(/[^0-9A-Za-z_-]+/g,'').slice(-48):'')||'report');
/* 存储 {dev,base,src}：src=user 用户在本浏览器自选（最高优先）；src=project 工作台项目阈值的本地副本（供页面脚本前载入档位用，项目设置变了会更新） */
K._thrSel=(()=>{try{return JSON.parse(localStorage.getItem(K.thrKey)||'null')}catch(e){return null}})();
K.thr=()=>{const c=(C0().thresholds)||{},S=window.KZS,u=K._thrSel,src=(u&&u.src==='user')?u:(S&&S.thresholds)?S.thresholds:(u||{}),sel={...c,...src};
  return {dev:sel.dev??c.dev??.3,base:sel.base??c.base??.3,per_metric:sel.per_metric??c.per_metric??{}}};
K.thrOf=mid=>{const t=K.thr(),pm=(t.per_metric||{})[mid]||{},ti=((C0().metricTight)||{})[mid]||{};
  const d=pm.dev??t.dev,b=pm.base??t.base;
  return {dev:ti.dev!=null?Math.min(d,ti.dev):d,base:ti.base!=null?Math.min(b,ti.base):b,ov:pm.dev!=null||pm.base!=null,tight:ti.dev!=null||ti.base!=null}};
K.relOn=g=>!!g&&g.risk==='REL'&&!g.off;
K.relRisk=g=>K.relOn(g)&&(g.bind||'none')==='none';   /* 只有未关联 AE/病史的才算需关注 */
K.relBind=g=>({AE:['已关联AE','grn'],MH:['已关联病史','grn'],DIS:['研究疾病相关','grn']}[g.bind]||({NCS:['未关联·判为无临床意义','yel'],NA:['未关联·未评价','yel'],N:['未关联·判正常','yel'],CS:['未关联·判为有临床意义','red']}[g.judg]||['未关联','yel']));
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
K.STC=Object.assign({'完成试验':'grn','已入组':'blu','治疗结束':'brn','提前终止治疗':'brn','提前退出':'red','筛选失败':'','筛选中':'yel'},(((window.KZ||{}).cfg||{}).statusColors)||{});
K.status=s=>K.p(s,K.STC[s]??'');
/* header */
/* V5（用户 2026-10-31 晚）：主导航固定 8 项；「临床监查」「安全性概览」是由多个页面组成的空间，页内第二行为空间子导航。
 * 方案偏离并入临床监查空间；「审阅要点与方法」页取消。V6：统一写「监查」。 */
K.SPACES={monitor:[['monitor.html','监查概况'],['deviations.html','方案偏离'],['center.html','中心画像']],
  safety:[['profile.html','概览'],['safety.html','AE/MH 风险'],['objective.html','检验检查趋势']],
  subjects:[['subjects.html','个例资料'],['raw.html','原始数据']]};   /* V6：listing 原始数据就地浏览 */
K.PAGES=[['index.html','总览'],['monitor.html','临床监查','monitor'],['profile.html','安全性概览','safety'],['efficacy.html','有效性概览'],
  ['subjects.html','参与者资料','subjects'],['timeline.html','时间线'],['queries.html','医学质疑'],['study.html','研究依据']];
K.spaceOf=p=>Object.keys(K.SPACES).find(s=>K.SPACES[s].some(([u])=>u===p))||'';
/* V6（用户审阅 RUX 第 14 条、裁定 6）：顶栏＝智研 METRIC 平台标识＋当前子系统标识（等高）；临床监查空间页显示「数字化临床监查」，
 * 其余页显示「数字化医学监查」；右侧固定显示项目代号（不写完整项目名、不写「医学监查报告」）；工作台有待确认的 CS 解释时页眉红标。 */
/* 智研 METRIC 统一页头（kangzhe-design design_specs/16，用户 2026-11-11：主标｜子系统横版，不放康哲标志）：[横版, 中文名, 方形图标] */
K.SUBSYS={cm:['assets/brand/metric/sub-C-lockup-header.svg','数字化临床监查','assets/brand/metric/sub-C.svg'],mm:['assets/brand/metric/sub-M-lockup-header.svg','数字化医学监查','assets/brand/metric/sub-M.svg']};
K.header=()=>{
  const cur=location.pathname.split('/').pop()||'index.html';const m=D().meta,c=C0(),st=c.study||{},br=c.brand||{};
  const code=st.short||st.code||'',sub=K.SUBSYS[K.spaceOf(cur)==='monitor'?'cm':'mm'];
  document.title=[(document.title.split(' · ')[0]||''),code,sub[1],'智研 METRIC'].filter(Boolean).join(' · ');
  {let ic=document.querySelector('link[rel="icon"]');if(!ic){ic=document.createElement('link');ic.rel='icon';ic.type='image/svg+xml';document.head.append(ic)}ic.href=sub[2]}
  const pend=+((((window.KZS||{}).csb)||{}).pending||0);
  const h=document.createElement('header');h.className='top';
  h.innerHTML=`<div class="bar"><a class="brand" href="index.html" title="智研 METRIC · ${sub[1]}"><img class="logo" src="${K.esc(br.platform||'assets/brand/metric/lockup-3x1-header.svg')}" alt="智研 METRIC"><span class="bsep"></span><img class="logo sub" src="${sub[0]}" alt="${sub[1]}"><img class="logo subi" src="${sub[2]}" alt="${sub[1]}"></a>
  <nav>${K.PAGES.map(([u,t,sp])=>`<a href="${u}" class="${u===cur||(sp&&sp===K.spaceOf(cur))?'on':''}">${t}</a>`).join('')}</nav>
  <div class="meta">${code?`<span class="proj" title="项目代号">${K.esc(code)}</span>`:''}${/* F12④：CS 待确认移到研究依据页系统提示（kz-sys 写入 #todo），页头不再挂红标 */ ''}${(c.headerTags||[['截止 '+(m.cutoff||''),'line','数据截止日期']]).map(t=>K.p(t[0],t[1]||'line',t[2])).join('')}${c.dataStage?K.p({daily:'日常监查',prelock:'锁库前',cfdi:'锁库后'}[c.dataStage]||'','line',{daily:'日常监查·数据录入中',prelock:'锁库前·全量数据',cfdi:'锁库后·核查前'}[c.dataStage]||''):''}${(()=>{/* CRA 测试（2026-11-11）：日常监查数据截止距今 >30 天要醒目提示，避免按旧数据安排访视 */
      const d=K.dd(m.cutoff,new Date().toISOString().slice(0,10));return c.dataStage==='daily'&&typeof d==='number'&&d>30?K.p(`数据已 ${d} 天未更新`,'org','数据截止 '+(m.cutoff||'')+'；访视、逾期与新鲜度均按截止日计算，请上传最新数据'):''})()}${c.blind&&c.blind.on?K.p(c.blind.tag||'盲态','blu'):''}</div></div>${(()=>{const sp=K.spaceOf(cur);return sp?`<div class="subnav"><div class="in">${K.SPACES[sp].map(([u,t])=>`<a href="${u}" class="${u===cur?'on':''}">${t}</a>`).join('')}</div></div>`:''})()}`;
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
/* ---- V6 原始数据层（data/rawidx.js 表单目录＋data/r/<sid>.js 按参与者原始行；raw_export.py 生成）
 * 用户 2026-11-02：风险/质疑/异常旁边直接看原始数据，不再另开 Excel。证据 [sh,row] 的 sh 与表单 id 同口径（工作簿别名:表单名）。 */
K._rc={};K._rw={};
window.KZ_RAW=(id,d)=>{K._rc[id]=d;(K._rw[id]||[]).forEach(f=>f(d));delete K._rw[id]};
K._js=src=>new Promise(res=>{const s=document.createElement('script');s.src=src;s.onload=()=>res(true);s.onerror=()=>res(false);document.head.append(s)});
K.rawIdx=async()=>{if(window.KZRI)return window.KZRI;if(!K._ri)K._ri=K._js('data/rawidx.js');await K._ri;return window.KZRI||null};
K.raw=async id=>{if(K._rc[id])return K._rc[id];const I=await K.rawIdx();if(!I||!(I.subs||{})[id])return null;
  return new Promise(res=>{(K._rw[id]=K._rw[id]||[]).push(res);if(K._rw[id].length>1)return;K._js('data/r/'+encodeURIComponent(id)+'.js').then(ok=>{if(!ok){res(null);delete K._rw[id]}})})};
/* 按表单载入（原始数据页）：只缓存当前一张表单，切换即释放 */
K._rsw={};window.KZ_RAWS=(k,d)=>{K._rsc={k,d};(K._rsw[k]||[]).forEach(f=>f(d));delete K._rsw[k]};
K.rawSheet=async k=>{if(K._rsc&&K._rsc.k===k)return K._rsc.d;const I=await K.rawIdx();const m=I&&I.sheets[k];if(!m||m.f==null)return null;
  return new Promise(res=>{(K._rsw[k]=K._rsw[k]||[]).push(res);if(K._rsw[k].length>1)return;K._js('data/rs/'+m.f+'.js').then(ok=>{if(!ok){res(null);delete K._rsw[k]}})})};
/* 证据表单键归一：完整 id 直接用；只给表单名（旧证据）时按名称唯一匹配 */
K.rawKey=(I,sh)=>{if(!I||!sh)return null;if(I.sheets[sh])return sh;const nm=String(sh).replace(/^[^:]*:/,'');const ks=Object.keys(I.sheets).filter(k=>(I.sheets[k].sheet||I.sheets[k].name)===nm);return ks.length?ks[0]:null};
/* 原始行表格：meta＝表单目录项，rows＝[[行号,…值]]，hit＝命中行号集合（加粗＋命中列高亮） */
/* 列顺序：判定相关列（hl）在前，其余内容列居中，EDC 系统元数据列（研究中心/参与者状态/页面…）放最后 */
K.RAW_META=/^(MM comment|Flag|研究中心|中心编号|中心名称|试验中心.*|受试者状态|页面.*|数据节|Instance.*|数据块|Block.*|数据页|最后修改时间|项目编号|项目名称|表单编号|表单集.*|行号|记录号|GROUPID|是否失活|数据库版本|访视OID|表单OID)$/i;
K.rawOrder=meta=>{const hl=new Set(meta.hl||[]),ix=meta.cols.map((c,j)=>j);const rk=j=>hl.has(meta.cols[j])?0:K.RAW_META.test(meta.cols[j])?2:1;return ix.sort((a,b)=>rk(a)-rk(b)||a-b)};
K.rawTable=(meta,rows,hit=new Set(),{max=400}={})=>{const hl=new Set(meta.hl||[]);const ord=K.rawOrder(meta),cols=ord.map(j=>meta.cols[j]);
  const cst=Object.entries(meta.const||{});
  return `${cst.length?`<div class="xs faint mb">本表单固定值：${cst.slice(0,6).map(([k,v])=>`${K.esc(k)}＝${K.esc(v)}`).join('；')}${cst.length>6?'…':''}</div>`:''}<div class="listing tw"><table><thead><tr><th>行</th>${cols.map(c=>`<th${hl.has(c)?' class="hlc"':''}>${K.esc(c)}</th>`).join('')}</tr></thead><tbody>${rows.slice(0,max).map(r=>{const h=hit.has(r[0]);
    return `<tr class="${h?'hit':''}"><td class="faint">${r[0]}</td>${ord.map(j=>{const c=meta.cols[j];return `<td class="${h&&hl.has(c)?'on':''}" title="${K.esc(r[j+1])}">${K.esc(r[j+1])}</td>`}).join('')}</tr>`}).join('')}</tbody></table></div>${rows.length>max?`<div class="xs muted">仅显示前 ${max} 行（共 ${rows.length} 行）</div>`:''}`};
/* 证据原始行区：ev＝[[sh,row]…]。每张表单默认显示命中行及其前后各 ctx 行（同参与者），可展开本参与者该表单全部行 */
K.rawBox=async(el,sid,ev,{ctx=2,title='原始数据'}={})=>{if(!el)return;el.innerHTML='<div class="empty small">载入原始数据…</div>';
  const I=await K.rawIdx(),R=I&&await K.raw(sid);
  if(!I||!R){el.innerHTML=I?'<div class="note small">该参与者无原始数据文件。</div>':'';return}
  const by={};(ev||[]).forEach(e=>{const k=K.rawKey(I,e[0]);if(k&&R[k])(by[k]=by[k]||new Set()).add(+e[1])});
  const ks=Object.keys(by);if(!ks.length){el.innerHTML='';return}
  el.innerHTML=`<div class="sec-t"><h2>${K.esc(title)}</h2><span class="muted small">listing 原行 · 橙底为本条涉及的行与列 · 已剔除姓名/缩写等隐私列</span></div>`+ks.map((k,i)=>{const m=I.sheets[k],rows=R[k],hit=by[k];
    const idx=rows.map((r,j)=>hit.has(r[0])?j:-1).filter(j=>j>=0);const keep=new Set();idx.forEach(j=>{for(let d=-ctx;d<=ctx;d++)if(rows[j+d])keep.add(j+d)});
    const part=rows.filter((r,j)=>keep.has(j));
    return `<div class="raw-sh" data-i="${i}"><div class="cap">${K.p(m.name,'sq')} 第 ${[...hit].join('、')} 行 <span class="faint">· 本参与者该表单 ${rows.length} 行</span>${rows.length>part.length?` <a class="small raw-all" data-k="${K.esc(k)}">显示全部</a>`:''}</div><div class="raw-tb">${K.rawTable(m,part,hit)}</div></div>`}).join('');
  el.querySelectorAll('.raw-all').forEach(a=>a.onclick=()=>{const k=a.dataset.k;a.closest('.raw-sh').querySelector('.raw-tb').innerHTML=K.rawTable(I.sheets[k],R[k],by[k]);a.remove()})};
K.sub=id=>new Promise(res=>{if(K._cache[id])return res(K._cache[id]);(K._wait[id]=K._wait[id]||[]).push(res);if(K._wait[id].length>1)return;const s=document.createElement('script');s.src='data/s/'+id+'.js';s.onerror=()=>res(null);document.head.append(s)});
/* table（V6 用户审阅 RUX 第 3/6 条：所有表格可筛选、可排序；参与者号/分级/访视/日期类列不折行）
 * 排序：每列都可点（有 s/k 用其值，否则按单元格文字；两侧都是数字按数值）。
 * 筛选：>8 行时表上方出现搜索框＋最多 4 个分类列下拉（取值 2–25 种）；页面自己的筛选（tb.set）照常叠加。
 * 不折行：列标题含参与者/访视/日期/分级/等级/中心/编号/排名/优先级等，或 c.nw=true；c.nw=false 可关闭。 */
K.NWT=/受试者|参与者|访视|日期|时间|分级|等级|级别|中心|编号|排名|优先级|^风险$|状态|方案窗|目标日|实际/;
K.cellTxt=h=>String(h==null?'':h).replace(/<[^>]+>/g,' ').replace(/&nbsp;|&amp;|&lt;|&gt;|&quot;/g,m=>({'&nbsp;':' ','&amp;':'&','&lt;':'<','&gt;':'>','&quot;':'"'}[m])).replace(/\s+/g,' ').trim();
/* 日期/日期时间（2025-01-03、2025-01-03 10:20）按字符串比（parseFloat 只读到年份）；其余以数字开头的按数值，否则按文字 */
K._DTRX=/^\s*\d{4}-\d{1,2}(-\d{1,2})?/;
K.cmpTxt=(x,y)=>{x=String(x??'');y=String(y??'');if(K._DTRX.test(x)&&K._DTRX.test(y))return x.trim().localeCompare(y.trim());const a=parseFloat(x.replace('−','-')),b=parseFloat(y.replace('−','-'));
  if(x!==''&&y!==''&&!isNaN(a)&&!isNaN(b)&&/^[\s+\-−]?\d/.test(x)&&/^[\s+\-−]?\d/.test(y))return a-b;return x.localeCompare(y,'zh')};
K.table=(el,cfg)=>{
  const st={sort:cfg.sort||null,dir:cfg.dir||-1,page:0,q:'',f:{}};const ps=cfg.pageSize||60;
  const tx=(c,r)=>c.fv?String(c.fv(r)??''):c.f?K.cellTxt(c.f(r)):String(r[c.k]??'');
  const sv=(c,r)=>c.s?c.s(r):c.k in r&&r[c.k]==null&&!c.f?null:(c.k in r&&r[c.k]!=null&&typeof r[c.k]!=='object')?r[c.k]:tx(c,r);
  const nw=c=>c.nw!=null?c.nw:K.NWT.test(K.cellTxt(c.t));
  let fcols=[];
  function prep(){fcols=[];if(cfg.filter===false||cfg.rows.length<=8)return;
    cfg.cols.forEach((c,i)=>{if(c.nf)return;const m=new Map();for(const r of cfg.rows){const v=tx(c,r);if(v&&v.length<=24)m.set(v,(m.get(v)||0)+1);if(m.size>25)return}
      if(m.size>=2&&m.size<=25)fcols.push([i,[...m.entries()].sort((a,b)=>K.cmpTxt(a[0],b[0]))])});
    fcols=fcols.sort((a,b)=>a[1].length-b[1].length).slice(0,4).sort((a,b)=>a[0]-b[0])}
  function prune(){Object.keys(st.f).forEach(i=>{const fc=fcols.find(x=>x[0]===+i);if(!fc||!fc[1].some(([v])=>v===st.f[i]))delete st.f[i]})}   /* 选项已不存在的列筛选作废，避免看不见的筛选继续吞行 */
  function view(){let rows=cfg.rows;const q=st.q.toLowerCase(),fs=Object.entries(st.f).filter(([,v])=>v!=='');
    if(q||fs.length)rows=rows.filter(r=>fs.every(([i,v])=>tx(cfg.cols[+i],r)===v)&&(!q||cfg.cols.some(c=>tx(c,r).toLowerCase().includes(q))));
    rows=rows.slice();
    if(st.sort){const c=cfg.cols.find(c=>c.k===st.sort);if(c)rows.sort((a,b)=>{const x=sv(c,a),y=sv(c,b);if((x==null||x==='')&&(y==null||y===''))return 0;if(x==null||x==='')return 1;if(y==null||y==='')return -1;
      return (typeof x==='number'&&typeof y==='number'?x-y:K.cmpTxt(String(x),String(y)))*st.dir})}
    return rows}
  function bar(){if(!fcols.length&&cfg.rows.length<=8&&!st.q)return '';
    return `<div class="tflt"><input class="s" data-tq placeholder="在表内搜索" value="${K.esc(st.q)}">${fcols.map(([i,vs])=>`<select class="s" data-tf="${i}"><option value="">${K.esc(K.cellTxt(cfg.cols[i].t))}：全部</option>${vs.map(([v,n])=>`<option value="${K.esc(v)}"${st.f[i]===v?' selected':''}>${K.esc(v)}（${n}）</option>`).join('')}</select>`).join('')}${st.q||Object.values(st.f).some(Boolean)?'<a class="small" data-tc href="javascript:void 0">清除筛选</a>':''}</div>`}
  function draw(){
    const rows=view();
    const n=rows.length,pages=Math.max(1,Math.ceil(n/ps));if(st.page>=pages)st.page=0;const vw=cfg.noPage?rows:rows.slice(st.page*ps,st.page*ps+ps);
    let grpPrev=null;
    const body=vw.map(r=>{let g='';if(cfg.group){const gv=cfg.group(r);if(gv!==grpPrev){grpPrev=gv;g=`<tr class="grp"><td colspan="${cfg.cols.length}">${cfg.groupHead?cfg.groupHead(gv,r):gv}</td></tr>`}}
      return g+`<tr class="${cfg.onRow?'click':''}" data-i="${cfg.rows.indexOf(r)}">${cfg.cols.map(c=>`<td class="${c.cls||''}${nw(c)?' nw':''}"${c.w?` style="width:${c.w}"`:''}>${c.f?c.f(r):K.esc(r[c.k])}</td>`).join('')}</tr>`}).join('');
    const filt=n!==cfg.rows.length?` / 共 ${cfg.rows.length}`:'';
    el.innerHTML=bar()+`<div class="tw ${cfg.max===false?'':'max'}" data-kzt${cfg.h?` style="max-height:${cfg.h}"`:''}><table class="t ${cfg.cls||''}" data-kz="1"><thead><tr>${cfg.cols.map(c=>`<th class="s ${c.cls||''}" data-k="${c.k}"${c.tip?` title="${K.esc(c.tip)}"`:''}>${c.t}${st.sort===c.k?`<span class="ar">${st.dir>0?'▲':'▼'}</span>`:''}</th>`).join('')}</tr></thead><tbody>${body||`<tr><td colspan="${cfg.cols.length}" class="empty">无匹配记录</td></tr>`}</tbody></table></div>`+
      (cfg.noPage||pages<=1?`<div class="pager">${n} 行${filt}</div>`:`<div class="pager">${n} 行${filt} · 第 ${st.page+1}/${pages} 页 <button data-p="-1" ${st.page?'':'disabled'}>‹</button><button data-p="1" ${st.page<pages-1?'':'disabled'}>›</button></div>`);
    el.querySelectorAll('th.s').forEach(th=>th.onclick=()=>{const k=th.dataset.k;if(st.sort===k)st.dir*=-1;else{st.sort=k;st.dir=-1}draw()});
    el.querySelectorAll('.pager button').forEach(b=>b.onclick=()=>{st.page+=+b.dataset.p;draw()});
    const qi=el.querySelector('[data-tq]');if(qi){const go=()=>{st.q=qi.value.trim();st.page=0;const pos=qi.selectionStart;draw();const n2=el.querySelector('[data-tq]');if(n2){n2.focus();try{n2.setSelectionRange(pos,pos)}catch(e){}}};
      qi.oninput=e=>{if(e.isComposing)return;go()};qi.addEventListener('compositionend',go)}   /* 拼音输入法组字期间不重绘（否则无法输入中文） */
    el.querySelectorAll('[data-tf]').forEach(sl=>sl.onchange=()=>{st.f[sl.dataset.tf]=sl.value;st.page=0;draw()});
    const tc=el.querySelector('[data-tc]');if(tc)tc.onclick=()=>{st.q='';st.f={};draw()};
    if(cfg.onRow)el.querySelectorAll('tbody tr[data-i]').forEach(tr=>tr.onclick=e=>{if(e.target.closest('a'))return;cfg.onRow(cfg.rows[+tr.dataset.i],e)});
    cfg.after&&cfg.after(el);
  }
  prep();draw();return {set(rows){cfg.rows=rows;st.page=0;prep();prune();draw()},draw};
};
/* 手写表格（页面直接拼的 table.t）：单行表头、无分组/合并单元格的表加列排序；≥8 行加表内搜索；不折行列同 K.NWT。
 * 无表头的键值明细表不处理（用户裁定 5：无表头明细表豁免）。新插入的表（抽屉等）由 MutationObserver 自动处理。 */
K.enhance=root=>{(root||document).querySelectorAll('table.t:not([data-kz])').forEach(t=>{t.dataset.kz='1';const th=t.tHead,tb=t.tBodies[0];if(t.hasAttribute('data-nosort'))return;
  if(!th||th.rows.length!==1||!tb||tb.rows.length<2||tb.querySelector('tr.grp,td[rowspan],td[colspan],th[rowspan]')||th.querySelector('[colspan]'))return;
  const hs=[...th.rows[0].cells];hs.forEach((h,i)=>{if(K.NWT.test(h.textContent))[...tb.rows].forEach(r=>r.cells[i]&&r.cells[i].classList.add('nw'))});
  let si=-1,dir=1;hs.forEach((h,i)=>{h.classList.add('s');h.onclick=()=>{dir=si===i?-dir:1;si=i;const rows=[...tb.rows];
    /* tr.pin（如「研究整体」参照行）固定在顶；tr.dx（展开的明细行）跟随其上方的主行一起移动 */
    const units=[];rows.forEach(r=>{if(r.classList.contains('dx')&&units.length)units[units.length-1].push(r);else units.push([r])});
    const pin=units.filter(u=>u[0].classList.contains('pin')),rest=units.filter(u=>!u[0].classList.contains('pin'));
    rest.sort((a,b)=>K.cmpTxt((a[0].cells[i]||{}).textContent?.trim()||'',(b[0].cells[i]||{}).textContent?.trim()||'')*dir);[...pin,...rest].flat().forEach(r=>tb.appendChild(r));
    hs.forEach(x=>{const ar=x.querySelector('.ar');if(ar)ar.remove()});h.insertAdjacentHTML('beforeend',`<span class="ar">${dir>0?'▲':'▼'}</span>`)}});
  if(tb.rows.length>=8)K._tbar(t,tb,hs)})};
/* 表内搜索＋取值少的列下拉筛选（用户 2026-11-11：各处表格要能筛选）；tr.pin 常显，tr.dx 明细行跟随主行 */
K._tbar=(t,tb,hs)=>{const main=[...tb.rows].filter(r=>!r.classList.contains('dx')),txt=(r,i)=>(r.cells[i]&&r.cells[i].innerText||'').trim();
  const fc=[];hs.forEach((h,i)=>{if(fc.length>=3)return;const m=new Map();for(const r of main){const v=txt(r,i);if(v.length>24){m.clear();break}if(v)m.set(v,(m.get(v)||0)+1);if(m.size>20)break}
    if(m.size>=2&&m.size<=20&&[...m.values()].some(n=>n>1))fc.push([i,[...m.entries()].sort((a,b)=>K.cmpTxt(a[0],b[0]))])});
  const host=t.closest('.tw,.listing')||t,bar=document.createElement('div');bar.className='tflt';
  bar.innerHTML=`<input class="s" placeholder="在表内搜索">${fc.map(([i,vs])=>`<select class="s" data-i="${i}"><option value="">${K.esc(hs[i].innerText.replace(/[▲▼]/g,'').trim())}：全部</option>${vs.map(([v,n])=>`<option value="${K.esc(v)}">${K.esc(v)}（${n}）</option>`).join('')}</select>`).join('')}<span class="xs muted kzn"></span>`;
  host.parentNode.insertBefore(bar,host);
  const apply=()=>{const q=bar.querySelector('input').value.trim().toLowerCase(),fs=[...bar.querySelectorAll('select')].filter(x=>x.value).map(x=>[+x.dataset.i,x.value]);let show=true,n=0;
    [...tb.rows].forEach(r=>{if(r.classList.contains('dx')){r.style.display=show?'':'none';return}
      show=r.classList.contains('pin')||(fs.every(([i,v])=>txt(r,i)===v)&&(!q||r.innerText.toLowerCase().includes(q)));r.style.display=show?'':'none';if(show)n++});
    bar.querySelector('.kzn').textContent=q||fs.length?`${n} / ${main.length} 行`:''};
  bar.querySelector('input').addEventListener('input',apply);bar.querySelectorAll('select').forEach(x=>x.addEventListener('change',apply))};
if(typeof MutationObserver==='function'&&typeof document.body!=='undefined'){let tm=null;const mo=new MutationObserver(()=>{clearTimeout(tm);tm=setTimeout(()=>K.enhance(document),80)});
  document.addEventListener('DOMContentLoaded',()=>{mo.observe(document.body,{childList:true,subtree:true});K.enhance(document)})}
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
/* V6：类别色取康哲 tokens charts.categorical（固定顺序、5 色，已过色觉区分度校验）＋对照中性色；风险红不再混作类别色（状态色专用） */
K.COL=['#D46B08','#008F8A','#7B5CC7','#B38A00','#C4457C','#6E7B8C'];
/* R2-1（D002 E2E 深链页 pageerror×6）：markLine/markPoint 坐标不可用（yAxis:undefined——KRI 未配置容忍限度、
 * 空集合中位数 null/NaN）在 ECharts marker 转换后 e[0].coord 取 undefined 崩整页。K.chart 入口统一守卫：
 * 坐标缺失/非有限值的 marker 项剔除，全部无效则撤除整个 markLine/markPoint（不渲染辅助线，不崩页）；
 * 字符串坐标（时间/类目轴日期）与有限数值、coord/点对形态全部保留。 */
K._coordOk=v=>typeof v==='number'?isFinite(v):typeof v==='string'?v.trim()!=='':false;
K._markerItemOk=it=>{if(it==null)return false;if(Array.isArray(it))return it.length===2?(K._markerItemOk(it[0])&&K._markerItemOk(it[1])):it.every(K._coordOk);
  if(typeof it!=='object')return K._coordOk(it);
  if('coord'in it)return(it.coord||[]).every(K._coordOk);
  if('xAxis'in it||'yAxis'in it)return(!('xAxis'in it)||K._coordOk(it.xAxis))&&(!('yAxis'in it)||K._coordOk(it.yAxis));
  return true};
K.chartGuard=opt=>{(opt&&opt.series||[]).forEach(s=>{if(!s)return;for(const mk of['markLine','markPoint','markArea']){const m=s[mk];   /* V6：markArea 同口径（区间端点缺失→整块撤除，不让整张图空白） */
  if(!m||!Array.isArray(m.data))continue;m.data=m.data.filter(K._markerItemOk);if(!m.data.length)delete s[mk]}});return K.axisGuard(opt)};
/* 用户 2026-11-11（首页入组进度横轴「7月」与「3」重叠、参考线标签「计划」被裁成「计」）：全部图表统一防重叠——
 * 坐标轴标签自动避让（显式 interval:0 的分类轴除外）；时间轴用中文分级标签（年/月/日不混排）；
 * 水平参考线标签放线内侧右上、竖直参考线标签放顶端，不压坐标轴文字；显示数值标签的系列自动隐藏互相重叠的标签。 */
K.TIMEFMT={year:'{yyyy}年',month:'{M}月',day:'{M}/{d}',hour:'{HH}:{mm}',minute:'{HH}:{mm}',second:'{HH}:{mm}:{ss}',millisecond:'{HH}:{mm}:{ss}',none:'{yyyy}-{MM}-{dd}'};
/* 访视代码中文名（重叠排查 2026-11-11：横轴 SCR/USV/ET/EOT 英文代码外露）；只换显示，数据键不变 */
K.VCODE=/^(SCR|USV|UNS|ET|EOT|EOS|FU)(?=$|[\s\d])/;
K.VNAME={SCR:'筛选期',USV:'计划外',UNS:'计划外',ET:'提前退出',EOT:'治疗结束',EOS:'研究结束',FU:'随访'};
K.sup=t=>String(t).replace(/10\^(-?\d+)/g,(_,e)=>'10'+[...e].map(c=>'⁰¹²³⁴⁵⁶⁷⁸⁹'['0123456789'.indexOf(c)]||'⁻').join(''));   /* ×10^9/L → ×10⁹/L */
K.vname=v=>String(v??'').replace(K.VCODE,m=>K.VNAME[m]||m);
K.axisGuard=opt=>{if(!opt)return opt;const ax=k=>[].concat(opt[k]||[]).filter(a=>a&&typeof a==='object');
  [...ax('xAxis'),...ax('yAxis')].forEach(a=>{const L=a.axisLabel=Object.assign({},a.axisLabel||{});if(typeof a.name==='string')a.name=K.sup(a.name);
    if(L.hideOverlap==null&&!(a.type==='category'&&L.interval===0))L.hideOverlap=true;
    if(a.type==='time'&&L.formatter==null)L.formatter=K.TIMEFMT;
    if(a.type==='category'&&L.formatter==null&&Array.isArray(a.data)&&a.data.some(v=>K.VCODE.test(String(v))))L.formatter=v=>K.vname(v)});
  /* 柱图纵轴从 0 起（自动范围从 2 起时值 3 的柱像满格）；自动范围的数值轴上下留白，落在边上的点和标签不被轴线/边框遮一半 */
  const hasBar=(opt.series||[]).some(s=>s&&s.type==='bar');
  ax('yAxis').forEach(a=>{if(a.type!=='value'||a.min!=null||a.max!=null)return;if(hasBar&&a.scale)a.scale=false;else if(a.scale&&a.boundaryGap==null)a.boundaryGap=['6%','10%']});
  const vert=new Set(ax('xAxis').length?['xAxis']:[]);
  (opt.series||[]).forEach(s=>{if(!s)return;const m=s.markLine;
    if(m&&Array.isArray(m.data))m.data.forEach(d=>{if(!d||Array.isArray(d))return;const lb=d.label=Object.assign({},m.label||{},d.label||{});if(lb.position)return;
      if(d.yAxis!=null)lb.position='insideEndTop';else if(d.xAxis!=null&&vert.size)lb.position='end'});
    const lb=s.label;if(lb&&lb.show&&!s.labelLayout&&['line','scatter','bar'].includes(s.type))s.labelLayout={hideOverlap:true}});
  return opt};
/* V6（用户审阅 RUX 第 17 条、裁定 14）：生长动效只在图第一次进入视野时播放——此前图在页面下方/隐藏页签里初始化，
 * 动画在用户看见之前就放完了。不在视野内的新图先挂起配置，进入视野（IntersectionObserver）再渲染；同一张图之后的更新不再动画。 */
K._waitQ=new Set();
/* 打印/导出 PDF 与整页截图（render_check）时把仍在等进入视野的图一次画完 */
K.flushCharts=()=>{K._waitQ.forEach(c=>{const o=c._kzWait;c._kzWait=null;if(o&&!c.isDisposed())c.setOption(o,true)});K._waitQ.clear()};
if(typeof window.addEventListener==='function')window.addEventListener('beforeprint',()=>K.flushCharts());
K._inView=el=>{const r=el.getBoundingClientRect();return r.width>0&&r.height>0&&r.bottom>0&&r.right>0&&r.top<(window.innerHeight||0)&&r.left<(window.innerWidth||0)};
K.chart=(el,opt)=>{if(typeof el==='string')el=document.querySelector(el);let c=echarts.getInstanceByDom(el);const first=!c;
  if(!c){c=echarts.init(el,null,{renderer:'canvas'});new ResizeObserver(()=>c.resize()).observe(el)}
  K.chartLang(opt);
  opt=Object.assign({color:K.COL,textStyle:{fontFamily:'Microsoft YaHei, PingFang SC, Noto Sans CJK SC, Arial',fontSize:12,color:'#404040'},
    animationDuration:K.RM?0:700,animationEasing:'cubicOut',animationDurationUpdate:0},K.chartGuard(opt));
  if(c._kzWait){c._kzWait=opt;return c}                                   /* 仍在等进入视野：只换成最新配置 */
  if(first&&!K.RM&&typeof IntersectionObserver==='function'&&!K._inView(el)){c._kzWait=opt;K._waitQ.add(c);
    const io=new IntersectionObserver(es=>{if(!es.some(e=>e.isIntersecting))return;io.disconnect();K._waitQ.delete(c);const o=c._kzWait;c._kzWait=null;if(o&&!c.isDisposed())c.setOption(o,true)},{threshold:.12});
    io.observe(el);return c}
  if(!first)opt.animation=false;
  c.setOption(opt,true);return c};
/* V6 图表语言（康哲 05 CHART-02/04）：折线不平滑、缺失点留缺口（不当 0）；数据揭示只在首次出现时生长，切换口径直接呈现新真值（不补间）；
 * 减少动态时不做动画。显式写了 smooth/connectNulls 的图表沿用其设置。 */
K.RM=typeof matchMedia==='function'&&matchMedia('(prefers-reduced-motion: reduce)').matches;
K.chartLang=opt=>{(opt&&opt.series||[]).forEach(s=>{if(!s||s.type!=='line')return;if(s.smooth===undefined)s.smooth=false;if(s.connectNulls===undefined)s.connectNulls=false});return opt};
K.axis={axisLine:{onZero:false,lineStyle:{color:'#CED3D8'}},axisTick:{show:false},axisLabel:{color:'#404040'},splitLine:{lineStyle:{color:'#E7EBEE'}}};
K.q=(arr,p)=>{if(!arr.length)return null;const a=arr.slice().sort((x,y)=>x-y);const i=(a.length-1)*p,lo=Math.floor(i),hi=Math.ceil(i);return a[lo]+(a[hi]-a[lo])*(i-lo)};
K.median=a=>K.q(a,.5);
/* EDC-like listing render: rows [{sh,row,f,hl}] */
K.listing=(rows,{cols=null,cap=true}={})=>{
  const bySheet={};rows.forEach(r=>(bySheet[r.sh]=bySheet[r.sh]||[]).push(r));
  return Object.entries(bySheet).map(([sh,rs])=>{
    let keys=cols||[...new Set(rs.flatMap(r=>Object.keys(r.f)))];
    const hk=new Set(rs.flatMap(r=>r.hl));
    if(!cols&&keys.length>14){const keep=new Set(['参与者编号','表单集名称',...hk]);const imp=keys.filter(k=>keep.has(k)||/日期|结果|名称|项目|评价|严重|关系|AESI|SAE|单位|下限|上限|值|体积|压|QTc|心率|持续|剂量/.test(k));keys=[...new Set([...keys.filter(k=>keep.has(k)),...imp])].slice(0,18)}
    return `${cap?`<div class="cap">${K.p(K.shName(sh),'sq')} 第 ${rs.map(r=>r.row).join(', ')} 行</div>`:''}<div class="listing tw"><table><thead><tr><th>行</th>${keys.map(k=>`<th>${K.esc(k)}</th>`).join('')}</tr></thead><tbody>${rs.map(r=>`<tr><td class="faint">${r.row}</td>${keys.map(k=>`<td class="${r.hl.includes(k)?'on':''}" title="${K.esc(r.f[k]||'')}">${K.esc(r.f[k]??'')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`}).join('');
};
K.hlNum=t=>K.esc(t).replace(/(\d+(?:\.\d+)?(?:\s?(?:g\/L|mmol\/L|U\/L|ms|mmHg|g\/cm²|kg|%|×10\^9\/L|umol\/L|IU\/L)))/g,'<span class="num-hl">$1</span>').replace(/(20\d\d-\d\d-\d\d)/g,'<span class="num-hl">$1</span>');
K.qById=id=>D().queries.find(q=>q.id===id);
K.qPill=id=>`<span class="p org sq click mono" data-q="${id}">${id}</span>`;
/* ---- mm5 全程数据面板（用户 2026-10-31：风险、质疑等条目点开要看该参与者该指标前后全部数据，并显示 CS/NCS、CS 原因等）
 * o={sid, tests:[指标显示名…], hl:[[sheet,row]…] 本条证据点（加粗），ae:true 是否附本例 AE/MH/合并用药}。
 * 数据来自个例文件 s/<sid>.js 的 labs/vs/ecg 行：[0日期,1访视,2值,3原值,4单位,5下限,6上限,7判定,8说明,9sheet,10行,11时间点,12时间,13基线,14归因码,15原因说明,16关联摘要,17分级,18较基线%,19疑似录入错误]。 */
/* V6（用户审阅 RUX 第 16 条）：CS 异常的关联对象卡——把检验行关联/归因的 AE、病史、研究疾病的完整信息放进抽屉（此前只有一个「CS」标记）。
 * rows＝个例检验行（尾部扩位 [14 归因码, 15 原因说明, 16 关联摘要「AE 术语·开始日期」/「病史 术语」]），s＝个例文件。 */
K.linkCard=(s,rows)=>{const seen=new Set(),out=[];
  (rows||[]).forEach(r=>{(String(r[16]||'').split('；').filter(Boolean)).forEach(it=>{if(seen.has(it))return;seen.add(it);
      const ae=it.startsWith('AE '),body=it.replace(/^(AE|病史) /,''),[term,start]=body.split('·');
      if(ae){const a=(s.ae||[]).find(a=>a.t===term&&(!start||String(a.s||'').startsWith(start)))||(s.ae||[]).find(a=>a.t===term);
        out.push(`<tr><td class="nw">${K.p('AE','grn')}</td><td><b>${K.esc(term)}</b>${a&&a.sae?' '+K.p('SAE','solid-red'):''}${a&&a.aesi?' '+K.p('AESI','red'):''}</td><td class="nw">${K.esc((a&&a.s)||start||'')} → ${a?(a.e?K.esc(a.e):'持续'):'—'}</td><td class="nw">${a&&a.g?K.p(a.g,String(a.g)>='3'?'red':'yel'):''}</td><td class="small">${K.esc([a&&a.rel&&'相关性：'+a.rel,a&&a.act&&'措施：'+a.act,a&&a.out&&'转归：'+a.out].filter(x=>x&&!/：—$/.test(x)).join(' · '))}</td><td class="xs faint">${K.esc(r[1]||'')} ${K.esc(String(r[0]||'').slice(0,10))} 的检验关联</td></tr>`)}
      else{const m=(s.mh||[]).find(m=>m.t===term);
        out.push(`<tr><td class="nw">${K.p('病史','org')}</td><td><b>${K.esc(term)}</b></td><td class="nw">${K.esc((m&&m.s)||'')}${m&&m.ong==='是'?' · 持续':m&&m.e?' → '+K.esc(m.e):''}</td><td></td><td class="small">${K.esc((m&&m.note)||'')}</td><td class="xs faint">${K.esc(r[1]||'')} ${K.esc(String(r[0]||'').slice(0,10))} 的检验关联</td></tr>`)}})});
  (rows||[]).filter(r=>r[14]==='disease').forEach(r=>{const k='dis|'+r[1];if(seen.has(k))return;seen.add(k);
    out.push(`<tr><td class="nw">${K.p('研究疾病','blu')}</td><td colspan="4" class="small">研究者归因研究疾病${r[15]?'：'+K.esc(r[15]):''}</td><td class="xs faint">${K.esc(r[1]||'')} ${K.esc(String(r[0]||'').slice(0,10))}</td></tr>`)});
  if(!out.length){const cs=(rows||[]).filter(r=>r[7]===2);return cs.length?`<div class="sec-t"><h2>关联记录</h2></div><div class="box small">判为有临床意义的 ${cs.length} 条记录未关联 AE / 病史，也未归因研究疾病${cs.some(r=>r[15])?'；说明栏：'+K.esc(cs.map(r=>r[15]).filter(Boolean)[0]):''}</div>`:''}
  return `<div class="sec-t"><h2>关联记录</h2><span class="muted small">本条涉及的检验记录所关联/归因的对象</span></div><table class="t"><tbody>${out.join('')}</tbody></table>`};
K.seriesPanel=async(el,o)=>{if(!el)return;
  if((o.hl||[]).length&&!o.noRaw){const rb=document.createElement('div');rb.className='rawbox';el.before(rb);K.rawBox(rb,o.sid,o.hl)}   /* V6：证据原行在前 */
  el.innerHTML='<div class="empty">载入全程数据…</div>';const s=await K.sub(o.sid);if(!s){el.innerHTML='<div class="empty">无个例数据</div>';return}
  const core=x=>String(x||'').replace(/（.*?）|\(.*?\)/g,'').trim();
  const pick=t=>{for(const k of ['labs','vs','ecg']){const m=s[k]||{};if(m[t])return [t,m[t]];const kk=Object.keys(m).find(x=>core(x)===core(t));if(kk)return [kk,m[kk]]}return null};
  const sers=[...new Map((o.tests||[]).filter(Boolean).map(pick).filter(Boolean).map(x=>[x[0],x])).values()].slice(0,4);
  const pl=sh=>String(sh||'').replace(/^[^:]*:/,'');const HL=new Set((o.hl||[]).map(e=>pl(e[0])+'|'+e[1]));
  const sd=d=>K.studyDay(d,s.fd);
  el.innerHTML=sers.map((x,i)=>`<div class="sec-t"><h2>${K.esc(x[0])} · 全程</h2><span class="muted small">${x[1].length} 次记录 · 加粗为本条涉及的记录</span></div><div class="chart sm" id="sp${i}" style="height:190px"></div>
    <table class="t"><thead><tr><th>访视</th><th>日期</th><th>结果</th><th>参考范围</th><th>较基线</th><th>等级</th><th>判定与关联</th><th>说明</th><th>来源</th></tr></thead><tbody>${x[1].slice().sort((a,b)=>String(a[0]).localeCompare(String(b[0]))).map(r=>{const h=HL.has(pl(r[9])+'|'+r[10]);
      return `<tr${h?' style="background:#FFF6E8;font-weight:600"':''}><td>${K.p(r[1]||'—','blu')}${r[13]?' '+K.p('基线','line'):''}</td><td class="nowrap">${K.esc(r[0]||'')} <span class="xs faint">${sd(String(r[0]||'').slice(0,10))}</span></td>
      <td class="num"><b>${K.esc(r[3]??'')}</b> <span class="xs muted">${K.esc(r[4]||'')}</span>${r[19]?`<div>${K.p('疑似录入错误','org',r[19])}</div>`:''}</td><td class="nowrap">${K.rng(r[5],r[6])}</td>
      <td class="num">${r[18]==null?'':K.pct(r[18])}</td><td>${r[17]?K.grade(r[17]):''}</td><td>${K.judgeCell?K.judgeCell(r,o.sid):K.clin(r[7])}</td><td class="small">${K.esc(r[8]||'')}</td><td class="xs faint">${K.esc(K.loc(r[9],r[10]))}</td></tr>`}).join('')}</tbody></table>`).join('')
    +(sers.length?'':(o.tests||[]).length?`<div class="note small">该条目涉及「${K.esc((o.tests||[]).join('、'))}」，个例数据中未找到对应的检验/检查序列。</div>`:'')
    +K.linkCard(s,sers.flatMap(x=>x[1]).filter(r=>HL.size?HL.has(pl(r[9])+'|'+r[10]):r[7]===2))
    +(o.ae===false?'':`<div class="sec-t"><h2>本例 AE / 病史 / 合并用药</h2><span class="muted small">AE ${s.ae.length} · 病史 ${s.mh.length} · 合并用药 ${s.cm.length}</span></div><table class="t"><tbody>
      ${s.ae.map(a=>`<tr><td style="width:56px">${K.p('AE','grn')}</td><td><b>${K.esc(a.t)}</b>${a.sae?' '+K.p('SAE','solid-red'):''}${a.aesi?' '+K.p('AESI','red'):''}</td><td class="nowrap">${K.esc(a.s||'')} → ${a.e?K.esc(a.e):'持续'}</td><td>${K.p(a.g,String(a.g)>='2'?'red':'yel')}</td><td class="small">${K.esc(a.rel||'')}</td></tr>`).join('')}
      ${s.mh.map(a=>`<tr><td>${K.p('病史','org')}</td><td>${K.esc(a.t)}</td><td class="nowrap">${K.esc(a.s||'')}${a.ong==='是'?' · 持续':''}</td><td></td><td></td></tr>`).join('')}
      ${s.cm.slice(0,40).map(c=>`<tr><td>${K.p('用药','blu')}</td><td>${K.esc(c.t)}</td><td class="nowrap">${K.esc(c.s||'')} → ${c.e?K.esc(c.e):c.ong?'持续':''}</td><td class="small">${K.esc(c.dose||'')}</td><td class="small">${K.esc(c.ind||c.why||'')}</td></tr>`).join('')}
      ${s.ae.length+s.mh.length+s.cm.length?'':'<tr><td class="empty">无</td></tr>'}</tbody></table>`)
    +`<div class="mt"><a class="small" href="subjects.html#s=${o.sid}&t=lab">参与者资料 ›</a>　<a class="small" href="profile.html#s=${o.sid}">安全性概览 ›</a>　<a class="small" href="timeline.html#s=${o.sid}">时间线 ›</a></div>`;
  sers.forEach((x,i)=>{const pts=x[1].filter(r=>r[2]!=null).sort((a,b)=>String(a[0]).localeCompare(String(b[0])));if(!pts.length){el.querySelector('#sp'+i).style.display='none';return}
    const lo=pts.find(r=>r[5]!=null)?.[5],hi=pts.find(r=>r[6]!=null)?.[6];
    K.chart(el.querySelector('#sp'+i),{grid:{left:44,right:16,top:16,bottom:26},tooltip:{trigger:'item',formatter:p=>{const r=p.data.r;return `${K.esc(r[1]||'')} ${K.esc(r[0]||'')}<br><b>${K.esc(r[3])} ${K.esc(r[4]||'')}</b> ${r[7]===2?'CS':r[7]===1?'NCS':r[7]===0?'正常':'未评价'}${r[17]?' · '+r[17]+'级':''}${r[15]?'<br>'+K.esc(r[15]):''}`}},
      xAxis:{type:'time',...K.axis},yAxis:{type:'value',scale:true,...K.axis},
      series:[{type:'line',data:pts.map(r=>({value:[r[0],r[2]],r,itemStyle:{color:r[7]===2?'#8B0000':r[7]===1?'#E8C300':'#407AAA',borderColor:HL.has(pl(r[9])+'|'+r[10])?'#FF9900':undefined,borderWidth:HL.has(pl(r[9])+'|'+r[10])?3:0},symbolSize:HL.has(pl(r[9])+'|'+r[10])?12:r[7]>0?9:6})),lineStyle:{color:'#9DB7D3'},
        markArea:lo!=null&&hi!=null?{silent:true,itemStyle:{color:'rgba(88,123,59,.07)'},data:[[{yAxis:lo},{yAxis:hi}]]}:undefined,
        markLine:{symbol:'none',silent:true,data:[s.fd?{xAxis:s.fd,label:{formatter:'D1',color:'#B86400'},lineStyle:{color:'#FF9900',type:'dashed'}}:null,s.ld?{xAxis:s.ld,label:{formatter:'末次给药',color:'#64676B'},lineStyle:{color:'#C9CCD1',type:'dashed'}}:null].filter(Boolean)}}]})})};
/* 观察/期望：期望＝总体率×分母（随访人日、记录数或人数）。V5：显著性用精确泊松尾概率（期望 >60 用正态近似），
 * 再按 Benjamini–Hochberg 全表校正（上一轮自审：约 360 格逐格 z>2，纯随机也会标出约 8 格）。 */
K.erfc=x=>{const z=Math.abs(x),t=1/(1+.5*z),r=t*Math.exp(-z*z-1.26551223+t*(1.00002368+t*(.37409196+t*(.09678418+t*(-.18628806+t*(.27886807+t*(-1.13520398+t*(1.48851587+t*(-.82215223+t*.17087277)))))))));return x>=0?r:2-r};
K.poisUp=(o,e)=>{if(o<=0)return 1;if(e<=0)return 0;if(e>60)return .5*K.erfc((o-.5-e)/Math.sqrt(2*e));let t=Math.exp(-e),c=0;for(let i=0;i<o;i++){c+=t;t*=e/(i+1)}return Math.max(0,Math.min(1,1-c))};
K.poisLo=(o,e)=>{if(e<=0)return 1;if(e>60)return .5*K.erfc((e-o-.5)/Math.sqrt(2*e));let t=Math.exp(-e),c=0;for(let i=0;i<=o;i++){c+=t;t*=e/(i+1)}return Math.min(1,c)};
K.bh=ps=>{const ix=ps.map((p,i)=>[p,i]).filter(x=>x[0]!=null).sort((a,b)=>a[0]-b[0]),m=ix.length,q=ps.map(()=>null);let run=1;for(let r=m-1;r>=0;r--){run=Math.min(run,ix[r][0]*m/(r+1));q[ix[r][1]]=run}return q};
K.oe=(obs,n,rate)=>{const e=rate*n;return {o:obs,e,ratio:e>0?obs/e:null,z:e>0?(obs-e)/Math.sqrt(e):0,pu:K.poisUp(obs,e),pl:K.poisLo(obs,e)}};
/* 按校正后的 q 着色：高侧 q<0.05 明显偏高、q<0.10 偏高；低侧（只对「偏低＝可能漏报」的类别）q<0.10 标蓝 */
K.qlt=(v,a)=>v!=null&&v<a;   /* q 值可为 null（不适用）：null<0.1 在 JS 中为真，必须先判非空 */
K.qStyle=(qu,ql)=>qu!=null&&qu<.05?'background:rgba(230,126,0,.62)':qu!=null&&qu<.10?'background:rgba(230,126,0,.30)':ql!=null&&ql<.10?'background:rgba(64,122,170,.18)':'';
K.qTip=x=>x?`观察 ${x.o} / 期望 ${x.e.toFixed(1)}${x.qu!=null?` · 校正后 q=${x.qu<.001?'<0.001':x.qu.toFixed(3)}`:''}${x.ql!=null&&x.ql<.10?` · 偏低 q=${x.ql.toFixed(3)}`:''}`:'';
/* V5 修复波：小中心偏高格的「个案驱动」标注（K.centerRisk().small）——只改呈现不改判定 */
K.caseNote=(x,small)=>x&&small&&K.qlt(x.qu,.10)?' · 个案驱动（分母极小，偏高可能由个别参与者驱动）':'';
/* 一列（各中心）比率：rows=[[分子,分母]…]，期望＝整体率×分母，逐行泊松上尾、按列 BH → [{o,e,qu,style}|null] */
K.colFlags=(rows,all)=>{const r=rows.map(([n,d])=>d?K.oe(n,d,all):null),q=K.bh(r.map(x=>x?x.pu:null));return r.map((x,i)=>x?{...x,qu:q[i],style:K.qStyle(q[i])}:null)};
/* 中心风险类别（风险页「中心总览」热力图、总览「需关注中心」、中心画像、风险排名共用）。
 * V5 期望数按随访人日（KZ.ops.fu；录入错误按该中心数值型检验记录数 ops.nnum），旧构建无 fu 时按给药人数。 */
K.centerRisk=()=>{if(K._cr)return K._cr;const D=window.KZ,lab=K.lab,oth=D.others,aes=D.aes,O=D.ops||{};
  const S=K.subs(),pd=((D.pd||{}).potential)||[],entry=(O.entry)||[];
  const subSite=Object.fromEntries(S.map(s=>[s.id,s.site]));
  const CS=D.centers.filter(c=>c.n).slice().sort((a,b)=>b.dosed-a.dosed||b.n-a.n);
  /* 风险类别：[键, 组, 列名, 取条目(按中心), 说明] —— 条目数组用于点击下钻 */
  const L=k=>lab.filter(g=>Array.isArray(k)?k.includes(g.risk):g.risk===k);
  const C=[
    ['csx','检验','有临床意义未关联',()=>L('CSX'),'判 CS 但未关联 AE/病史（参与者×指标）'],
    ['wor','检验','较基线加重',()=>L(['MH','DISW']),'判 CS 仅关联病史或归因研究疾病，但较基线加重'],
    ['g2','检验','≥2级未判为有临床意义',()=>L(['NCS2','NA2','G2NF','NA']),'达 ≥2 级判为无临床意义/未评价、超范围未评价'],
    ['rel','检验','显著变化·未关联',()=>lab.filter(g=>g.risk==='REL'&&K.relRisk(g)),'较基线显著变化且未关联 AE/病史（按当前阈值）'],
    ['inc','检验','判定不一致',()=>oth.filter(o=>o.cat==='临床意义判定不一致'),'相近结果判定不同'],
    ['trd','检验','范围内变化/趋势',()=>oth.filter(o=>o.cat==='范围内明显变化'||o.cat==='持续变化趋势'),'参考范围内的明显变化与持续不利趋势（提示）'],
    ['ae','AE','TEAE',()=>aes.filter(a=>a.te!==false),'给药后 AE 例次'],
    ['ae3','AE','≥3级',()=>aes.filter(a=>parseInt(a.g)>=3),'≥3 级 AE 例次'],
    ['sae','AE','SAE',()=>aes.filter(a=>a.sae),'严重不良事件'],
    ['aesi','AE','AESI',()=>aes.filter(a=>a.aesi),'特别关注不良事件'],
    ['pd','方案偏离','潜在PD',()=>pd,'数据推断的潜在方案偏离'],
    ['pdi','方案偏离','重要PD',()=>pd.filter(x=>x.grade==='重要'),'潜在 PD 中分级为重要的'],
    ['q','质疑','申办方',()=>D.queries,'申办方医学质疑'],
    ['cro','质疑','CRO',()=>D.cro.map(c=>({sid:c[2],site:subSite[c[2]],c})),'CRO/外部已发质疑'],
    ['ent','数据质量','疑似录入错误',()=>entry,'小数点/单位疑似录错（临床监查页）']];
  const siteOf=x=>x.site||subSite[x.sid]||'';
  const fu=O.fu||null,nn=O.nnum||{},den={};S.forEach(s=>{if(s.fd)den[s.site]=(den[s.site]||0)+(fu?(fu[s.id]||0):1)});
  const dOf=(k,site)=>k==='ent'&&O.nnum?(nn[site]||0):(den[site]||0);
  const lowK=new Set(['ae']);                          /* TEAE 偏低：可能漏报 */
  const items={},rate={},cell={};C.forEach(([k,,,f])=>{const all=f();items[k]={};all.forEach(x=>{const s=siteOf(x);(items[k][s]=items[k][s]||[]).push(x)});
    const tot=CS.reduce((a,c)=>a+dOf(k,c.site),0)||1;rate[k]=all.length/tot});
  const flat=[];C.forEach(([k])=>{cell[k]={};CS.forEach(c=>{const d=dOf(k,c.site);if(!d)return;const x=K.oe((items[k][c.site]||[]).length,d,rate[k]);cell[k][c.site]=x;flat.push([k,x])})});
  const qu=K.bh(flat.map(f=>f[1].pu)),ql=K.bh(flat.map(f=>lowK.has(f[0])?f[1].pl:null));flat.forEach((f,i)=>{f[1].qu=qu[i];f[1].ql=ql[i]});
  const hot=site=>C.filter(([k])=>K.qlt(((cell[k]||{})[site]||{}).qu,.10)).map(x=>x[2]);
  const low=site=>C.filter(([k])=>K.qlt(((cell[k]||{})[site]||{}).ql,.10)).map(x=>x[2]);
  /* 小中心（分母极小：随访人日 <200，或给药人数 ≤3；旧构建无 fu 时按给药人数）的偏高格统计上成立但中心层面误导
   * （V5 修复波：1 例给药/204 随访人日产出 8 条 CS＋8 条潜在 PD 也被标「偏高」）→ 只补「个案驱动」标注，不改显著性判定。 */
  const small=new Set(CS.filter(c=>(fu?(den[c.site]||0)<200:(den[c.site]||0)<=3)||(c.dosed||0)<=3).map(c=>c.site));
  const cased=(k,s)=>K.qlt(((cell[k]||{})[s]||{}).qu,.10)&&small.has(s);
  return K._cr={cats:C,items,rate,centers:CS,hot,low,cell,den,small,cased,unit:fu?'随访人日':'给药人数'}};
K.showQ=id=>{const q=K.qById(id);if(!q)return;const cro=D().cro.filter(c=>c[2]===q.sid);
  K.drawer(`${q.id} · ${K.catN(q.cat)}`,`<div class="flex wrap mb">${K.sid(q.sid)}${K.p(K.center(q.site),'line')}${K.p(K.loc(q.sh,q.row),'sq')}${K.p(q.v,'blu')}${q.test?K.p(q.test,''):''}${K.p(q.cro,q.cro==='冲突澄清'?'red':q.cro==='未见同问'?'grn':q.cro==='同主题已查重'?'yel':'line')}</div>
  <div class="box org" style="font-size:13px;line-height:1.7">${K.hlNum(q.text)}</div>
  <div class="sec-t"><h2>证据记录</h2><span class="muted small">${q.ev.length} 行 · ${K.esc((C0().query||{}).note||'已写入交付表格对应记录行的首列')}</span></div><div class="ex-rows muted">载入中…</div>
  <div class="q-series"></div>
  <div class="sec-t"><h2>本例 ${K.esc((C0().query||{}).extLabel||'CRO 既往意见')}</h2><span class="muted small">${cro.length} 条</span></div>${cro.length?`<table class="t"><tbody>${cro.map(c=>`<tr><td class="nowrap">${K.p(c[0],'sq')} ${c[1]}</td><td>${K.p(c[3],'blu')}</td><td>${K.esc(c[4])}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">无</div>'}`);
  const box=document.querySelector('.dr .ex-rows');const X=window.KZX;const ex=X&&Object.values(X.ex).find(e=>e.q===id);
  if(ex){box.innerHTML=K.listing(ex.rows);box.classList.remove('muted')}else{box.innerHTML=`<table class="t"><tbody>${q.ev.map(e=>`<tr><td>${K.p(K.shName(e[0]),'sq')}</td><td>行 ${e[1]}</td><td>${K.p(e[2],'blu')}</td><td>${K.esc(e[3])}</td></tr>`).join('')}</tbody></table>`}
  /* V6：有原始数据层时，证据记录改为就地原行（含前后行、可展开全表单），旧摘录收起 */
  K.rawIdx().then(I=>{if(I&&(I.subs||{})[q.sid]){const _p=box.previousElementSibling;if(_p)_p.style.display='none';box.style.display='none'}});
  K.seriesPanel(document.querySelector('.dr .q-series'),{sid:q.sid,tests:[q.test,...q.ev.map(e=>e[3])],hl:q.ev.map(e=>[e[0],e[1]])});
};
document.addEventListener('click',e=>{const q=e.target.closest('[data-q]');if(q){e.preventDefault();K.showQ(q.dataset.q)}});
K.CTX=((((window.KZ||{}).cfg||{}).taxonomy||{}).ctx||[['^提醒：同期另有可能对应的 AE','提醒：同期AE未关联','yel'],['^(IB|类效应|方案列明风险)','IB/类效应风险','red'],['^已关联病史「','已关联病史','grn'],['^已关联AE：','已关联AE','grn'],['^未关联AE/病史，研究者判定NCS','未关联·判无临床意义','yel'],['无CTCAE条目|不能仅凭数值','无CTCAE数值条目',''],['症状/处置型','需结合症状/处置',''],['单位|换算','单位待核','org'],['基线.*(回退|替代)|替代基线|改用首次','替代基线','blu'],['研究疾病表现.*未进一步加重|研究者归因：研究疾病$','研究疾病表现·未加重','grn'],['研究疾病表现.*进一步加重','疾病表现·较基线加重','org'],['可能为研究疾病表现','可能为疾病表现','']]).map(([re,l,c])=>[new RegExp(re),l,c]);
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
K.pdGrade=g=>K.p(g||'—',K.PDG[g]||'line',g==='重要'?'可能显著影响参与者权益/安全/福祉，或关键数据完整性/准确性/可靠性（ICH E3 Q&A R1；E6(R3)）':g==='待判定'?'需结合原因、源文件或医学判断确定分级':'不满足重要偏离标准');
K.PDS={'已记录':'grn','未见记录':'org','无 PD 记录可比对':'line'};
K.pdStatus=s=>s?K.p(s,K.PDS[s]||'line',s==='未见记录'?'方案偏离记录表中未见同参与者、同类别、时间相近的记录':s==='已记录'?'方案偏离记录表已有对应记录':'未提供方案偏离记录表'):'';
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
  <div class="flex wrap mb">${K.sid(it.sid)}${it.ctq?K.p('关键数据','solid-red',it.ctq):''}${K.p(K.center(it.site),'line')}${it.visit?K.p(it.visit,'blu'):''}${it.date?K.p(it.date,'line'):''}${K.pdGrade(it.grade)}${conf?(it.rawGrade?K.p('原文：'+it.rawGrade,'line'):''):K.pdStatus(it.status)}${conf?'':K.pdAct(it.action)}</div>
  <div class="box ${it.grade==='重要'?'red':'org'}" style="font-size:13px;line-height:1.7">${K.hlNum(conf?it.desc:it.fact)}</div>
  ${conf?'':`<div class="sec-t"><h2>分级与依据</h2></div><div class="flex small" style="align-items:flex-start;line-height:1.7">${K.pdGrade(it.grade)}<span>${K.esc(it.why)}</span></div>
  <div class="xs muted mt" style="line-height:1.7">重要偏离：可能显著影响参与者权益、安全或福祉，或显著影响关键数据的完整性、准确性、可靠性（ICH E3 Q&A R1；ICH E6(R3)）。潜在 PD 由数据推断，核实属实前不计入 PD 率。</div>`}
  <div class="pd-raw"></div><div class="pd-src"><div class="sec-t"><h2>源数据</h2><span class="muted small">${ev?ev.length+' 行':'未取得原始行'}</span></div>${ev?K.listing(ev):(it.src||[]).length?`<table class="t"><tbody>${it.src.map(s=>`<tr><td>${K.p(K.shName(s[0]),'sq')}</td><td>行 ${s[1]??'—'}</td><td>${K.esc(s[2]||'')}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">按方案访视计划推断，无对应原始记录</div>'}</div>
  ${conf?`<div class="sec-t"><h2>归类</h2></div><div class="kv"><dt>统一分类</dt><dd>${K.pdCat(it.cat)} ${K.p(it.layer||'—','line')}</dd><dt>原文类别</dt><dd>${K.esc(it.rawCat||'—')} ${K.esc(it.sub||'')}</dd><dt>数据比对</dt><dd>${related.length?related.map(r=>`<span class="p sq mono click line" data-pd="${r.id}">${r.id}</span> ${K.esc(r.title)}`).join('<br>'):'<span class="muted">需现场/源文件核查（数据核查不覆盖）</span>'}</dd></div>`
  :`<div class="sec-t"><h2>判定依据</h2>${refs.map(r=>K.rp(r)).join('')}</div><div class="kv"><dt>检查</dt><dd>${K.esc(rule.title||'')}</dd><dt>逻辑</dt><dd>${K.esc(rule.logic||'')}</dd><dt>所需数据</dt><dd>${K.esc(rule.data||'')}</dd></div>
  <div class="sec-t"><h2>与已记录 PD 比对</h2></div>${m?`<div class="box grn small"><b>${m.id}</b> ${K.esc(m.date)} · ${K.esc(m.rawCat)}：${K.esc(m.desc)}${m.rawGrade?' （'+K.esc(m.rawGrade)+'）':''}</div>`:`<div class="box small">${it.status==='无 PD 记录可比对'?'未提供方案偏离记录表，无法比对。':'方案偏离记录表中未见同参与者、同类别、时间相近的记录。'}</div>`}
  ${sig?`<div class="sec-t"><h2>关联信号与质疑</h2></div><div class="flex wrap">${it.sig[0]==='lab'?`<a href="safety.html#tab=lab&risk=${sig.risk}">${K.risk(sig.risk)}</a>`:`<a href="safety.html#tab=oth&cat=${encodeURIComponent(sig.cat)}">${K.p(sig.cat,'line')}</a>`}${(sig.q||[]).map(K.qPill).join('')}${K.ctxTags(sig.ctx)}</div>`:''}
  <div class="sec-t"><h2>处理建议</h2>${K.pdAct(it.action)}</div><div class="small" style="line-height:1.7">${K.esc(K.PDACT[it.action]||'')}</div>${it.tip?`<div class="note small mt" style="line-height:1.7">${K.esc(it.tip)}</div>`:''}`}
  <div class="pd-series"></div>
  <div class="mt"><a class="small" href="timeline.html#s=${it.sid}">查看 ${it.sid} 时间线 ›</a>　<a class="small" href="deviations.html#id=${it.id}">在方案偏离页定位 ›</a></div>`,conf?K.pdCat(it.cat):`${K.pdCat(it.cat)}${K.p(it.layer+'层面','line')}`);
  const hlr=(sig&&sig.pts||[]).map(p=>[p[7],p[8]]).concat((it.src||[]).map(s=>[s[0],s[1]])).filter(e=>e[0]&&e[1]!=null);
  if(hlr.length){const rb=document.querySelector('.dr .pd-raw');K.rawBox(rb,it.sid,hlr,{title:'源数据'}).then(()=>{if(rb.innerHTML.trim())document.querySelector('.dr .pd-src').style.display='none'})}   /* V6：就地原行 */
  const tests=[sig&&sig.test,...(it.src||[]).map(s=>s[2])].filter(Boolean);
  if(tests.length)K.seriesPanel(document.querySelector('.dr .pd-series'),{sid:it.sid,tests,hl:hlr,ae:false,noRaw:true})};
document.addEventListener('click',e=>{const a=e.target.closest('[data-pd]');if(a){e.preventDefault();K.showPD(a.dataset.pd)}});
K.applyThr();
})();
K.DOM=(((window.KZ||{}).cfg||{}).taxonomy||{}).domains||[];
/* V6 审阅 RUX 第 21 条：内部类别名（质疑键/统计依赖它，不改）→ 页面显示用医学化名称；研究配置 taxonomy.catLabels 可覆盖 */
K.CATN=Object.assign({'CS未关联AE/MH':'有临床意义异常未关联AE或病史','CS未关联·同期疑似AE':'有临床意义异常未关联AE（同期疑似AE）',
  'CS仅关联病史·加重核对':'有临床意义异常仅关联病史（是否加重）','CS归因研究疾病·给药后加重':'归因研究疾病的异常给药后加重',
  'CS较基线加重·请确认AE':'有临床意义异常较基线加重（是否为AE）','NCS但达分级≥2级':'判为无临床意义但毒性分级≥2级',
  '达分级≥2级·表单无临床意义评价':'毒性分级≥2级但未评价临床意义','超出参考范围·未评价临床意义':'超出参考范围但未评价临床意义',
  'AE一致性核对（PT级）':'疑似同一事件编码为不同PT','用药原因补漏':'停药信息补录',   /* F12①：按内容重命名（旧构建类目） */'阈值规则核对':'方案阈值核对','入排洗脱用药核对':'入排洗脱期用药核对','CS未关联·研究疾病表现较基线加重':'研究疾病相关异常较基线加重（是否为AE）',
  '未评价临床意义·达分级≥2级':'毒性分级≥2级且未评价临床意义'},
  ((((window.KZ||{}).cfg||{}).taxonomy||{}).catLabels)||{});
K.catN=c=>{c=String(c||'');const m=c.match(/^(?:AI审阅·)(.+)$/);return m?(K.CATN[m[1]]||m[1]):(K.CATN[c]||c)};   /* F12①：类目前缀从页面移除（旧构建数据也剥掉） */
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
  const c=K.chart(el,{grid:{left:o.left||48,right:28,top:18,bottom:34},
   tooltip:{trigger:'item',formatter:p=>{const r=p.data&&p.data.r;if(!r)return '';return `<b>中心 ${r.site}</b>${o.names&&o.names[r.site]?' '+K.esc(o.names[r.site]):''}<br>n=${r.n}${r.x!=null?'（'+r.x+' 例）':''} · ${o.kind==='p'?'比例':'均值'} ${fm(r.m)}<br>整体 ${fm(F.mu)} · z=${r.z.toFixed(1)}<br>${K.FL[r.flag][0]}${r.n<2?'（n<2 不判）':''}`}},
   xAxis:{type:'value',name:o.xName||'中心参与者数 n',nameLocation:'middle',nameGap:20,nameTextStyle:{color:'#64676B',fontSize:10},min:0,max:Math.ceil(maxN*1.05),minInterval:1,...K.axis,axisLabel:{color:'#404040',showMaxLabel:false}},
   yAxis:{type:'value',scale:true,...K.axis,axisLabel:{color:'#64676B',showMinLabel:false,showMaxLabel:false,formatter:v=>o.kind==='p'?Math.round(v*100)+'%':K.fmt(v)},min:o.ymin!=null?o.ymin:yr[0],max:o.ymax!=null?o.ymax:yr[1]},
   series:[L('整体',[[0,F.mu],[maxN,F.mu]],'#64676B','solid'),L('+2SE',lim(2,1),'#F2B567','dashed'),L('−2SE',lim(2,-1),'#F2B567','dashed'),L('+3SE',lim(3,1),'#B88A8A','dotted'),L('−3SE',lim(3,-1),'#B88A8A','dotted'),
    /* 用户 2026-11-11 重叠排查：中心编号互相压住 → 标签自动避让，优先保留选中中心与偏离中心（数据按优先级排序） */
    {type:'scatter',z:5,labelLayout:{hideOverlap:true},data:F.rows.slice().sort((a,b)=>(b.site===hc)-(a.site===hc)||(!!b.flag)-(!!a.flag)||b.n-a.n).map(r=>{const s=r.site===hc;return {value:[r.n,o.ymax!=null?Math.min(r.m,o.ymax):r.m],r,symbolSize:s?13:8,
      itemStyle:{color:K.FL[r.flag][1],opacity:hc&&!s?.55:.9,borderColor:s?'#0F1115':'#fff',borderWidth:s?2:1},
      label:{show:s||!!r.flag||r.n>=Math.max(3,maxN*.2),position:'right',formatter:r.site,fontSize:s?11:9,fontWeight:s?700:400,color:s?'#0F1115':'#9A9DA3'}}})}]});
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
/* 用户 2026-11-11：各处手写表格与原始数据表补排序、筛选（K.table 已有的不重复处理）。
 * 规则：单行表头、≥6 行的表——点表头升/降序；≥8 行时表上方加表内搜索，取值 2–20 种的列（最多 3 列）加下拉筛选。
 * 跳过：K.table 生成的（data-kz）、K.enhance 负责的 table.t、热力矩阵（.heat）、多级表头、含展开明细/分组行的、无表头的键值表。 */
K.enhanceTable=tb=>{if(!tb||tb.dataset.kz||tb.dataset.kze||tb.classList.contains('heat')||tb.classList.contains('t'))return;tb.dataset.kze='1';   /* table.t 由 K.enhance 负责（排序＋搜索），这里只管原始数据/原始行等其余表，避免同一张表两个搜索框 */
  const th=tb.tHead&&tb.tHead.rows.length===1?[...tb.tHead.rows[0].cells]:null,body=tb.tBodies[0];
  if(!th||!body||th.some(c=>c.colSpan>1||c.rowSpan>1))return;
  const rows=[...body.rows];if(rows.length<6||rows.some(r=>r.classList.contains('grp')||r.classList.contains('dx')||[...r.cells].some(c=>c.colSpan>1)))return;
  const txt=(r,i)=>(r.cells[i]&&r.cells[i].innerText||'').trim();
  let sc=-1,dir=1;
  th.forEach((h,i)=>{h.style.cursor='pointer';h.title=(h.title?h.title+'；':'')+'点击排序';h.addEventListener('click',()=>{dir=sc===i?-dir:1;sc=i;
    const rs=[...body.rows].sort((a,b)=>{const x=txt(a,i),y=txt(b,i);if(!x&&!y)return 0;if(!x)return 1;if(!y)return -1;return K.cmpTxt(x,y)*dir});
    rs.forEach(r=>body.appendChild(r));th.forEach((c,j)=>{const m=c.querySelector('.kzs');if(m)m.remove();if(j===i)c.insertAdjacentHTML('beforeend',`<span class="kzs" style="color:var(--brand-d)"> ${dir>0?'▲':'▼'}</span>`)})})});
  if(rows.length>=8)K._tbar(tb,body,th)};
K._enhQ=null;K.enhanceAll=()=>{K._enhQ=null;document.querySelectorAll('table').forEach(K.enhanceTable)};
if(typeof MutationObserver==='function'&&typeof document!=='undefined')document.addEventListener('DOMContentLoaded',()=>{K.enhanceAll();
  new MutationObserver(()=>{if(!K._enhQ)K._enhQ=setTimeout(K.enhanceAll,60)}).observe(document.body,{childList:true,subtree:true})});
