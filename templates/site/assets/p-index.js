/* 总览及行动项（V5，用户 2026-10-31 晚）：一、综合数据（研究进展与数据状态）→ 二、风险数据（容忍限度、医学风险、方案偏离、中心）
 * → 三、需要干什么（按角色汇总的行动项：今日优先 / 处理中 / 暂缓 / 已处理，状态跨上传保留）。 */
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
const fresh=Object.entries(O.fresh||{}).filter(([,f])=>f[2]&&f[1]!=null&&f[1]>30);
const kpi=(l,v,s,href,cls='')=>`<${href?'a':'div'} class="kpi ${cls}${href?' click':''}"${href?` href="${href}" style="text-decoration:none;color:inherit"`:''}><div class="l">${l}</div><div class="v">${v}</div><div class="s">${s}</div></${href?'a':'div'}>`;
const sec=(n,t,s)=>`<div class="sec-h"><span class="n">${n}</span><b>${t}</b><span class="s">${s}</span></div>`;
app.innerHTML=`${K.knBar(D.knowledge)}
${sec('一','综合数据',`研究进展与数据状态 · 数据截止 ${K.esc(cut)}${O.stage==='daily'?' · 日常监查，数据仍在录入':''}`)}
<div class="kpis">
 ${kpi('筛选 / 随机并给药',`${m.n}<small>/ ${m.dosed} 例</small>`,Object.entries(st).map(([k,v])=>K.p(k+' '+v,K.STC[k]??'')).join(''),'monitor.html#tab=enr')}
 ${kpi('入组进度',planned?`${(dosed.length/planned*100).toFixed(0)}<small>% · ${dosed.length}/${planned}</small>`:`${dosed.length}<small>例给药</small>`,planned?(dosed.length>=planned?K.p('已达计划例数','grn'):proj?K.p('按近 90 天速率预计 '+proj+' 达成','line'):K.p('近 90 天入组不足 3 例，无法预测','line')):'<span class="xs faint">方案未给计划例数</span>','monitor.html#tab=enr','blu')}
 ${kpi('中心（有给药 / 全部）',`${D.centers.filter(c=>c.dosed).length}<small>/ ${D.centers.length}</small>`,fresh.length?K.p(fresh.length+' 个中心 >30 天无新数据','org'):K.p('各中心数据均在 30 天内','grn'),'center.html')}
 ${kpi('不良事件（给药者）',`${ae}<small>例次 · ${dosed.filter(s=>s.nae).length} 例</small>`,`${K.p('SAE '+S.reduce((a,s)=>a+s.sae,0),'grn')}${K.p('AESI '+S.reduce((a,s)=>a+s.aesi,0),'red')}${K.p('≥2级 '+S.filter(s=>s.maxg>=2).length+' 例','org')}`,'profile.html')}
 ${kpi('访视执行',`${due.length}<small>次应完成</small>`,due.length?`${K.p('逾期 '+ov,ov?'org':'line')}${K.p('超窗 '+oo,oo?'yel':'line')}${K.p('未来 14 天 '+up,'blu')}`:'<span class="xs faint">方案访视窗未配置</span>','monitor.html#tab=vis')}
 ${kpi('申办方医学质疑'+(QC.label?'（'+K.esc(QC.label)+'）':''),`${D.queries.length}<small>条</small>`,`${D.cro.length?K.p((QC.extShort||'外部质疑')+' '+D.cro.length+' 条已查重','line'):''}${K.p('冲突澄清 '+D.queries.filter(q=>q.cro==='冲突澄清').length,'red')}`,'queries.html','grn')}
</div>
<div class="grid g21 mt"><div class="card"><div class="hd"><h2>入组进度</h2><span class="sub">首次给药累计${planned?' · 灰线为计划例数':''}${proj?' · 虚线为按近 90 天速率的预测':''}</span></div><div id="enr" class="chart sm" style="height:210px"></div></div>
 <div class="card" id="hist"></div></div>
${K.deltaCard()}
${sec('二','风险数据','研究层面容忍限度 · 医学风险分层 · 方案偏离 · 需关注中心')}
<div class="card"><div class="hd"><h2>研究层面容忍限度</h2><span class="sub">关键质量因素的研究层面指标，超出或接近限度时进入行动项</span><span class="sp"></span><span id="qtlbar"></span></div><div id="qtl"></div>
 <div class="xs faint mt">${K.esc((D.kri||{}).source||'')}</div></div>
<div class="grid g12 mt">
 <div class="card"><div class="hd"><h2>医学风险分层</h2><span class="sub">点击进入明细${pdCats.size?' · 入排/用药/访视类信号见方案偏离':''}</span><span class="sp"></span><span class="legend"><span><i class="dot red"></i> 优先核实</span><span><i class="dot org"></i> 需核实</span><span><i class="dot yel"></i> 结合临床/提示</span><span>${K.p('Q','org sq')} 已发质疑</span></span></div><div id="dom"></div></div>
 ${PD?`<div class="card"><div class="hd"><h2>方案偏离</h2><span class="sub">潜在 PD 按分级堆叠 · 右侧为已记录数</span><span class="sp"></span><span class="legend"><span><i class="dot red"></i> 重要</span><span><i class="dot yel"></i> 待判定</span><span><i class="dot"></i> 一般</span></span><a class="small" href="deviations.html" style="margin-left:8px">进入 ›</a></div><div id="pdo"></div></div>`:'<div></div>'}
</div>
<div class="grid g12 mt">
 <div class="card"><div class="hd"><h2>需关注中心</h2><span class="sub">风险类别高于按${K.esc(K.centerRisk().unit)}推算的期望（校正多重比较后），或 AE 报告偏少、数据长期未更新</span><span class="sp"></span><a class="small" href="safety.html#tab=ov">中心总览热力图 ›</a></div><div id="ctr"></div></div>
 <div class="card"><div class="hd"><h2>AE 谱 × IB / 类效应</h2><span class="sub">${(CF.blind||{}).on?'盲态合并 · ':''}给药后 · 点击条形进入明细</span></div><div id="aech" class="chart" style="height:280px"></div></div>
</div>
${sec('三','需要干什么','按角色汇总的行动项 · 点行打开证据并处置，状态跨上传保留，处置后加重会重新打开')}
<div class="card"><div class="tbar"><span class="seg" id="role"></span><span class="sp"></span><span id="actn" class="small muted"></span></div><div id="act"></div></div>
<div class="card mt"><div class="hd"><h2>系统提示</h2><span class="sub">构建与审阅过程中的提示（词表、AI 审阅、数据变化等）</span></div><div id="todo"></div></div>`;
/* ---------- 一、综合数据 ---------- */
{const pts=fds.map((d,i)=>[d,i+1]),ser=[{type:'line',step:'end',data:pts,symbol:'none',lineStyle:{color:'#FF9900',width:2},areaStyle:{color:'rgba(255,153,0,.12)'},
   markLine:planned?{symbol:'none',data:[{yAxis:planned,label:{formatter:'计划 '+planned,color:'#64676B'},lineStyle:{color:'#C9CCD1',type:'dashed'}}]}:undefined}];
 if(proj)ser.push({type:'line',data:[[cut,dosed.length],[proj,planned]],symbol:'none',lineStyle:{color:'#FF9900',type:'dashed',width:1.5},tooltip:{show:false}});
 K.chart('#enr',{grid:{left:36,right:12,top:10,bottom:24},tooltip:{trigger:'axis'},xAxis:{type:'time',...K.axis},yAxis:{type:'value',...K.axis,max:planned?Math.ceil(planned*1.08):null},series:ser})}
{const H=K.hist(),el=document.getElementById('hist');
 if(H.length>=2){const met=[['lab','检验风险项'],['oth','专项信号'],['pd','潜在方案偏离'],['ent','疑似录入错误'],['q','申办方质疑']];
  el.innerHTML=`<div class="hd"><h2>跨上传趋势</h2><span class="sub">最近 ${H.length} 次上传 · 数据截止 ${K.esc(H[0].cutoff||'')} → ${K.esc(H[H.length-1].cutoff||'')}</span></div>
   <table class="t"><tbody>${met.map(([k,l],i)=>`<tr><td class="nowrap small">${l}</td><td style="width:46%"><div id="sk${i}" style="height:26px"></div></td><td class="num"><b>${(H[H.length-1].n||{})[k]??'—'}</b></td></tr>`).join('')}</tbody></table>
   <div class="xs muted mt">每次上传的风险项变化（新增 / 已解决）</div><div id="burn" style="height:96px"></div>`;
  met.forEach(([k],i)=>K.spark(document.getElementById('sk'+i),H.map(h=>(h.n||{})[k]??null),{lab:j=>H[j].cutoff||''}));
  K.chart('#burn',{grid:{left:30,right:6,top:6,bottom:20},tooltip:{trigger:'axis'},legend:{show:false},xAxis:{type:'category',data:H.map(h=>(h.cutoff||'').slice(5)),...K.axis},yAxis:{type:'value',...K.axis},
   series:[{type:'bar',name:'新增',stack:'a',data:H.map(h=>(h.rd||{}).new||0),itemStyle:{color:'#E67E00'}},{type:'bar',name:'加重',stack:'a',data:H.map(h=>(h.rd||{}).worse||0),itemStyle:{color:'#8B0000'}},
    {type:'bar',name:'已解决',data:H.map(h=>-((h.rd||{}).resolved||0)),itemStyle:{color:'#587B3B'}}]})}
 else{const g=[['完成试验','#587B3B'],['已入组','#407AAA'],['治疗结束','#9A9DA3'],['提前退出','#8B0000'],['筛选失败','#C9CCD1']].filter(([k])=>st[k]);
  el.innerHTML=`<div class="hd"><h2>受试者状态</h2><span class="sub">上传第二次数据后，这里显示跨上传趋势与风险项消化情况</span></div><div id="stc" style="height:170px"></div>`;
  K.chart('#stc',{grid:{left:70,right:40,top:4,bottom:4},tooltip:{trigger:'item',formatter:p=>`${p.name} ${p.value} 例（${(p.value/m.n*100).toFixed(0)}%）`},xAxis:{type:'value',show:false},
   yAxis:{type:'category',inverse:true,data:g.map(x=>x[0]),...K.axis,axisLabel:{color:'#404040'}},
   series:[{type:'bar',barWidth:12,data:g.map(([k,c])=>({value:st[k],itemStyle:{color:c}})),label:{show:true,position:'right',color:'#404040',fontSize:11}}]})}}
