K.init(()=>{
const D=KZ,app=document.getElementById('app'),Q=D.queries;
const dom=q=>K.domOf(q.cat);const domCol=d=>(K.DOM.find(x=>x[0]===d)||[])[2]||'';
const CROC={'冲突澄清':'red','同主题已查重':'yel','未见同问':'grn','未提供 CRO 质疑':'line'};
const CRON={'冲突澄清':'与 CRO 质疑结论不同','同主题已查重':'CRO 已问过同类','未见同问':'CRO 未问过','未提供 CRO 质疑':'未提供 CRO 质疑'};
const subjN=new Set(Q.map(q=>q.sid)).size,ctrN=new Set(Q.map(q=>q.site)).size;
const cnt=(arr,f)=>{const m={};arr.forEach(x=>{const k=f(x);m[k]=(m[k]||0)+1});return m};
const byDom=cnt(Q,dom),bySite=cnt(Q,q=>q.site),byCro=cnt(Q,q=>q.cro),bySh=cnt(Q,q=>K.shName(q.sh));   /* 按显示名归并（「edc:LB1」与「LB1」是同一数据页，运营复审：筛选项重复） */
app.innerHTML=`
<div class="kpis">
 <div class="kpi"><div class="l">申办方医学质疑</div><div class="v">${Q.length}<small>条</small></div><div class="s" title="按条目计：同一记录行多条合并为一条编号（合并行不计）；与页头、清单、质疑工作簿三处同一数字">${K.p(subjN+' 例','line')}${K.p(ctrN+' 中心','line')}${D.meta.qsMerged?K.p(`另有 ${D.meta.qsMerged} 条同一数据点的问题已合并（见正文「另：」）`,'yel'):''}</div></div>
 ${K.DOM.map(([d,cats,c])=>byDom[d]?`<div class="kpi ${c==='red'?'risk':c==='blu'?'blu':c==='grn'?'grn':''}"><div class="l">${d}</div><div class="v">${byDom[d]}<small>条</small></div><div class="s">${cats.filter(x=>Q.some(q=>q.cat===x)).length} 个主题</div></div>`:'').join('')}${byDom['其他']&&!K.DOM.some(d=>d[0]==='其他')?`<div class="kpi"><div class="l">其他</div><div class="v">${byDom['其他']}<small>条</small></div><div class="s">${new Set(Q.filter(q=>dom(q)==='其他').map(q=>q.cat)).size} 个主题</div></div>`:''}
</div>
${K.knHint(D.knowledge)}
<div class="grid g21 mt" style="grid-template-columns:1.5fr 1fr">
 <div class="card"><div class="hd"><h2>筛选</h2><span class="sp"></span><select class="s" id="fctr"><option value="">全部中心</option>${Object.entries(bySite).sort((a,b)=>a[0].localeCompare(b[0])).map(([k,v])=>`<option value="${k}">${k} ${K.esc(K.center(k))}（${v}）</option>`).join('')}</select><input class="s" id="qs" placeholder="搜索 编号/参与者/指标/文字"></div>
  <div class="col">
   <div class="flex wrap"><span class="muted small nowrap" style="width:56px">风险域</span><div class="chips" id="fdom"></div></div>
   <div class="flex wrap"><span class="muted small nowrap" style="width:56px">与${K.esc((K.cfg().query||{}).extShort||'外部')}对照</span><div class="chips" id="fcro"></div></div>
   <div class="flex wrap"><span class="muted small nowrap" style="width:56px">数据页</span><div class="chips" id="fsh"></div></div>
   
  </div></div>
 <div class="card"><div class="hd"><h2>中心分布</h2><span class="sub">点击柱筛选</span></div><div id="ctrch" class="chart sm" style="height:190px"></div></div>
</div>
<div class="sec-t"><h2>质疑清单</h2><span class="muted small" id="qn"></span><span class="sp"></span><span class="legend">同主题通用要求只在分组标题显示一次（虚线框），行内仅列个案事实；点击行查看证据记录与 CRO 意见</span></div>
<div id="qt"></div>
<div class="box blu mt small">质疑工作簿：<b><a href="../${K.esc((K.cfg().query||{}).file||'')}">下载质疑表（Excel）</a></b> —— 每条质疑写在对应记录行的首列，同一行多条以编号分隔；「query 清单」页列出全部质疑及与本页编号的对照。${D.cro.length?`${K.esc((K.cfg().query||{}).extLabel||'外部质疑')} 查重：${Object.entries(byCro).map(([k,v])=>K.p(k+' '+v,CROC[k])).join('')}；「冲突澄清」表示与已发意见口径相反，需统一后回复中心。`:''}</div>`;
const F={dom:null,cro:null,sh:null,site:null,s:''};
const domOpts=K.DOM.filter(d=>byDom[d[0]]).map(d=>[d[0],`<i class="dot ${d[2]}"></i> ${d[0]}`,byDom[d[0]]]).concat(byDom['其他']&&!K.DOM.some(d=>d[0]==='其他')?[['其他','<i class="dot"></i> 其他',byDom['其他']]]:[]);   /* 审阅者 2026-11-10：未归类类目（AI 审阅新类目）也计入，卡片合计＝总数 */
const cD=K.chips(app.querySelector('#fdom'),domOpts,v=>{F.dom=v;draw()});
const cC=K.chips(app.querySelector('#fcro'),Object.entries(byCro).map(([k,v])=>[k,CRON[k]||k,v]),v=>{F.cro=v;draw()});
K.chips(app.querySelector('#fsh'),Object.entries(bySh).sort((a,b)=>b[1]-a[1]).map(([k,v])=>[k,k,v]),v=>{F.sh=v;draw()});
const sel=app.querySelector('#fctr');sel.onchange=()=>{F.site=sel.value||null;draw()};const ctrChips={set:v=>sel.value=v||''};
app.querySelector('#qs').oninput=e=>{F.s=e.target.value.trim();draw()};
const ctrs=Object.entries(bySite).sort((a,b)=>b[1]-a[1]);
const ch=K.chart('#ctrch',{grid:{left:28,right:8,top:10,bottom:24},tooltip:{trigger:'axis',formatter:p=>`${K.center(p[0].name)}<br>${p[0].value} 条`},xAxis:{type:'category',data:ctrs.map(c=>c[0]),...K.axis,axisLabel:{color:'#64676B',fontSize:10,interval:0,rotate:ctrs.length>18?60:0}},yAxis:{type:'value',...K.axis,minInterval:1},series:[{type:'bar',data:ctrs.map(c=>c[1]),itemStyle:{color:'#FF9900',borderRadius:[3,3,0,0]},barMaxWidth:18}]});
ch.on('click',p=>{F.site=F.site===p.name?null:p.name;ctrChips.set(F.site);draw()});
const order=K.DOM.flatMap(d=>d[1]);const oi=c=>{const i=order.indexOf(c);return i<0?99:i};
/* D001 测试第四轮（2026-11-11）：「阈值规则核对」一类下有两种要求（海氏法则只对肝功能适用），被当作整组通用要求挂在贫血行上 →
 * 只有一种要求时才作为本组通用要求在组标题显示；多种要求时每行显示自己的完整要求 */
const comG=g=>{const c=(D.qcommon||{})[g]||[];return c.length===1?c:[]};
const comOf=q=>comG(q.cat);
// 本组没有通用要求（工作台并入的 AI 质疑组）时，行内显示本条完整请求，不再挂空的「＋通用要求」（审阅 2026-11-10：42 条请求不可见）
const uniq=q=>q.parts.filter(p=>!p[1]||!comOf(q).length).map(p=>K.hlNum(p[0])).join(' ');
const tbl=K.table(app.querySelector('#qt'),{rows:[],noPage:true,h:'calc(100vh - 160px)',onRow:r=>K.showQ(r.id),
 group:r=>r.cat,groupHead:(g,r)=>{const n=cur.filter(q=>q.cat===g).length;const com=comG(g);return `<div class="flex wrap"><i class="dot ${domCol(dom(r))}"></i><b>${K.catN(g)}</b>${K.p(n+' 条','line')}${K.p(dom(r),domCol(dom(r)))}<span class="sp"></span>${K.ibTags(g)}</div>${com.length?`<div class="qtpl">通用要求：${com.map(K.esc).join(' ')}</div>`:''}`},
 cols:[{k:'id',t:'编号',f:r=>K.qPill(r.id)+(r.flags||[]).map(fl=>fl==='L3不同意·须人审'?K.p('复核存疑','red','另一模型复核不同意该质疑，请重点判断'):'').join(''),w:'64px'},{k:'sid',t:'参与者',f:r=>K.sid(r.sid)+`<div class="xs faint">${K.esc(K.center(r.site))}</div>`,w:'110px'},
  {k:'sh',t:'数据位置',f:r=>`${K.p(K.shName(r.sh),'sq')}<div class="xs muted" title="导出表第 ${r.row} 行">${K.esc([r.v,r.d].filter(Boolean).join(' · '))||'第 '+r.row+' 行'}${r.ev.length>1?' · 涉及 '+r.ev.length+' 条记录':''}</div>`,w:'120px'},
  {k:'v',t:'访视',f:r=>`${r.v?K.p(r.v,'blu'):''}<div class="xs faint">${K.esc(r.d||'')}</div>`,w:'86px',s:r=>(r.d||'9999')+'|'+String(K.vi(r.v)).padStart(3,'0')},
  {k:'test',t:'对象',f:r=>`<span class="small">${K.esc(r.test||'—')}</span>`,w:'150px'},
  {k:'text',t:'个案事实与请求',f:r=>`<div class="small" style="line-height:1.6">${uniq(r)}${r.parts.some(p=>p[1])&&comOf(r).length?` ${K.p('＋本组通用要求','line')}`:''}</div>`},
  {k:'cro',t:'与'+((K.cfg().query||{}).extShort||'外部')+'质疑对照',f:r=>K.p(CRON[r.cro]||r.cro,CROC[r.cro]),w:'110px'}]});
let cur=[];
function draw(){const s=F.s.toLowerCase();cur=Q.filter(q=>(!F.dom||dom(q)===F.dom)&&(!F.cro||q.cro===F.cro)&&(!F.sh||K.shName(q.sh)===F.sh)&&(!F.site||q.site===F.site)&&(!s||[q.id,q.sid,q.test,q.text,q.cat,q.sh].join(' ').toLowerCase().includes(s)))
 .sort((a,b)=>oi(a.cat)-oi(b.cat)||a.cat.localeCompare(b.cat)||a.sid.localeCompare(b.sid)||a.id.localeCompare(b.id));
 app.querySelector('#qn').textContent=`${cur.length} 条 · ${new Set(cur.map(q=>q.cat)).size} 个主题 · ${new Set(cur.map(q=>q.sid)).size} 例`;tbl.set(cur);K.setHash({dom:F.dom,cro:F.cro,site:F.site,q:F.s})}
const h=K.hash();if(h.q)app.querySelector('#qs').value=F.s=h.q;if(h.site){F.site=h.site;ctrChips.set(h.site)}if(h.dom){F.dom=h.dom;cD.set(h.dom)}if(h.cro){F.cro=h.cro;cC.set(h.cro)}
draw();if(h.id)K.showQ(h.id);
});
