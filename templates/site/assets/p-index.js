/* 总览：一、综合数据（研究进展与数据状态）→ 二、风险数据（容忍限度、医学风险、方案偏离、中心）
 * → 三、风险排名（V6 用户审阅 RUX 第 1/5 条：报告只做报告，按角色过滤＋加权排序、可按中心筛选；系统提示移到研究依据页底部）。 */
K.init(()=>{
const CF=K.cfg(),SD=CF.study||{},QC=CF.query||{};const D=KZ,app=document.getElementById('app'),S=K.subs(),m=D.meta,O=D.ops||{};
const dosed=S.filter(s=>s.fd),ae=dosed.reduce((a,s)=>a+s.nae,0),st=m.status;
const lab=K.lab,oth=D.others,rc=k=>lab.filter(g=>g.risk===k).length;
const PD=D.pd,POT=(PD||{}).potential||[],CONF=(PD||{}).confirmed||[],pdImp=POT.filter(x=>x.grade==='重要').length,pdMiss=POT.filter(x=>x.status==='未见记录').length;
const pdCats=new Set(PD?oth.filter(o=>o.pd&&o.pd!=='SAFE-03'&&o.pd!=='SAFE-02').map(o=>o.cat):[]);
const cut=O.cutoff||m.cutoff||'',planned=O.planned||SD.planned||null;
/* 入组预测：近 90 天首剂速率外推到计划例数 */
const fds=dosed.map(s=>s.fd).filter(Boolean).sort(),n90=cut?fds.filter(d=>K.days(cut,d)>=0&&K.days(cut,d)<90).length:0;
const addD=(d,n)=>{const x=new Date(d+'T00:00:00Z');x.setUTCDate(x.getUTCDate()+Math.round(n));return x.toISOString().slice(0,10)};
const proj=planned&&cut&&dosed.length<planned&&n90>=3?addD(cut,(planned-dosed.length)/(n90/90)):null;
const due=O.due||[],ov=due.filter(d=>d[6]==='overdue').length,oo=due.filter(d=>d[6]==='out').length,up=(O.upcoming||[]).length;
/* F6①（V6 RUX）：新鲜度如实——按分中心新鲜度数据生成（超限中心数如实写，含在研数为 0 的中心），
 * 禁用「各中心数据均在 30 天内」无条件断言（实证：总览称均在 30 天内，监查页 12/19 中心超 30 天）。 */
const freshAll=Object.entries(O.fresh||{}).filter(([,f])=>f[1]!=null);
const fresh=freshAll.filter(([,f])=>f[2]&&f[1]>30);   // 待办/行动项仍只列仍有在研参与者的中心（可行动）
const freshStale=freshAll.filter(([,f])=>f[1]>30);
const freshSub=()=>!freshAll.length?'<span class="xs faint">无分中心新鲜度数据</span>'
  :freshStale.length?K.p(`${freshStale.length}/${freshAll.length} 个中心 >30 天无新数据`,'org')
  :K.p(`各中心数据均在 30 天内（${freshAll.length} 个中心）`,'grn');
const kpi=(l,v,s,href,cls='')=>`<${href?'a':'div'} class="kpi ${cls}${href?' click':''}"${href?` href="${href}" style="text-decoration:none;color:inherit"`:''}><div class="l">${l}</div><div class="v">${v}</div><div class="s">${s}</div></${href?'a':'div'}>`;
const sec=(n,t,s)=>`<div class="sec-h"><span class="n">${n}</span><b>${t}</b><span class="s">${s}</span></div>`;
app.innerHTML=`${K.knBar(D.knowledge)}
${(()=>{/* 用户 2026-11-11：首屏「本期风险提示」——交互式报告不设待办，按风险口径把最需要先知道的事放在第一屏，每项可点进明细 */
  const qx=K.qtlRows?K.qtlRows().filter(r=>r.st==='exceed'):[],hi=K.riskFor?K.riskFor('mm').filter(a=>a.score>=80).length:0,
    sae=S.reduce((a,s)=>a+s.sae,0),preg=oth.filter(o=>o.cat==='妊娠暴露核查').length,gap=oth.filter(o=>o.cat==='访视中断核对').length;
  const f=(lab,v,u,href,risk,tip)=>`<span class="f${risk?' risk':''}"${tip?` title="${tip}"`:''}>${href?`<a href="${href}">`:''}${lab} <b>${v}</b> ${u}${href?'</a>':''}</span>`;
  const nq=D.queries.length,nqs=new Set(D.queries.map(q=>q.sid)).size,g3=new Set((D.aes||[]).filter(a=>a.te&&(parseInt(String(a.g).replace(/\D/g,''))||0)>=3).map(a=>a.sid)).size,
    aesiU=oth.filter(o=>o.cat==='AESI标记核对').length;
  return `<div class="card mb"><div class="hd"><h2>本期风险提示</h2><span class="sub">数据截至 ${K.esc(D.meta.cutoff||'—')} · 点任一项查看明细</span></div><div class="facts">${f('医学质疑',nq,`条 · ${nqs} 例`,'queries.html',nq>0,'程序与 AI 核对后建议向中心提出的质疑；是否发出由您决定')}${f('高风险项（医学监查）',hi,'项','#rank',hi>0)}${f('容忍限度超限',qx.length,'项','monitor.html#tab=kri',qx.length>0)}${f('SAE',sae,'例次','profile.html',sae>0,'治疗期（TEAE）SAE 记录数；完全重复导出第 2 份起、首剂前不计')}${g3?f('≥3 级 AE',g3,'例','profile.html',true):''}${aesiU?f('符合 AESI 定义但未标记',aesiU,'条','safety.html#tab=oth',true):''}${preg?f('妊娠暴露',preg,'例','safety.html#tab=oth',true):''}${gap?f('访视中断',gap,'例','safety.html#tab=oth',true):''}</div></div>`})()}
${sec('一','综合数据',`研究进展与数据状态${O.stage==='daily'?' · 日常监查，数据仍在录入':''}`)}
<div class="kpis">
 ${kpi('筛选 / 随机并给药',`${m.n}<small>/ ${m.dosed} 例</small>`,Object.entries(st).map(([k,v])=>K.p(k+' '+v,K.STC[k]??'')).join(''),'monitor.html#tab=enr')}
 ${kpi('入组进度',planned?`${(dosed.length/planned*100).toFixed(0)}<small>% · ${dosed.length}/${planned}</small>`:`${dosed.length}<small>例给药</small>`,planned?(dosed.length>=planned?K.p('已达计划例数','grn'):proj?K.p('按近 90 天速率预计 '+proj+' 达成','line'):K.p('近 90 天入组不足 3 例，无法预测','line')):'<span class="xs faint">方案未给计划例数</span>','monitor.html#tab=enr','blu')}
 ${kpi('中心（有给药 / 全部）',`${D.centers.filter(c=>c.dosed).length}<small>/ ${D.centers.length}</small>`,freshSub(),'center.html')}
 ${kpi('不良事件（给药者）',`${ae}<small>例次 · ${dosed.filter(s=>s.nae).length} 例</small>`,`${K.p('SAE '+S.reduce((a,s)=>a+s.sae,0),'grn')}${K.p('AESI 已标 '+S.reduce((a,s)=>a+s.aesi,0),'red')}${(D.aesiCal||{}).defHit?K.p('符合定义待核实 '+D.aesiCal.defHit,'yel'):''}${K.p('≥2级 '+S.filter(s=>s.maxg>=2).length+' 例','org')}`,'profile.html')}
 ${kpi('访视执行',`${due.length}<small>次应完成</small>`,due.length?`${K.p('逾期 '+ov,ov?'org':'line')}${K.p('超窗 '+oo,oo?'yel':'line')}${K.p('未来 14 天 '+up,'blu')}`:'<span class="xs faint">方案访视窗未配置</span>','monitor.html#tab=vis')}
 ${kpi('医学质疑'+(QC.label?'（'+K.esc(QC.label)+'）':''),`${D.queries.length}<small>条</small>`,`${D.cro.length?K.p((QC.extShort||'外部质疑')+' '+D.cro.length+' 条已查重','line'):''}${K.p('冲突澄清 '+D.queries.filter(q=>q.cro==='冲突澄清').length,'red')}`,'queries.html','grn')}
</div>
<div class="grid g21 mt"><div class="card"><div class="hd"><h2>入组进度</h2><span class="sub">首次给药累计${planned?' · 灰线为计划例数':''}${proj?' · 虚线为按近 90 天速率的预测':''}</span></div><div id="enr" class="chart sm" style="height:210px"></div></div>
 <div class="card" id="hist"></div></div>
${K.deltaCard()}
${sec('二','风险数据','研究层面容忍限度 · 医学风险分层 · 方案偏离 · 中心风险热力图')}
<div class="card"><div class="hd"><h2>研究层面容忍限度</h2><span class="sub">关键质量因素的研究层面指标，超出或接近限度时进入风险排名</span><span class="sp"></span><span id="qtlbar"></span></div><div id="qtl"></div>
 <div class="xs faint mt">${K.esc((D.kri||{}).source||'')}</div></div>
<div class="grid g12 mt">
 <div class="card"><div class="hd"><h2>医学风险分层</h2><span class="sub">点击进入明细${pdCats.size?' · 入排/用药/访视类信号见方案偏离':''}</span><span class="sp"></span><span class="legend"><span><i class="dot red"></i> 优先核实</span><span><i class="dot org"></i> 需核实</span><span><i class="dot yel"></i> 结合临床/提示</span><span>${K.p('Q','org sq')} 已发质疑</span></span></div><div id="dom"></div></div>
 ${PD?`<div class="card"><div class="hd"><h2>方案偏离</h2><span class="sub">潜在 PD 按分级堆叠 · 右侧为已记录数</span><span class="sp"></span><span class="legend"><span><i class="dot red"></i> 重要</span><span><i class="dot yel"></i> 待判定</span><span><i class="dot"></i> 一般</span></span><a class="small" href="deviations.html" style="margin-left:8px">进入 ›</a></div><div id="pdo"></div></div>`:'<div></div>'}
</div>
<div class="grid g12 mt">
 <div class="card"><div class="hd"><h2>中心风险热力图</h2><span class="sub">每格＝该中心在这一维度上比其他中心明显偏高的风险类别数（已按各中心入组和随访时间折算；明显偏高计 2、偏高计 1，AE 报告偏少计 1）；综合＝各维度之和 · 点格看明细</span><span class="sp"></span><a class="small" href="safety.html#tab=ov">逐类热力图 ›</a></div><div id="ctr"></div></div>
 <div class="card"><div class="hd"><h2>AE 谱 × IB / 类效应</h2><span class="sub">${(CF.blind||{}).on?'盲态合并 · ':''}给药后 · 点击条形进入明细</span></div><div id="aech" class="chart" style="height:280px"></div></div>
</div>
${sec('三','风险排名','按职能分列：医学监查侧重检验与安全性，临床监查侧重访视、录入与执行偏离，项目经理侧重容忍限度与中心 · 点行查看证据与原始数据')}
<div id="rank"><div class="tbar"><select class="s" id="rsite"></select><span class="sp"></span><span class="xs muted">每列显示前 10 项，点「全部」看完整排名</span></div><div class="grid g3" id="rkcards"></div></div>`;
/* ---------- 一、综合数据 ---------- */
{const pts=fds.map((d,i)=>[d,i+1]),ser=[{type:'line',step:'end',data:pts,symbol:'none',lineStyle:{color:'#FF9900',width:2},areaStyle:{color:'rgba(255,153,0,.12)'},
   markLine:planned?{symbol:'none',data:[{yAxis:planned,label:{formatter:'计划 '+planned,color:'#64676B'},lineStyle:{color:'#C9CCD1',type:'dashed'}}]}:undefined}];
 if(proj)ser.push({type:'line',data:[[cut,dosed.length],[proj,planned]],symbol:'none',lineStyle:{color:'#FF9900',type:'dashed',width:1.5},tooltip:{show:false}});
 K.chart('#enr',{grid:{left:36,right:12,top:10,bottom:24},tooltip:{trigger:'axis'},xAxis:{type:'time',...K.axis},yAxis:{type:'value',...K.axis,max:planned?Math.ceil(Math.max(planned,dosed.length)*1.08):null},series:ser})}
{const H=K.hist(),el=document.getElementById('hist');
 if(H.length>=2){const met=[['lab','检验风险项'],['oth','专项信号'],['pd','潜在方案偏离'],['ent','疑似录入错误'],['q','医学质疑']];
  el.innerHTML=`<div class="hd"><h2>跨上传趋势</h2><span class="sub">最近 ${H.length} 次上传 · 数据截止 ${K.esc(H[0].cutoff||'')} → ${K.esc(H[H.length-1].cutoff||'')}</span></div>
   <table class="t"><tbody>${met.map(([k,l],i)=>`<tr><td class="nowrap small">${l}</td><td style="width:46%"><div id="sk${i}" style="height:26px"></div></td><td class="num"><b>${(H[H.length-1].n||{})[k]??'—'}</b></td></tr>`).join('')}</tbody></table>
   <div class="xs muted mt">每次上传的风险项变化（新增 / 已解决）</div><div id="burn" style="height:96px"></div>`;
  met.forEach(([k],i)=>K.spark(document.getElementById('sk'+i),H.map(h=>(h.n||{})[k]??null),{lab:j=>H[j].cutoff||''}));
  K.chart('#burn',{grid:{left:30,right:6,top:6,bottom:20},tooltip:{trigger:'axis'},legend:{show:false},xAxis:{type:'category',data:H.map(h=>(h.cutoff||'').slice(5)),...K.axis},yAxis:{type:'value',...K.axis},
   series:[{type:'bar',name:'新增',stack:'a',data:H.map(h=>(h.rd||{}).new||0),itemStyle:{color:'#E67E00'}},{type:'bar',name:'加重',stack:'a',data:H.map(h=>(h.rd||{}).worse||0),itemStyle:{color:'#8B0000'}},
    {type:'bar',name:'已解决',data:H.map(h=>-((h.rd||{}).resolved||0)),itemStyle:{color:'#587B3B'}}]})}
 else{const g=[['完成试验','#587B3B'],['已入组','#407AAA'],['治疗结束','#9A9DA3'],['提前终止治疗','#B07A3B'],['提前退出','#8B0000'],['筛选失败','#C9CCD1']].filter(([k])=>st[k]);
  el.innerHTML=`<div class="hd"><h2>参与者状态</h2><span class="sub">下次数据更新后，这里显示变化趋势与风险项的消化情况</span></div><div id="stc" style="height:170px"></div>`;
  K.chart('#stc',{grid:{left:70,right:40,top:4,bottom:4},tooltip:{trigger:'item',formatter:p=>`${p.name} ${p.value} 例（${(p.value/m.n*100).toFixed(0)}%）`},xAxis:{type:'value',show:false},
   yAxis:{type:'category',inverse:true,data:g.map(x=>x[0]),...K.axis,axisLabel:{color:'#404040'}},
   series:[{type:'bar',barWidth:12,data:g.map(([k,c])=>({value:st[k],itemStyle:{color:c}})),label:{show:true,position:'right',color:'#404040',fontSize:11}}]})}}
/* ---------- 二、风险数据 ---------- */
K.qtlBar(document.getElementById('qtlbar'));K.qtlTiles(document.getElementById('qtl'));
{const rows=K.DOM.map(([name,cats,c])=>{const items=cats.filter(cat=>!pdCats.has(cat)).map(cat=>{const o=oth.filter(x=>x.cat===cat);return {cat,n:o.length,p4:o.filter(x=>x.pr===4).length,p3:o.filter(x=>x.pr===3).length,q:D.queries.filter(q=>q.cat===cat).length}}).filter(x=>x.n);return {name,c,items}}).filter(r=>r.items.length);
 rows.splice(1,0,{name:'检验异常 → AE/MH',c:'org',lab:true});
 const cnt=oth.reduce((a,o)=>{a[o.cat]=(a[o.cat]||0)+1;return a},{}),maxN=Math.max(1,...Object.values(cnt));
 const bar=(n,max,col)=>`<div class="bar-in" style="flex:1"><i style="width:${Math.max(3,n/max*100)}%;background:${col}"></i></div>`;
 const blk=r=>{if(r.lab)return `<div class="dblk"><div class="dh">${K.p(r.name,'org')}<span class="xs muted">${lab.length} 行 / ${lab.reduce((a,g)=>a+g.pts.length,0)} 点</span></div>${(()=>{const pref=['CSX','DISW','MH','HXU','MHU','NCS2','NA2','G2NF','NA','CSI','DISL','DIS','AE','MHL','NCS'];return pref.concat([...new Set(lab.map(g=>g.risk))].filter(k=>!pref.includes(k)))})().filter(k=>rc(k)).map(k=>`<a class="drow" href="safety.html#tab=lab&risk=${k}"><span class="dn">${K.risk(k)}</span>${bar(rc(k),lab.length,k==='CSX'?'#8B0000':k==='MH'?'#FF9900':k==='NCS2'?'#E8C300':k==='AE'?'#587B3B':'#C9CCD1')}<b>${rc(k)}</b><span class="dq">${(()=>{const n=lab.filter(g=>g.risk===k&&g.q.length).length;return n?K.p('Q'+n,'org sq'):''})()}</span></a>`).join('')}</div>`;
  return `<div class="dblk"><div class="dh">${K.p(r.name,r.c)}<span class="xs muted">${r.items.reduce((a,i)=>a+i.n,0)} 条</span></div>${r.items.map(it=>`<a class="drow" href="safety.html#tab=oth&cat=${encodeURIComponent(it.cat)}"><span class="dn">${K.catN(it.cat)}</span>${bar(it.n,maxN,it.p4?'#8B0000':it.p3?'#FF9900':'#E8C300')}<b>${it.n}</b><span class="dq">${it.q?K.p('Q'+it.q,'org sq'):''}</span></a>`).join('')}</div>`};
 document.getElementById('dom').innerHTML=`<div class="dgrid">${rows.map(blk).join('')}</div><div class="xs muted mt" style="line-height:1.6">口径：「检验异常 → AE/MH」按参与者×指标计（同一指标多次异常只计一行）；专项核查里的「CS未关联AE/MH」按单条记录计（含心电图/生命体征/体检整份判定与逐点复核）；橙色 Q＝已写入质疑交付表格的条数。三者不相加。</div>`}
if(PD){const TX=K.pdTax(),G=[['重要','#8B0000'],['待判定','#E8C300'],['一般','#C9CCD1']];const mx=Math.max(1,...Object.values(POT.reduce((a,x)=>{a[x.cat]=(a[x.cat]||0)+1;return a},{})));
 const blkP=lay=>{const cs=(PD.taxonomy||[]).filter(t=>t[2]===lay).map(t=>t[0]).filter(c=>POT.some(x=>x.cat===c)||CONF.some(x=>x.cat===c));const n=POT.filter(x=>(TX[x.cat]||[])[2]===lay).length;
  return `<div class="dblk"><div class="dh">${K.p(lay+'层面',lay==='执行'?'blu':'org')}<span class="xs muted">潜在 ${n} 条</span></div>${cs.map(c=>{const ps=POT.filter(x=>x.cat===c),cf=CONF.filter(x=>x.cat===c).length;
   return `<a class="drow" href="deviations.html#tab=${lay==='执行'?'exe':'sci'}&cat=${c}"><span class="dn">${K.esc((TX[c]||[])[1]||c)}</span><div class="bar-in" style="flex:1;display:flex">${G.map(([g,col])=>{const k=ps.filter(x=>x.grade===g).length;return k?`<i style="width:${k/mx*100}%;background:${col}"></i>`:''}).join('')}</div><b>${ps.length}</b><span class="dq">${cf?K.p(cf,'grn sq'):''}</span></a>`}).join('')||'<div class="xs faint" style="padding:4px">无</div>'}</div>`};
 document.getElementById('pdo').innerHTML=`<div class="dgrid">${blkP('执行')}${blkP('科学')}</div><div class="flex wrap mt xs muted" style="gap:10px"><span>已记录 PD <b style="color:var(--ink)">${CONF.length}</b></span><span>潜在未见记录 <b style="color:var(--brand-d)">${(PD||{}).hasListing===false?'—':pdMiss}</b>${(PD||{}).hasListing===false?'（未提供方案偏离记录表，无法比对）':''}</span><span>潜在重要 <b style="color:var(--risk)">${pdImp}</b></span><span>潜在偏离涉及参与者 <b style="color:var(--ink)">${new Set(POT.map(x=>x.sid)).size}</b></span><span class="sp"></span><a href="deviations.html#tab=rules">查看核查清单 ›</a></div>`}
/* V6（用户审阅 RUX 第 2 条、裁定 4）：总览中心风险热力图——综合＋各维度；分值＝显著格数加权（q<0.05 计 2、q<0.10 计 1；AE 偏少计 1；数据 >30 天未更新计 1） */
{const CR=K.centerRisk(),FR=Object.fromEntries(fresh),G=[...new Set(CR.cats.map(c=>c[1]))];
 const cellOf=(site,g)=>{const hits=[];let sc=0;CR.cats.filter(c=>c[1]===g).forEach(([k,,l,,desc])=>{const x=(CR.cell[k]||{})[site];if(!x)return;
   if(K.qlt(x.qu,.10)){const w=K.qlt(x.qu,.05)?2:1;sc+=w;hits.push([l,w===2?'明显偏高':'偏高',x,desc])}
   else if(k==='ae'&&K.qlt(x.ql,.10)){sc+=1;hits.push([l,'偏少（可能漏报）',x,desc])}});return {sc,hits}};
 const rows=CR.centers.map(c=>{const by=Object.fromEntries(G.map(g=>[g,cellOf(c.site,g)])),f=FR[c.site],fs=f?1:0;
   return {c,by,f,fs,tot:G.reduce((a,g)=>a+by[g].sc,0)+fs}}).sort((a,b)=>b.tot-a.tot||b.c.dosed-a.c.dosed);
 const mx=Math.max(1,...rows.map(r=>r.tot)),mg=Math.max(1,...rows.flatMap(r=>G.map(g=>r.by[g].sc)));
 const bg=(v,m)=>v?`background:rgba(192,0,0,${(.10+.55*Math.min(1,v/m)).toFixed(2)});color:${v/m>.55?'#fff':'var(--ink)'}`:'';
 const el=document.getElementById('ctr');
 el.innerHTML=rows.length?`<div class="tw" style="max-height:330px"><table class="t heat ctrheat"><thead><tr><th>中心</th><th class="num">给药</th><th class="h">综合</th>${G.map(g=>`<th class="h">${K.esc(g)}</th>`).join('')}<th class="h">数据更新</th></tr></thead><tbody>${rows.map((r,i)=>`<tr>
   <td class="nw"><a href="center.html#c=${r.c.site}">${K.p(r.c.site,'sq mono')} ${K.esc(r.c.name.length>10?r.c.name.slice(0,10)+'…':r.c.name)}</a>${CR.small.has(r.c.site)?' <span class="xs faint" title="分母极小，偏高可能由个别参与者驱动">小中心</span>':''}</td><td class="num">${r.c.dosed}</td>
   <td class="h click" data-i="${i}" data-g="" style="${bg(r.tot,mx)};font-weight:700">${r.tot||'<span class="faint">0</span>'}</td>
   ${G.map(g=>`<td class="h${r.by[g].sc?' click':''}" data-i="${i}" data-g="${K.esc(g)}" style="${bg(r.by[g].sc,mg)}">${r.by[g].sc||'<span class="faint">·</span>'}</td>`).join('')}
   <td class="h" style="${r.fs?bg(1,mg):''}" title="${r.f?`最近记录 ${K.esc(r.f[0])}，${r.f[1]} 天无新数据，仍有 ${r.f[2]} 例在研`:''}">${r.f?r.f[1]+' 天':'<span class="faint">·</span>'}</td></tr>`).join('')}</tbody></table></div>`:'<div class="empty">无中心数据</div>';
 el.querySelectorAll('td.click').forEach(td=>td.onclick=()=>{const r=rows[+td.dataset.i],g=td.dataset.g,gs=g?[g]:G;const hs=gs.flatMap(x=>r.by[x].hits.map(h=>[x,...h]));
   K.drawer(`${r.c.site} ${K.esc(K.center(r.c.site))} · ${g||'综合'}风险`,`<div class="note small mb">${K.esc(CR.unit)}推算期望；校正多重比较后的显著格${CR.small.has(r.c.site)?'；本中心分母极小，偏高可能由个别参与者驱动':''}。</div>
    ${hs.length?`<table class="t"><thead><tr><th>维度</th><th>类别</th><th>判断</th><th class="num">观察</th><th class="num">期望</th></tr></thead><tbody>${hs.map(([gg,l,j,x,desc])=>`<tr title="${K.esc(desc)}"><td>${K.esc(gg)}</td><td>${K.esc(l)}</td><td>${K.p(j,j.startsWith('明显')?'red':j.startsWith('偏少')?'blu':'org')}</td><td class="num">${x.o}</td><td class="num">${x.e.toFixed(1)}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">该维度没有显著偏离的类别</div>'}
    ${!g&&r.f?`<div class="box small mt">数据新鲜度：最近记录 ${K.esc(r.f[0])}，${r.f[1]} 天无新数据，仍有 ${r.f[2]} 例在研。</div>`:''}
    <div class="mt"><a class="small" href="center.html#c=${r.c.site}">中心画像 ›</a>　<a class="small" href="safety.html#tab=ov">逐类热力图 ›</a></div>`)})}
{const cats=Object.assign({},D.aesum);let order=Object.keys(cats).sort((a,b)=>cats[a].n-cats[b].n);
 if(order.length>12){const rest=order.slice(0,order.length-12);
  cats['其他（'+rest.length+' 类）']=rest.reduce((a,k)=>({n:a.n+cats[k].n,s:a.s+cats[k].s,g2:a.g2+cats[k].g2,rel:a.rel+cats[k].rel,aesi:a.aesi+cats[k].aesi,terms:a.terms.concat(cats[k].terms)}),{n:0,s:0,g2:0,rel:0,aesi:0,terms:[]});
  order=['其他（'+rest.length+' 类）'].concat(order.slice(-12))}
 K.chart('#aech',{grid:{left:120,right:120,top:6,bottom:20},tooltip:{trigger:'axis',axisPointer:{type:'shadow'},formatter:p=>{const c=cats[p[0].name];return `<b>${p[0].name}</b><br>${c.n} 例次 / ${c.s} 例<br>≥2级 ${c.g2} · 相关 ${c.rel} · AESI ${c.aesi}<br>${(D.ibtag[p[0].name]||[]).join(' · ')}<br><span style="color:#999">术语 ${c.terms.length} 种：${c.terms.slice(0,6).join('、')}</span>`}},
  xAxis:{type:'value',...K.axis},yAxis:{type:'category',data:order,...K.axis,axisLabel:{color:'#404040',fontSize:11}},
  series:[{type:'bar',stack:'a',name:'1级',data:order.map(k=>cats[k].n-cats[k].g2),itemStyle:{color:'#FFCC80'},barWidth:12},{type:'bar',stack:'a',name:'≥2级',data:order.map(k=>({value:cats[k].g2,itemStyle:{color:'#E67E00'}})),label:{show:true,position:'right',formatter:p=>{const c=cats[p.name];const t=(D.ibtag[p.name]||[])[0];return c.n+(t?'  '+t:'')},color:'#64676B',fontSize:10.5}}]}).on('click',p=>location.href='safety.html#tab=ae&c='+encodeURIComponent(p.name))}
/* ---------- 三、风险排名 ---------- */
{let site='';const rs=document.getElementById('rsite');
 rs.innerHTML='<option value="">全部中心</option>'+D.centers.filter(c=>c.n).map(c=>`<option value="${K.esc(c.site)}">${K.esc(c.site)} ${K.esc(c.name.length>12?c.name.slice(0,12)+'…':c.name)}</option>`).join('');
 const RC=K.ROLES.filter(r=>r[0]!=='all');
 const card=([rk,rl])=>{const L=K.riskFor(rk,site),hi=L.filter(a=>a.score>=80).length,mid=L.filter(a=>a.score>=40&&a.score<80).length;
   return `<div class="card"><div class="hd"><h2>${K.esc(rl)}</h2><span class="sub">高 ${hi} · 中 ${mid} · 共 ${L.length} 项</span><span class="sp"></span>${L.length>10?`<a class="small" href="javascript:void 0" data-all="${rk}">全部 ›</a>`:''}</div>
   <div class="rk-list">${L.slice(0,10).map((a,i)=>`<div class="rk-it click" data-r="${rk}" data-i="${i}" style="display:flex;gap:8px;padding:6px 2px;border-top:1px solid var(--line,#eee)">${K.rlv(a.score)}<div style="flex:1;min-width:0"><b class="small" style="color:var(--ink)">${K.esc(a.title)}</b><div class="xs muted" style="line-height:1.5;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${K.esc(String(a.why||''))}">${K.esc(String(a.why||''))}</div></div>${a.sid?`<span class="xs nowrap">${K.sid(a.sid)}</span>`:''}</div>`).join('')||'<div class="empty">无</div>'}</div></div>`};
 const draw=()=>{const el=document.getElementById('rkcards');el.innerHTML=RC.map(card).join('');
   el.querySelectorAll('.rk-it').forEach(x=>x.onclick=e=>{if(e.target.closest('a'))return;K.riskFor(x.dataset.r,site)[+x.dataset.i].open()});
   el.querySelectorAll('[data-all]').forEach(x=>x.onclick=()=>{const rl=(RC.find(r=>r[0]===x.dataset.all)||[])[1]||'';const b=K.drawer(`风险排名 · ${K.esc(rl)}`,'<div id="rkall"></div>');K.riskTable(b.querySelector('#rkall'),K.riskFor(x.dataset.all,site),{h:'calc(100vh - 140px)'})})};
 rs.onchange=()=>{site=rs.value;draw()};draw()}
});