/* ---------- 二、风险数据 ---------- */
K.qtlBar(document.getElementById('qtlbar'));K.qtlTiles(document.getElementById('qtl'));
{const rows=K.DOM.map(([name,cats,c])=>{const items=cats.filter(cat=>!pdCats.has(cat)).map(cat=>{const o=oth.filter(x=>x.cat===cat);return {cat,n:o.length,p4:o.filter(x=>x.pr===4).length,p3:o.filter(x=>x.pr===3).length,q:D.queries.filter(q=>q.cat===cat).length}}).filter(x=>x.n);return {name,c,items}}).filter(r=>r.items.length);
 rows.splice(1,0,{name:'检验异常 → AE/MH',c:'org',lab:true});
 const cnt=oth.reduce((a,o)=>{a[o.cat]=(a[o.cat]||0)+1;return a},{}),maxN=Math.max(1,...Object.values(cnt));
 const bar=(n,max,col)=>`<div class="bar-in" style="flex:1"><i style="width:${Math.max(3,n/max*100)}%;background:${col}"></i></div>`;
 const blk=r=>{if(r.lab)return `<div class="dblk"><div class="dh">${K.p(r.name,'org')}<span class="xs muted">${lab.length} 行 / ${lab.reduce((a,g)=>a+g.pts.length,0)} 点</span></div>${['CSX','DISW','MH','MHU','NCS2','NA2','G2NF','NA','CSI','DIS','AE','MHL','NCS'].filter(k=>rc(k)).map(k=>`<a class="drow" href="safety.html#tab=lab&risk=${k}"><span class="dn">${K.risk(k)}</span>${bar(rc(k),lab.length,k==='CSX'?'#8B0000':k==='MH'?'#FF9900':k==='NCS2'?'#E8C300':k==='AE'?'#587B3B':'#C9CCD1')}<b>${rc(k)}</b><span class="dq">${(()=>{const n=lab.filter(g=>g.risk===k&&g.q.length).length;return n?K.p('Q'+n,'org sq'):''})()}</span></a>`).join('')}</div>`;
  return `<div class="dblk"><div class="dh">${K.p(r.name,r.c)}<span class="xs muted">${r.items.reduce((a,i)=>a+i.n,0)} 条</span></div>${r.items.map(it=>`<a class="drow" href="safety.html#tab=oth&cat=${encodeURIComponent(it.cat)}"><span class="dn">${it.cat}</span>${bar(it.n,maxN,it.p4?'#8B0000':it.p3?'#FF9900':'#E8C300')}<b>${it.n}</b><span class="dq">${it.q?K.p('Q'+it.q,'org sq'):''}</span></a>`).join('')}</div>`};
 document.getElementById('dom').innerHTML=`<div class="dgrid">${rows.map(blk).join('')}</div>`}
