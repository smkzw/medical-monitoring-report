K.init(()=>{
const D=KZ,app=document.getElementById('app'),Q=D.queries;
const dom=q=>K.domOf(q.cat);const domCol=d=>(K.DOM.find(x=>x[0]===d)||[])[2]||'';
const CROC={'冲突澄清':'red','同主题已查重':'yel','未见同问':'grn'};
const subjN=new Set(Q.map(q=>q.sid)).size,ctrN=new Set(Q.map(q=>q.site)).size;
const cnt=(arr,f)=>{const m={};arr.forEach(x=>{const k=f(x);m[k]=(m[k]||0)+1});return m};
const byDom=cnt(Q,dom),bySite=cnt(Q,q=>q.site),byCro=cnt(Q,q=>q.cro),bySh=cnt(Q,q=>q.sh);
app.innerHTML=`
<div class="kpis">
 <div class="kpi"><div class="l">申办方医学质疑</div><div class="v">${Q.length}<small>条</small></div><div class="s">${K.p(subjN+' 例','line')}${K.p(ctrN+' 中心','line')}</div></div>
 ${K.DOM.map(([d,cats,c])=>byDom[d]?`<div class="kpi ${c==='red'?'risk':c==='blu'?'blu':c==='grn'?'grn':''}"><div class="l">${d}</div><div class="v">${byDom[d]}<small>条</small></div><div class="s">${cats.filter(x=>Q.some(q=>q.cat===x)).length} 个主题</div></div>`:'').join('')}
</div>
<div class="grid g21 mt" style="grid-template-columns:1.5fr 1fr">
 <div class="card"><div class="hd"><h2>筛选</h2><span class="sp"></span><select class="s" id="fctr"><option value="">全部中心</option>${Object.entries(bySite).sort((a,b)=>a[0].localeCompare(b[0])).map(([k,v])=>`<option value="${k}">${k} ${K.esc(K.center(k))}（${v}）</option>`).join('')}</select><input class="s" id="qs" placeholder="搜索 编号/受试者/指标/文字"></div>
  <div class="col">
   <div class="flex wrap"><span class="muted small nowrap" style="width:56px">风险域</span><div class="chips" id="fdom"></div></div>
   <div class="flex wrap"><span class="muted small nowrap" style="width:56px">${K.esc((K.cfg().query||{}).extShort||'外部')}查重</span><div class="chips" id="fcro"></div></div>
   <div class="flex wrap"><span class="muted small nowrap" style="width:56px">数据页</span><div class="chips" id="fsh"></div></div>
   
  </div></div>
 <div class="card"><div class="hd"><h2>中心分布</h2><span class="sub">点击柱筛选</span></div><div id="ctrch" class="chart sm" style="height:190px"></div></div>
</div>
<div class="sec-t"><h2>质疑清单</h2><span class="muted small" id="qn"></span><span class="sp"></span><span class="legend">同主题通用要求只在分组标题显示一次（虚线框），行内仅列个案事实；点击行查看证据记录与 CRO 意见</span></div>
<div id="qt"></div>
<div class="box blu mt small">交付文件：<b>${K.esc((K.cfg().query||{}).file||'申办方MM_query_首列版.xlsx')}</b> —— 每条质疑写在对应证据行首列「申办方MM query」，同一行多条以编号分隔。${D.cro.length?`${K.esc((K.cfg().query||{}).extLabel||'外部质疑')} 查重：${Object.entries(byCro).map(([k,v])=>K.p(k+' '+v,CROC[k])).join('')}；「冲突澄清」表示与已发意见口径相反，需统一后回复中心。`:''}</div>`;
const F={dom:null,cro:null,sh:null,site:null,s:''};
const domOpts=K.DOM.filter(d=>byDom[d[0]]).map(d=>[d[0],`<i class="dot ${d[2]}"></i> ${d[0]}`,byDom[d[0]]]);
const cD=K.chips(app.querySelector('#fdom'),domOpts,v=>{F.dom=v;draw()});
const cC=K.chips(app.querySelector('#fcro'),Object.entries(byCro).map(([k,v])=>[k,k,v]),v=>{F.cro=v;draw()});
K.chips(app.querySelector('#fsh'),Object.entries(bySh).sort((a,b)=>b[1]-a[1]).map(([k,v])=>[k,k,v]),v=>{F.sh=v;draw()});
const sel=app.querySelector('#fctr');sel.onchange=()=>{F.site=sel.value||null;draw()};const ctrChips={set:v=>sel.value=v||''};
app.querySelector('#qs').oninput=e=>{F.s=e.target.value.trim();draw()};
const ctrs=Object.entries(bySite).sort((a,b)=>b[1]-a[1]);
const ch=K.chart('#ctrch',{grid:{left:28,right:8,top:10,bottom:24},tooltip:{trigger:'axis',formatter:p=>`${K.center(p[0].name)}<br>${p[0].value} 条`},xAxis:{type:'category',data:ctrs.map(c=>c[0]),...K.axis,axisLabel:{color:'#64676B',fontSize:10,interval:0,rotate:ctrs.length>18?60:0}},yAxis:{type:'value',...K.axis,minInterval:1},series:[{type:'bar',data:ctrs.map(c=>c[1]),itemStyle:{color:'#FF9900',borderRadius:[3,3,0,0]},barMaxWidth:18}]});
ch.on('click',p=>{F.site=F.site===p.name?null:p.name;ctrChips.set(F.site);draw()});
const order=K.DOM.flatMap(d=>d[1]);const oi=c=>{const i=order.indexOf(c);return i<0?99:i};
const uniq=q=>q.parts.filter(p=>!p[1]).map(p=>K.hlNum(p[0])).join(' ');
const tbl=K.table(app.querySelector('#qt'),{rows:[],noPage:true,h:'calc(100vh - 160px)',onRow:r=>K.showQ(r.id),
 group:r=>r.cat,groupHead:(g,r)=>{const n=cur.filter(q=>q.cat===g).length;const com=(D.qcommon[g]||[]);return `<div class="flex wrap"><i class="dot ${domCol(dom(r))}"></i><b>${g}</b>${K.p(n+' 条','line')}${K.p(dom(r),domCol(dom(r)))}<span class="sp"></span>${K.ibTags(g)}</div>${com.length?`<div class="qtpl">通用要求：${com.map(K.esc).join(' ')}</div>`:''}`},
 cols:[{k:'id',t:'编号',f:r=>K.qPill(r.id),w:'64px'},{k:'sid',t:'受试者',f:r=>K.sid(r.sid)+`<div class="xs faint">${K.esc(K.center(r.site))}</div>`,w:'110px'},
  {k:'sh',t:'数据位置',f:r=>`${K.p(r.sh,'sq mono')}<div class="xs muted">行 ${r.row}${r.ev.length>1?' · 证据 '+r.ev.length+' 行':''}</div>`,w:'92px'},
  {k:'v',t:'访视',f:r=>`${r.v?K.p(r.v,'blu'):''}<div class="xs faint">${K.esc(r.d||'')}</div>`,w:'86px',s:r=>K.vi(r.v)},
  {k:'test',t:'对象',f:r=>`<span class="small">${K.esc(r.test||'—')}</span>`,w:'150px'},
  {k:'text',t:'个案事实与请求',f:r=>`<div class="small" style="line-height:1.6">${uniq(r)}${r.parts.some(p=>p[1])?` ${K.p('＋通用要求','line')}`:''}</div>`},
  {k:'cro',t:((K.cfg().query||{}).extShort||'外部')+'查重',f:r=>K.p(r.cro.replace('同主题',''),CROC[r.cro]),w:'96px'}]});
let cur=[];
function draw(){const s=F.s.toLowerCase();cur=Q.filter(q=>(!F.dom||dom(q)===F.dom)&&(!F.cro||q.cro===F.cro)&&(!F.sh||q.sh===F.sh)&&(!F.site||q.site===F.site)&&(!s||[q.id,q.sid,q.test,q.text,q.cat,q.sh].join(' ').toLowerCase().includes(s)))
 .sort((a,b)=>oi(a.cat)-oi(b.cat)||a.cat.localeCompare(b.cat)||a.sid.localeCompare(b.sid)||a.id.localeCompare(b.id));
 app.querySelector('#qn').textContent=`${cur.length} 条 · ${new Set(cur.map(q=>q.cat)).size} 个主题 · ${new Set(cur.map(q=>q.sid)).size} 例`;tbl.set(cur);K.setHash({dom:F.dom,cro:F.cro,site:F.site,q:F.s})}
const h=K.hash();if(h.q)app.querySelector('#qs').value=F.s=h.q;if(h.site){F.site=h.site;ctrChips.set(h.site)}if(h.dom){F.dom=h.dom;cD.set(h.dom)}if(h.cro){F.cro=h.cro;cC.set(h.cro)}
draw();if(h.id)K.showQ(h.id);
});
