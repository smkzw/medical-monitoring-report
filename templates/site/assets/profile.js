/* mm5 安全性概况（三级 Profile：全试验 / 中心 / 受试者）——用户 2026-10-31：AE（TEAE/TRAE/SAE/AESI/分级）、MH、合并用药、
 * 检验/客观指标趋势、检验异常（含基线→基线后）、有效性趋势集中联动呈现；中心对照整体，受试者对照所在中心与整体。
 * 呈现沿用检验检查趋势/有效性趋势的画法（按访视箱线＋中位线），不另起炉灶。K.profile(el, {site, sid}) 供 profile.html 与参与者资料「概况」页签共用。 */
(function(){
const K=window.K;
K.loadJS=src=>new Promise(res=>{if(document.querySelector(`script[data-src="${src}"]`))return res();const s=document.createElement('script');s.src=src;s.dataset.src=src;s.onload=s.onerror=()=>res();document.head.append(s)});
const pct=(a,n)=>n?(a/n*100).toFixed(0)+'%':'—';
const gi=g=>parseInt(String(g||''))||0;
const stopRe=/停药|永久停|终止|撤药|中止/;
K.profile=async(el,sc)=>{
  el.innerHTML='<div class="card empty">载入中…</div>';
  if(!window.KZT)await K.loadJS('data/trend.js');
  const D=KZ,T=window.KZT||{subjects:[],metrics:[],obs:{},meta:{visits:[]}},S=K.subs(),dosed=S.filter(s=>s.fd);
  const sub=sc.sid?K.subBy(sc.sid):null,site=sc.site||(sub&&sub.site)||'';
  const groups=[];                                   /* [标签, 受试者集合] —— 第一个为本级 */
  if(sub)groups.push(['本例',dosed.filter(s=>s.id===sub.id).length?[sub]:[sub]]);
  else if(site)groups.push(['本中心',dosed.filter(s=>s.site===site)]);
  else groups.push(['全试验',dosed]);
  if(sub)groups.push(['所在中心',dosed.filter(s=>s.site===sub.site)]);
  if(sub||site)groups.push(['整体',dosed]);
  /* V6（锁库揭盲项目 RUX/MY008）：非盲构建有分组时，本级按分组拆列（盲态构建 grp 已在构建端清空，自然不出现） */
  if(!sub){const lv=groups[0][1],arms=[...new Set(lv.map(s=>s.grp).filter(Boolean))].sort();
    if(arms.length>=2)groups.splice(1,0,...arms.map(a=>[a,lv.filter(s=>s.grp===a)]))}
  const ids=g=>new Set(g[1].map(s=>s.id));
  const title=sub?`${sub.id} · ${K.esc(K.center(sub.site))}`:site?`${site} ${K.esc(K.center(site))}`:'全试验';
  const refNote=(sub?'对照：所在中心、整体（按给药受试者）':site?'对照：整体（按给药受试者）':'全部给药受试者')+(groups.some(g=>!['本例','本中心','全试验','所在中心','整体'].includes(g[0]))?' · 按分组拆列（非盲数据）':'');
  /* ---------- AE ---------- */
  const AE=D.aes.filter(a=>a.te!==false&&!a.dup);   /* F-D：完全重复记录（第 2 份起）不计例次；明细表仍列出并标「重复」 */
  /* 用户 2026-11-04 审阅第 13 条：TEAE 与 TRAE 分栏，各含 例数/%/例次；行＝总体、1–4 级、≥3 级、导致中断、导致停药/终止、SAE、AESI。
   * 措施按构建端受控分类 ak（interrupted/reduced/withdrawn/none/na；「暂时停用后又恢复」＝导致中断）。 */
  const aeRows=[['任一不良事件',a=>true],...[1,2,3,4].map(k=>[`${k} 级`,a=>gi(a.g)===k]),['≥3 级',a=>gi(a.g)>=3],
    ['导致暂停/中断给药',a=>a.ak==='interrupted'||(!a.ak&&/暂停|暂时停|中断/.test(a.act||''))],['导致停药/终止',a=>a.ak==='withdrawn'||(!a.ak&&stopRe.test(a.act||''))],
    ['严重不良事件（SAE）',a=>a.sae],['特别关注不良事件（AESI）',a=>a.aesi]];
  const aeCell=(g,f,tr)=>{const I=ids(g),xs=AE.filter(a=>I.has(a.sid)&&(!tr||a.rl)&&f(a)),ns=new Set(xs.map(a=>a.sid)).size;
    return sub&&g[0]==='本例'?`<b>${xs.length}</b> <span class="xs muted">例次</span>`:`<b>${ns}</b> <span class="xs muted">例（${pct(ns,g[1].length)}）· ${xs.length} 例次</span>`};
  const aeTbl=()=>`<table class="t"><thead><tr><th rowspan="2"></th>${groups.map(g=>`<th colspan="2">${g[0]}${sub&&g[0]==='本例'?'':`<span class="xs faint"> n=${g[1].length}</span>`}</th>`).join('')}</tr>
    <tr>${groups.map(()=>'<th>TEAE</th><th>TRAE（与研究药物相关）</th>').join('')}</tr></thead><tbody>${aeRows.map(([l,f])=>`<tr><td class="nowrap">${l}</td>${groups.map(g=>`<td>${aeCell(g,f,false)}</td><td>${aeCell(g,f,true)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  const cats=(()=>{const I=ids(groups[0]),c={};AE.filter(a=>I.has(a.sid)).forEach(a=>{c[a.c]=(c[a.c]||0)+1});return Object.entries(c).sort((a,b)=>b[1]-a[1]).slice(0,12).map(x=>x[0])})();
  /* ---------- MH / CM ---------- */
  const MC=D.mhcm||{mh:[],cm:[]};
  const topTerms=(rows,col)=>{const I=ids(groups[0]),c={};rows.filter(r=>I.has(r[0])).forEach(r=>{const t=String(r[col]).trim();if(t)(c[t]=c[t]||new Set()).add(r[0])});return Object.entries(c).sort((a,b)=>b[1].size-a[1].size).slice(0,10).map(x=>x[0])};
  const termPct=(rows,col,t,g)=>{const I=ids(g),n=new Set(rows.filter(r=>I.has(r[0])&&String(r[col]).trim()===t).map(r=>r[0])).size;return sub&&g[0]==='本例'?(n?'有':'—'):`${n}（${pct(n,g[1].length)}）`};
  const fdOf=Object.fromEntries(S.map(s=>[s.id,s.fd]));
  const cmNew=g=>{const I=ids(g),xs=MC.cm.filter(r=>I.has(r[0])&&r[2]&&fdOf[r[0]]&&r[2].slice(0,10)>=fdOf[r[0]]);return sub&&g[0]==='本例'?`${xs.length} 条`:`${new Set(xs.map(r=>r[0])).size} 例（${pct(new Set(xs.map(r=>r[0])).size,g[1].length)}）`};
  /* ---------- 检验异常：风险层（每例）＋基线→基线后最差（参考范围 L/N/H） ---------- */
  const LAY=[['CSX','CS未关联'],['MH','仅关联病史·加重'],['DISW','研究疾病·加重'],['DISL','研究疾病指标波动（清单）'],['NCS2','NCS·≥2级'],['NA2','未评价·≥2级'],['G2NF','≥2级·无评价字段'],['NA','超范围未评价'],['CSI','判定不一致'],['REL','显著变化·未关联']];
  const layCell=(g,k)=>{const I=ids(g),n=K.lab.filter(x=>I.has(x.sid)&&x.risk===k&&(k!=='REL'||K.relRisk(x))).length;return sub&&g[0]==='本例'?`<b>${n}</b>`:`<b>${n}</b> <span class="xs muted">（每例 ${(n/(g[1].length||1)).toFixed(2)}）</span>`};
  const si=Object.fromEntries((T.subjects||[]).map((x,i)=>[x[0],i]));
  const cls=r=>r[13]!=null&&r[3]>r[13]?'H':r[12]!=null&&r[3]<r[12]?'L':'N';
  const shift={};                                    /* mid -> {sid -> 'new'|'worse'|''} */
  (T.metrics||[]).forEach(m=>{const by={};(T.obs[m.id]||[]).forEach(r=>{(by[r[0]]=by[r[0]]||{b:null,p:[]});if(r[9])by[r[0]].b=r;else if(r[16]===1)by[r[0]].p.push(r)});
    const o={};Object.entries(by).forEach(([i,x])=>{if(!x.b||!x.p.length)return;const bc=cls(x.b),w=x.p.map(cls).filter(c=>c!=='N');if(!w.length)return;
      const sid=T.subjects[i][0];o[sid]=bc==='N'?'new':w.some(c=>c===bc)&&x.p.some(r=>Math.abs((r[11]||0))>=30)?'worse':''});shift[m.id]=o});
  const shiftN=(g,kind,mid)=>{const I=ids(g);let n=0;Object.entries(mid?{[mid]:shift[mid]||{}}:shift).forEach(([,o])=>Object.entries(o).forEach(([sid,v])=>{if(I.has(sid)&&v===kind)n++}));return n};
  const topShift=(()=>{const I=ids(groups[0]);return (T.metrics||[]).map(m=>[m,Object.entries(shift[m.id]||{}).filter(([sid,v])=>I.has(sid)&&v==='new').length]).filter(x=>x[1]).sort((a,b)=>b[1]-a[1]).slice(0,12)})();
  /* ---------- 组装 ---------- */
  const th=groups.map(g=>`<th>${g[0]}${sub&&g[0]==='本例'?'':`<span class="xs faint"> n=${g[1].length}</span>`}</th>`).join('');
  const tbl=(rows)=>`<table class="t"><thead><tr><th></th>${th}</tr></thead><tbody>${rows.map(([l,cells])=>`<tr><td class="nowrap">${l}</td>${cells.map(c=>`<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  const subAE=sub?D.aes.filter(a=>a.sid===sub.id):[];
  /* ---------- 微生物培养与药敏（第三轮：判读型结果分域呈现，不进检验异常/质疑链；KZ.micro=[sid,日期,访视,项目,结果,判读,C|S]） ---------- */
  const MI=D.micro||[];
  const miCell=g=>{const I=ids(g),xs=MI.filter(r=>I.has(r[0])),nc=xs.filter(r=>r[6]==='C').length,ns=new Set(xs.map(r=>r[0])).size;return sub&&g[0]==='本例'?`<b>${nc}</b> 份培养 · ${xs.length-nc} 项药敏`:`<b>${ns}</b> 例（${pct(ns,g[1].length)}）· ${nc} 份培养`};
  const miList=rows=>`<table class="t"><tbody>${rows.map(r=>`<tr><td>${r[6]==='C'?'<b>'+K.esc(r[3])+'</b>':K.esc(r[3])}</td><td class="nowrap">${K.p(r[2],'blu')} ${K.esc(r[1])}</td><td>${K.esc(r[4])}</td><td class="small">${K.esc(r[5])}</td></tr>`).join('')||'<tr><td class="empty">无</td></tr>'}</tbody></table>`;
  const microCard=MI.length?`<div class="card mb"><div class="sec-t" style="margin-top:0"><h2>微生物培养与药敏</h2><span class="muted small">判读型结果（培养/涂片/药敏 MIC）单独呈现，不进入检验异常与质疑链</span></div>${tbl([['有培养/药敏记录',groups.map(miCell)]])}${sub?miList(MI.filter(r=>r[0]===sub.id)):''}</div>`:'';
  el.innerHTML=`<div class="card mb"><div class="hd"><h2>安全性概览 · ${title}</h2><span class="sub">${refNote}</span>${sub?`<span class="sp"></span><a class="small" href="subjects.html#s=${sub.id}">参与者资料 ›</a>　<a class="small" href="timeline.html#s=${sub.id}">时间线 ›</a>`:site?`<span class="sp"></span><a class="small" href="subjects.html#c=${site}">本中心受试者 ›</a>　<a class="small" href="safety.html#tab=ov">中心总览 ›</a>`:''}</div>
   <div class="grid ${groups.length>3?'':'g2'}"><div style="min-width:0;overflow-x:auto"><div class="sec-t" style="margin-top:0"><h2>不良事件</h2><span class="muted small">给药后（TEAE）</span></div>${aeTbl()}</div>
   <div><div class="sec-t" style="margin-top:0"><h2>AE 类别</h2><span class="muted small">${sub?'本例发生的类别 · 所在中心与整体的发生率（受试者%）':'发生率（受试者%）· 前 '+cats.length+' 类'}</span></div><div class="chart" id="pf-aec" style="height:${Math.max(160,cats.length*24+40)}px"></div></div></div>
   ${sub?`<div class="sec-t"><h2>本例 AE 明细</h2></div><table class="t"><tbody>${subAE.map(a=>`<tr><td><b>${K.esc(a.t)}</b> ${a.sae?K.p('SAE','solid-red'):''}${a.aesi?K.p('AESI','red'):''}${a.rl?K.p('相关','org'):''}${a.dup?' '+K.p(a.dup_kind==='sub'?`严重程度变化×${a.dup_n||2}`:`重复×${a.dup_n||2}`,a.dup_kind==='sub'?'line':'yel'):''}</td><td class="nowrap">${K.esc(a.s||'')} → ${a.e?K.esc(a.e):'持续'}</td><td>${K.p(a.g,gi(a.g)>=3?'solid-red':gi(a.g)>=2?'red':'yel')}</td><td class="small">${K.esc(a.act||'')}</td><td class="small">${K.esc(a.out||'')}</td></tr>`).join('')||'<tr><td class="empty">无 AE 记录</td></tr>'}</tbody></table>`:''}</div>
  <div class="grid g2 mb">
   <div class="card"><div class="sec-t" style="margin-top:0"><h2>病史（MH）</h2><span class="muted small">${sub?'本例全部':'最常见 10 项 · 例数（%）'}</span></div>${sub?mhList(MC.mh.filter(r=>r[0]===sub.id)):tbl(topTerms(MC.mh,1).map(t=>[K.esc(t),groups.map(g=>termPct(MC.mh,1,t,g))]))}</div>
   <div class="card"><div class="sec-t" style="margin-top:0"><h2>合并用药（CM）</h2><span class="muted small">${sub?'本例全部':'最常见 10 种 · 例数（%）'}</span></div>
    ${tbl([['给药后新开始的用药',groups.map(cmNew)]])}${sub?cmList(MC.cm.filter(r=>r[0]===sub.id),fdOf[sub.id]):tbl(topTerms(MC.cm,1).map(t=>[K.esc(t),groups.map(g=>termPct(MC.cm,1,t,g))]))}</div></div>
  ${microCard}
  <div class="card mb"><div class="sec-t" style="margin-top:0"><h2>检验异常</h2><span class="muted small">风险层（受试者×指标，按当前阈值）· 基线→基线后最差（参考范围）</span><span class="sp"></span><a class="small" href="safety.html#tab=lab${site&&!sub?'&c='+site:''}">检验异常明细 ›</a></div>
   <div class="grid g2"><div>${tbl(LAY.filter(([k])=>K.lab.some(x=>x.risk===k)).map(([k,l])=>[`<a href="safety.html#tab=lab&risk=${k}">${l}</a>`,groups.map(g=>layCell(g,k))]))}</div>
   <div>${tbl([['基线正常 → 基线后异常（新发）',groups.map(g=>sub&&g[0]==='本例'?`<b>${shiftN(g,'new')}</b> 项指标`:`<b>${shiftN(g,'new')}</b> <span class="xs muted">（每例 ${(shiftN(g,'new')/(g[1].length||1)).toFixed(2)}）</span>`)],
       ['基线已异常 → 同向加重 ≥30%',groups.map(g=>sub&&g[0]==='本例'?`<b>${shiftN(g,'worse')}</b> 项指标`:`<b>${shiftN(g,'worse')}</b> <span class="xs muted">（每例 ${(shiftN(g,'worse')/(g[1].length||1)).toFixed(2)}）</span>`)]])}
    <div class="xs muted mt">新发异常最多的指标</div>${tbl(topShift.map(([m])=>[`<a href="javascript:void 0" data-pm="${K.esc(m.id)}">${K.esc(m.label)}</a>`,groups.map(g=>{const n=shiftN(g,'new',m.id);return sub&&g[0]==='本例'?(n?K.p('新发','org'):'—'):`${n}（${pct(n,g[1].length)}）`})]))}</div></div></div>
  <div class="card mb"><div class="sec-t" style="margin-top:0"><h2>检验 / 客观指标趋势</h2><span class="muted small">箱线＝整体（给药者，按访视）${site?' · 橙线＝'+(sub?'所在中心':'本中心')+'中位数':''}${sub?' · 红线＝本例':''}</span><span class="sp"></span><select class="s" id="pf-m"></select><div class="seg" id="pf-v"></div></div><div class="chart" id="pf-tr" style="height:300px"></div></div>
  <div class="card mb" id="pf-effc"><div class="sec-t" style="margin-top:0"><h2>有效性趋势</h2><span class="muted small">整体中位数${site?' · 中心中位数':''}${sub?' · 本例':''}</span><span class="sp"></span><select class="s" id="pf-e"></select></div><div class="chart" id="pf-ef" style="height:280px"></div></div>`;
  function mhList(rows){return `<table class="t"><tbody>${rows.map(r=>`<tr><td>${K.esc(r[1])}</td><td>${r[2]?K.p('持续','line'):''}</td></tr>`).join('')||'<tr><td class="empty">无</td></tr>'}</tbody></table>`}
  function cmList(rows,fd){return `<table class="t"><tbody>${rows.map(r=>`<tr><td><b>${K.esc(r[1])}</b>${fd&&r[2]&&r[2].slice(0,10)>=fd?' '+K.p('给药后开始','org'):''}</td><td class="nowrap">${K.esc(r[2])} → ${r[3]?K.esc(r[3]):r[4]?'持续':''}</td><td class="small">${K.esc(r[5])}</td></tr>`).join('')||'<tr><td class="empty">无</td></tr>'}</tbody></table>`}
  /* AE 类别图：本级与对照的发生率（受试者%） */
  const inc=(g,c)=>{const I=ids(g);const n=new Set(AE.filter(a=>I.has(a.sid)&&a.c===c).map(a=>a.sid)).size;return sub&&g[0]==='本例'?AE.filter(a=>a.sid===sub.id&&a.c===c).length:+(n/(g[1].length||1)*100).toFixed(1)};
  const col=['#FF9900','#407AAA','#9DB7D3','#587B3B','#A85F34','#7A5195','#C9CCD1'];
  /* 受试者层：本例有的类别 → 所在中心与整体在该类别的发生率（看本例的 AE 在中心/整体中是否常见） */
  if(cats.length)K.chart('#pf-aec',{grid:{left:150,right:30,top:24,bottom:20},legend:{top:0},tooltip:{trigger:'axis',axisPointer:{type:'shadow'},valueFormatter:v=>v+'%'},
    xAxis:{type:'value',...K.axis,axisLabel:{formatter:v=>v+'%'}},yAxis:{type:'category',data:cats.slice().reverse(),...K.axis,axisLabel:{color:'#404040',fontSize:11,width:140,overflow:'truncate'}},
    series:(sub?groups.slice(1):groups).map((g,i)=>({type:'bar',name:g[0],data:cats.slice().reverse().map(c=>inc(g,c)),itemStyle:{color:col[sub?i+1:i]},barMaxWidth:10}))});
  else el.querySelector('#pf-aec').innerHTML='<div class="empty">无 AE</div>';
  /* 趋势：整体箱线＋中心中位＋本例 */
  const VL=(T.meta||{}).visits||K.VIS;
  const ms=(T.metrics||[]).slice().sort((a,b)=>(topShift.findIndex(x=>x[0].id===b.id)>=0?1:0)-(topShift.findIndex(x=>x[0].id===a.id)>=0?1:0));
  const msel=el.querySelector('#pf-m');msel.innerHTML=ms.map(m=>`<option value="${K.esc(m.id)}">${K.esc(m.label)}</option>`).join('');
  let mode='val';
  const draw=()=>{const mid=msel.value,rows=(T.obs[mid]||[]).filter(r=>T.subjects[r[0]][3]===1&&K.isAgg(VL[r[5]])&&(r[16]===1||r[9]));
    const v=r=>mode==='val'?r[3]:mode==='chg'?r[10]:r[11];const vis=VL.filter((x,i)=>rows.some(r=>r[5]===i&&v(r)!=null));
    const box=vis.map(x=>{const a=rows.filter(r=>VL[r[5]]===x).map(v).filter(y=>y!=null);return a.length?[Math.min(...a),K.q(a,.25),K.q(a,.5),K.q(a,.75),Math.max(...a)]:[]});
    const med=(pred)=>vis.map(x=>{const a=rows.filter(r=>VL[r[5]]===x&&pred(T.subjects[r[0]])).map(v).filter(y=>y!=null);return a.length?+K.median(a).toFixed(3):null});
    const ser=[{type:'boxplot',name:'整体',data:box,itemStyle:{color:'#F4F6F8',borderColor:'#9DB7D3'}}];
    if(site)ser.push({type:'line',name:sub?'所在中心中位':'本中心中位',data:med(s=>s[1]===site),lineStyle:{color:'#FF9900',width:2},itemStyle:{color:'#FF9900'},connectNulls:true});
    if(sub)ser.push({type:'line',name:'本例',data:vis.map(x=>{const r=rows.filter(r=>T.subjects[r[0]][0]===sub.id&&VL[r[5]]===x).map(v).filter(y=>y!=null);return r.length?r[r.length-1]:null}),lineStyle:{color:'#8B0000',width:2},itemStyle:{color:'#8B0000'},connectNulls:true,symbolSize:7});
    K.chart('#pf-tr',{grid:{left:50,right:20,top:30,bottom:30},legend:{top:0},tooltip:{trigger:'axis'},xAxis:{type:'category',data:vis,...K.axis},yAxis:{type:'value',scale:true,...K.axis,name:mode==='val'?((ms.find(m=>m.id===mid)||{}).units||[[]])[0][0]||'':mode==='chg'?'较基线变化':'较基线%'},series:ser})};
  K.seg(el.querySelector('#pf-v'),[['val','数值'],['chg','较基线变化'],['pct','较基线%']],mode,x=>{mode=x;draw()});
  msel.onchange=draw;if(ms.length)draw();
  el.querySelectorAll('[data-pm]').forEach(a=>a.onclick=()=>{msel.value=a.dataset.pm;draw();el.querySelector('#pf-tr').scrollIntoView({block:'center',behavior:'smooth'})});
  /* 有效性 */
  const EF=D.eff||{metrics:[],data:[]};const esel=el.querySelector('#pf-e');
  if(!(EF.metrics||[]).length){el.querySelector('#pf-effc').style.display='none';return}
  esel.innerHTML=EF.metrics.map(m=>`<option value="${K.esc(m.id)}">${K.esc(m.label)}</option>`).join('');
  const de=()=>{const m=EF.metrics.find(x=>x.id===esel.value)||EF.metrics[0],V=m.visits||[];
    const md=pred=>V.map(x=>{const a=EF.data.filter(pred).map(e=>((e.v||{})[m.id]||{})[x]).filter(y=>y!=null);return a.length?+K.median(a).toFixed(2):null});
    const ser=[{type:'line',name:'整体中位',data:md(()=>true),lineStyle:{color:'#9DB7D3',width:2},itemStyle:{color:'#9DB7D3'},connectNulls:true}];
    if(site)ser.push({type:'line',name:sub?'所在中心中位':'本中心中位',data:md(e=>e.site===site),lineStyle:{color:'#FF9900',width:2},itemStyle:{color:'#FF9900'},connectNulls:true});
    if(sub)ser.push({type:'line',name:'本例',data:md(e=>e.sid===sub.id),lineStyle:{color:'#8B0000',width:2},itemStyle:{color:'#8B0000'},connectNulls:true,symbolSize:7});
    K.chart('#pf-ef',{grid:{left:50,right:20,top:30,bottom:30},legend:{top:0},tooltip:{trigger:'axis'},xAxis:{type:'category',data:V,...K.axis},yAxis:{type:'value',scale:true,...K.axis,name:m.unit||''},series:ser})};
  esel.onchange=de;de();
};
})();