if(PD){const TX=K.pdTax(),G=[['重要','#8B0000'],['待判定','#E8C300'],['一般','#C9CCD1']];const mx=Math.max(1,...Object.values(POT.reduce((a,x)=>{a[x.cat]=(a[x.cat]||0)+1;return a},{})));
 const blkP=lay=>{const cs=(PD.taxonomy||[]).filter(t=>t[2]===lay).map(t=>t[0]).filter(c=>POT.some(x=>x.cat===c)||CONF.some(x=>x.cat===c));const n=POT.filter(x=>(TX[x.cat]||[])[2]===lay).length;
  return `<div class="dblk"><div class="dh">${K.p(lay+'层面',lay==='执行'?'blu':'org')}<span class="xs muted">潜在 ${n} 条</span></div>${cs.map(c=>{const ps=POT.filter(x=>x.cat===c),cf=CONF.filter(x=>x.cat===c).length;
   return `<a class="drow" href="deviations.html#tab=${lay==='执行'?'exe':'sci'}&cat=${c}"><span class="dn">${K.esc((TX[c]||[])[1]||c)}</span><div class="bar-in" style="flex:1;display:flex">${G.map(([g,col])=>{const k=ps.filter(x=>x.grade===g).length;return k?`<i style="width:${k/mx*100}%;background:${col}"></i>`:''}).join('')}</div><b>${ps.length}</b><span class="dq">${cf?K.p(cf,'grn sq'):''}</span></a>`}).join('')||'<div class="xs faint" style="padding:4px">无</div>'}</div>`};
 document.getElementById('pdo').innerHTML=`<div class="dgrid">${blkP('执行')}${blkP('科学')}</div><div class="flex wrap mt xs muted" style="gap:10px"><span>已记录 PD <b style="color:var(--ink)">${CONF.length}</b></span><span>潜在未见记录 <b style="color:var(--brand-d)">${pdMiss}</b></span><span>重要 <b style="color:var(--risk)">${pdImp}</b></span><span>涉及受试者 <b style="color:var(--ink)">${new Set(POT.map(x=>x.sid)).size}</b></span>${PD.hasListing?'':'<span>未提供方案偏离记录表</span>'}<span class="sp"></span><a href="deviations.html#tab=rules">已执行检查 ${(PD.rules||[]).filter(r=>r.state==='ran').length}/${(PD.rules||[]).length} 项 ›</a></div>`}
{const CR=K.centerRisk(),FR=Object.fromEntries(fresh);
 const rows=CR.centers.map(c=>[c,CR.hot(c.site),CR.low(c.site),FR[c.site]]).filter(x=>x[1].length||x[2].length||x[3]).sort((a,b)=>(b[1].length+b[2].length+(b[3]?1:0))-(a[1].length+a[2].length+(a[3]?1:0)));
 document.getElementById('ctr').innerHTML=rows.length?`<table class="t"><thead><tr><th>中心</th><th class="num">给药</th><th>偏高 / 偏少 / 数据</th></tr></thead><tbody>${rows.slice(0,9).map(([c,h,l,f])=>`<tr class="click" onclick="location.href='center.html#c=${c.site}'"><td class="nowrap">${K.p(c.site,'sq mono')} ${K.esc(c.name.length>14?c.name.slice(0,14)+'…':c.name)}</td><td class="num">${c.dosed}</td><td>${h.map(x=>K.p(x,'org')).join('')}${l.map(x=>K.p(x+'偏少','blu')).join('')}${f?K.p(f[1]+' 天无新数据','yel'):''}</td></tr>`).join('')}</tbody></table>${rows.length>9?`<div class="xs muted mt">另有 ${rows.length-9} 个中心，见中心画像</div>`:''}`:'<div class="empty">没有中心在校正多重比较后明显偏离，各中心数据均在 30 天内</div>'}
{const cats=Object.assign({},D.aesum);let order=Object.keys(cats).sort((a,b)=>cats[a].n-cats[b].n);
 if(order.length>12){const rest=order.slice(0,order.length-12);
  cats['其他（'+rest.length+' 类）']=rest.reduce((a,k)=>({n:a.n+cats[k].n,s:a.s+cats[k].s,g2:a.g2+cats[k].g2,rel:a.rel+cats[k].rel,aesi:a.aesi+cats[k].aesi,terms:a.terms.concat(cats[k].terms)}),{n:0,s:0,g2:0,rel:0,aesi:0,terms:[]});
  order=['其他（'+rest.length+' 类）'].concat(order.slice(-12))}
 K.chart('#aech',{grid:{left:120,right:120,top:6,bottom:20},tooltip:{trigger:'axis',axisPointer:{type:'shadow'},formatter:p=>{const c=cats[p[0].name];return `<b>${p[0].name}</b><br>${c.n} 例次 / ${c.s} 例<br>≥2级 ${c.g2} · 相关 ${c.rel} · AESI ${c.aesi}<br>${(D.ibtag[p[0].name]||[]).join(' · ')}<br><span style="color:#999">术语 ${c.terms.length} 种：${c.terms.slice(0,6).join('、')}</span>`}},
  xAxis:{type:'value',...K.axis},yAxis:{type:'category',data:order,...K.axis,axisLabel:{color:'#404040',fontSize:11}},
  series:[{type:'bar',stack:'a',name:'1级',data:order.map(k=>cats[k].n-cats[k].g2),itemStyle:{color:'#FFCC80'},barWidth:12},{type:'bar',stack:'a',name:'≥2级',data:order.map(k=>({value:cats[k].g2,itemStyle:{color:'#E67E00'}})),label:{show:true,position:'right',formatter:p=>{const c=cats[p.name];const t=(D.ibtag[p.name]||[])[0];return c.n+(t?'  '+t:'')},color:'#64676B',fontSize:10.5}}]}).on('click',p=>location.href='safety.html#tab=ae&c='+encodeURIComponent(p.name))}
/* ---------- 三、需要干什么 ---------- */
let role=K.role(),showAll=false;
K.seg(document.getElementById('role'),K.ROLES,role,v=>{role=v;K.setRole(v);showAll=false;drawAct()});
const QB=[['doing','处理中'],['done','已处理'],['fp','无问题']];
function row(a,i){const t=K.SIGST[a.sig.s]||K.SIGST.open;
  return `<tr class="click${a.sig.s==='done'||a.sig.s==='fp'?' done':''}" data-i="${i}"><td class="sc" style="width:28px">${a.score}</td>
   <td style="width:150px">${K.p(a.tag[0],a.tag[1])}${a.tags.map(t=>K.p(t[0],t[1],t[2])).join('')}</td>
   <td><b style="color:var(--ink)">${K.esc(a.title)}</b><div class="xs muted" style="margin-top:2px;line-height:1.5">${K.esc(String(a.why||'').slice(0,140))}</div></td>
   <td class="nowrap" style="width:120px">${a.sid?K.sid(a.sid):''} ${a.site?`<a class="xs" href="center.html#c=${a.site}">${K.esc(a.site)}</a>`:''}</td>
   <td style="width:72px">${a.sig.s==='open'&&!a.sig.re?'':K.sigPill(a.kind,a.x)||K.p(t[0],t[1])}</td>
   <td style="width:150px"><span class="qb">${QB.filter(([s])=>s!==a.sig.s).map(([s,l])=>`<button data-s="${s}" data-i="${i}">${l}</button>`).join('')}</span></td></tr>`}
function drawAct(){const A=K.actFor(role),g=s=>A.filter(a=>a.sig.s===s);
  const open=g('open'),doing=g('doing'),hold=g('hold'),done=A.filter(a=>a.sig.s==='done'||a.sig.s==='fp');
  const top=showAll?open:open.slice(0,12),idx=new Map();const L=[];const push=a=>{L.push(a);return L.length-1};
  const tbl=(rows)=>`<table class="t actq"><tbody>${rows.map(a=>row(a,push(a))).join('')}</tbody></table>`;
  document.getElementById('actn').innerHTML=`待处理 <b>${open.length}</b> · 处理中 <b>${doing.length}</b> · 暂缓 <b>${hold.length}</b> · 已处理 <b>${done.length}</b>`;
  document.getElementById('act').innerHTML=(open.length?`<div class="sec-t" style="margin-top:0"><h2>今日优先处理</h2><span class="muted small">按严重程度、是否本次新增/加重、是否关键数据排序</span></div>${tbl(top)}${open.length>12?`<div class="mt"><a class="small" href="javascript:void 0" id="more">${showAll?'只看前 12 项':'显示全部 '+open.length+' 项'}</a></div>`:''}`:'<div class="empty">该角色没有待处理事项</div>')
   +(doing.length?`<div class="sec-t"><h2>处理中</h2><span class="muted small">${doing.length} 项</span></div>${tbl(doing)}`:'')
   +(hold.length?`<details class="fold"><summary>暂缓 ${hold.length} 项</summary><div class="fold-b">${tbl(hold)}</div></details>`:'')
   +(done.length?`<details class="fold"><summary>已处理 / 核实无问题 ${done.length} 项</summary><div class="fold-b">${tbl(done)}</div></details>`:'');
  const el=document.getElementById('act');
  el.querySelectorAll('tr[data-i]').forEach(tr=>tr.onclick=e=>{if(e.target.closest('a,button'))return;L[+tr.dataset.i].open()});
  el.querySelectorAll('.qb button').forEach(b=>b.onclick=e=>{e.stopPropagation();const a=L[+b.dataset.i],s=b.dataset.s;K.sigSet(a.kind,a.x,s,(K.SIGR[s]||[])[0]||'')});
  const mo=document.getElementById('more');if(mo)mo.onclick=()=>{showAll=!showAll;drawAct()}}
drawAct();document.addEventListener('kz-sig',()=>drawAct());
{const todo=(D.todo&&D.todo.length?D.todo:[]).map(t=>[K.p(t[0],t[1]),t[2],t[3]]);
 document.getElementById('todo').innerHTML=todo.length?`<table class="t"><tbody>${todo.map(t=>`<tr class="click" onclick="location.href='${t[2]}'"><td style="width:90px">${t[0]}</td><td>${t[1]}</td><td class="faint">›</td></tr>`).join('')}</tbody></table>`:'<div class="empty">无</div>'}
});
